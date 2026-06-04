const { contextBridge, ipcRenderer } = require("electron");

let trayActionCallback = null;

// 监听主进程的 tray-action 消息
ipcRenderer.on("tray-action", (_event, action) => {
  if (typeof trayActionCallback === "function") {
    trayActionCallback(action);
  }
});

contextBridge.exposeInMainWorld("__AIASYS_DESKTOP__", {
  platform: "electron",
  mode: process.env.AIASYS_DESKTOP_MODE || "dev",
  // 注册托盘动作回调，让前端可以响应托盘菜单点击
  onTrayAction(callback) {
    trayActionCallback = callback;
  },
});
