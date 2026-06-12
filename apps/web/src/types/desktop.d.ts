// Electron preload 注入的桌面环境标识
// 见 apps/desktop/src/preload.cjs

export interface TrayAction {
  type: "open-settings";
  section?: string;
}

export interface SelectFolderResult {
  canceled: boolean;
  filePaths: string[];
}

declare global {
  interface Window {
    __AIASYS_DESKTOP__?: {
      platform: "electron";
      mode: "dev" | "preview";
      /** 注册托盘菜单动作回调 */
      onTrayAction?(callback: (action: TrayAction) => void): void;
      /** 选择本地文件夹（桌面版） */
      selectFolder?(options?: {
        title?: string;
        defaultPath?: string;
      }): Promise<SelectFolderResult>;
    };
  }
}

export {};
