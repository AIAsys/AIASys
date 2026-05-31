const path = require("path");
const { app, BrowserWindow, dialog, shell, Tray, Menu } = require("electron");
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
const runtimeStateRoot = path.join(app.getPath("userData"), "backend-runtime");

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

function logError(message, error) {
  console.error(`[aiasys-desktop] ${message}:`, error);
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
  const appRoot = app.isPackaged
    ? path.join(process.resourcesPath, "app.asar")
    : path.join(__dirname, "..");
  if (process.platform === "win32") {
    return path.join(appRoot, "build", "icon.ico");
  }
  return path.join(appRoot, "build", "icon.png");
}

function createMainWindow(rendererBaseUrl) {
  const preloadPath = path.join(__dirname, "preload.cjs");
  const initialUrl = new URL(startPath, rendererBaseUrl).toString();

  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 720,
    autoHideMenuBar: true,
    show: false,
    title: "AIASys Desktop",
    icon: getWindowIconPath(),
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
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

function createTray() {
  const iconPath = getWindowIconPath();
  tray = new Tray(iconPath);
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
      label: "打开日志目录",
      click: () => {
        const logsDir = path.join(runtimeStateRoot, "logs");
        fs.mkdirSync(logsDir, { recursive: true });
        void shell.openPath(logsDir);
      },
    },
    {
      label: "打开数据目录",
      click: () => {
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
  serviceManager = new DesktopServiceManager({
    mode: desktopMode,
    isPackaged: app.isPackaged,
    resourcesPath: process.resourcesPath,
    runtimeStateRoot,
  });
  const rendererBaseUrl = await serviceManager.start();
  createMainWindow(rendererBaseUrl);
  createTray();
}

app.whenReady().then(() => {
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
