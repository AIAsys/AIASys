import { useRef } from "react";
import { useLocalStorageState } from "@/hooks/useLocalStorageState";

export function useUIState() {
  const [isRightSidebarOpen, setIsRightSidebarOpen] = useLocalStorageState(
    "aiasys:ui:isRightSidebarOpen",
    false,
  );
  const [userClosedSidebar, setUserClosedSidebar] = useLocalStorageState(
    "aiasys:ui:userClosedSidebar",
    false,
  );
  const [sidebarWidth, setSidebarWidth] = useLocalStorageState(
    "aiasys:ui:sidebarWidth",
    420,
  );
  const [sidebarMode, setSidebarMode] = useLocalStorageState<"expanded" | "collapsed">(
    "aiasys:ui:sidebarMode",
    "expanded",
  );
  const [showImportModal, setShowImportModal] = useLocalStorageState(
    "aiasys:ui:showImportModal",
    false,
  );

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  return {
    isRightSidebarOpen,
    setIsRightSidebarOpen,
    userClosedSidebar,
    setUserClosedSidebar,
    sidebarWidth,
    setSidebarWidth,
    sidebarMode,
    setSidebarMode,
    showImportModal,
    setShowImportModal,
    messagesEndRef,
    fileInputRef,
  };
}