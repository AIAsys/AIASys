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
      /** 注册后端崩溃回调（桌面版自动重启时触发） */
      onBackendCrashed?(callback: () => void): void;
      /** 注册后端重启就绪回调 */
      onBackendReady?(callback: () => void): void;
      /** 选择本地文件夹（桌面版） */
      selectFolder?(options?: {
        title?: string;
        defaultPath?: string;
      }): Promise<SelectFolderResult>;
    };
  }
}

export {};
