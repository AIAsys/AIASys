// Electron preload 注入的桌面环境标识
// 见 apps/desktop/src/preload.cjs

export interface TrayAction {
  type: "open-settings";
  section?: string;
}

declare global {
  interface Window {
    __AIASYS_DESKTOP__?: {
      platform: "electron";
      mode: "dev" | "preview";
      /** 注册托盘菜单动作回调 */
      onTrayAction?(callback: (action: TrayAction) => void): void;
    };
  }
}

export {};
