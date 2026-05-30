import { useCallback, useMemo, useState } from "react";
import {
  normalizeKnowledgeGraphDialogTab,
  type KnowledgeGraphDialogTab,
} from "@/components/KnowledgeGraphDialog/types";

export type DatabaseResourceDialogTab = "catalog" | "mounts";
export type DatabaseResourceDialogAction = "manage" | "create";
export type KnowledgeBaseDialogTab = "catalog" | "mounts";
export type { KnowledgeGraphDialogTab } from "@/components/KnowledgeGraphDialog/types";
export type ResourceManagementSection = "knowledge_base" | "knowledge_graph";
export type AnalysisDialogOverlay =
  | "database"
  | "knowledge_base"
  | "knowledge_graph"
  | "agent_config"
  | null;

interface OpenOverlayOptions {
  syncRoute?: boolean;
  action?: DatabaseResourceDialogAction;
}

function getCurrentAnalysisOverlay(): AnalysisDialogOverlay {
  if (typeof window === "undefined") {
    return null;
  }

  const normalizedPath =
    window.location.pathname.replace(/\/+$/, "") || "/";
  if (normalizedPath !== "/analysis") {
    return null;
  }

  const overlay = new URLSearchParams(window.location.search).get("overlay");
  if (
    overlay === "database" ||
    overlay === "knowledge_base" ||
    overlay === "knowledge_graph" ||
    overlay === "agent-config" ||
    overlay === "agent_config"
  ) {
    return overlay === "agent-config" ? "agent_config" : overlay;
  }
  return null;
}

function replaceAnalysisOverlay(nextOverlay: AnalysisDialogOverlay) {
  if (typeof window === "undefined") {
    return;
  }

  const normalizedPath =
    window.location.pathname.replace(/\/+$/, "") || "/";
  if (normalizedPath !== "/analysis") {
    return;
  }

  const currentUrl = new URL(window.location.href);
  const currentOverlay = currentUrl.searchParams.get("overlay");
  if ((currentOverlay || null) === nextOverlay) {
    return;
  }

  if (nextOverlay) {
    currentUrl.searchParams.set(
      "overlay",
      nextOverlay === "agent_config" ? "agent-config" : nextOverlay,
    );
  } else {
    currentUrl.searchParams.delete("overlay");
  }

  const nextUrl = `${currentUrl.pathname}${currentUrl.search}`;
  const withAppNavigate = window as Window & {
    appNavigate?: (path: string, options?: { replace?: boolean }) => void;
  };
  if (withAppNavigate.appNavigate) {
    withAppNavigate.appNavigate(nextUrl, { replace: true });
    window.dispatchEvent(new PopStateEvent("popstate"));
    return;
  }
  window.history.replaceState(window.history.state, "", nextUrl);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export interface UseDataAnalysisOverlayStateReturn {
  showDatabaseConnectionsDialog: boolean;
  setShowDatabaseConnectionsDialog: (show: boolean) => void;
  defaultDatabaseResourceDialogTab: DatabaseResourceDialogTab;
  defaultDatabaseResourceDialogAction: DatabaseResourceDialogAction;
  openDatabaseConnectionsDialog: (
    tab?: DatabaseResourceDialogTab,
    options?: OpenOverlayOptions,
  ) => void;
  showResourceManagementDialog: boolean;
  setShowResourceManagementDialog: (show: boolean) => void;
  defaultResourceManagementSection: ResourceManagementSection;
  openResourceManagementDialog: (
    section?: ResourceManagementSection,
    options?: OpenOverlayOptions,
  ) => void;
  defaultKnowledgeBaseDialogTab: KnowledgeBaseDialogTab;
  openKnowledgeBaseDialog: (
    tab?: KnowledgeBaseDialogTab,
    options?: OpenOverlayOptions,
  ) => void;
  defaultKnowledgeGraphDialogTab: KnowledgeGraphDialogTab;
  openKnowledgeGraphDialog: (
    tab?: KnowledgeGraphDialogTab,
    options?: OpenOverlayOptions,
  ) => void;
  showLLMConfigDialog: boolean;
  setShowLLMConfigDialog: (show: boolean) => void;
  openLLMConfigDialog: () => void;
  showAgentConfigDialog: boolean;
  setShowAgentConfigDialog: (show: boolean) => void;
  openAgentConfigDialog: () => void;
  syncRouteOverlay: (overlay: AnalysisDialogOverlay) => void;
}

export function useDataAnalysisOverlayState(): UseDataAnalysisOverlayStateReturn {
  const [showDatabaseConnectionsDialog, setShowDatabaseConnectionsDialogState] =
    useState(false);
  const [defaultDatabaseResourceDialogTab, setDefaultDatabaseResourceDialogTab] =
    useState<DatabaseResourceDialogTab>("catalog");
  const [
    defaultDatabaseResourceDialogAction,
    setDefaultDatabaseResourceDialogAction,
  ] = useState<DatabaseResourceDialogAction>("manage");
  const [showResourceManagementDialog, setShowResourceManagementDialogState] =
    useState(false);
  const [defaultResourceManagementSection, setDefaultResourceManagementSection] =
    useState<ResourceManagementSection>("knowledge_base");
  const [defaultKnowledgeBaseDialogTab, setDefaultKnowledgeBaseDialogTab] =
    useState<KnowledgeBaseDialogTab>("catalog");
  const [defaultKnowledgeGraphDialogTab, setDefaultKnowledgeGraphDialogTab] =
    useState<KnowledgeGraphDialogTab>("workbench");
  const [showLLMConfigDialog, setShowLLMConfigDialog] = useState(false);
  const [showAgentConfigDialog, setShowAgentConfigDialogState] = useState(false);

  const setShowDatabaseConnectionsDialog = useCallback((show: boolean) => {
    setShowDatabaseConnectionsDialogState(show);
    if (!show && getCurrentAnalysisOverlay() === "database") {
      replaceAnalysisOverlay(null);
    }
    if (!show) {
      setDefaultDatabaseResourceDialogAction("manage");
    }
  }, []);

  const setShowResourceManagementDialog = useCallback((show: boolean) => {
    setShowResourceManagementDialogState(show);
    if (!show) {
      const currentOverlay = getCurrentAnalysisOverlay();
      if (
        currentOverlay === "knowledge_base" ||
        currentOverlay === "knowledge_graph"
      ) {
        replaceAnalysisOverlay(null);
      }
    }
  }, []);

  const setShowAgentConfigDialog = useCallback((show: boolean) => {
    setShowAgentConfigDialogState(show);
    if (!show && getCurrentAnalysisOverlay() === "agent_config") {
      replaceAnalysisOverlay(null);
    }
  }, []);

  const openResourceManagementDialog = useCallback((
    section: ResourceManagementSection = "knowledge_base",
    options?: OpenOverlayOptions,
  ) => {
    setDefaultResourceManagementSection(section);
    setShowDatabaseConnectionsDialogState(false);
    setShowResourceManagementDialogState(true);
    if (options?.syncRoute !== false) {
      replaceAnalysisOverlay(section);
    }
  }, []);

  const openDatabaseConnectionsDialog = useCallback((
    tab: DatabaseResourceDialogTab = "catalog",
    options?: OpenOverlayOptions,
  ) => {
    setDefaultDatabaseResourceDialogTab(tab);
    setDefaultDatabaseResourceDialogAction(options?.action ?? "manage");
    setShowResourceManagementDialogState(false);
    setShowDatabaseConnectionsDialogState(true);
    if (options?.syncRoute !== false) {
      replaceAnalysisOverlay("database");
    }
  }, []);

  const openKnowledgeBaseDialog = useCallback((
    tab: KnowledgeBaseDialogTab = "catalog",
    options?: OpenOverlayOptions,
  ) => {
    setDefaultKnowledgeBaseDialogTab(tab);
    openResourceManagementDialog("knowledge_base", options);
  }, [openResourceManagementDialog]);

  const openKnowledgeGraphDialog = useCallback((
    tab: KnowledgeGraphDialogTab = "workbench",
    options?: OpenOverlayOptions,
  ) => {
    setDefaultKnowledgeGraphDialogTab(tab);
    openResourceManagementDialog("knowledge_graph", options);
  }, [openResourceManagementDialog]);

  const openLLMConfigDialog = useCallback(() => {
    setShowLLMConfigDialog(true);
  }, []);

  const openAgentConfigDialog = useCallback(() => {
    setShowDatabaseConnectionsDialogState(false);
    setShowResourceManagementDialogState(false);
    setShowAgentConfigDialogState(true);
    replaceAnalysisOverlay("agent_config");
  }, []);

  const syncRouteOverlay = useCallback((overlay: AnalysisDialogOverlay) => {
    if (overlay === "database") {
      setShowAgentConfigDialogState(false);
      setShowResourceManagementDialogState(false);
      setShowDatabaseConnectionsDialogState(true);
      return;
    }

    if (overlay === "knowledge_base") {
      setShowAgentConfigDialogState(false);
      openKnowledgeBaseDialog("catalog", { syncRoute: false });
      return;
    }

    if (overlay === "knowledge_graph") {
      setShowAgentConfigDialogState(false);
      const tab = normalizeKnowledgeGraphDialogTab(
        new URLSearchParams(window.location.search).get("knowledge_graph_tab"),
      );
      openKnowledgeGraphDialog(tab || "workbench", { syncRoute: false });
      return;
    }

    if (overlay === "agent_config") {
      setShowDatabaseConnectionsDialogState(false);
      setShowResourceManagementDialogState(false);
      setShowAgentConfigDialogState(true);
      return;
    }

    setShowDatabaseConnectionsDialogState(false);
    setShowResourceManagementDialogState(false);
    setShowAgentConfigDialogState(false);
    setDefaultDatabaseResourceDialogAction("manage");
  }, [
    openKnowledgeBaseDialog,
    openKnowledgeGraphDialog,
  ]);

  return useMemo(() => ({
    showDatabaseConnectionsDialog,
    setShowDatabaseConnectionsDialog,
    defaultDatabaseResourceDialogTab,
    defaultDatabaseResourceDialogAction,
    openDatabaseConnectionsDialog,
    showResourceManagementDialog,
    setShowResourceManagementDialog,
    defaultResourceManagementSection,
    openResourceManagementDialog,
    defaultKnowledgeBaseDialogTab,
    openKnowledgeBaseDialog,
    defaultKnowledgeGraphDialogTab,
    openKnowledgeGraphDialog,
    showLLMConfigDialog,
    setShowLLMConfigDialog,
    openLLMConfigDialog,
    showAgentConfigDialog,
    setShowAgentConfigDialog,
    openAgentConfigDialog,
    syncRouteOverlay,
  }), [
    showDatabaseConnectionsDialog,
    setShowDatabaseConnectionsDialog,
    defaultDatabaseResourceDialogTab,
    defaultDatabaseResourceDialogAction,
    openDatabaseConnectionsDialog,
    showResourceManagementDialog,
    setShowResourceManagementDialog,
    defaultResourceManagementSection,
    openResourceManagementDialog,
    defaultKnowledgeBaseDialogTab,
    openKnowledgeBaseDialog,
    defaultKnowledgeGraphDialogTab,
    openKnowledgeGraphDialog,
    showLLMConfigDialog,
    setShowLLMConfigDialog,
    openLLMConfigDialog,
    showAgentConfigDialog,
    setShowAgentConfigDialog,
    openAgentConfigDialog,
    syncRouteOverlay,
  ]);
}
