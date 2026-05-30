// Electron preload 注入的桌面环境标识
// 见 apps/desktop/src/preload.cjs
declare global {
  interface Window {
    __AIASYS_DESKTOP__?: {
      platform: "electron";
      mode: "dev" | "preview";
    };
  }
}

export {};