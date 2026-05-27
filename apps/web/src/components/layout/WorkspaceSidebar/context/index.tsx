/**
 * * WorkspaceSidebar Context
 *
 * 提供 Sidebar 组件间共享的状态和动作
 */
import { createContext, useContext } from "react";
import type { SidebarContextValue } from "./types";

const SidebarContext = createContext<SidebarContextValue | null>(null);

export function useSidebarContext() {
  const context = useContext(SidebarContext);
  if (!context) {
    throw new Error("useSidebarContext must be used within SidebarProvider");
  }
  return context;
}

// 导出类型
export type {
  SidebarState,
  SidebarActions,
  SidebarMeta,
  SidebarContextValue,
  SidebarTab,
} from "./types";

export { SidebarContext };
