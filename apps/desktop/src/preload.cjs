const { contextBridge, ipcRenderer } = require("electron");

let trayActionCallback = null;

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

contextBridge.exposeInMainWorld("__AIASYS_DESKTOP__", {
  platform: "electron",
  mode: process.env.AIASYS_DESKTOP_MODE || "dev",
  // 后端服务地址，供前端 WebSocket 等需要直连后端的场景使用
  backendBaseUrl: getBackendBaseUrlFromArgv(),
  // 注册托盘动作回调，让前端可以响应托盘菜单点击
  onTrayAction(callback) {
    trayActionCallback = callback;
  },
  // 选择本地文件夹
  selectFolder(options) {
    return ipcRenderer.invoke("aiasys:select-folder", options);
  },
});
