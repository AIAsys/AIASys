import { useCallback, useEffect, useRef, useState } from "react";
import { API_ENDPOINTS, getCurrentUserId } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";
import { isGenericallyEditable } from "@/utils/workspaceFileEditing";

interface FileContentResponse {
  content: string;
  editable?: boolean;
  edit_lock_reason?: string | null;
}

export interface EditableFileState {
  content: string;
  originalContent: string;
  isLoading: boolean;
  isSaving: boolean;
  error: string | null;
  editable: boolean;
  editLockReason: string | null;
  loaded: boolean;
}

export interface UseEditableFileOptions {
  fileName: string;
  sessionId?: string | null;
  workspaceId?: string | null;
  /** 外部加载回调，如果不提供则直接调 API */
  loadContent?: (fileName: string) => Promise<string | null>;
  /** dirty 状态变化通知 */
  onDirtyChange?: (dirty: boolean) => void;
  /** 保存成功后刷新工作区 */
  onRefreshWorkspace?: (sessionId: string) => Promise<void> | void;
}

export interface UseEditableFileResult {
  content: string;
  originalContent: string;
  isLoading: boolean;
  isSaving: boolean;
  error: string | null;
  editable: boolean;
  editLockReason: string | null;
  loaded: boolean;
  dirty: boolean;
  setContent: (content: string) => void;
  save: () => Promise<boolean>;
  reset: () => void;
}

function createInitialState(fileName: string): EditableFileState {
  return {
    content: "",
    originalContent: "",
    isLoading: false,
    isSaving: false,
    error: null,
    editable: isGenericallyEditable(fileName),
    editLockReason: null,
    loaded: false,
  };
}

export function useEditableFile(
  options: UseEditableFileOptions,
): UseEditableFileResult {
  const { fileName, sessionId, workspaceId, loadContent, onDirtyChange, onRefreshWorkspace } =
    options;

  const [state, setState] = useState<EditableFileState>(
    createInitialState(fileName),
  );
  const dirtyRef = useRef(false);
  const loadingRef = useRef<Set<string>>(new Set());
  const loadedRef = useRef(state.loaded);

  useEffect(() => {
    loadedRef.current = state.loaded;
  }, [state.loaded]);

  // 加载文件内容
  useEffect(() => {
    if (!fileName || (!sessionId && !workspaceId)) {
      setState(createInitialState(fileName));
      return;
    }

    const requestKey = `${workspaceId || sessionId}:${fileName}`;
    if (loadedRef.current || loadingRef.current.has(requestKey)) {
      return;
    }

    const controller = new AbortController();
    loadingRef.current.add(requestKey);

    setState((prev) => ({
      ...(prev.loaded ? prev : createInitialState(fileName)),
      isLoading: true,
      error: null,
    }));

    const doLoad = async () => {
      try {
        let data: string | null = null;

        if (loadContent) {
          data = await loadContent(fileName);
        } else if (workspaceId) {
          const res = await apiRequest<FileContentResponse>(
            API_ENDPOINTS.WORKSPACE_FILE_CONTENT(workspaceId, fileName),
            { signal: controller.signal },
          );
          data = res.content;
          setState((prev) => ({
            ...prev,
            editable:
              res.editable ?? isGenericallyEditable(fileName),
            editLockReason: res.edit_lock_reason ?? null,
          }));
        } else if (sessionId) {
          const userId = getCurrentUserId();
          const res = await apiRequest<FileContentResponse>(
            API_ENDPOINTS.FILES_CONTENT(userId, sessionId, fileName),
            { signal: controller.signal },
          );
          data = res.content;
          setState((prev) => ({
            ...prev,
            editable:
              res.editable ?? isGenericallyEditable(fileName),
            editLockReason: res.edit_lock_reason ?? null,
          }));
        }

        if (controller.signal.aborted) return;
        loadingRef.current.delete(requestKey);

        if (data !== null) {
          setState((prev) => ({
            ...prev,
            content: data!,
            originalContent: data!,
            isLoading: false,
            error: null,
            loaded: true,
          }));
          dirtyRef.current = false;
          onDirtyChange?.(false);
        } else {
          setState((prev) => ({
            ...prev,
            isLoading: false,
            error: "无法读取文件内容",
            loaded: true,
          }));
        }
      } catch (err) {
        loadingRef.current.delete(requestKey);
        if (controller.signal.aborted) return;
        const message =
          err instanceof Error ? err.message : "读取文件内容失败";
        setState((prev) => ({
          ...prev,
          isLoading: false,
          error: message,
          loaded: true,
        }));
      }
    };

    void doLoad();

    const ref = loadingRef.current;
    return () => {
      ref.delete(requestKey);
      controller.abort();
    };
  }, [fileName, sessionId, workspaceId, loadContent, onDirtyChange]);

  const setContent = useCallback(
    (nextContent: string) => {
      setState((prev) => {
        const dirty = nextContent !== prev.originalContent;
        if (dirty !== dirtyRef.current) {
          dirtyRef.current = dirty;
          onDirtyChange?.(dirty);
        }
        return { ...prev, content: nextContent };
      });
    },
    [onDirtyChange],
  );

  const save = useCallback(async () => {
    if (!fileName || (!sessionId && !workspaceId) || state.isSaving || !state.loaded) return false;

    setState((prev) => ({ ...prev, isSaving: true, error: null }));

    try {
      const url = workspaceId
        ? API_ENDPOINTS.WORKSPACE_FILE_CONTENT(workspaceId, fileName)
        : API_ENDPOINTS.FILES_CONTENT(getCurrentUserId(), sessionId!, fileName);
      await apiRequest(url, {
        method: "PUT",
        body: { content: state.content },
      });
      setState((prev) => {
        dirtyRef.current = false;
        onDirtyChange?.(false);
        return {
          ...prev,
          originalContent: prev.content,
          isSaving: false,
          error: null,
        };
      });
      if (sessionId) {
        await onRefreshWorkspace?.(sessionId);
      }
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : "保存文件失败";
      setState((prev) => ({ ...prev, isSaving: false, error: message }));
      return false;
    }
  }, [fileName, sessionId, workspaceId, state.content, state.isSaving, state.loaded, onDirtyChange, onRefreshWorkspace]);

  const reset = useCallback(() => {
    setState((prev) => {
      dirtyRef.current = false;
      onDirtyChange?.(false);
      return { ...prev, content: prev.originalContent };
    });
  }, [onDirtyChange]);

  const dirty = state.content !== state.originalContent;

  return {
    ...state,
    dirty,
    setContent,
    save,
    reset,
  };
}
