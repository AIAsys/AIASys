const fs = require("fs");
const path = require("path");
const { app, BrowserWindow, dialog, ipcMain, shell, Tray, Menu, nativeImage } = require("electron");
const { DesktopServiceManager } = require("./service-manager.cjs");

const desktopMode =
  process.env.AIASYS_DESKTOP_MODE || (app.isPackaged ? "preview" : "dev");
const openDevTools =
  desktopMode === "dev" && process.env.AIASYS_DESKTOP_OPEN_DEVTOOLS !== "0";
const startPath = process.env.AIASYS_DESKTOP_START_PATH || "/analysis";
const remoteDebuggingPort = process.env.AIASYS_DESKTOP_REMOTE_DEBUGGING_PORT;
const disableGpu =
  process.env.AIASYS_DESKTOP_DISABLE_GPU === "1" ||
  (!process.env.DISPLAY && process.platform === "linux");
const runtimeStateRoot = process.env.AIASYS_DESKTOP_HOME
  || path.join(app.getPath("userData"), "backend-runtime");

let mainWindow = null;
let tray = null;
let serviceManager = null;
let shutdownStarted = false;
let signalShutdownPromise = null;
let isQuitting = false;

if (remoteDebuggingPort) {
  app.commandLine.appendSwitch("remote-debugging-port", remoteDebuggingPort);
}

if (disableGpu) {
  app.commandLine.appendSwitch("disable-gpu");
  app.disableHardwareAcceleration();
}

if (process.platform === "linux") {
  app.commandLine.appendSwitch("no-sandbox");
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
  // 收到第二个实例启动请求时，恢复并聚焦主窗口。
  app.on("second-instance", () => {
    if (!mainWindow || mainWindow.isDestroyed()) {
      // 主窗口尚未创建或已销毁（例如被最小化到托盘后关闭），无需处理
      return;
    }
    if (mainWindow.isMinimized()) {
      mainWindow.restore();
    }
    if (!mainWindow.isVisible()) {
      mainWindow.show();
    }
    mainWindow.focus();
  });
}

function logError(message, error) {
  console.error(`[aiasys-desktop] ${message}:`, error);
  try {
    const logsDir = path.join(app.getPath("userData"), "backend-runtime", "logs");
    fs.mkdirSync(logsDir, { recursive: true });
    const logPath = path.join(logsDir, "electron-main.log");
    const timestamp = new Date().toISOString();
    const errorMessage = error instanceof Error ? error.stack || error.message : String(error);
    fs.appendFileSync(logPath, `[${timestamp}] ERROR: ${message}\n${errorMessage}\n\n`);
  } catch {
    // ignore logging failures
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
  return undefined;
}

function createMainWindow(rendererBaseUrl) {
  const preloadPath = path.join(__dirname, "preload.cjs");
  const initialUrl = new URL(startPath, rendererBaseUrl).toString();
  // 把后端地址通过命令行参数注入 renderer，供 preload 暴露给前端。
  // 这样 WebSocket 等需要直连后端的场景不必依赖页面同源或 preview server 代理。
  const backendBaseUrl = serviceManager ? serviceManager.backendBaseUrl : "";
  const additionalArguments = backendBaseUrl
    ? [`--aiasys-backend-base-url=${backendBaseUrl}`]
    : [];

  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 720,
    autoHideMenuBar: true,
    show: false,
    title: "AIASys Desktop",
    icon: getWindowIcon(),
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      additionalArguments,
    },
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith(rendererBaseUrl)) {
      return { action: "allow" };
    }
    void shell.openExternal(url);
    return { action: "deny" };
  });

  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (url.startsWith(rendererBaseUrl)) {
      return;
    }
    event.preventDefault();
    void shell.openExternal(url);
  });

  mainWindow.webContents.on("render-process-gone", (_event, details) => {
    console.error("[aiasys-desktop] render process gone:", details);
  });

  mainWindow.webContents.on(
    "did-fail-load",
    (_event, errorCode, errorDescription, validatedUrl) => {
      console.error(
        "[aiasys-desktop] load failed:",
        JSON.stringify({ errorCode, errorDescription, validatedUrl }),
      );
    },
  );

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  mainWindow.on("close", (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow?.show();
    if (openDevTools) {
      mainWindow?.webContents.openDevTools({ mode: "detach" });
    }
  });

  void mainWindow.loadURL(initialUrl);
}

function sendTrayAction(action) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("tray-action", action);
    mainWindow.show();
    mainWindow.focus();
  }
}

function createTray() {
  const icon = getWindowIcon();
  tray = new Tray(icon);
  tray.setToolTip("AIASys Desktop");

  const contextMenu = Menu.buildFromTemplate([
    {
      label: "显示窗口",
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
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
    if (mainWindow) {
      if (mainWindow.isVisible()) {
        mainWindow.hide();
      } else {
        mainWindow.show();
        mainWindow.focus();
      }
    } else if (serviceManager) {
      createMainWindow(serviceManager.rendererBaseUrl);
    }
  });
}

async function bootstrap() {
  console.log("[aiasys-desktop] bootstrap start");
  logError("bootstrap", "bootstrap started");
  serviceManager = new DesktopServiceManager({
    mode: desktopMode,
    isPackaged: app.isPackaged,
    resourcesPath: process.resourcesPath,
    runtimeStateRoot,
  });

  // 后端崩溃时通知渲染进程显示遮罩
  serviceManager.onBackendCrash = () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("backend:crashed");
    }
  };

  // 后端重启就绪后通知渲染进程隐藏遮罩
  serviceManager.onBackendReady = () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("backend:ready");
    }
  };

  console.log("[aiasys-desktop] starting backend...");
  const rendererBaseUrl = await serviceManager.start();
  console.log("[aiasys-desktop] backend started, creating window...");
  createMainWindow(rendererBaseUrl);
  console.log("[aiasys-desktop] creating tray...");
  createTray();
  console.log("[aiasys-desktop] bootstrap complete");
}

// 注册 IPC：选择本地文件夹
ipcMain.handle("aiasys:select-folder", async (_event, options = {}) => {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return { canceled: true, filePaths: [] };
  }
  const result = await dialog.showOpenDialog(mainWindow, {
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
  void bootstrap().catch(async (error) => {
    logError("bootstrap failed", error);

    // 收集日志路径信息
    const logsDir = path.join(runtimeStateRoot, "logs");
    const errorMessage =
      error instanceof Error ? error.stack || error.message : String(error);
    const fullMessage = `${errorMessage}\n\n日志目录: ${logsDir}`;

    dialog.showErrorBox("AIASys Desktop 启动失败", fullMessage);

    // 尝试打开日志目录
    try {
      void shell.openPath(logsDir);
    } catch {
      // 忽略打开目录失败
    }

    await shutdownApp();
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

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0 && serviceManager) {
    createMainWindow(serviceManager.rendererBaseUrl);
  }
});

app.on("window-all-closed", () => {
  // macOS 上保持应用运行（通过托盘），其他平台也不退出，由托盘控制
  // 不调用 app.quit()，让托盘保持活跃
});

app.on("will-quit", (event) => {
  if (!serviceManager || shutdownStarted) {
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
