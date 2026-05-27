const path = require("path");
const { app, BrowserWindow, dialog, shell } = require("electron");
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
let serviceManager = null;
let shutdownStarted = false;
let signalShutdownPromise = null;

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

  mainWindow.once("ready-to-show", () => {
    mainWindow?.show();
    if (openDevTools) {
      mainWindow?.webContents.openDevTools({ mode: "detach" });
    }
  });

  void mainWindow.loadURL(initialUrl);
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
}

app.whenReady().then(() => {
  void bootstrap().catch(async (error) => {
    logError("bootstrap failed", error);
    dialog.showErrorBox(
      "AIASys Desktop 启动失败",
      error instanceof Error ? error.stack || error.message : String(error),
    );
    await shutdownApp();
    app.exit(1);
  });
});

process.once("SIGINT", () => {
  exitAfterShutdown(0);
});

process.once("SIGTERM", () => {
  exitAfterShutdown(0);
});

process.on("message", (message) => {
  if (!message || message.type !== "shutdown") {
    return;
  }

  exitAfterShutdown(0);
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0 && serviceManager) {
    createMainWindow(serviceManager.rendererBaseUrl);
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("will-quit", (event) => {
  if (!serviceManager || shutdownStarted) {
    return;
  }

  event.preventDefault();
  void shutdownApp().finally(() => {
    app.quit();
  });
});
