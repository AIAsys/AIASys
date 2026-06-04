import React, { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { parseCanvasContent, stringifyCanvasDocument } from "./canvasUtils";
import { useCanvasInteraction } from "./useCanvasInteraction";
import { useCanvasState } from "./useCanvasState";
import { useCanvasHandlers } from "./useCanvasHandlers";
import { CanvasViewport } from "./CanvasViewport";
import { CanvasToolbar } from "./CanvasToolbar";
import { CanvasContextMenuComponent } from "./CanvasContextMenu";
import { EdgeLabelDialog, FilePickerDialog } from "./CanvasDialogs";
import { CanvasPropertiesPanel } from "./CanvasPropertiesPanel";
import type {
  CanvasContextMenu,
  FilePickerMode,
  SaveState,
} from "./useCanvasHandlers";
import type { PreviewFile } from "@/components/layout/WorkspaceSidebar/preview";
import type { WorkspaceFile } from "@/types/task";

interface CanvasEditorProps {
  initialContent?: string;
  workspaceId?: string;
  filePath?: string;
  sessionId?: string | null;
  token?: string;
  workspaceFiles?: WorkspaceFile[];
  onSave?: (content: string) => void;
  onPersistContent?: (content: string) => Promise<void>;
  onOpenWorkspaceFile?: (fileName: string) => void;
  onOpenPreviewFile?: (file: PreviewFile) => void;
  onRequestImmersivePreview?: () => void;
}

export const CanvasEditor: React.FC<CanvasEditorProps> = ({
  initialContent,
  workspaceId,
  filePath,
  sessionId,
  token,
  workspaceFiles = [],
  onSave,
  onPersistContent,
  onOpenWorkspaceFile,
  onOpenPreviewFile,
  onRequestImmersivePreview,
}) => {
  const parsedInitial = useRef(parseCanvasContent(initialContent));
  const editorRef = useRef<HTMLDivElement | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const saveTimerRef = useRef<number | null>(null);
  const pendingSaveRef = useRef<
    ReturnType<typeof parseCanvasContent>["canvas"] | null
  >(null);
  const saveVersionRef = useRef(0);
  const lastPointerRef = useRef<{
    clientX: number;
    clientY: number;
  } | null>(null);

  const [parseError, setParseError] = useState<string | null>(
    parsedInitial.current.error,
  );
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [editingNodeId, setEditingNodeId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [editingEdgeId, setEditingEdgeId] = useState<string | null>(null);
  const [edgeEditValue, setEdgeEditValue] = useState("");
  const [contextMenu, setContextMenu] = useState<CanvasContextMenu | null>(
    null,
  );
  const [filePickerMode, setFilePickerMode] = useState<FilePickerMode | null>(
    null,
  );
  const [filePickerQuery, setFilePickerQuery] = useState("");
  const [isSpacePanning, setIsSpacePanning] = useState(false);
  const hasCanvasFocusRef = useRef(false);

  const {
    canvas,
    replaceCanvas,
    setCanvasDocument,
    recordHistorySnapshot,
    undoCanvas,
    redoCanvas,
    canUndo,
    canRedo,
    getCanvas,
    viewport,
    setViewport,
    selectedNodeIds,
    setSelectedNodeIds,
    selectedEdgeId,
    setSelectedEdgeId,
    isDraggingNode,
    setIsDraggingNode,
    isPanning,
    setIsPanning,
    addNode,
    updateNode,
    updateNodes,
    removeNodes,
    addEdge,
    updateEdge,
    removeEdge,
  } = useCanvasState(parsedInitial.current.canvas);

  // clientToCanvas must be available before useCanvasHandlers (which uses it),
  // and also before useCanvasInteraction (which also constructs its own internally).
  const clientToCanvas = useCallback(
    (clientX: number, clientY: number) => {
      const rect = viewportRef.current?.getBoundingClientRect();
      if (!rect) {
        return { x: 0, y: 0 };
      }
      return {
        x: (clientX - rect.left - viewport.x) / viewport.scale,
        y: (clientY - rect.top - viewport.y) / viewport.scale,
      };
    },
    [viewport, viewportRef],
  );

  const handlers = useCanvasHandlers({
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
    addEdge,
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
  });

  const {
    connectionPreview,
    selectionBox,
    alignmentGuides,
    handleNodePointerDown,
    handleResizeHandlePointerDown,
    handleConnectionHandlePointerDown,
    handleEdgePointerDown,
    handleBackgroundPointerDown,
    handlePointerMove,
    handlePointerUp,
    handleWheel,
    handleNativeWheel,
    handleBackgroundDoubleClick,
  } = useCanvasInteraction({
    canvas,
    selectedNodeIds,
    viewport,
    viewportRef,
    setViewport,
    setSelectedNodeId: (id) => setSelectedNodeIds(id ? [id] : []),
    setSelectedNodeIds,
    setSelectedEdgeId,
    setIsDraggingNode,
    setIsPanning,
    isSpacePanning,
    getCanvas,
    recordHistorySnapshot,
    updateNode,
    updateNodes,
    addNode,
    addEdge,
    onSave: handlers.scheduleSave,
  });
  const handleCanvasKeyDown = handlers.handleKeyDown;

  // Sync initialContent changes
  useEffect(() => {
    const parsed = parseCanvasContent(initialContent);
    if (
      !parsed.error &&
      stringifyCanvasDocument(parsed.canvas) === stringifyCanvasDocument(getCanvas())
    ) {
      setParseError(null);
      return;
    }

    replaceCanvas(parsed.canvas);
    setParseError(parsed.error);
    setSaveError(null);
    setSaveState("idle");
    setEditingNodeId(null);
    setEditValue("");
    setEditingEdgeId(null);
    setEdgeEditValue("");
    setContextMenu(null);
  }, [getCanvas, initialContent, replaceCanvas]);

  // Cleanup save timer on unmount
  useEffect(() => {
    const timer = saveTimerRef.current;
    return () => {
      if (timer !== null) {
        window.clearTimeout(timer);
      }
    };
  }, []);

  // Space panning keyboard listeners
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (
        event.code !== "Space" ||
        editingNodeId ||
        editingEdgeId ||
        (event.target instanceof HTMLElement &&
          (event.target.tagName.toLowerCase() === "input" ||
            event.target.tagName.toLowerCase() === "textarea" ||
            event.target.tagName.toLowerCase() === "select" ||
            event.target.isContentEditable))
      ) {
        return;
      }
      event.preventDefault();
      setIsSpacePanning(true);
    };
    const handleKeyUp = (event: KeyboardEvent) => {
      if (event.code === "Space") {
        setIsSpacePanning(false);
      }
    };
    const handleBlur = () => {
      setIsSpacePanning(false);
    };

    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("keyup", handleKeyUp);
    window.addEventListener("blur", handleBlur);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("keyup", handleKeyUp);
      window.removeEventListener("blur", handleBlur);
    };
  }, [editingEdgeId, editingNodeId]);

  useEffect(() => {
    const viewportElement = viewportRef.current;
    if (!viewportElement) {
      return;
    }

    viewportElement.addEventListener("wheel", handleNativeWheel, {
      passive: false,
    });
    return () => {
      viewportElement.removeEventListener("wheel", handleNativeWheel);
    };
  }, [handleNativeWheel]);

  useEffect(() => {
    const handleDocumentKeyDown = (event: KeyboardEvent) => {
      if (
        !hasCanvasFocusRef.current ||
        !editorRef.current ||
        editorRef.current.contains(event.target as Node | null)
      ) {
        return;
      }
      handleCanvasKeyDown(event);
    };
    const releaseCanvasFocus = (event: Event) => {
      if (
        editorRef.current &&
        !editorRef.current.contains(event.target as Node | null)
      ) {
        hasCanvasFocusRef.current = false;
      }
    };

    document.addEventListener("keydown", handleDocumentKeyDown);
    document.addEventListener("pointerdown", releaseCanvasFocus, true);
    document.addEventListener("focusin", releaseCanvasFocus, true);
    return () => {
      document.removeEventListener("keydown", handleDocumentKeyDown);
      document.removeEventListener("pointerdown", releaseCanvasFocus, true);
      document.removeEventListener("focusin", releaseCanvasFocus, true);
    };
  }, [handleCanvasKeyDown]);

  const contextEdgeArrowShown = handlers.contextEdge?.toEnd !== "none";

  return (
    <div
      ref={editorRef}
      className={cn(
        "relative flex h-full w-full flex-col overflow-hidden rounded-lg border border-slate-200 bg-white",
        isPanning ? "cursor-grabbing" : isSpacePanning ? "cursor-grab" : "",
        isDraggingNode && "cursor-move",
      )}
      tabIndex={0}
      onKeyDown={handlers.handleKeyDown}
      onPaste={handlers.handlePaste}
      onPointerDownCapture={(event) => {
        hasCanvasFocusRef.current = true;
        handlers.handleEditorPointerDownCapture(event);
      }}
      onPointerMoveCapture={handlers.handleEditorPointerMoveCapture}
      onFocusCapture={() => {
        hasCanvasFocusRef.current = true;
      }}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerLeave={handlePointerUp}
    >
      <CanvasToolbar
        canDelete={handlers.canDelete}
        saveState={saveState}
        viewportScale={viewport.scale}
        selectedNode={handlers.selectedNode}
        selectedEdge={handlers.selectedEdge}
        selectedColor={String(handlers.selectedColor)}
        parseError={parseError}
        saveError={saveError}
        showConnectionPreview={Boolean(connectionPreview)}
        hasSaveTarget={Boolean(onSave || (workspaceId && filePath))}
        canUndo={canUndo}
        canRedo={canRedo}
        onAddTextNode={handlers.handleAddTextNode}
        onAddFileNode={() => setFilePickerMode("file")}
        onAddImageNode={() => setFilePickerMode("image")}
        onAddLinkNode={handlers.handleAddLinkNode}
        onAddGroupNode={handlers.handleAddGroupNode}
        onDeleteSelected={handlers.handleDeleteSelected}
        onSave={handlers.flushSave}
        onUndo={handlers.handleUndo}
        onRedo={handlers.handleRedo}
        onZoomIn={handlers.handleZoomIn}
        onZoomOut={handlers.handleZoomOut}
        onResetZoom={handlers.handleResetZoom}
        onFitView={handlers.handleFitView}
        onAutoLayout={handlers.handleAutoLayout}
        onRequestImmersivePreview={onRequestImmersivePreview}
        onApplyColor={handlers.handleApplyColor}
      />

      <CanvasViewport
        canvas={canvas}
        viewport={viewport}
        viewportRef={viewportRef}
        selectedNodeIds={selectedNodeIds}
        selectedEdgeId={selectedEdgeId}
        editingNodeId={editingNodeId}
        editValue={editValue}
        connectionPreview={connectionPreview}
        selectionBox={selectionBox}
        alignmentGuides={alignmentGuides}
        isPanning={isPanning}
        isSpacePanning={isSpacePanning}
        onEditValueChange={setEditValue}
        getFileUrl={handlers.getFileUrl}
        onOpenLink={handlers.handleOpenLinkNode}
        onOpenFile={handlers.handleOpenFileNode}
        onNodePointerDown={handleNodePointerDown}
        onConnectionHandlePointerDown={handleConnectionHandlePointerDown}
        onResizeHandlePointerDown={handleResizeHandlePointerDown}
        onNodeContextMenu={handlers.handleNodeContextMenu}
        onNodeDoubleClick={handlers.handleNodeDoubleClick}
        onEdgePointerDown={handleEdgePointerDown}
        onEdgeDoubleClick={handlers.handleEdgeDoubleClick}
        onEdgeContextMenu={handlers.handleEdgeContextMenu}
        onBackgroundPointerDown={handleBackgroundPointerDown}
        onBackgroundDoubleClick={handleBackgroundDoubleClick}
        onWheel={handleWheel}
        onDragOver={handlers.handleCanvasDragOver}
        onDrop={handlers.handleDropWorkspaceFile}
        onEditCommit={handlers.handleEditCommit}
        onEditCancel={handlers.handleEditCancel}
      />

      {contextMenu ? (
        <CanvasContextMenuComponent
          contextMenu={contextMenu}
          contextMenuTitle={handlers.contextMenuTitle}
          selectedNodeCount={selectedNodeIds.length}
          canEditNode={
            contextMenu.kind === "node" && Boolean(handlers.contextNode)
          }
          contextEdgeArrowShown={contextEdgeArrowShown}
          onEditNode={handlers.handleNodeDoubleClick}
          onDuplicateNodes={handlers.handleDuplicateSelectedNodes}
          onReorderNodes={handlers.handleReorderSelectedNodes}
          onApplyColor={handlers.handleApplyColor}
          onEditEdgeLabel={handlers.openEdgeLabelEditor}
          onToggleEdgeArrow={handlers.handleToggleEdgeArrow}
          onDelete={handlers.handleDeleteSelected}
          onClose={() => setContextMenu(null)}
        />
      ) : null}

      <CanvasPropertiesPanel
        selectedNode={handlers.selectedNode}
        selectedEdge={handlers.selectedEdge}
        selectedNodeCount={selectedNodeIds.length}
        onBeginNodeChange={handlers.handleBeginSelectedNodeChange}
        onBeginEdgeChange={handlers.handleBeginSelectedEdgeChange}
        onUpdateNode={handlers.handleUpdateSelectedNode}
        onUpdateEdge={handlers.handleUpdateSelectedEdge}
        onClose={() => {
          setSelectedNodeIds([]);
          setSelectedEdgeId(null);
        }}
      />

      <EdgeLabelDialog
        open={Boolean(editingEdgeId)}
        value={edgeEditValue}
        onValueChange={setEdgeEditValue}
        onCommit={handlers.handleEdgeEditCommit}
        onCancel={handlers.handleEdgeEditCancel}
      />

      <FilePickerDialog
        open={Boolean(filePickerMode)}
        mode={filePickerMode}
        query={filePickerQuery}
        candidates={handlers.fileCandidates}
        onQueryChange={setFilePickerQuery}
        onSelectFile={handlers.handleAddWorkspaceFileNode}
        onClose={() => {
          setFilePickerMode(null);
          setFilePickerQuery("");
        }}
      />
    </div>
  );
};
