import { useCallback, useState } from "react";
import {
  createGlobalWorkspacePreviewFile,
  createWorkspacePreviewFile,
} from "@/utils/workspaceFiles";
import { WORKSPACE_FILE_DRAG_MIME } from "@/components/CanvasEditor/canvasUtils";
import type { PreviewFile } from "@/components/layout/WorkspaceSidebar/preview";
import type { GlobalResourceNode } from "@/components/layout/WorkspaceSidebar/assetPreviewFactory";
import { type WorkspaceTab } from "./components/WorkspaceTabBar";
import type { SidebarTab } from "@/components/layout/WorkspaceSidebar/context/types";
import { getCanvasDropZone } from "./PaneRenderer";
import type { CanvasDropZone } from "./PaneRenderer";
import {
  createRootLeaf,
  findLeaf,
  updateLeaf,
  removeTab,
  pruneEmptyLeaves,
  moveTab,
  splitLeafForToolbar,
  splitWithTab,
  openFileInLeaf,
  splitLeafWithNewTab,
  getAllLeafIds,
  findLeafWithTab,
  type PaneTreeNode,
} from "./paneTree";

export function usePaneTree(
  executorSessionId: string | undefined,
  token: string | undefined,
  workspaceId?: string,
) {
  const [paneTree, setPaneTree] = useState<PaneTreeNode>(createRootLeaf());
  const [activeLeafId, setActiveLeafId] = useState("main");
  const [dropZones, setDropZones] = useState<Record<string, CanvasDropZone>>({});
  const [workspaceDefaultActiveTab, setWorkspaceDefaultActiveTab] = useState<SidebarTab>("artifacts");
  const [workspaceInitialArtifactFile, setWorkspaceInitialArtifactFile] =
    useState<PreviewFile | null>(null);
  const [tabDirtyMap, setTabDirtyMap] = useState<Record<string, boolean>>({});

  const openWorkspaceFileTarget = useCallback(
    (file: PreviewFile, options?: { mode?: "preview" | "edit" }) => {
      const mode = options?.mode ?? "preview";
      setWorkspaceDefaultActiveTab("artifacts");
      setWorkspaceInitialArtifactFile(file);
      setPaneTree((current) => {
        const targetLeafId = findLeaf(current, activeLeafId)
          ? activeLeafId
          : (getAllLeafIds(current)[0] ?? "main");
        const leaf = findLeaf(current, targetLeafId);
        if (!leaf) return current;
        const existingIndex = leaf.tabs.findIndex(
          (t) => t.file?.name === file.name && t.mode === mode,
        );
        if (existingIndex >= 0) {
          setActiveLeafId(targetLeafId);
          return updateLeaf(current, targetLeafId, (l) => ({
            ...l,
            activeTabId: l.tabs[existingIndex].id,
          }));
        }
        const newTab: WorkspaceTab = { id: `${file.name}:${mode}:${Date.now()}`, file, mode };
        setActiveLeafId(targetLeafId);
        return updateLeaf(current, targetLeafId, (l) => ({
          ...l,
          tabs: [...l.tabs, newTab],
          activeTabId: newTab.id,
        }));
      });
    },
    [activeLeafId],
  );

  const openSubagentDetailTab = useCallback(
    (subagentId: string) => {
      setPaneTree((current) => {
        const targetLeafId = findLeaf(current, activeLeafId)
          ? activeLeafId
          : (getAllLeafIds(current)[0] ?? "main");
        const leaf = findLeaf(current, targetLeafId);
        if (!leaf) return current;
        const existingIndex = leaf.tabs.findIndex(
          (t) => t.subagentId === subagentId,
        );
        if (existingIndex >= 0) {
          setActiveLeafId(targetLeafId);
          return updateLeaf(current, targetLeafId, (l) => ({
            ...l,
            activeTabId: l.tabs[existingIndex].id,
          }));
        }
        const newTab: WorkspaceTab = {
          id: `subagent:${subagentId}:${Date.now()}`,
          subagentId,
        };
        setActiveLeafId(targetLeafId);
        return updateLeaf(current, targetLeafId, (l) => ({
          ...l,
          tabs: [...l.tabs, newTab],
          activeTabId: newTab.id,
        }));
      });
    },
    [activeLeafId],
  );

  const openTerminalTab = useCallback((options?: { forceNew?: boolean }) => {
    setPaneTree((current) => {
      const targetLeafId = findLeaf(current, activeLeafId)
        ? activeLeafId
        : (getAllLeafIds(current)[0] ?? "main");
      const leaf = findLeaf(current, targetLeafId);
      if (!leaf) return current;
      const existingTab = leaf.tabs.find((t) => t.terminalId);
      if (existingTab && !options?.forceNew) {
        setActiveLeafId(targetLeafId);
        return updateLeaf(current, targetLeafId, (l) => ({
          ...l,
          activeTabId: existingTab.id,
        }));
      }
      const terminalId = `terminal-${Date.now()}`;
      const newTab: WorkspaceTab = {
        id: `terminal:${terminalId}`,
        terminalId,
      };
      setActiveLeafId(targetLeafId);
      return updateLeaf(current, targetLeafId, (l) => ({
        ...l,
        tabs: [...l.tabs, newTab],
        activeTabId: newTab.id,
      }));
    });
  }, [activeLeafId]);

  const openDatabaseQueryTab = useCallback((databaseHandle: string) => {
    setPaneTree((current) => {
      const targetLeafId = findLeaf(current, activeLeafId)
        ? activeLeafId
        : (getAllLeafIds(current)[0] ?? "main");
      const leaf = findLeaf(current, targetLeafId);
      if (!leaf) return current;
      const existingTab = leaf.tabs.find(
        (t) => t.databaseHandle === databaseHandle,
      );
      if (existingTab) {
        setActiveLeafId(targetLeafId);
        return updateLeaf(current, targetLeafId, (l) => ({
          ...l,
          activeTabId: existingTab.id,
        }));
      }
      const tabId = `db:${databaseHandle}:${Date.now()}`;
      const newTab: WorkspaceTab = {
        id: tabId,
        databaseHandle,
      };
      setActiveLeafId(targetLeafId);
      return updateLeaf(current, targetLeafId, (l) => ({
        ...l,
        tabs: [...l.tabs, newTab],
        activeTabId: newTab.id,
      }));
    });
  }, [activeLeafId]);

  const openCapabilityDetailTab = useCallback((capabilityId: string, targetWorkspaceId: string, displayName: string) => {
    setPaneTree((current) => {
      const targetLeafId = findLeaf(current, activeLeafId)
        ? activeLeafId
        : (getAllLeafIds(current)[0] ?? "main");
      const leaf = findLeaf(current, targetLeafId);
      if (!leaf) return current;
      const allLeafIds = getAllLeafIds(current);
      const existingTab = allLeafIds
        .map((leafId) => findLeaf(current, leafId))
        .flatMap((currentLeaf) => currentLeaf?.tabs ?? [])
        .find((tab) => tab.capabilityDetail?.capabilityId === capabilityId);
      if (existingTab) {
        const existingLeaf = findLeafWithTab(current, existingTab.id);
        const existingLeafId = existingLeaf?.id ?? targetLeafId;
        setActiveLeafId(existingLeafId);
        return updateLeaf(current, existingLeafId, (l) => ({
          ...l,
          activeTabId: existingTab.id,
        }));
      }
      const newTab: WorkspaceTab = {
        id: `capability-detail:${capabilityId}:${Date.now()}`,
        capabilityDetail: { workspaceId: targetWorkspaceId, capabilityId, displayName },
      };
      setActiveLeafId(targetLeafId);
      return updateLeaf(current, targetLeafId, (l) => ({
        ...l,
        tabs: [...l.tabs, newTab],
        activeTabId: newTab.id,
      }));
    });
  }, [activeLeafId]);

  const globalResourceNodeToPreviewFile = useCallback(
    (node: GlobalResourceNode): PreviewFile =>
      createGlobalWorkspacePreviewFile(
        {
          name: node.path,
          resource_type: node.resource_type,
          schema_kind: node.schema_kind,
          preview_kind: node.preview_kind,
          renderer_hint: node.renderer_hint,
          meta: {
            ...(node.meta ?? {}),
            _globalResource: true,
            relative_path: node.path,
          },
        },
        (node.meta?.workspace_id as string | undefined) ?? workspaceId,
        token,
      ),
    [token, workspaceId],
  );

  const handleOpenGlobalResource = useCallback(
    (node: GlobalResourceNode) => {
      openWorkspaceFileTarget(globalResourceNodeToPreviewFile(node));
    },
    [globalResourceNodeToPreviewFile, openWorkspaceFileTarget],
  );

  const activateWorkspaceTab = useCallback((leafId: string, tabId: string) => {
    setActiveLeafId(leafId);
    setPaneTree((current) =>
      updateLeaf(current, leafId, (leaf) => ({ ...leaf, activeTabId: tabId })),
    );
  }, []);

  const _confirmCloseDirtyTab = useCallback(
    (tab: WorkspaceTab): boolean => {
      if (tab.mode === "edit" && tabDirtyMap[tab.id]) {
        return window.confirm(`关闭 "${tab.file?.name ?? '标签'}" 并放弃未保存修改吗？`);
      }
      return true;
    },
    [tabDirtyMap],
  );

  const closeWorkspaceTab = useCallback(
    (leafId: string, tabId: string) => {
      setPaneTree((current) => {
        const leaf = findLeaf(current, leafId);
        const tab = leaf?.tabs.find((t) => t.id === tabId);
        if (tab && !_confirmCloseDirtyTab(tab)) {
          return current;
        }
        let next = removeTab(current, leafId, tabId);
        next = pruneEmptyLeaves(next);
        if (next.kind === "leaf" && next.tabs.length === 0) {
          return createRootLeaf();
        }
        if (!findLeaf(next, activeLeafId)) {
          const ids = getAllLeafIds(next);
          if (ids.length > 0) setActiveLeafId(ids[0]);
        }
        return next;
      });
      setTabDirtyMap((prev) => {
        const next = { ...prev };
        delete next[tabId];
        return next;
      });
    },
    [activeLeafId, _confirmCloseDirtyTab],
  );

  const closeOtherTabs = useCallback(
    (leafId: string, keepTabId: string) => {
      setPaneTree((current) => {
        const leaf = findLeaf(current, leafId);
        if (!leaf) return current;
        const tabsToClose = leaf.tabs.filter((t) => t.id !== keepTabId);
        for (const tab of tabsToClose) {
          if (tab.mode === "edit" && tabDirtyMap[tab.id]) {
            if (!window.confirm(`关闭 "${tab.file?.name ?? '标签'}" 并放弃未保存修改吗？`)) {
              return current;
            }
          }
        }
        let next = updateLeaf(current, leafId, (l) => ({
          ...l,
          tabs: l.tabs.filter((t) => t.id === keepTabId),
          activeTabId: keepTabId,
        }));
        next = pruneEmptyLeaves(next);
        if (next.kind === "leaf" && next.tabs.length === 0) {
          return createRootLeaf();
        }
        if (!findLeaf(next, activeLeafId)) {
          const ids = getAllLeafIds(next);
          if (ids.length > 0) setActiveLeafId(ids[0]);
        }
        return next;
      });
      setTabDirtyMap((prev) => {
        const next = { ...prev };
        const leaf = findLeaf(paneTree, leafId);
        if (leaf) {
          for (const tab of leaf.tabs) {
            if (tab.id !== keepTabId) delete next[tab.id];
          }
        }
        return next;
      });
    },
    [activeLeafId, paneTree, tabDirtyMap],
  );

  const closeRightTabs = useCallback(
    (leafId: string, anchorTabId: string) => {
      setPaneTree((current) => {
        const leaf = findLeaf(current, leafId);
        if (!leaf) return current;
        const anchorIndex = leaf.tabs.findIndex((t) => t.id === anchorTabId);
        if (anchorIndex < 0 || anchorIndex >= leaf.tabs.length - 1) return current;
        const tabsToClose = leaf.tabs.slice(anchorIndex + 1);
        for (const tab of tabsToClose) {
          if (tab.mode === "edit" && tabDirtyMap[tab.id]) {
            if (!window.confirm(`关闭 "${tab.file?.name ?? '标签'}" 并放弃未保存修改吗？`)) {
              return current;
            }
          }
        }
        const remainingTabs = leaf.tabs.slice(0, anchorIndex + 1);
        let next = updateLeaf(current, leafId, (l) => ({
          ...l,
          tabs: remainingTabs,
          activeTabId: remainingTabs.some((t) => t.id === l.activeTabId)
            ? l.activeTabId
            : anchorTabId,
        }));
        next = pruneEmptyLeaves(next);
        if (next.kind === "leaf" && next.tabs.length === 0) {
          return createRootLeaf();
        }
        if (!findLeaf(next, activeLeafId)) {
          const ids = getAllLeafIds(next);
          if (ids.length > 0) setActiveLeafId(ids[0]);
        }
        return next;
      });
      setTabDirtyMap((prev) => {
        const next = { ...prev };
        const leaf = findLeaf(paneTree, leafId);
        if (leaf) {
          const anchorIndex = leaf.tabs.findIndex((t) => t.id === anchorTabId);
          for (let i = anchorIndex + 1; i < leaf.tabs.length; i++) {
            delete next[leaf.tabs[i].id];
          }
        }
        return next;
      });
    },
    [activeLeafId, paneTree, tabDirtyMap],
  );

  const closeAllTabs = useCallback(
    (leafId: string) => {
      setPaneTree((current) => {
        const leaf = findLeaf(current, leafId);
        if (!leaf) return current;
        for (const tab of leaf.tabs) {
          if (tab.mode === "edit" && tabDirtyMap[tab.id]) {
            if (!window.confirm(`关闭 "${tab.file?.name ?? '标签'}" 并放弃未保存修改吗？`)) {
              return current;
            }
          }
        }
        let next = updateLeaf(current, leafId, (l) => ({
          ...l,
          tabs: [],
          activeTabId: null,
        }));
        next = pruneEmptyLeaves(next);
        if (next.kind === "leaf" && next.tabs.length === 0) {
          return createRootLeaf();
        }
        if (!findLeaf(next, activeLeafId)) {
          const ids = getAllLeafIds(next);
          if (ids.length > 0) setActiveLeafId(ids[0]);
        }
        return next;
      });
      setTabDirtyMap((prev) => {
        const next = { ...prev };
        const leaf = findLeaf(paneTree, leafId);
        if (leaf) {
          for (const tab of leaf.tabs) {
            delete next[tab.id];
          }
        }
        return next;
      });
    },
    [activeLeafId, paneTree, tabDirtyMap],
  );

  const splitPane = useCallback(
    (leafId: string, tabId: string, direction: "horizontal" | "vertical") => {
      setPaneTree((current) => {
        const leaf = findLeaf(current, leafId);
        if (!leaf) return current;
        const result = splitLeafForToolbar(current, leaf.id, tabId, direction);
        setActiveLeafId(result.newLeafId);
        return result.tree;
      });
    },
    [],
  );

  const moveTabToPane = useCallback(
    (tabId: string, fromLeafId: string, toLeafId: string) => {
      setPaneTree((current) => {
        const result = moveTab(current, tabId, fromLeafId, toLeafId);
        setActiveLeafId(toLeafId);
        return result;
      });
    },
    [],
  );

  const buildWorkspacePreviewFile = useCallback(
    (file: string | PreviewFile): PreviewFile =>
      createWorkspacePreviewFile(file, executorSessionId, token),
    [executorSessionId, token],
  );

  const handleDragOver = useCallback((e: React.DragEvent, leafId: string) => {
    const types = e.dataTransfer.types;
    const isTabDrag =
      types.includes("application/x-canvas-tab-id") ||
      types.includes("application/x-canvas-leaf-id");
    const isFileDrag = types.includes(WORKSPACE_FILE_DRAG_MIME);
    if (!isTabDrag && !isFileDrag) return;
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = isFileDrag ? "copy" : "move";
    const zone = getCanvasDropZone(e);
    setDropZones((prev) => ({ ...prev, [leafId]: zone }));
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent, leafId: string) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setDropZones((prev) => {
        const next = { ...prev };
        delete next[leafId];
        return next;
      });
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent, targetLeafId: string) => {
      e.preventDefault();
      e.stopPropagation();
      const zone = dropZones[targetLeafId] ?? getCanvasDropZone(e);
      setDropZones((prev) => {
        const next = { ...prev };
        delete next[targetLeafId];
        return next;
      });

      const tabId = e.dataTransfer.getData("application/x-canvas-tab-id");
      if (tabId) {
        const sourceLeafId =
          e.dataTransfer.getData("application/x-canvas-leaf-id") || targetLeafId;
        if (zone === "center") {
          moveTabToPane(tabId, sourceLeafId, targetLeafId);
        } else {
          const direction = zone === "left" || zone === "right" ? "horizontal" : "vertical";
          const tabFirst = zone === "left" || zone === "top";
          if (sourceLeafId === targetLeafId) {
            splitPane(targetLeafId, tabId, direction);
          } else {
            setPaneTree((current) => {
              const result = splitWithTab(current, tabId, sourceLeafId, targetLeafId, direction, tabFirst);
              setActiveLeafId(result.newLeafId);
              return result.tree;
            });
          }
        }
        return;
      }

      const fileName = e.dataTransfer.getData(WORKSPACE_FILE_DRAG_MIME);
      if (fileName) {
        const previewFile = buildWorkspacePreviewFile(fileName);
        const newTab: WorkspaceTab = {
          id: `${fileName}:preview:${Date.now()}`,
          file: previewFile,
          mode: "preview",
        };
        if (zone === "center") {
          setPaneTree((current) => {
            const result = openFileInLeaf(current, targetLeafId, newTab);
            setActiveLeafId(targetLeafId);
            return result.tree;
          });
        } else {
          const direction = zone === "left" || zone === "right" ? "horizontal" : "vertical";
          const tabFirst = zone === "left" || zone === "top";
          setPaneTree((current) => {
            const result = splitLeafWithNewTab(current, targetLeafId, newTab, direction, tabFirst);
            setActiveLeafId(result.newLeafId);
            return result.tree;
          });
        }
      }
    },
    [dropZones, moveTabToPane, splitPane, buildWorkspacePreviewFile],
  );

  const openWorkspaceFileFromCanvas = useCallback(
    (fileName: string) => {
      openWorkspaceFileTarget(buildWorkspacePreviewFile(fileName));
    },
    [buildWorkspacePreviewFile, openWorkspaceFileTarget],
  );

  const handleEditFileInMainCanvas = useCallback(
    (file: PreviewFile) => {
      openWorkspaceFileTarget(file, { mode: "edit" });
    },
    [openWorkspaceFileTarget],
  );

  const resetPaneTree = useCallback(() => {
    setPaneTree(createRootLeaf());
    setActiveLeafId("main");
    setDropZones({});
    setWorkspaceDefaultActiveTab("artifacts");
    setWorkspaceInitialArtifactFile(null);
    setTabDirtyMap({});
  }, []);

  return {
    paneTree,
    setPaneTree,
    activeLeafId,
    setActiveLeafId,
    dropZones,
    workspaceDefaultActiveTab,
    setWorkspaceDefaultActiveTab,
    workspaceInitialArtifactFile,
    tabDirtyMap,
    setTabDirtyMap,
    resetPaneTree,
    openWorkspaceFileTarget,
    openSubagentDetailTab,
    openTerminalTab,
    openDatabaseQueryTab,
    openCapabilityDetailTab,
    handleOpenGlobalResource,
    activateWorkspaceTab,
    closeWorkspaceTab,
    closeOtherTabs,
    closeRightTabs,
    closeAllTabs,
    splitPane,
    buildWorkspacePreviewFile,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    openWorkspaceFileFromCanvas,
    handleEditFileInMainCanvas,
  };
}
