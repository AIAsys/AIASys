const fs = require("fs");
const path = require("path");

// Linux (Ubuntu 23.10+/AppArmor) 默认阻止 unprivileged user namespace，
// 必须在 require('electron') 之前设置该环境变量，否则 zygote 初始化阶段会 FATAL。
// 该环境变量在 Windows/macOS 上无实际作用，因此按平台隔离即可保持兼容。
if (process.platform === "linux") {
  process.env.ELECTRON_DISABLE_SANDBOX = process.env.ELECTRON_DISABLE_SANDBOX || "1";
}

const { app, BrowserWindow, dialog, ipcMain, shell, Tray, Menu, nativeImage } = require("electron");
const { DesktopServiceManager } = require("./service-manager.cjs");

// Windows 打包应用启动后 stdout/stderr 可能已被重定向到关闭的管道，
// 任何 console.* 写入都会触发 EPIPE，进而被 uncaughtException 捕获再次触发写入，
// 形成死循环。这里忽略 stdout/stderr 的 EPIPE 错误，避免异常传播。
for (const stream of [process.stdout, process.stderr]) {
  if (stream && typeof stream.on === "function") {
    stream.on("error", (err) => {
      if (err && (err.code === "EPIPE" || err.code === "EOF")) {
        return;
      }
      // 其他错误交给默认处理
    });
  }
}

process.on("unhandledRejection", (reason) => {
  logError("unhandled rejection", reason);
  // 未处理 Promise 拒绝说明主进程已处于不可预期状态，安全退出
  exitAfterShutdown(1);
});
process.on("uncaughtException", (error) => {
  // 兜底：先把异常写入固定路径的紧急日志，防止 logError 也失败时丢失现场
  try {
    const emergencyLog = path.join(app.getPath("userData") || process.cwd(), "aiasys-crash.log");
    fs.appendFileSync(
      emergencyLog,
      `[${new Date().toISOString()}] UNCAUGHT: ${error.stack || error.message}\n`,
    );
  } catch {
    // ignore
  }
  logError("uncaught exception", error);
  // 未捕获异常后进程状态不可信，记录日志后安全退出
  exitAfterShutdown(1);
});

const desktopMode =
  process.env.AIASYS_DESKTOP_MODE || (app.isPackaged ? "preview" : "dev");
const agentMode = process.env.AIASYS_AGENT_MODE === "1";
// 确保 renderer/preload 继承的 mode 与主进程计算结果一致
process.env.AIASYS_DESKTOP_MODE = desktopMode;
const openDevTools =
  desktopMode === "dev" && process.env.AIASYS_DESKTOP_OPEN_DEVTOOLS !== "0";
const startPath = process.env.AIASYS_DESKTOP_START_PATH || "/analysis";
const remoteDebuggingPort = process.env.AIASYS_DESKTOP_REMOTE_DEBUGGING_PORT;
const isSafeMode =
  app.commandLine.hasSwitch("disable-gpu") ||
  process.env.AIASYS_DESKTOP_DISABLE_GPU === "1" ||
  (!process.env.DISPLAY && process.platform === "linux");
const disableGpu = isSafeMode;
const runtimeStateRoot = process.env.AIASYS_DESKTOP_HOME
  || path.join(app.getPath("userData"), "backend-runtime");

// 多窗口管理：主进程统一管理所有 BrowserWindow，避免独立启动第二个进程导致后端端口冲突。
const windows = new Map();
let nextWindowId = 1;
let primaryWindowId = null;
let tray = null;
let serviceManager = null;
let shutdownStarted = false;
let signalShutdownPromise = null;
let isQuitting = false;
let mainWindowLoadRetryCount = 0;
const MAX_MAIN_WINDOW_LOAD_RETRIES = 3;
let pendingDeepLink = null;

function getWindowById(id) {
  return windows.get(id) ?? null;
}

function getPrimaryWindow() {
  if (primaryWindowId !== null) {
    const win = windows.get(primaryWindowId);
    if (win && !win.isDestroyed()) {
      return win;
    }
  }
  for (const win of windows.values()) {
    if (!win.isDestroyed()) {
      return win;
    }
  }
  return null;
}

function getAnyVisibleWindow() {
  for (const win of windows.values()) {
    if (!win.isDestroyed() && win.isVisible()) {
      return win;
    }
  }
  return null;
}

function sendToPrimaryWindow(channel, ...args) {
  const win = getPrimaryWindow();
  if (win && !win.isDestroyed()) {
    win.webContents.send(channel, ...args);
  }
}

function sendToAllWindows(channel, ...args) {
  for (const win of windows.values()) {
    if (!win.isDestroyed()) {
      win.webContents.send(channel, ...args);
    }
  }
}

if (remoteDebuggingPort) {
  app.commandLine.appendSwitch("remote-debugging-port", remoteDebuggingPort);
}

if (disableGpu) {
  app.commandLine.appendSwitch("disable-gpu");
  app.commandLine.appendSwitch("disable-gpu-compositing");
  app.commandLine.appendSwitch("disable-gpu-rasterization");
  app.commandLine.appendSwitch("disable-gpu-sandbox");
  app.commandLine.appendSwitch("use-gl", "swiftshader-webgl");
  app.commandLine.appendSwitch("use-angle", "swiftshader");
  app.commandLine.appendSwitch("disable-d3d11");
  app.commandLine.appendSwitch("disable-direct-composition");
  app.commandLine.appendSwitch("disable-features", "CalculateNativeWinOcclusion,HardwareMediaKeyHandling");
  app.commandLine.appendSwitch("no-sandbox");
  app.commandLine.appendSwitch("disable-setuid-sandbox");
  app.commandLine.appendSwitch("disable-namespace-sandbox");
  app.commandLine.appendSwitch("disable-dev-shm-usage");
  app.disableHardwareAcceleration();
  console.log("[aiasys-desktop] GPU disabled, using software rendering and relaxed sandbox");
}

function isWSL() {
  if (process.platform !== "linux") return false;
  try {
    const release = fs.readFileSync("/proc/sys/kernel/osrelease", "utf8");
    return release.toLowerCase().includes("wsl");
  } catch (e) {
    console.error("[aiasys-desktop] WSL detection failed:", e);
    return false;
  }
}

function isAgentMode() {
  return agentMode;
}

if (process.platform === "linux") {
  app.commandLine.appendSwitch("no-sandbox");
  // Ubuntu 23.10+ AppArmor 默认阻止 unprivileged user namespace，
  // 同时关闭 namespace/setuid sandbox 避免 FATAL:zygote_linux。
  app.commandLine.appendSwitch("disable-namespace-sandbox");
  app.commandLine.appendSwitch("disable-setuid-sandbox");
  // /dev/shm 在 WSLg/容器/低内存环境可能不足或不可写，显式禁用。
  app.commandLine.appendSwitch("disable-dev-shm-usage");
}

// Windows 任务栏需要稳定的 AppUserModelID，否则运行中窗口会被识别为 Electron 默认图标
if (process.platform === "win32") {
  app.setAppUserModelId("com.aiasys.desktop");
}

// 单实例锁：确保同一时间只有一个 AIASys 桌面端进程在运行。
// 不加锁时，Windows 上双击图标或通过开始菜单再次启动会拉起第二个实例，
// 第二个实例会尝试占用同一后端端口导致冲突，并创建重复窗口。
// requestSingleInstanceLock 必须在 app.whenReady() 之前尽早调用，
// 返回 false 表示已有实例在运行，当前进程应立即退出。
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  // 已有实例持有锁，当前进程无需继续初始化，直接退出。
  // 注意不要调用 shutdownApp()，否则会错误地停止主实例的后端进程。
  app.quit();
} else {
  // 收到第二个实例启动请求时，由当前运行实例负责创建新窗口或聚焦已有窗口。
  app.on("second-instance", (_event, argv) => {
    // 处理通过 aiasys:// 协议传入的启动参数
    const rawDeepLink = argv.find((arg) => arg.startsWith("aiasys://"));
    if (rawDeepLink) {
      const validation = validateDeepLink(rawDeepLink);
      if (!validation.valid) {
        console.warn(`[aiasys-desktop] 忽略非法 deeplink (${validation.reason}): ${rawDeepLink.slice(0, 100)}`);
        return;
      }
      const deepLink = rawDeepLink;
      const targetWindow = getPrimaryWindow();
      if (targetWindow) {
        if (targetWindow.isMinimized()) {
          targetWindow.restore();
        }
        if (!targetWindow.isVisible()) {
          targetWindow.show();
        }
        targetWindow.focus();
        targetWindow.webContents.send("deep-link", deepLink);
      } else {
        pendingDeepLink = deepLink;
      }
      return;
    }

    // 解析命令行参数中的 workspace_id / session_id，在已有实例中打开新窗口
    const wsArg = argv.find((arg) => arg.startsWith("--workspace-id="));
    const sessionArg = argv.find((arg) => arg.startsWith("--session-id="));
    if (wsArg || sessionArg) {
      const workspaceId = wsArg ? wsArg.slice("--workspace-id=".length) : undefined;
      const sessionId = sessionArg ? sessionArg.slice("--session-id=".length) : undefined;
      if (serviceManager) {
        createWorkspaceWindow(serviceManager.rendererBaseUrl, { workspaceId, sessionId });
      }
      return;
    }

    // 无参数时聚焦主窗口
    const targetWindow = getPrimaryWindow();
    if (!targetWindow) {
      return;
    }
    if (targetWindow.isMinimized()) {
      targetWindow.restore();
    }
    if (!targetWindow.isVisible()) {
      targetWindow.show();
    }
    targetWindow.focus();
  });
}

function getLogsDir() {
  return path.join(runtimeStateRoot, "logs");
}

const MAX_DEEP_LINK_LENGTH = 8 * 1024; // 8KB

function validateDeepLink(url) {
  if (!url || typeof url !== "string") {
    return { valid: false, reason: "empty" };
  }
  if (url.length > MAX_DEEP_LINK_LENGTH) {
    return { valid: false, reason: "too_long" };
  }
  if (!url.startsWith("aiasys://")) {
    return { valid: false, reason: "invalid_scheme" };
  }
  try {
    const parsed = new URL(url);
    // 只允许小写字母、数字、连字符、点、下划线作为 hostname
    if (!/^[a-z0-9][-a-z0-9._]*$/i.test(parsed.hostname)) {
      return { valid: false, reason: "invalid_hostname" };
    }
  } catch {
    return { valid: false, reason: "malformed_url" };
  }
  return { valid: true };
}

function isSameOrigin(url, baseUrl) {
  try {
    return new URL(url).origin === new URL(baseUrl).origin;
  } catch {
    return false;
  }
}

function logError(message, error) {
  // 打包后的 Windows 应用可能将 stdout/stderr 重定向到已关闭的管道，
  // 任何 stderr 写入（console.error / process.stderr.write）都会触发 EPIPE，
  // 而 EPIPE 又会被 uncaughtException 捕获并再次调用 logError，形成死循环。
  // 因此 logError 内部不再向 stderr 写入，仅记录到日志文件。
  const errorMessage = error instanceof Error ? error.stack || error.message : String(error);

  try {
    const logsDir = getLogsDir();
    fs.mkdirSync(logsDir, { recursive: true });
    const logPath = path.join(logsDir, "electron-main.log");
    // 简单轮转：超过 10MB 时保留一份备份
    try {
      const stat = fs.statSync(logPath);
      if (stat.size >= 10 * 1024 * 1024) {
        const backupPath = `${logPath}.1`;
        if (fs.existsSync(backupPath)) {
          fs.rmSync(backupPath, { force: true });
        }
        fs.renameSync(logPath, backupPath);
      }
    } catch {
      // ignore rotation errors
    }
    const timestamp = new Date().toISOString();
    fs.appendFileSync(logPath, `[${timestamp}] ERROR: ${message}\n${errorMessage}\n\n`);
  } catch {
    // ignore
  }
}

function exitAfterShutdown(code = 0) {
  void shutdownApp().finally(() => {
    app.exit(code);
  });
}

async function shutdownApp() {
  if (shutdownStarted) {
    return signalShutdownPromise;
  }

  shutdownStarted = true;
  signalShutdownPromise = (async () => {
    if (serviceManager) {
      try {
        await serviceManager.stop();
      } catch (error) {
        logError("service manager stop failed", error);
      }
      serviceManager = null;
    }
  })();
  return signalShutdownPromise;
}

function getWindowIconPath() {
  // Windows 使用 .ico 更可靠（任务栏/托盘兼容性更好）
  const iconName = process.platform === "win32" ? "icon.ico" : "icon.png";

  if (app.isPackaged) {
    // 打包模式下 icon 在 app.asar 内，macOS 原生图像 API 无法从 ASAR 读取，
    // 需要解出到临时文件
    const asarIconPath = path.join(process.resourcesPath, "app.asar", "build", iconName);
    const tempDir = path.join(app.getPath("temp"), "aiasys-icons");
    fs.mkdirSync(tempDir, { recursive: true });
    const tempIconPath = path.join(tempDir, iconName);
    if (!fs.existsSync(tempIconPath)) {
      fs.writeFileSync(tempIconPath, fs.readFileSync(asarIconPath));
    }
    return tempIconPath;
  }

  const appRoot = path.join(__dirname, "..");
  return path.join(appRoot, "build", iconName);
}

function getWindowIcon() {
  const iconPath = getWindowIconPath();
  try {
    const image = nativeImage.createFromPath(iconPath);
    if (!image.isEmpty()) {
      return image;
    }
    console.warn(`[aiasys-desktop] 图标加载失败，路径: ${iconPath}`);
  } catch (error) {
    console.warn(`[aiasys-desktop] 加载图标异常: ${error.message}`);
  }
  return null;
}

function getTrayIconPath() {
  // macOS 菜单栏（状态栏）图标需要专用小尺寸模板图，避免 300x300 应用图标被放大显示
  const iconName = process.platform === "darwin" ? "trayTemplate.png" : "icon.png";

  if (app.isPackaged) {
    const asarIconPath = path.join(process.resourcesPath, "app.asar", "build", iconName);
    const tempDir = path.join(app.getPath("temp"), "aiasys-icons");
    fs.mkdirSync(tempDir, { recursive: true });
    const tempIconPath = path.join(tempDir, iconName);
    if (!fs.existsSync(tempIconPath)) {
      fs.writeFileSync(tempIconPath, fs.readFileSync(asarIconPath));
    }
    return tempIconPath;
  }

  const appRoot = path.join(__dirname, "..");
  return path.join(appRoot, "build", iconName);
}

function getTrayIcon() {
  if (process.platform !== "darwin") {
    // Windows/Linux 沿用窗口图标，后续可按平台补充专用托盘图
    return getWindowIcon();
  }

  const iconPath = getTrayIconPath();
  try {
    const image = nativeImage.createFromPath(iconPath);
    if (!image.isEmpty()) {
      // 显式声明为模板图，macOS 会根据菜单栏亮/暗模式自动着色
      image.setTemplateImage(true);
      return image;
    }
    console.warn(`[aiasys-desktop] 托盘图标加载失败，路径: ${iconPath}`);
  } catch (error) {
    console.warn(`[aiasys-desktop] 加载托盘图标异常: ${error.message}`);
  }
  return null;
}

let splashWindow = null;

function createSplashWindow() {
  splashWindow = new BrowserWindow({
    width: 360,
    height: 240,
    frame: false,
    alwaysOnTop: true,
    resizable: false,
    movable: true,
    show: false,
    transparent: true,
    backgroundColor: "#0f0f0f",
    skipTaskbar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
    icon: getWindowIcon(),
  });

  const splashHtml = `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { background: #0f0f0f; color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans SC", sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; overflow: hidden; user-select: none; -webkit-app-region: drag; }
    .container { text-align: center; width: 260px; }
    .logo { font-size: 28px; font-weight: 600; letter-spacing: -0.5px; margin-bottom: 24px; background: linear-gradient(135deg, #ffffff 0%, #a0a0a0 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .status { font-size: 13px; color: #aaaaaa; min-height: 20px; margin-bottom: 8px; }
    .step-text { font-size: 11px; color: #666666; margin-bottom: 16px; }
    .progress { width: 100%; height: 3px; background: #2a2a2a; border-radius: 2px; overflow: hidden; }
    .progress-bar { height: 100%; width: 0%; background: #ffffff; transition: width 0.3s ease; }
    .spinner { width: 24px; height: 24px; border: 2px solid #333333; border-top-color: #ffffff; border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 20px; }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <div class="container">
    <div class="spinner"></div>
    <div class="logo">AIASys</div>
    <div class="status" id="status">正在启动...</div>
    <div class="step-text" id="step-text"></div>
    <div class="progress"><div class="progress-bar" id="progress-bar"></div></div>
  </div>
  <script>
    window.setSplashStatus = (payload) => {
      const message = typeof payload === "string" ? payload : (payload?.message || "");
      const step = typeof payload === "object" ? payload?.step : null;
      const total = typeof payload === "object" ? payload?.total : null;
      const percent = typeof payload === "object" && payload?.percent !== undefined ? payload.percent : null;
      const statusEl = document.getElementById('status');
      const stepEl = document.getElementById('step-text');
      const barEl = document.getElementById('progress-bar');
      if (statusEl) statusEl.textContent = message;
      if (stepEl) {
        if (step && total) {
          stepEl.textContent = '步骤 ' + step + ' / ' + total;
        } else {
          stepEl.textContent = '';
        }
      }
      if (barEl) {
        if (percent !== null && percent >= 0) {
          barEl.style.width = Math.max(2, Math.min(100, percent)) + '%';
        } else if (step && total) {
          barEl.style.width = Math.max(5, Math.round((step / total) * 100)) + '%';
        } else {
          barEl.style.width = '0%';
        }
      }
    };
  </script>
</body>
</html>`;

  void splashWindow.loadURL(
    `data:text/html;charset=utf-8,${encodeURIComponent(splashHtml)}`,
  );
  splashWindow.once("ready-to-show", () => {
    splashWindow?.show();
  });

  splashWindow.on("closed", () => {
    splashWindow = null;
  });
}

function setSplashStatus(payload) {
  if (!splashWindow || splashWindow.isDestroyed()) return;
  try {
    void splashWindow.webContents.executeJavaScript(
      `window.setSplashStatus && window.setSplashStatus(${JSON.stringify(payload)})`,
    );
  } catch (e) {
    // 忽略 splash 状态更新失败
  }
}

function closeSplashWindow() {
  if (!splashWindow || splashWindow.isDestroyed()) return;
  splashWindow.close();
  splashWindow = null;
}

/**
 * 探测后端是否已能响应 API 请求。
 * 只要返回任意 HTTP 状态码（包括 401/403）即认为后端可访问；
 * 网络错误 / 连接拒绝才视为未就绪。
 */
function probeBackendSession(backendBaseUrl) {
  return new Promise((resolve) => {
    if (!backendBaseUrl) {
      return resolve(false);
    }
    const url = new URL("/api/auth/session", backendBaseUrl);
    const client = url.protocol === "https:" ? require("https") : require("http");
    const request = client.get(
      url,
      { timeout: 3000 },
      (response) => {
        response.resume();
        const statusCode = response.statusCode;
        // 2xx 表示后端已可处理请求；401/403 表示认证/鉴权配置生效，也说明服务已就绪。
        // 5xx 表示后端虽在监听但内部未初始化完成或出错，不应视为就绪。
        resolve(statusCode !== undefined && (statusCode < 500));
      },
    );
    request.on("error", () => resolve(false));
    request.on("timeout", () => {
      try {
        request.destroy();
      } catch {
        // ignore
      }
      resolve(false);
    });
  });
}

/**
 * 等待后端 API 真正可响应。
 * 给首次启动时后端健康检查通过后仍存在的短暂初始化窗口一个兜底。
 */
async function waitForBackendSession(backendBaseUrl, timeoutMs = 15_000) {
  const start = Date.now();
  const intervalMs = 500;
  while (Date.now() - start < timeoutMs) {
    if (await probeBackendSession(backendBaseUrl)) {
      console.log(
        `[aiasys-desktop] 后端 API 已可响应，耗时 ${Date.now() - start}ms`,
      );
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  console.warn(
    `[aiasys-desktop] 后端 API 在 ${timeoutMs}ms 内未响应，继续显示主窗口`,
  );
  return false;
}

function createWorkspaceWindow(rendererBaseUrl, options = {}) {
  const { workspaceId, sessionId, isPrimary = false } = options;
  const preloadPath = path.join(__dirname, "preload.cjs");
  // 桌面版加载 dist 根路径，让前端路由自己处理 startPath；
  // 直接加载 /analysis 会导致绝对路径的 /assets/... 被浏览器相对于当前路径解析（或
  // preview server 把不存在的 /analysis/assets/... 回退成 index.html），页面白屏。
  // 指定工作区/会话时直接打开 /workspace，否则让前端路由按 startPath 处理首页。
  const url = new URL(workspaceId || sessionId ? "/workspace" : "/", rendererBaseUrl);
  if (workspaceId) {
    url.searchParams.set("workspace_id", workspaceId);
  }
  if (sessionId) {
    url.searchParams.set("session_id", sessionId);
  }
  const initialUrl = url.toString();
  // 把后端地址通过命令行参数注入 renderer，供 preload 暴露给前端。
  // 这样 WebSocket 等需要直连后端的场景不必依赖页面同源或 preview server 代理。
  const backendBaseUrl = serviceManager ? serviceManager.backendBaseUrl : "";
  const additionalArguments = backendBaseUrl
    ? [`--aiasys-backend-base-url=${backendBaseUrl}`]
    : [];

  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 720,
    autoHideMenuBar: true,
    show: false,
    title: "AIASys",
    icon: getWindowIcon(),
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      additionalArguments,
    },
  });

  const windowId = nextWindowId++;
  windows.set(windowId, win);
  if (isPrimary || primaryWindowId === null) {
    primaryWindowId = windowId;
  }

  win.webContents.setWindowOpenHandler(({ url }) => {
    if (isSameOrigin(url, rendererBaseUrl)) {
      return { action: "allow" };
    }
    void shell.openExternal(url);
    return { action: "deny" };
  });

  win.webContents.on("will-navigate", (event, url) => {
    if (isSameOrigin(url, rendererBaseUrl)) {
      return;
    }
    event.preventDefault();
    void shell.openExternal(url);
  });

  win.webContents.on("render-process-gone", (_event, details) => {
    console.error("[aiasys-desktop] render process gone:", details);
    closeSplashWindow();

    // 首次渲染进程崩溃时，自动以禁用 GPU/沙箱的安全模式重启一次
    if (
      (details.reason === "crashed" || details.reason === "killed") &&
      !isSafeMode
    ) {
      console.error("[aiasys-desktop] 检测到渲染进程崩溃，将以安全模式重启");
      if (!isAgentMode()) {
        dialog.showErrorBox(
          "AIASys",
          "检测到图形渲染兼容性问题，应用将以兼容模式重新启动。",
        );
      }
      app.relaunch({ args: [...process.argv.slice(1), "--disable-gpu"] });
      app.exit(1);
      return;
    }

    if (!isAgentMode()) {
      dialog.showErrorBox(
        "AIASys",
        "渲染进程异常退出，应用将尝试重新加载页面。",
      );
    }
    if (!win.isDestroyed() && serviceManager) {
      win.loadURL(serviceManager.rendererBaseUrl).catch((err) => {
        console.error("[aiasys-desktop] 重新加载渲染页面失败:", err);
      });
    }
  });

  win.webContents.on(
    "did-fail-load",
    (_event, errorCode, errorDescription, validatedUrl) => {
      // errorCode -3 为 ERR_ABORTED，通常是页面主动重导航或重载，不必重试
      if (errorCode === -3) {
        return;
      }
      console.error(
        "[aiasys-desktop] load failed:",
        JSON.stringify({ errorCode, errorDescription, validatedUrl }),
      );
      if (mainWindowLoadRetryCount < MAX_MAIN_WINDOW_LOAD_RETRIES) {
        mainWindowLoadRetryCount += 1;
        const delay = mainWindowLoadRetryCount * 1000;
        console.log(
          `[aiasys-desktop] 页面加载失败，${delay}ms 后第 ${mainWindowLoadRetryCount}/${MAX_MAIN_WINDOW_LOAD_RETRIES} 次重试...`,
        );
        setSplashStatus(
          `页面加载失败，正在重试 (${mainWindowLoadRetryCount}/${MAX_MAIN_WINDOW_LOAD_RETRIES})...`,
        );
        setTimeout(() => {
          if (!win.isDestroyed()) {
            void win.loadURL(validatedUrl || initialUrl);
          }
        }, delay);
      } else {
        logError("page load failed after retries", {
          errorCode,
          errorDescription,
          validatedUrl,
        });
        closeSplashWindow();
        if (!isAgentMode()) {
          dialog.showErrorBox(
            "AIASys 加载失败",
            `无法加载页面：${validatedUrl || initialUrl}\n错误：${errorDescription} (${errorCode})\n\n请检查日志目录获取详细信息。`,
          );
        }
      }
    },
  );

  win.on("closed", () => {
    windows.delete(windowId);
    if (primaryWindowId === windowId) {
      primaryWindowId = null;
    }
  });

  win.on("close", (event) => {
    if (isQuitting) {
      return;
    }
    // 多窗口模式下，只要还有其它窗口，当前窗口可以直接关闭
    if (windows.size > 1) {
      return;
    }
    // 仅剩一个窗口时，保持原有托盘隐藏行为
    if (!tray) {
      isQuitting = true;
      return;
    }
    event.preventDefault();
    win.hide();
  });

  // 等页面真正加载完成且后端 API 可响应后，再关闭 splash 并展示主窗口，
  // 避免首次启动时安全软件扫描 / 后端初始化未完成导致的白屏。
  let windowReadyToShow = false;
  let pageLoadFinished = false;
  let showFinalized = false;

  function finalizeWindowShow() {
    if (showFinalized || !windowReadyToShow || !pageLoadFinished) {
      return;
    }
    if (win.isDestroyed()) {
      return;
    }
    showFinalized = true;

    if (isPrimary) {
      setSplashStatus({ message: "正在连接本地服务...", step: 5, total: 5 });
      waitForBackendSession(backendBaseUrl, 15_000)
        .then((ready) => {
          if (!ready) {
            console.warn(
              "[aiasys-desktop] 后端 API 未就绪，继续显示主窗口，由前端展示错误状态",
            );
          }
          closeSplashWindow();
          win.show();
          if (openDevTools) {
            win.webContents.openDevTools({ mode: "detach" });
          }
        })
        .catch((error) => {
          console.error("[aiasys-desktop] 等待后端 API 时异常:", error);
          closeSplashWindow();
          win.show();
        });
    } else {
      // 非主窗口（如新开工作区窗口）不需要等待 splash，直接显示
      win.show();
    }
  }

  // 兜底：窗口创建 30 秒后如果还没展示，强制展示，避免某个事件永远不触发导致卡死
  const showFallbackTimeout = setTimeout(() => {
    if (!showFinalized && !win.isDestroyed()) {
      console.warn(
        "[aiasys-desktop] 窗口展示超时，强制显示窗口",
      );
      showFinalized = true;
      if (isPrimary) {
        closeSplashWindow();
      }
      win.show();
      if (isPrimary && openDevTools) {
        win.webContents.openDevTools({ mode: "detach" });
      }
    }
  }, 30_000);

  win.once("ready-to-show", () => {
    windowReadyToShow = true;
    finalizeWindowShow();
  });

  win.webContents.on("did-finish-load", () => {
    pageLoadFinished = true;
    finalizeWindowShow();

    // 主窗口在创建前收到 deeplink，此时补发给渲染进程
    if (isPrimary && pendingDeepLink) {
      win.webContents.send("deep-link", pendingDeepLink);
      pendingDeepLink = null;
    }
  });

  win.once("closed", () => {
    clearTimeout(showFallbackTimeout);
  });

  if (isPrimary) {
    mainWindowLoadRetryCount = 0;
  }
  void win.loadURL(initialUrl);

  return win;
}

function createMainWindow(rendererBaseUrl) {
  return createWorkspaceWindow(rendererBaseUrl, { isPrimary: true });
}

function sendTrayAction(action) {
  const targetWindow = getPrimaryWindow();
  if (targetWindow && !targetWindow.isDestroyed()) {
    targetWindow.webContents.send("tray-action", action);
    targetWindow.show();
    targetWindow.focus();
  }
}

function createTray() {
  const icon = getTrayIcon();
  if (!icon) {
    console.warn("[aiasys-desktop] 无法创建托盘：图标加载失败");
    return;
  }
  tray = new Tray(icon);
  tray.setToolTip("AIASys");

  const contextMenu = Menu.buildFromTemplate([
    {
      label: "显示窗口",
      click: () => {
        const targetWindow = getPrimaryWindow();
        if (targetWindow) {
          targetWindow.show();
          targetWindow.focus();
        } else if (serviceManager) {
          createMainWindow(serviceManager.rendererBaseUrl);
        }
      },
    },
    { type: "separator" },
    {
      label: "设置",
      submenu: [
        { label: "能力管理", click: () => sendTrayAction({ type: "open-settings", section: "capabilities" }) },
        { label: "模型配置", click: () => sendTrayAction({ type: "open-settings", section: "llm" }) },
        { label: "全局环境变量", click: () => sendTrayAction({ type: "open-settings", section: "env-vars" }) },
        { label: "存储位置", click: () => sendTrayAction({ type: "open-settings", section: "storage" }) },
        { label: "执行资源", click: () => sendTrayAction({ type: "open-settings", section: "execution-resources" }) },
        { label: "自动化任务", click: () => sendTrayAction({ type: "open-settings", section: "auto-tasks" }) },
        { label: "监控任务", click: () => sendTrayAction({ type: "open-settings", section: "monitor-tasks" }) },
      ],
    },
    { type: "separator" },
    {
      label: "打开日志目录",
      click: () => {
        const logsDir = path.join(runtimeStateRoot, "logs");
        fs.mkdirSync(logsDir, { recursive: true });
        void shell.openPath(logsDir);
      },
    },
    {
      label: "打开用户配置目录",
      click: () => {
        const configPaths = [
          path.join(runtimeStateRoot, "data", "config"),
          path.join(runtimeStateRoot, "data"),
          path.join(app.getPath("userData"), "backend-runtime", "data", "config"),
          path.join(app.getPath("userData"), "backend-runtime", "data"),
        ];
        for (const configDir of configPaths) {
          if (fs.existsSync(configDir)) {
            void shell.openPath(configDir);
            return;
          }
        }
        void shell.openPath(app.getPath("userData"));
      },
    },
    {
      label: "打开工作区目录",
      click: () => {
        const workspacePaths = [
          path.join(runtimeStateRoot, "data", "workspaces"),
          path.join(app.getPath("userData"), "backend-runtime", "data", "workspaces"),
        ];
        for (const wsDir of workspacePaths) {
          if (fs.existsSync(wsDir)) {
            void shell.openPath(wsDir);
            return;
          }
        }
        void shell.openPath(app.getPath("userData"));
      },
    },
    {
      label: "关于 AIASys",
      click: () => {
        const version = app.getVersion();
        const targetWindow = getPrimaryWindow();
        dialog.showMessageBox(targetWindow, {
          type: "info",
          title: "关于 AIASys",
          message: `AIASys v${version}`,
          detail: "新一代智能工业/科研平台\n本地部署优先，桌面端优先。",
          buttons: ["确定"],
        });
      },
    },
    { type: "separator" },
    {
      label: "退出",
      click: () => {
        isQuitting = true;
        exitAfterShutdown(0);
      },
    },
  ]);

  tray.setContextMenu(contextMenu);

  tray.on("click", () => {
    const targetWindow = getPrimaryWindow();
    if (targetWindow) {
      if (targetWindow.isVisible()) {
        targetWindow.hide();
      } else {
        targetWindow.show();
        targetWindow.focus();
      }
    } else if (serviceManager) {
      createMainWindow(serviceManager.rendererBaseUrl);
    }
  });
}

async function bootstrap() {
  console.log("[aiasys-desktop] bootstrap start");

  serviceManager = new DesktopServiceManager({
    mode: desktopMode,
    isPackaged: app.isPackaged,
    resourcesPath: process.resourcesPath,
    runtimeStateRoot,
  });

  // 后端崩溃时通知所有渲染进程显示遮罩
  serviceManager.onBackendCrash = (info) => {
    sendToAllWindows("backend:crashed", info);
  };

  // 后端重启就绪后通知所有渲染进程隐藏遮罩
  serviceManager.onBackendReady = () => {
    sendToAllWindows("backend:ready");
  };

  // 启动进度透传到 splash
  serviceManager.onStatusUpdate = (status) => {
    setSplashStatus(status);
  };

  console.log("[aiasys-desktop] starting backend...");
  const rendererBaseUrl = await serviceManager.start();
  console.log("[aiasys-desktop] backend started, creating window...");

  setSplashStatus({ message: "正在加载界面...", step: 4, total: 5 });
  createMainWindow(rendererBaseUrl);
  console.log("[aiasys-desktop] creating tray...");
  createTray();
  console.log("[aiasys-desktop] bootstrap complete");
}

// 注册 IPC：选择本地文件夹
ipcMain.handle("aiasys:open-path", async (_event, targetPath) => {
  if (!targetPath || typeof targetPath !== "string") {
    return false;
  }
  try {
    await shell.openPath(targetPath);
    return true;
  } catch (e) {
    console.error("[aiasys-desktop] open-path failed:", e);
    return false;
  }
});

// 注册 IPC：获取应用版本号
ipcMain.handle("aiasys:get-version", () => {
  try {
    return app.getVersion();
  } catch (e) {
    console.error("[aiasys-desktop] get-version failed:", e);
    return "";
  }
});

// 注册 IPC：用系统默认浏览器打开外部链接
ipcMain.handle("aiasys:open-external", async (_event, url) => {
  if (!url || typeof url !== "string") {
    return false;
  }
  try {
    await shell.openExternal(url);
    return true;
  } catch (e) {
    console.error("[aiasys-desktop] open-external failed:", e);
    return false;
  }
});

// 注册 IPC：在新窗口打开指定工作区
ipcMain.handle("aiasys:open-workspace-window", (_event, options = {}) => {
  if (!serviceManager) {
    return { success: false, error: "service not ready" };
  }
  const { workspaceId, sessionId } = options;
  createWorkspaceWindow(serviceManager.rendererBaseUrl, {
    workspaceId: typeof workspaceId === "string" ? workspaceId : undefined,
    sessionId: typeof sessionId === "string" ? sessionId : undefined,
  });
  return { success: true };
});

ipcMain.handle("aiasys:select-folder", async (event, options = {}) => {
  // 优先使用触发该 IPC 的窗口作为对话框父窗口，回退到主窗口
  const sourceWindow = event.sender
    ? BrowserWindow.fromWebContents(event.sender)
    : null;
  const parentWindow = sourceWindow && !sourceWindow.isDestroyed()
    ? sourceWindow
    : getPrimaryWindow();
  if (!parentWindow) {
    return { canceled: true, filePaths: [] };
  }
  // Agent 模式：不阻塞等待用户选择，直接返回取消
  if (isAgentMode()) {
    console.log("[aiasys-desktop] agent mode: auto-cancel select-folder");
    return { canceled: true, filePaths: [] };
  }
  const result = await dialog.showOpenDialog(parentWindow, {
    properties: ["openDirectory"],
    title: options.title || "选择文件夹",
    defaultPath: options.defaultPath,
  });
  return result;
});

app.whenReady().then(() => {
  // 第二实例已在 requestSingleInstanceLock 后退出，不会走到这里；
  // 此处仅作为防御性检查，确保非主实例不执行 bootstrap。
  if (!gotTheLock) {
    return;
  }
  // 注册 aiasys:// 自定义协议，用于从浏览器/外部应用唤起桌面端
  if (!app.isDefaultProtocolClient("aiasys")) {
    app.setAsDefaultProtocolClient("aiasys");
  }

  // 尽早展示启动画面，让用户感知到应用正在启动
  createSplashWindow();
  setSplashStatus({ message: "正在初始化...", step: 1, total: 5 });

  void bootstrap().catch(async (error) => {
    logError("bootstrap failed", error);
    closeSplashWindow();

    // 先安全关闭后端/前端子进程，再弹出阻塞式错误对话框，
    // 避免用户在对话框期间后端继续运行导致资源残留。
    await shutdownApp();

    // 收集日志路径信息
    const logsDir = path.join(runtimeStateRoot, "logs");
    const errorMessage =
      error instanceof Error ? error.stack || error.message : String(error);
    const fullMessage = `${errorMessage}\n\n日志目录: ${logsDir}`;

    if (!isAgentMode()) {
      dialog.showErrorBox("AIASys 启动失败", fullMessage);
    } else {
      console.error("[aiasys-desktop] bootstrap failed in agent mode:", fullMessage);
    }

    // 尝试打开日志目录
    try {
      void shell.openPath(logsDir);
    } catch (e) {
      console.error("[aiasys-desktop] open directory failed:", e);
    }

    app.exit(1);
  });
});

process.once("SIGINT", () => {
  isQuitting = true;
  exitAfterShutdown(0);
});

process.once("SIGTERM", () => {
  isQuitting = true;
  exitAfterShutdown(0);
});

process.on("message", (message) => {
  if (!message || message.type !== "shutdown") {
    return;
  }

  isQuitting = true;
  exitAfterShutdown(0);
});

app.on("open-url", (_event, url) => {
  const validation = validateDeepLink(url);
  if (!validation.valid) {
    console.warn(`[aiasys-desktop] 忽略非法 deeplink (${validation.reason}): ${String(url).slice(0, 100)}`);
    return;
  }
  const targetWindow = getPrimaryWindow();
  if (targetWindow) {
    if (targetWindow.isMinimized()) {
      targetWindow.restore();
    }
    if (!targetWindow.isVisible()) {
      targetWindow.show();
    }
    targetWindow.focus();
    targetWindow.webContents.send("deep-link", url);
  } else {
    pendingDeepLink = url;
  }
});

app.on("activate", () => {
  const targetWindow = getPrimaryWindow();
  if (targetWindow) {
    if (!targetWindow.isVisible()) {
      targetWindow.show();
    }
    targetWindow.focus();
  } else if (BrowserWindow.getAllWindows().length === 0 && serviceManager) {
    createMainWindow(serviceManager.rendererBaseUrl);
  }
});

app.on("window-all-closed", () => {
  // macOS 上保持应用运行（通过托盘），其他平台也不退出，由托盘控制
  // 不调用 app.quit()，让托盘保持活跃
});

app.on("will-quit", (event) => {
  if (!serviceManager) {
    return;
  }

  // shutdown 已在进行中，等待其完成后再退出，避免后端子进程残留
  if (shutdownStarted) {
    if (signalShutdownPromise) {
      event.preventDefault();
      void signalShutdownPromise.finally(() => {
        app.quit();
      });
    }
    return;
  }

  event.preventDefault();
  isQuitting = true;
  void shutdownApp().finally(() => {
    app.quit();
  });
});

app.on("before-quit", () => {
  isQuitting = true;
});
