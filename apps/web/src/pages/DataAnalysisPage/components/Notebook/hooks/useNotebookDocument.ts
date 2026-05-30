import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  clearNotebookOutputs,
  forkNotebookToSession,
  getNotebookDocument,
  getNotebookRuntimeState,
  getNotebookWorkbench,
  interruptNotebookRuntime,
  promoteNotebookToWorkspace,
  restartNotebookRuntime,
  runNotebook as runNotebookRequest,
  saveNotebookDocument,
  stopNotebookRuntime,
} from "@/lib/api/notebooks";
import type {
  NotebookCell,
  NotebookDocument,
  NotebookRuntimeStateResponse,
  NotebookWorkbenchSnapshot,
} from "@/types/notebook";

import {
  buildNotebookRuntimeState,
  cloneNotebookDocument,
  deleteNotebookCellInDocument,
  insertNotebookCellInDocument,
  isNotebookDocumentDirty,
  moveNotebookCellInDocument,
  toNotebookCellInput,
  updateNotebookCellInDocument,
} from "../notebookDataTransformers";
import type {
  NotebookRuntimeAction,
  UseNotebookDocumentOptions,
  UseNotebookDocumentResult,
} from "../types";

export function useNotebookDocument({
  file,
  sessionId,
  workspaceFiles,
  onRefreshWorkspace,
  onRefreshSessionStatus,
}: UseNotebookDocumentOptions): UseNotebookDocumentResult {
  const [savedDocument, setSavedDocument] = useState<NotebookDocument | null>(null);
  const [draftDocument, setDraftDocument] = useState<NotebookDocument | null>(null);
  const [workbenchSnapshot, setWorkbenchSnapshot] =
    useState<NotebookWorkbenchSnapshot | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [runningCellId, setRunningCellId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [externalUpdateDetected, setExternalUpdateDetected] = useState(false);
  const [runtimeState, setRuntimeState] = useState<NotebookRuntimeStateResponse | null>(null);
  const [runtimeAction, setRuntimeAction] = useState<NotebookRuntimeAction | null>(null);
  const [inspectorRefreshVersion, setInspectorRefreshVersion] = useState(0);

  const fileMtimeRef = useRef<string | null>(null);
  const notebookPath = file.name;

  const workspaceFileEntry = useMemo(
    () => workspaceFiles.find((item) => item.name === notebookPath) ?? null,
    [workspaceFiles, notebookPath],
  );

  const isDirty = useMemo(
    () => isNotebookDocumentDirty(savedDocument, draftDocument),
    [draftDocument, savedDocument],
  );

  function bumpInspectorRefreshVersion(): void {
    setInspectorRefreshVersion((prev) => prev + 1);
  }

  async function refreshWorkspace(): Promise<void> {
    if (!sessionId || !onRefreshWorkspace) {
      return;
    }
    await onRefreshWorkspace(sessionId);
  }

  function refreshSessionStatus(): void {
    onRefreshSessionStatus?.();
  }

  const replaceDocument = useCallback((document: NotebookDocument): void => {
    const cloned = cloneNotebookDocument(document);
    setWorkbenchSnapshot(null);
    setSavedDocument(cloned);
    setDraftDocument(cloneNotebookDocument(document));
    setRuntimeState(null);
    setExternalUpdateDetected(false);
    fileMtimeRef.current = workspaceFileEntry?.mtime ?? null;
  }, [workspaceFileEntry?.mtime]);

  const replaceWorkbenchSnapshot = useCallback((snapshot: NotebookWorkbenchSnapshot): void => {
    replaceDocument(snapshot.document);
    setWorkbenchSnapshot(snapshot);
    setRuntimeState(snapshot.runtime_state);
  }, [replaceDocument]);

  function patchNotebookState(
    nextState: NotebookDocument["state"],
    nextRuntimeState?: NotebookRuntimeStateResponse | null,
  ): void {
    setSavedDocument((prev) => (prev ? { ...prev, state: nextState } : prev));
    setDraftDocument((prev) => (prev ? { ...prev, state: nextState } : prev));
    if (nextRuntimeState !== undefined) {
      setRuntimeState(nextRuntimeState);
    }
  }

  const loadDocument = useCallback(async (silent = false): Promise<void> => {
    if (!sessionId) {
      setError("当前缺少会话上下文，无法打开 notebook。");
      setIsLoading(false);
      return;
    }

    if (!silent) {
      setIsLoading(true);
    }
    setError(null);

    try {
      const snapshot = await getNotebookWorkbench(sessionId, notebookPath, {
        includeVariables: true,
        recordsLimit: 30,
      });
      replaceWorkbenchSnapshot(snapshot);
    } catch (err) {
      try {
        const document = await getNotebookDocument(sessionId, notebookPath);
        setWorkbenchSnapshot(null);
        replaceDocument(document);
      } catch {
        setError(err instanceof Error ? err.message : "读取 notebook 失败");
      }
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, notebookPath, replaceDocument, replaceWorkbenchSnapshot]);

  useEffect(() => {
    void loadDocument();
  }, [loadDocument]);

  useEffect(() => {
    const nextMtime = workspaceFileEntry?.mtime ?? null;
    if (!nextMtime || nextMtime === fileMtimeRef.current || !savedDocument) {
      return;
    }
    if (isDirty || isRunning) {
      setExternalUpdateDetected(true);
      return;
    }
    void loadDocument(true);
  }, [workspaceFileEntry?.mtime, savedDocument, isDirty, isRunning, loadDocument]);

  const refreshRuntimeState = useCallback(async (): Promise<NotebookRuntimeStateResponse | null> => {
    if (!sessionId || !draftDocument) {
      return null;
    }
    const nextRuntimeState = await getNotebookRuntimeState(
      sessionId,
      draftDocument.notebook_path,
    );
    setRuntimeState(nextRuntimeState);
    return nextRuntimeState;
  }, [sessionId, draftDocument]);

  useEffect(() => {
    if (!draftDocument || !sessionId) {
      return;
    }
    void refreshRuntimeState();
  }, [draftDocument, sessionId, refreshRuntimeState]);

  async function saveDocument(): Promise<boolean> {
    if (!sessionId || !draftDocument) {
      return false;
    }
    setIsSaving(true);
    setError(null);
    try {
      const document = await saveNotebookDocument(sessionId, {
        notebook_path: draftDocument.notebook_path,
        metadata: draftDocument.metadata,
        cells: draftDocument.cells.map(toNotebookCellInput),
      });
      replaceDocument(document);
      await refreshWorkspace();
      bumpInspectorRefreshVersion();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存 notebook 失败");
      return false;
    } finally {
      setIsSaving(false);
    }
  }

  async function ensureSavedBeforeRun(): Promise<boolean> {
    if (!isDirty) {
      return true;
    }
    return saveDocument();
  }

  async function runNotebook(scope: "all" | "cell", cellId?: string): Promise<void> {
    if (!sessionId || !draftDocument) {
      return;
    }
    setIsRunning(true);
    setRunningCellId(scope === "cell" ? cellId ?? null : null);
    setError(null);
    try {
      const ready = await ensureSavedBeforeRun();
      if (!ready) {
        return;
      }
      const response = await runNotebookRequest(sessionId, {
        notebook_path: draftDocument.notebook_path,
        scope,
        cell_id: cellId,
      });
      replaceDocument(response.document);
      await refreshWorkspace();
      refreshSessionStatus();
      await loadDocument(true);
      bumpInspectorRefreshVersion();
    } catch (err) {
      setError(err instanceof Error ? err.message : "运行 notebook 失败");
    } finally {
      setIsRunning(false);
      setRunningCellId(null);
    }
  }

  async function restartAndRunAll(): Promise<void> {
    if (!sessionId || !draftDocument) {
      return;
    }
    setIsRunning(true);
    setError(null);
    try {
      const ready = await ensureSavedBeforeRun();
      if (!ready) {
        return;
      }
      const response = await runNotebookRequest(sessionId, {
        notebook_path: draftDocument.notebook_path,
        scope: "all",
        restart_runtime: true,
      });
      replaceDocument(response.document);
      await refreshWorkspace();
      refreshSessionStatus();
      await loadDocument(true);
      bumpInspectorRefreshVersion();
    } catch (err) {
      setError(err instanceof Error ? err.message : "重建环境并运行失败");
    } finally {
      setIsRunning(false);
    }
  }

  async function clearOutputs(cellId?: string): Promise<void> {
    if (!sessionId || !draftDocument) {
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      const ready = await ensureSavedBeforeRun();
      if (!ready) {
        return;
      }
      const document = await clearNotebookOutputs(sessionId, {
        notebook_path: draftDocument.notebook_path,
        cell_id: cellId,
        clear_all: !cellId,
      });
      replaceDocument(document);
      await refreshWorkspace();
      bumpInspectorRefreshVersion();
    } catch (err) {
      setError(err instanceof Error ? err.message : "清空输出失败");
    } finally {
      setIsSaving(false);
    }
  }

  async function forkToSession(): Promise<void> {
    if (!sessionId || !draftDocument) {
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      const document = await forkNotebookToSession(sessionId, draftDocument.notebook_path);
      replaceDocument(document);
      await refreshWorkspace();
      bumpInspectorRefreshVersion();
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建当前会话副本失败");
    } finally {
      setIsSaving(false);
    }
  }

  async function promoteToWorkspace(): Promise<void> {
    if (!sessionId || !draftDocument) {
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      const response = await promoteNotebookToWorkspace(sessionId, {
        notebook_path: draftDocument.notebook_path,
        overwrite: true,
      });
      replaceDocument(response.document);
      await refreshWorkspace();
      bumpInspectorRefreshVersion();
    } catch (err) {
      setError(err instanceof Error ? err.message : "发布 notebook 到工作区失败");
    } finally {
      setIsSaving(false);
    }
  }

  async function controlRuntime(action: NotebookRuntimeAction): Promise<void> {
    if (!sessionId || !draftDocument) {
      return;
    }
    setRuntimeAction(action);
    setError(null);
    try {
      const response =
        action === "interrupt"
          ? await interruptNotebookRuntime(sessionId, draftDocument.notebook_path)
          : action === "restart"
            ? await restartNotebookRuntime(sessionId, draftDocument.notebook_path)
            : await stopNotebookRuntime(sessionId, draftDocument.notebook_path);
      patchNotebookState(response.state, buildNotebookRuntimeState(response));
      refreshSessionStatus();
      bumpInspectorRefreshVersion();
    } catch (err) {
      setError(err instanceof Error ? err.message : "控制 notebook kernel 失败");
    } finally {
      setRuntimeAction(null);
    }
  }

  function updateCell(cellId: string, patch: Partial<NotebookCell>): void {
    setDraftDocument((prev) =>
      prev ? updateNotebookCellInDocument(prev, cellId, patch) : prev,
    );
  }

  function insertCell(
    referenceIndex: number,
    position: "before" | "after",
    type: NotebookCell["cell_type"],
  ): void {
    setDraftDocument((prev) =>
      prev ? insertNotebookCellInDocument(prev, referenceIndex, position, type) : prev,
    );
  }

  function moveCell(index: number, direction: "up" | "down"): void {
    setDraftDocument((prev) =>
      prev ? moveNotebookCellInDocument(prev, index, direction) : prev,
    );
  }

  function deleteCell(cellId: string): void {
    setDraftDocument((prev) =>
      prev ? deleteNotebookCellInDocument(prev, cellId) : prev,
    );
  }

  return {
    draftDocument,
    workbenchSnapshot,
    isLoading,
    isSaving,
    isRunning,
    runningCellId,
    error,
    externalUpdateDetected,
    isDirty,
    runtimeState,
    runtimeAction,
    inspectorRefreshVersion,
    loadDocument,
    refreshRuntimeState,
    saveDocument,
    runNotebook,
    restartAndRunAll,
    clearOutputs,
    forkToSession,
    promoteToWorkspace,
    controlRuntime,
    updateCell,
    insertCell,
    moveCell,
    deleteCell,
  };
}
