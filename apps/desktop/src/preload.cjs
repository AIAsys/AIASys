const { contextBridge, ipcRenderer } = require("electron");

const trayActionListeners = new Set();
const backendCrashedListeners = new Set();
const backendReadyListeners = new Set();
const deepLinkListeners = new Set();

function getBackendBaseUrlFromArgv() {
  const arg = process.argv.find((a) => a.startsWith("--aiasys-backend-base-url="));
  return arg ? arg.slice("--aiasys-backend-base-url=".length) : "";
}

function createListener(channel, listeners) {
  return (callback) => {
    listeners.add(callback);
    return () => {
      listeners.delete(callback);
    };
  };
}

function emit(listeners, ...args) {
  for (const listener of listeners) {
    try {
      listener(...args);
    } catch (error) {
      console.error("[aiasys-desktop] preload listener error:", error);
    }
  }
}

// 监听主进程的 tray-action 消息
ipcRenderer.on("tray-action", (_event, action) => {
  emit(trayActionListeners, action);
});

// 监听后端崩溃通知
ipcRenderer.on("backend:crashed", (_event, info) => {
  emit(backendCrashedListeners, info);
});

// 监听后端重启就绪通知
ipcRenderer.on("backend:ready", () => {
  emit(backendReadyListeners);
});

// 监听自定义协议 deeplink
ipcRenderer.on("deep-link", (_event, url) => {
  emit(deepLinkListeners, url);
});

contextBridge.exposeInMainWorld("__AIASYS_DESKTOP__", {
  platform: "electron",
  mode: process.env.AIASYS_DESKTOP_MODE || "dev",
  // 后端服务地址，供前端 WebSocket 等需要直连后端的场景使用
  backendBaseUrl: getBackendBaseUrlFromArgv(),
  // 注册托盘动作回调，让前端可以响应托盘菜单点击
  onTrayAction: createListener("tray-action", trayActionListeners),
  // 注册后端崩溃回调（桌面版自动重启时触发）
  onBackendCrashed: createListener("backend:crashed", backendCrashedListeners),
  // 注册后端重启就绪回调
  onBackendReady: createListener("backend:ready", backendReadyListeners),
  // 注册自定义协议 deeplink 回调
  onDeepLink: createListener("deep-link", deepLinkListeners),
  // 选择本地文件夹
  selectFolder(options) {
    return ipcRenderer.invoke("aiasys:select-folder", options);
  },
  // 在系统资源管理器中打开指定路径
  openPath(targetPath) {
    return ipcRenderer.invoke("aiasys:open-path", targetPath);
  },
  // 获取桌面端应用版本号
  getVersion() {
    return ipcRenderer.invoke("aiasys:get-version");
  },
  // 用系统默认浏览器打开外部链接
  openExternal(url) {
    return ipcRenderer.invoke("aiasys:open-external", url);
  },
  // 在新窗口打开指定工作区（桌面端多窗口能力）
  openWorkspaceWindow(options) {
    return ipcRenderer.invoke("aiasys:open-workspace-window", options);
  },
});
