import { useCallback, useMemo, useRef } from "react";
import { API_ENDPOINTS } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";
import type { PreviewFile } from "@/components/layout/WorkspaceSidebar/preview";
import type { WorkspaceFile } from "@/types/task";
import {
  isImageFile,
  isWorkspaceFolderMarkerFile,
} from "@/utils/fileTreeUtils";
import {
  createGlobalWorkspacePreviewFile,
  createWorkspacePreviewFile,
  resolveWorkspaceFileUrl,
} from "@/utils/workspaceFiles";
import type { WorkspaceMarkdownLinkScope } from "@/utils/workspaceMarkdownLinks";
import {
  createCanvasId,
  getWorkspaceFileLabel,
  stringifyCanvasDocument,
  WORKSPACE_FILE_DRAG_MIME,
} from "./canvasUtils";
import {
  buildNodeTextPatch,
  clipboardHasFiles,
  getContextMenuPosition,
  getEditableNodeText,
  getFileNodeSize,
  getPastedTextNodeSize,
  isCanvasControlTarget,
  isKeyboardEditingTarget,
  normalizeCanvasLinkUrl,
} from "./helpers";
import type {
  CanvasDocument,
  CanvasEdge,
  CanvasNode,
  CanvasNodeDraft,
  CanvasViewportState,
} from "./types";

export type SaveState = "idle" | "dirty" | "saving" | "saved" | "error";
export type FilePickerMode = "file" | "image";
export type CanvasContextMenu =
  | { kind: "node"; nodeId: string; x: number; y: number }
  | { kind: "edge"; edgeId: string; x: number; y: number };

interface CanvasWriteResponse {
  canvas: CanvasDocument;
}

interface UseCanvasHandlersOptions {
  workspaceId?: string;
  filePath?: string;
  sessionId?: string | null;
  token?: string;
  workspaceFiles: WorkspaceFile[];
  onSave?: (content: string) => void;
  onPersistContent?: (content: string) => Promise<void>;
  onOpenWorkspaceFile?: (fileName: string) => void;
  onOpenPreviewFile?: (file: PreviewFile) => void;

  // Canvas state
  canvas: CanvasDocument;
  getCanvas: () => CanvasDocument;
  setCanvasDocument: (canvas: CanvasDocument) => CanvasDocument;
  recordHistorySnapshot: () => void;
  undoCanvas: () => CanvasDocument | null;
  redoCanvas: () => CanvasDocument | null;
  viewport: CanvasViewportState;
  setViewport: React.Dispatch<React.SetStateAction<CanvasViewportState>>;
  selectedNodeIds: string[];
  setSelectedNodeIds: (ids: string[]) => void;
  selectedEdgeId: string | null;
  setSelectedEdgeId: (id: string | null) => void;
  addNode: (node: CanvasNode) => CanvasDocument;
  updateNode: (nodeId: string, patch: Partial<CanvasNode>) => CanvasDocument;
  updateNodes: (
    patches: Record<string, Partial<CanvasNode>>,
  ) => CanvasDocument;
  removeNodes: (nodeIds: string[]) => CanvasDocument;
  addEdge: (edge: CanvasEdge) => CanvasDocument;
  updateEdge: (edgeId: string, patch: Partial<CanvasEdge>) => CanvasDocument;
  removeEdge: (edgeId: string) => CanvasDocument;

  // Editing state
  editingNodeId: string | null;
  setEditingNodeId: (id: string | null) => void;
  editValue: string;
  setEditValue: (value: string) => void;
  editingEdgeId: string | null;
  setEditingEdgeId: (id: string | null) => void;
  edgeEditValue: string;
  setEdgeEditValue: (value: string) => void;

  // Context menu
  contextMenu: CanvasContextMenu | null;
  setContextMenu: (menu: CanvasContextMenu | null) => void;

  // File picker
  filePickerMode: FilePickerMode | null;
  setFilePickerMode: (mode: FilePickerMode | null) => void;
  filePickerQuery: string;
  setFilePickerQuery: (query: string) => void;

  // Other state
  setParseError: (error: string | null) => void;
  setSaveState: (state: SaveState) => void;
  setSaveError: (error: string | null) => void;

  // Interaction
  clientToCanvas: (
    clientX: number,
    clientY: number,
  ) => { x: number; y: number };

  // Refs
  viewportRef: React.RefObject<HTMLDivElement | null>;
  saveTimerRef: React.MutableRefObject<number | null>;
  pendingSaveRef: React.MutableRefObject<CanvasDocument | null>;
  saveVersionRef: React.MutableRefObject<number>;
  lastPointerRef: React.MutableRefObject<{
    clientX: number;
    clientY: number;
  } | null>;
  editorRef: React.RefObject<HTMLDivElement | null>;
}

export function useCanvasHandlers(options: UseCanvasHandlersOptions) {
  const {
    workspaceId,
    filePath,
    sessionId,
    token,
    workspaceFiles,
    onSave,
    onPersistContent,
    onOpenWorkspaceFile,
    onOpenPreviewFile,
    canvas,
    getCanvas,
    setCanvasDocument,
    recordHistorySnapshot,
    undoCanvas,
    redoCanvas,
    viewport,
    setViewport,
    selectedNodeIds,
    setSelectedNodeIds,
    selectedEdgeId,
    setSelectedEdgeId,
    addNode,
    updateNode,
    updateNodes,
    removeNodes,
    updateEdge,
    removeEdge,
    editingNodeId,
    setEditingNodeId,
    editValue,
    setEditValue,
    editingEdgeId,
    setEditingEdgeId,
    edgeEditValue,
    setEdgeEditValue,
    contextMenu,
    setContextMenu,
    filePickerMode,
    setFilePickerMode,
    filePickerQuery,
    setFilePickerQuery,
    setParseError,
    setSaveState,
    setSaveError,
    clientToCanvas,
    viewportRef,
    saveTimerRef,
    pendingSaveRef,
    saveVersionRef,
    lastPointerRef,
    editorRef,
  } = options;
  const saveInFlightRef = useRef(false);
  const queuedSaveRef = useRef<{
    canvas: CanvasDocument;
    version: number;
  } | null>(null);

  // ── Persistence ──────────────────────────────────────────────

  const writeCanvas = useCallback(
    async (next: CanvasDocument) => {
      const json = stringifyCanvasDocument(next);
      onSave?.(json);

      if (onPersistContent) {
        await onPersistContent(json);
        return null;
      }

      if (workspaceId && filePath) {
        const response = await apiRequest<CanvasWriteResponse>(
          API_ENDPOINTS.WORKSPACE_CANVAS(workspaceId, filePath),
          {
            method: "PUT",
            body: { canvas: JSON.parse(json) },
          },
        );
        return response.canvas;
      }

      return null;
    },
    [filePath, onPersistContent, onSave, workspaceId],
  );

  const persistCanvas = useCallback(
    async (next: CanvasDocument, version: number) => {
      if (saveInFlightRef.current) {
        queuedSaveRef.current = { canvas: next, version };
        return;
      }

      saveInFlightRef.current = true;
      setSaveState("saving");
      setSaveError(null);

      let currentCanvas = next;
      let currentVersion = version;
      while (true) {
        try {
          const savedCanvas = await writeCanvas(currentCanvas);
          if (saveVersionRef.current === currentVersion) {
            if (savedCanvas) {
              setCanvasDocument(savedCanvas);
            }
            setParseError(null);
            setSaveState("saved");
          }
        } catch (error) {
          if (saveVersionRef.current === currentVersion) {
            setSaveState("error");
            setSaveError(
              error instanceof Error ? error.message : "保存失败",
            );
          }
        }

        const queued = queuedSaveRef.current;
        queuedSaveRef.current = null;
        if (!queued) {
          saveInFlightRef.current = false;
          return;
        }
        currentCanvas = queued.canvas;
        currentVersion = queued.version;
        setSaveState("saving");
        setSaveError(null);
      }
    },
    [
      writeCanvas,
      setCanvasDocument,
      saveVersionRef,
      setSaveState,
      setSaveError,
      setParseError,
    ],
  );

  const scheduleSave = useCallback(
    (next: CanvasDocument) => {
      saveVersionRef.current += 1;
      pendingSaveRef.current = next;
      setSaveState("dirty");
      if (saveTimerRef.current !== null) {
        window.clearTimeout(saveTimerRef.current);
      }
      saveTimerRef.current = window.setTimeout(() => {
        saveTimerRef.current = null;
        const pending = pendingSaveRef.current;
        pendingSaveRef.current = null;
        if (pending) {
          void persistCanvas(pending, saveVersionRef.current);
        }
      }, 300);
    },
    [
      persistCanvas,
      saveTimerRef,
      pendingSaveRef,
      saveVersionRef,
      setSaveState,
    ],
  );

  const flushSave = useCallback(() => {
    if (saveTimerRef.current !== null) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    const pending = pendingSaveRef.current || getCanvas();
    pendingSaveRef.current = null;
    saveVersionRef.current += 1;
    void persistCanvas(pending, saveVersionRef.current);
  }, [getCanvas, persistCanvas, saveTimerRef, pendingSaveRef, saveVersionRef]);

  const handleUndo = useCallback(() => {
    const next = undoCanvas();
    if (next) {
      setContextMenu(null);
      scheduleSave(next);
    }
  }, [scheduleSave, setContextMenu, undoCanvas]);

  const handleRedo = useCallback(() => {
    const next = redoCanvas();
    if (next) {
      setContextMenu(null);
      scheduleSave(next);
    }
  }, [redoCanvas, scheduleSave, setContextMenu]);

  // ── Zoom & View ──────────────────────────────────────────────

  const handleZoomIn = useCallback(() => {
    setViewport((current) => ({
      ...current,
      scale: Math.min(current.scale * 1.18, 3),
    }));
  }, [setViewport]);

  const handleZoomOut = useCallback(() => {
    setViewport((current) => ({
      ...current,
      scale: Math.max(current.scale / 1.18, 0.16),
    }));
  }, [setViewport]);

  const handleResetZoom = useCallback(() => {
    const rect = viewportRef.current?.getBoundingClientRect();
    if (!rect) {
      setViewport((current) => ({ ...current, scale: 1 }));
      return;
    }

    setViewport((current) => {
      const centerX = (rect.width / 2 - current.x) / current.scale;
      const centerY = (rect.height / 2 - current.y) / current.scale;
      return {
        x: rect.width / 2 - centerX,
        y: rect.height / 2 - centerY,
        scale: 1,
      };
    });
  }, [setViewport, viewportRef]);

  const handleFitView = useCallback(() => {
    const rect = viewportRef.current?.getBoundingClientRect();
    const current = getCanvas();
    if (!rect || current.nodes.length === 0) {
      setViewport({ x: 40, y: 40, scale: 1 });
      return;
    }

    const minX = Math.min(...current.nodes.map((node) => node.x));
    const minY = Math.min(...current.nodes.map((node) => node.y));
    const maxX = Math.max(
      ...current.nodes.map((node) => node.x + node.width),
    );
    const maxY = Math.max(
      ...current.nodes.map((node) => node.y + node.height),
    );
    const padding = 120;
    const width = Math.max(1, maxX - minX + padding * 2);
    const height = Math.max(1, maxY - minY + padding * 2);
    const nextScale = Math.min(
      Math.max(Math.min(rect.width / width, rect.height / height), 0.16),
      1.35,
    );
    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;

    setViewport({
      x: rect.width / 2 - centerX * nextScale,
      y: rect.height / 2 - centerY * nextScale,
      scale: nextScale,
    });
  }, [getCanvas, setViewport, viewportRef]);

  // ── Node Open Handlers ───────────────────────────────────────

  const handleOpenLinkNode = useCallback((url: string) => {
    const normalizedUrl = normalizeCanvasLinkUrl(url);
    if (!normalizedUrl) {
      return;
    }
    window.open(normalizedUrl, "_blank", "noopener,noreferrer");
  }, []);

  const handleOpenFileNode = useCallback(
    (
      fileName: string,
      options?: { scope?: WorkspaceMarkdownLinkScope; suffix?: string },
    ) => {
      const normalizedFileName = fileName.trim();
      if (!normalizedFileName) {
        return;
      }
      const scope = options?.scope ?? "workspace";
      if (onOpenPreviewFile) {
        const meta = options?.suffix ? { subpath: options.suffix } : undefined;
        const previewFile =
          scope === "global"
            ? createGlobalWorkspacePreviewFile(
                { name: normalizedFileName, meta },
                workspaceId,
                token,
              )
            : createWorkspacePreviewFile(
                { name: normalizedFileName, meta },
                sessionId,
                token,
              );
        onOpenPreviewFile(previewFile);
        return;
      }
      onOpenWorkspaceFile?.(normalizedFileName);
    },
    [onOpenPreviewFile, onOpenWorkspaceFile, sessionId, token, workspaceId],
  );

  // ── Node Creation ────────────────────────────────────────────

  const createNodeAtCenter = useCallback(
    (node: CanvasNodeDraft) => {
      const rect = viewportRef.current?.getBoundingClientRect();
      const centerX = rect ? rect.width / 2 : 240;
      const centerY = rect ? rect.height / 2 : 180;
      const current = getCanvas();
      const baseX =
        (centerX - viewport.x) / viewport.scale - node.width / 2;
      const baseY =
        (centerY - viewport.y) / viewport.scale - node.height / 2;
      const gap = 36;
      const candidates = Array.from({ length: 49 }, (_, index) => {
        const row = Math.floor(index / 7) - 3;
        const column = (index % 7) - 3;
        return { row, column };
      }).sort((left, right) => {
        const leftDistance = Math.abs(left.row) + Math.abs(left.column);
        const rightDistance = Math.abs(right.row) + Math.abs(right.column);
        return (
          leftDistance - rightDistance ||
          Math.abs(left.row) - Math.abs(right.row) ||
          Math.abs(left.column) - Math.abs(right.column)
        );
      });
      let x = baseX;
      let y = baseY;

      for (const { row, column } of candidates) {
        const candidateX = baseX + column * (node.width + gap);
        const candidateY = baseY + row * (node.height + gap);
        const hasOverlap = current.nodes.some((existingNode) => {
          const paddedLeft = existingNode.x - gap;
          const paddedTop = existingNode.y - gap;
          const paddedRight = existingNode.x + existingNode.width + gap;
          const paddedBottom =
            existingNode.y + existingNode.height + gap;
          return (
            candidateX < paddedRight &&
            candidateX + node.width > paddedLeft &&
            candidateY < paddedBottom &&
            candidateY + node.height > paddedTop
          );
        });
        if (!hasOverlap) {
          x = candidateX;
          y = candidateY;
          break;
        }
      }

      const nodeId = createCanvasId("node");
      recordHistorySnapshot();
      const next = addNode({
        ...node,
        id: nodeId,
        x,
        y,
      });
      setSelectedNodeIds([nodeId]);
      setSelectedEdgeId(null);
      scheduleSave(next);
      return next;
    },
    [
      addNode,
      getCanvas,
      recordHistorySnapshot,
      scheduleSave,
      setSelectedEdgeId,
      setSelectedNodeIds,
      viewport,
      viewportRef,
    ],
  );

  const handleAddTextNode = useCallback(() => {
    createNodeAtCenter({
      type: "text",
      width: 280,
      height: 140,
      text: "新节点",
    });
  }, [createNodeAtCenter]);

  const handleAddLinkNode = useCallback(() => {
    createNodeAtCenter({
      type: "link",
      width: 300,
      height: 132,
      url: "https://",
    });
  }, [createNodeAtCenter]);

  const handleAddGroupNode = useCallback(() => {
    createNodeAtCenter({
      type: "group",
      width: 520,
      height: 320,
      label: "分组",
      color: "5",
    });
  }, [createNodeAtCenter]);

  const handleAddWorkspaceFileNode = useCallback(
    (fileName: string, mode: FilePickerMode) => {
      const size = getFileNodeSize(fileName);
      createNodeAtCenter({
        type: "file",
        width: mode === "image" ? size.width : 300,
        height: mode === "image" ? size.height : 154,
        file: fileName,
      });
      setFilePickerMode(null);
      setFilePickerQuery("");
    },
    [createNodeAtCenter, setFilePickerMode, setFilePickerQuery],
  );

  // ── File URL / Candidates ────────────────────────────────────

  const getFileUrl = useCallback(
    (fileName: string) => {
      if (!sessionId) {
        return "";
      }
      return resolveWorkspaceFileUrl(
        `/workspace/${fileName}`,
        sessionId,
        token,
        {
          disposition: "inline",
          preferDirectBackend: true,
        },
      );
    },
    [sessionId, token],
  );

  const fileCandidates = useMemo(() => {
    const query = filePickerQuery.trim().toLowerCase();
    return workspaceFiles
      .filter((file) => !isWorkspaceFolderMarkerFile(file.name))
      .filter((file) => file.name !== filePath)
      .filter((file) =>
        filePickerMode === "image"
          ? isImageFile(file.name)
          : !isImageFile(file.name),
      )
      .filter((file) =>
        query ? file.name.toLowerCase().includes(query) : true,
      )
      .slice(0, 80);
  }, [filePath, filePickerMode, filePickerQuery, workspaceFiles]);

  // ── Color & Delete ───────────────────────────────────────────

  const handleApplyColor = useCallback(
    (color: string) => {
      const nextColor = color || undefined;
      if (selectedNodeIds.length > 0) {
        recordHistorySnapshot();
        const patches = Object.fromEntries(
          selectedNodeIds.map((nodeId) => [
            nodeId,
            { color: nextColor },
          ]),
        );
        const next = updateNodes(patches);
        scheduleSave(next);
        return;
      }
      if (selectedEdgeId) {
        recordHistorySnapshot();
        const next = updateEdge(selectedEdgeId, {
          color: nextColor,
        });
        scheduleSave(next);
      }
    },
    [
      recordHistorySnapshot,
      scheduleSave,
      selectedEdgeId,
      selectedNodeIds,
      updateEdge,
      updateNodes,
    ],
  );

  const handleBeginSelectedNodeChange = useCallback(
    (nodeId: string) => {
      if (getCanvas().nodes.some((node) => node.id === nodeId)) {
        recordHistorySnapshot();
      }
    },
    [getCanvas, recordHistorySnapshot],
  );

  const handleBeginSelectedEdgeChange = useCallback(
    (edgeId: string) => {
      if (getCanvas().edges.some((edge) => edge.id === edgeId)) {
        recordHistorySnapshot();
      }
    },
    [getCanvas, recordHistorySnapshot],
  );

  const handleUpdateSelectedNode = useCallback(
    (
      nodeId: string,
      patch: Partial<CanvasNode>,
      options?: { recordHistory?: boolean },
    ) => {
      if (options?.recordHistory !== false) {
        recordHistorySnapshot();
      }
      const next = updateNode(nodeId, patch);
      scheduleSave(next);
    },
    [recordHistorySnapshot, scheduleSave, updateNode],
  );

  const handleUpdateSelectedEdge = useCallback(
    (
      edgeId: string,
      patch: Partial<CanvasEdge>,
      options?: { recordHistory?: boolean },
    ) => {
      if (options?.recordHistory !== false) {
        recordHistorySnapshot();
      }
      const next = updateEdge(edgeId, patch);
      scheduleSave(next);
    },
    [recordHistorySnapshot, scheduleSave, updateEdge],
  );

  const handleDeleteSelected = useCallback(() => {
    if (editingNodeId || editingEdgeId) {
      return;
    }

    if (selectedNodeIds.length > 0) {
      recordHistorySnapshot();
      const next = removeNodes(selectedNodeIds);
      setSelectedNodeIds([]);
      setSelectedEdgeId(null);
      scheduleSave(next);
      return;
    }

    if (selectedEdgeId) {
      recordHistorySnapshot();
      const next = removeEdge(selectedEdgeId);
      setSelectedEdgeId(null);
      scheduleSave(next);
    }
  }, [
    editingNodeId,
    editingEdgeId,
    removeEdge,
    removeNodes,
    recordHistorySnapshot,
    scheduleSave,
    selectedEdgeId,
    selectedNodeIds,
    setSelectedEdgeId,
    setSelectedNodeIds,
  ]);

  // ── Node Editing ─────────────────────────────────────────────

  const handleNodeDoubleClick = useCallback(
    (nodeId: string) => {
      const node = getCanvas().nodes.find((item) => item.id === nodeId);
      if (!node) {
        return;
      }
      setSelectedNodeIds([nodeId]);
      setSelectedEdgeId(null);
      setEditingNodeId(nodeId);
      setEditValue(getEditableNodeText(node));
    },
    [
      getCanvas,
      setSelectedEdgeId,
      setSelectedNodeIds,
      setEditingNodeId,
      setEditValue,
    ],
  );

  const handleEditCommit = useCallback(() => {
    if (!editingNodeId) {
      return;
    }

    const node = getCanvas().nodes.find(
      (item) => item.id === editingNodeId,
    );
    if (!node) {
      setEditingNodeId(null);
      setEditValue("");
      return;
    }

    const patch = buildNodeTextPatch(node, editValue);
    const changed = Object.entries(patch).some(([key, value]) => {
      return node[key as keyof CanvasNode] !== value;
    });
    const next = changed
      ? (recordHistorySnapshot(), updateNode(editingNodeId, patch))
      : getCanvas();
    setEditingNodeId(null);
    setEditValue("");
    if (changed) {
      scheduleSave(next);
    }
  }, [
    editValue,
    editingNodeId,
    getCanvas,
    recordHistorySnapshot,
    scheduleSave,
    setEditingNodeId,
    setEditValue,
    updateNode,
  ]);

  const handleEditCancel = useCallback(() => {
    setEditingNodeId(null);
    setEditValue("");
  }, [setEditingNodeId, setEditValue]);

  const openEdgeLabelEditor = useCallback(
    (edgeId: string) => {
      const edge = getCanvas().edges.find((item) => item.id === edgeId);
      if (!edge) {
        return;
      }
      setSelectedNodeIds([]);
      setSelectedEdgeId(edgeId);
      setEditingEdgeId(edgeId);
      setEdgeEditValue(edge.label || "");
      setContextMenu(null);
    },
    [
      getCanvas,
      setSelectedEdgeId,
      setSelectedNodeIds,
      setEditingEdgeId,
      setEdgeEditValue,
      setContextMenu,
    ],
  );

  const handleEdgeEditCommit = useCallback(() => {
    if (!editingEdgeId) {
      return;
    }
    const label = edgeEditValue.trim();
    const edge = getCanvas().edges.find((item) => item.id === editingEdgeId);
    const nextLabel = label || undefined;
    const changed = edge?.label !== nextLabel;
    const next = changed
      ? (recordHistorySnapshot(),
        updateEdge(editingEdgeId, {
          label: nextLabel,
        }))
      : getCanvas();
    setEditingEdgeId(null);
    setEdgeEditValue("");
    if (changed) {
      scheduleSave(next);
    }
  }, [
    edgeEditValue,
    editingEdgeId,
    getCanvas,
    recordHistorySnapshot,
    scheduleSave,
    setEditingEdgeId,
    setEdgeEditValue,
    updateEdge,
  ]);

  const handleEdgeEditCancel = useCallback(() => {
    setEditingEdgeId(null);
    setEdgeEditValue("");
  }, [setEditingEdgeId, setEdgeEditValue]);

  const handleEdgeDoubleClick = useCallback(
    (edgeId: string) => {
      openEdgeLabelEditor(edgeId);
    },
    [openEdgeLabelEditor],
  );

  // ── Context Menu Handlers ────────────────────────────────────

  const handleNodeContextMenu = useCallback(
    (event: React.MouseEvent, nodeId: string) => {
      event.preventDefault();
      event.stopPropagation();
      if (!selectedNodeIds.includes(nodeId)) {
        setSelectedNodeIds([nodeId]);
        setSelectedEdgeId(null);
      }
      const position = getContextMenuPosition(
        event.clientX,
        event.clientY,
      );
      setContextMenu({ kind: "node", nodeId, ...position });
    },
    [
      selectedNodeIds,
      setSelectedEdgeId,
      setSelectedNodeIds,
      setContextMenu,
    ],
  );

  const handleEdgeContextMenu = useCallback(
    (event: React.MouseEvent, edgeId: string) => {
      event.preventDefault();
      event.stopPropagation();
      setSelectedNodeIds([]);
      setSelectedEdgeId(edgeId);
      const position = getContextMenuPosition(
        event.clientX,
        event.clientY,
      );
      setContextMenu({ kind: "edge", edgeId, ...position });
    },
    [setSelectedEdgeId, setSelectedNodeIds, setContextMenu],
  );

  const handleDuplicateSelectedNodes = useCallback(() => {
    const current = getCanvas();
    const nodesToCopy = current.nodes.filter((node) =>
      selectedNodeIds.includes(node.id),
    );
    if (nodesToCopy.length === 0) {
      return;
    }
    const copiedNodes = nodesToCopy.map((node) => ({
      ...node,
      id: createCanvasId("node"),
      x: node.x + 40,
      y: node.y + 40,
    }));
    const copiedIdByOriginalId = new Map(
      nodesToCopy.map((node, index) => [node.id, copiedNodes[index].id]),
    );
    const copiedEdges = current.edges
      .filter(
        (edge) =>
          copiedIdByOriginalId.has(edge.fromNode) &&
          copiedIdByOriginalId.has(edge.toNode),
      )
      .map((edge) => ({
        ...edge,
        id: createCanvasId("edge"),
        fromNode:
          copiedIdByOriginalId.get(edge.fromNode) || edge.fromNode,
        toNode:
          copiedIdByOriginalId.get(edge.toNode) || edge.toNode,
      }));
    const next: CanvasDocument = {
      ...current,
      nodes: [...current.nodes, ...copiedNodes],
      edges: [...current.edges, ...copiedEdges],
    };
    recordHistorySnapshot();
    setCanvasDocument(next);
    setSelectedNodeIds(copiedNodes.map((node) => node.id));
    setSelectedEdgeId(null);
    setContextMenu(null);
    scheduleSave(next);
  }, [
    getCanvas,
    recordHistorySnapshot,
    scheduleSave,
    setCanvasDocument,
    selectedNodeIds,
    setSelectedEdgeId,
    setSelectedNodeIds,
    setContextMenu,
  ]);

  const handleReorderSelectedNodes = useCallback(
    (direction: "front" | "back") => {
      const current = getCanvas();
      const selected = new Set(selectedNodeIds);
      if (selected.size === 0) {
        return;
      }
      const selectedList = current.nodes.filter((node) =>
        selected.has(node.id),
      );
      const remainingList = current.nodes.filter(
        (node) => !selected.has(node.id),
      );
      const next: CanvasDocument = {
        ...current,
        nodes:
          direction === "front"
            ? [...remainingList, ...selectedList]
            : [...selectedList, ...remainingList],
      };
      recordHistorySnapshot();
      setCanvasDocument(next);
      setContextMenu(null);
      scheduleSave(next);
    },
    [
      getCanvas,
      recordHistorySnapshot,
      scheduleSave,
      selectedNodeIds,
      setContextMenu,
      setCanvasDocument,
    ],
  );

  const handleToggleEdgeArrow = useCallback(
    (edgeId: string) => {
      const edge = getCanvas().edges.find((item) => item.id === edgeId);
      if (!edge) {
        return;
      }
      recordHistorySnapshot();
      const next = updateEdge(edgeId, {
        toEnd: edge.toEnd === "none" ? "arrow" : "none",
      });
      setContextMenu(null);
      scheduleSave(next);
    },
    [getCanvas, recordHistorySnapshot, scheduleSave, updateEdge, setContextMenu],
  );

  const handleAutoLayout = useCallback(
    (mode: "horizontal" | "vertical" | "radial") => {
      const current = getCanvas();
      const selected = new Set(selectedNodeIds);
      const layoutNodes =
        selected.size > 0
          ? current.nodes.filter((node) => selected.has(node.id))
          : current.nodes.filter((node) => node.type !== "group");
      if (layoutNodes.length < 2) {
        return;
      }

      const sortedNodes = [...layoutNodes].sort((left, right) => {
        return left.y - right.y || left.x - right.x;
      });
      const startX = Math.min(...sortedNodes.map((node) => node.x));
      const startY = Math.min(...sortedNodes.map((node) => node.y));
      const centerX =
        sortedNodes.reduce((total, node) => total + node.x + node.width / 2, 0) /
        sortedNodes.length;
      const centerY =
        sortedNodes.reduce((total, node) => total + node.y + node.height / 2, 0) /
        sortedNodes.length;
      const maxWidth = Math.max(...sortedNodes.map((node) => node.width));
      const maxHeight = Math.max(...sortedNodes.map((node) => node.height));
      const horizontalGap = Math.max(48, Math.round(maxWidth * 0.22));
      const verticalGap = Math.max(40, Math.round(maxHeight * 0.28));
      const radius = Math.max(
        220,
        Math.round(sortedNodes.length * Math.max(maxWidth, maxHeight) * 0.18),
      );

      const patches: Record<string, Partial<CanvasNode>> = {};
      sortedNodes.forEach((node, index) => {
        if (mode === "horizontal") {
          patches[node.id] = {
            x: startX + index * (maxWidth + horizontalGap),
            y: startY,
          };
          return;
        }
        if (mode === "vertical") {
          patches[node.id] = {
            x: startX,
            y: startY + index * (maxHeight + verticalGap),
          };
          return;
        }

        const angle = -Math.PI / 2 + (Math.PI * 2 * index) / sortedNodes.length;
        patches[node.id] = {
          x: centerX + Math.cos(angle) * radius - node.width / 2,
          y: centerY + Math.sin(angle) * radius - node.height / 2,
        };
      });

      recordHistorySnapshot();
      const next = updateNodes(patches);
      setContextMenu(null);
      scheduleSave(next);
      handleFitView();
    },
    [
      getCanvas,
      handleFitView,
      recordHistorySnapshot,
      scheduleSave,
      selectedNodeIds,
      setContextMenu,
      updateNodes,
    ],
  );

  // ── Drop & Paste ─────────────────────────────────────────────

  const handleDropWorkspaceFile = useCallback(
    (event: React.DragEvent) => {
      const draggedWorkspaceFile = event.dataTransfer.getData(
        WORKSPACE_FILE_DRAG_MIME,
      );
      const plainTextFile = event.dataTransfer.getData("text/plain");
      const fileName =
        draggedWorkspaceFile ||
        (workspaceFiles.some((file) => file.name === plainTextFile)
          ? plainTextFile
          : "");
      if (!fileName) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();

      const point = clientToCanvas(event.clientX, event.clientY);
      const size = getFileNodeSize(fileName);
      const nodeId = createCanvasId("node");
      recordHistorySnapshot();
      const next = addNode({
        id: nodeId,
        type: "file",
        x: point.x - size.width / 2,
        y: point.y - size.height / 2,
        width: size.width,
        height: size.height,
        file: fileName,
      });
      setSelectedNodeIds([nodeId]);
      setSelectedEdgeId(null);
      scheduleSave(next);
    },
    [
      addNode,
      clientToCanvas,
      recordHistorySnapshot,
      scheduleSave,
      setSelectedEdgeId,
      setSelectedNodeIds,
      workspaceFiles,
    ],
  );

  const handleCanvasDragOver = useCallback(
    (event: React.DragEvent) => {
      if (
        Array.from(event.dataTransfer.types).includes(
          WORKSPACE_FILE_DRAG_MIME,
        )
      ) {
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
      }
    },
    [],
  );

  const getPasteInsertionPoint = useCallback(() => {
    const rect = viewportRef.current?.getBoundingClientRect();
    const pointer = lastPointerRef.current;
    if (
      rect &&
      pointer &&
      pointer.clientX >= rect.left &&
      pointer.clientX <= rect.right &&
      pointer.clientY >= rect.top &&
      pointer.clientY <= rect.bottom
    ) {
      return clientToCanvas(pointer.clientX, pointer.clientY);
    }

    if (rect) {
      return clientToCanvas(
        rect.left + rect.width / 2,
        rect.top + rect.height / 2,
      );
    }

    return { x: 0, y: 0 };
  }, [clientToCanvas, viewportRef, lastPointerRef]);

  const handlePaste = useCallback(
    (event: React.ClipboardEvent<HTMLDivElement>) => {
      if (
        editingNodeId ||
        editingEdgeId ||
        filePickerMode ||
        isKeyboardEditingTarget(event.target) ||
        clipboardHasFiles(event.clipboardData)
      ) {
        return;
      }

      const pastedText = event.clipboardData
        .getData("text/plain")
        .replace(/\r\n/g, "\n")
        .trimEnd();

      if (!pastedText.trim()) {
        return;
      }

      event.preventDefault();
      event.stopPropagation();

      const point = getPasteInsertionPoint();
      const size = getPastedTextNodeSize(pastedText);
      const nodeId = createCanvasId("node");
      recordHistorySnapshot();
      const next = addNode({
        id: nodeId,
        type: "text",
        x: point.x - size.width / 2,
        y: point.y - size.height / 2,
        width: size.width,
        height: size.height,
        text: pastedText,
      });

      setSelectedNodeIds([nodeId]);
      setSelectedEdgeId(null);
      setContextMenu(null);
      scheduleSave(next);
    },
    [
      addNode,
      editingEdgeId,
      editingNodeId,
      filePickerMode,
      getPasteInsertionPoint,
      recordHistorySnapshot,
      scheduleSave,
      setSelectedEdgeId,
      setSelectedNodeIds,
      setContextMenu,
    ],
  );

  const handleEditorPointerDownCapture = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      lastPointerRef.current = {
        clientX: event.clientX,
        clientY: event.clientY,
      };

      if (
        !isKeyboardEditingTarget(event.target) &&
        !isCanvasControlTarget(event.target)
      ) {
        editorRef.current?.focus({ preventScroll: true });
      }
    },
    [editorRef, lastPointerRef],
  );

  const handleEditorPointerMoveCapture = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      lastPointerRef.current = {
        clientX: event.clientX,
        clientY: event.clientY,
      };
    },
    [lastPointerRef],
  );

  // ── Keyboard ─────────────────────────────────────────────────

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent | KeyboardEvent) => {
      if (event.key === "Delete" || event.key === "Backspace") {
        if (
          !editingNodeId &&
          !editingEdgeId &&
          (selectedNodeIds.length > 0 || selectedEdgeId)
        ) {
          event.preventDefault();
          handleDeleteSelected();
        }
      }
      if (
        (event.metaKey || event.ctrlKey) &&
        !editingNodeId &&
        !editingEdgeId &&
        !isKeyboardEditingTarget(event.target)
      ) {
        const key = event.key.toLowerCase();
        if (key === "z" && !event.shiftKey) {
          event.preventDefault();
          handleUndo();
        } else if (key === "y" || (key === "z" && event.shiftKey)) {
          event.preventDefault();
          handleRedo();
        }
      }
    },
    [
      editingEdgeId,
      editingNodeId,
      handleRedo,
      handleDeleteSelected,
      handleUndo,
      selectedEdgeId,
      selectedNodeIds,
    ],
  );

  // ── Computed values ──────────────────────────────────────────

  const selectedNode = selectedNodeIds[0]
    ? canvas.nodes.find((node) => node.id === selectedNodeIds[0]) ?? null
    : null;
  const selectedEdge = selectedEdgeId
    ? canvas.edges.find((edge) => edge.id === selectedEdgeId) ?? null
    : null;
  const selectedColor =
    selectedNode?.color ?? selectedEdge?.color ?? "";

  const contextNode =
    contextMenu?.kind === "node"
      ? canvas.nodes.find((node) => node.id === contextMenu.nodeId) ??
        null
      : null;
  const contextEdge =
    contextMenu?.kind === "edge"
      ? canvas.edges.find(
          (edge) => edge.id === contextMenu.edgeId,
        ) ?? null
      : null;
  const contextMenuTitle =
    contextMenu?.kind === "node"
      ? selectedNodeIds.length > 1
        ? `${selectedNodeIds.length} 个节点`
        : contextNode
          ? getWorkspaceFileLabel(
              getEditableNodeText(contextNode),
            ) || "节点"
          : "节点"
      : contextEdge?.label || "连线";

  const canDelete = Boolean(
    selectedNodeIds.length > 0 || selectedEdgeId,
  );

  return {
    // Persistence
    scheduleSave,
    flushSave,
    handleUndo,
    handleRedo,

    // Zoom & View
    handleZoomIn,
    handleZoomOut,
    handleResetZoom,
    handleFitView,
    handleAutoLayout,

    // Node Open
    handleOpenLinkNode,
    handleOpenFileNode,

    // Node Creation
    createNodeAtCenter,
    handleAddTextNode,
    handleAddLinkNode,
    handleAddGroupNode,
    handleAddWorkspaceFileNode,

    // File
    getFileUrl,
    fileCandidates,

    // Selection derived
    selectedNode,
    selectedEdge,
    selectedColor,

    // Color & Delete
    handleApplyColor,
    handleBeginSelectedNodeChange,
    handleBeginSelectedEdgeChange,
    handleUpdateSelectedNode,
    handleUpdateSelectedEdge,
    handleDeleteSelected,
    canDelete,

    // Editing
    handleNodeDoubleClick,
    handleEditCommit,
    handleEditCancel,
    openEdgeLabelEditor,
    handleEdgeEditCommit,
    handleEdgeEditCancel,
    handleEdgeDoubleClick,

    // Context Menu
    handleNodeContextMenu,
    handleEdgeContextMenu,
    handleDuplicateSelectedNodes,
    handleReorderSelectedNodes,
    handleToggleEdgeArrow,

    // Drop & Paste
    handleDropWorkspaceFile,
    handleCanvasDragOver,
    handlePaste,
    handleEditorPointerDownCapture,
    handleEditorPointerMoveCapture,

    // Keyboard
    handleKeyDown,

    // Computed
    contextNode,
    contextEdge,
    contextMenuTitle,
  };
}
