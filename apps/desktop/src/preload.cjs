const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("__AIASYS_DESKTOP__", {
  platform: "electron",
  mode: process.env.AIASYS_DESKTOP_MODE || "dev",
});
