import { useCallback, useEffect, useState } from "react";

import { getModels, type LLMModelConfig } from "@/lib/api/llm";
import {
  getSessionLLMSelection,
  updateSessionLLMSelection,
  updateWorkspaceLLMSelection,
  type SessionLLMSelectionSummary,
} from "@/lib/api/llmSelection";
import { useFileUploadToast } from "@/components/file/FileUploadToast";

export interface UseModelSelectionReturn {
  models: LLMModelConfig[];
  selectedModelId: string;
  effectiveModelDisplayName: string | null;
  sessionSelection: SessionLLMSelectionSummary | null;
  isLoadingSelection: boolean;
  isUpdatingSessionSelection: boolean;
  isUpdatingWorkspaceSelection: boolean;
  setActiveSessionId: (sessionId?: string) => void;
  setSelectedModelId: (modelId: string) => Promise<void>;
  updateWorkspaceModelId: (modelId: string | null) => Promise<void>;
  reloadModels: () => Promise<void>;
  thinkingEnabled: boolean;
  thinkingEffort: "low" | "medium" | "high";
  setThinkingEnabled: (enabled: boolean) => void;
  setThinkingEffort: (effort: "low" | "medium" | "high") => void;
  /** 当前选中的模型是否支持 thinking */
  selectedModelSupportsThinking: boolean;
}

function getDisplayName(selection: SessionLLMSelectionSummary | null): string | null {
  if (!selection) {
    return null;
  }
  return (
    selection.effective.display_name ||
    selection.effective.model_name ||
    selection.effective.model_id ||
    null
  );
}

function getSessionSelectedModelId(selection: SessionLLMSelectionSummary | null): string {
  if (!selection) {
    return "system";
  }
  if (
    selection.session_scope.configured_model_id &&
    !selection.session_scope.configured_missing
  ) {
    return selection.session_scope.configured_model_id;
  }
  // 没有 session 级别覆盖时，直接显示当前生效的模型
  return selection.effective.model_id || "system";
}

function getThinkingStorageKey(sessionId: string): string {
  return `aia-thinking-${sessionId}`;
}

function loadThinkingConfig(
  sessionId: string,
): { enabled: boolean; effort: "low" | "medium" | "high" } | null {
  try {
    const raw = localStorage.getItem(getThinkingStorageKey(sessionId));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (
      typeof parsed.enabled === "boolean" &&
      ["low", "medium", "high"].includes(parsed.effort)
    ) {
      return { enabled: parsed.enabled, effort: parsed.effort };
    }
  } catch {
    // ignore
  }
  return null;
}

function saveThinkingConfig(
  sessionId: string,
  enabled: boolean,
  effort: "low" | "medium" | "high",
): void {
  try {
    localStorage.setItem(
      getThinkingStorageKey(sessionId),
      JSON.stringify({ enabled, effort }),
    );
  } catch {
    // ignore
  }
}

function modelSupportsThinking(model: LLMModelConfig | undefined): boolean {
  if (!model) return false;
  const caps = model.capabilities ?? [];
  return caps.includes("thinking") || caps.includes("always_thinking");
}

export function useModelSelection(
  initialSessionId?: string,
): UseModelSelectionReturn {
  const [activeSessionId, setActiveSessionIdState] = useState<string | undefined>(
    initialSessionId,
  );
  const [models, setModels] = useState<LLMModelConfig[]>([]);
  const [selectedModelId, setSelectedModelIdState] = useState("system");
  const [effectiveModelDisplayName, setEffectiveModelDisplayName] =
    useState<string | null>(null);
  const [sessionSelection, setSessionSelection] =
    useState<SessionLLMSelectionSummary | null>(null);
  const [isLoadingSelection, setIsLoadingSelection] = useState(false);
  const [isUpdatingSessionSelection, setIsUpdatingSessionSelection] =
    useState(false);
  const [isUpdatingWorkspaceSelection, setIsUpdatingWorkspaceSelection] =
    useState(false);
  const [thinkingEnabled, setThinkingEnabledState] = useState(false);
  const [thinkingEffort, setThinkingEffortState] = useState<"low" | "medium" | "high">("high");
  const { showError } = useFileUploadToast();

  const selectedModel = models.find((m) => m.id === selectedModelId);
  const selectedModelSupportsThinking = modelSupportsThinking(selectedModel);

  const reloadAvailableModels = useCallback(async () => {
    const res = await getModels(true, undefined);
    setModels(
      res.models.filter(
        (model) =>
          model.enabled !== false &&
          (model.model_type ?? "chat") === "chat",
      ),
    );
  }, []);

  const reloadScopedSelection = useCallback(async () => {
    if (!activeSessionId) {
      setSessionSelection(null);
      setSelectedModelIdState("system");
      setEffectiveModelDisplayName(null);
      return;
    }

    setIsLoadingSelection(true);
    try {
      const response = await getSessionLLMSelection(activeSessionId);
      setSessionSelection(response);
      setSelectedModelIdState(getSessionSelectedModelId(response));
      setEffectiveModelDisplayName(getDisplayName(response));
    } finally {
      setIsLoadingSelection(false);
    }
  }, [activeSessionId]);

  const reloadModels = useCallback(async () => {
    try {
      await Promise.all([reloadAvailableModels(), reloadScopedSelection()]);
    } catch (error) {
      console.error(error);
    }
  }, [reloadAvailableModels, reloadScopedSelection]);

  useEffect(() => {
    void reloadModels();
  }, [reloadModels]);

  // 切换 session 时恢复 thinking 配置
  useEffect(() => {
    if (!activeSessionId) {
      setThinkingEnabledState(false);
      setThinkingEffortState("high");
      return;
    }
    const saved = loadThinkingConfig(activeSessionId);
    if (saved) {
      setThinkingEnabledState(saved.enabled);
      setThinkingEffortState(saved.effort);
    } else {
      // 默认关闭，等待用户显式开启
      setThinkingEnabledState(false);
      setThinkingEffortState("high");
    }
  }, [activeSessionId]);

  // 切换模型时，如果新模型不支持 thinking，自动禁用
  useEffect(() => {
    if (!selectedModelSupportsThinking && thinkingEnabled) {
      setThinkingEnabledState(false);
      if (activeSessionId) {
        saveThinkingConfig(activeSessionId, false, thinkingEffort);
      }
    }
  }, [selectedModelSupportsThinking, selectedModelId, activeSessionId, thinkingEffort, thinkingEnabled]);

  const setActiveSessionId = useCallback((sessionId?: string) => {
    setActiveSessionIdState(sessionId);
  }, []);

  const setSelectedModelId = useCallback(
    async (modelId: string) => {
      if (!activeSessionId) {
        setSelectedModelIdState(modelId);
        return;
      }

      setIsUpdatingSessionSelection(true);
      try {
        const response = await updateSessionLLMSelection(
          activeSessionId,
          modelId === "system" ? null : modelId,
        );
        setSessionSelection(response);
        setSelectedModelIdState(getSessionSelectedModelId(response));
        setEffectiveModelDisplayName(getDisplayName(response));
      } catch (err) {
        showError(err instanceof Error ? err.message : "切换会话模型失败");
      } finally {
        setIsUpdatingSessionSelection(false);
      }
    },
    [activeSessionId, showError],
  );

  const updateWorkspaceModelId = useCallback(
    async (modelId: string | null) => {
      const workspaceId = sessionSelection?.workspace_id;
      if (!workspaceId) {
        return;
      }

      setIsUpdatingWorkspaceSelection(true);
      try {
        await updateWorkspaceLLMSelection(workspaceId, modelId);
        if (!activeSessionId) {
          return;
        }
        const refreshed = await getSessionLLMSelection(activeSessionId);
        setSessionSelection(refreshed);
        setSelectedModelIdState(getSessionSelectedModelId(refreshed));
        setEffectiveModelDisplayName(getDisplayName(refreshed));
      } catch (err) {
        showError(err instanceof Error ? err.message : "切换工作区模型失败");
      } finally {
        setIsUpdatingWorkspaceSelection(false);
      }
    },
    [activeSessionId, sessionSelection?.workspace_id, showError],
  );

  const setThinkingEnabled = useCallback(
    (enabled: boolean) => {
      setThinkingEnabledState(enabled);
      if (activeSessionId) {
        saveThinkingConfig(activeSessionId, enabled, thinkingEffort);
      }
    },
    [activeSessionId, thinkingEffort],
  );

  const setThinkingEffort = useCallback(
    (effort: "low" | "medium" | "high") => {
      setThinkingEffortState(effort);
      if (activeSessionId) {
        saveThinkingConfig(activeSessionId, thinkingEnabled, effort);
      }
    },
    [activeSessionId, thinkingEnabled],
  );

  return {
    models,
    selectedModelId,
    effectiveModelDisplayName,
    sessionSelection,
    isLoadingSelection,
    isUpdatingSessionSelection,
    isUpdatingWorkspaceSelection,
    setActiveSessionId,
    setSelectedModelId,
    updateWorkspaceModelId,
    reloadModels,
    thinkingEnabled,
    thinkingEffort,
    setThinkingEnabled,
    setThinkingEffort,
    selectedModelSupportsThinking,
  };
}
