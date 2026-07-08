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

export interface OpenWorkspaceWindowResult {
  success: boolean;
  error?: string;
}

declare global {
  interface Window {
    __AIASYS_DESKTOP__?: {
      platform: "electron";
      mode: "dev" | "preview";
      /** 注册托盘菜单动作回调，返回取消订阅函数 */
      onTrayAction?(callback: (action: TrayAction) => void): () => void;
      /** 注册后端崩溃回调（桌面版自动重启时触发），返回取消订阅函数 */
      onBackendCrashed?(callback: (info?: { exhausted?: boolean; error?: string; restartCount?: number; maxRestarts?: number }) => void): () => void;
      /** 注册后端重启就绪回调，返回取消订阅函数 */
      onBackendReady?(callback: () => void): () => void;
      /** 注册自定义协议 deeplink 回调，返回取消订阅函数 */
      onDeepLink?(callback: (url: string) => void): () => void;
      /** 选择本地文件夹（桌面版） */
      selectFolder?(options?: {
        title?: string;
        defaultPath?: string;
      }): Promise<SelectFolderResult>;
      /** 在系统资源管理器中打开指定路径（桌面版） */
      openPath?(targetPath: string): Promise<boolean>;
      /** 获取桌面端应用版本号 */
      getVersion?(): Promise<string>;
      /** 用系统默认浏览器打开外部链接 */
      openExternal?(url: string): Promise<boolean>;
      /** 在新窗口打开指定工作区（桌面端多窗口能力） */
      openWorkspaceWindow?(options: {
        workspaceId?: string;
        sessionId?: string;
      }): Promise<OpenWorkspaceWindowResult>;
    };
  }
}

export {};
