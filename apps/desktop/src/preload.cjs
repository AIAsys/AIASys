const { contextBridge, ipcRenderer } = require("electron");

let trayActionCallback = null;
let backendCrashedCallback = null;
let backendReadyCallback = null;

function getBackendBaseUrlFromArgv() {
  const arg = process.argv.find((a) => a.startsWith("--aiasys-backend-base-url="));
  return arg ? arg.slice("--aiasys-backend-base-url=".length) : "";
}

// 监听主进程的 tray-action 消息
ipcRenderer.on("tray-action", (_event, action) => {
  if (typeof trayActionCallback === "function") {
    trayActionCallback(action);
  }
});

// 监听后端崩溃通知
ipcRenderer.on("backend:crashed", () => {
  if (typeof backendCrashedCallback === "function") {
    backendCrashedCallback();
  }
});

// 监听后端重启就绪通知
ipcRenderer.on("backend:ready", () => {
  if (typeof backendReadyCallback === "function") {
    backendReadyCallback();
  }
});

contextBridge.exposeInMainWorld("__AIASYS_DESKTOP__", {
  platform: "electron",
  mode: process.env.AIASYS_DESKTOP_MODE || "dev",
  // 后端服务地址，供前端 WebSocket 等需要直连后端的场景使用
  backendBaseUrl: getBackendBaseUrlFromArgv(),
  // 注册托盘动作回调，让前端可以响应托盘菜单点击
  onTrayAction(callback) {
    trayActionCallback = callback;
  },
  // 注册后端崩溃回调（桌面版自动重启时触发）
  onBackendCrashed(callback) {
    backendCrashedCallback = callback;
  },
  // 注册后端重启就绪回调
  onBackendReady(callback) {
    backendReadyCallback = callback;
  },
  // 选择本地文件夹
  selectFolder(options) {
    return ipcRenderer.invoke("aiasys:select-folder", options);
  },
});
