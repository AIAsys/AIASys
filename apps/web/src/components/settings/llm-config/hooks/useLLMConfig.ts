/**
 * LLM 配置面板状态管理 Hook
 */

import { useCallback, useEffect, useState } from "react";
import type {
  LLMModelDefaults,
  LLMProviderConfigWithMeta,
  LLMModelConfigWithMeta,
  ModelCapability,
  ProviderTestResult,
  ProviderType,
  RemoteModelInfo,
} from "@/lib/api/llm";
import {
  getProviders,
  getModels,
  getModelDefaults,
  createProvider,
  updateProvider,
  deleteProvider,
  createModel,
  updateModel,
  deleteModel,
  testProvider,
  initializeDefaults,
  updateModelDefaults,
  fetchProviderModels,
  batchCreateModels,
  inferModelMaxContextSize,
  inferModelDefaults,
} from "@/lib/api/llm";

export type LoadingState = {
  providers: boolean;
  models: boolean;
  test: Record<string, boolean>;
  save: boolean;
  delete: string | null;
};

export interface UseLLMConfigOptions {
  onModelsChange?: () => void | Promise<void>;
}

export function useLLMConfig(options: UseLLMConfigOptions = {}) {
  const { onModelsChange } = options;

  // 数据状态
  const [providers, setProviders] = useState<LLMProviderConfigWithMeta[]>([]);
  const [models, setModels] = useState<LLMModelConfigWithMeta[]>([]);
  const [modelDefaults, setModelDefaults] = useState<LLMModelDefaults>({
    default_chat_model: null,
    default_embedding_model: null,
  });
  const [modelDefaultsDraft, setModelDefaultsDraft] = useState<LLMModelDefaults>({
    default_chat_model: null,
    default_embedding_model: null,
  });
  const [savingDefaults, setSavingDefaults] = useState(false);

  // 加载和提示状态
  const [loading, setLoading] = useState<LoadingState>(({
    providers: false,
    models: false,
    test: {},
    save: false,
    delete: null,
  }));
  const [error, setError] = useState<string>("");
  const [success, setSuccess] = useState<string>("");

  // Provider 编辑状态
  const [editingProvider, setEditingProvider] = useState<LLMProviderConfigWithMeta | null>(null);
  const [isAddProviderOpen, setIsAddProviderOpen] = useState(false);
  const [deleteProviderTarget, setDeleteProviderTarget] = useState<string | null>(null);

  // Model 编辑状态
  const [editingModel, setEditingModel] = useState<LLMModelConfigWithMeta | null>(null);
  const [isEditModelOpen, setIsEditModelOpen] = useState(false);
  const [deleteModelTarget, setDeleteModelTarget] = useState<string | null>(null);
  const [addModelProviderId, setAddModelProviderId] = useState<string>("");

  // 批量选择删除状态
  const [selectedModels, setSelectedModels] = useState<Set<string>>(new Set());
  const [batchDeleting, setBatchDeleting] = useState(false);

  // 远程模型获取状态
  const [isFetchModelsOpen, setIsFetchModelsOpen] = useState(false);
  const [fetchModelsProviderId, setFetchModelsProviderId] = useState<string>("");
  const [remoteModels, setRemoteModels] = useState<RemoteModelInfo[]>([]);
  const [selectedRemoteModels, setSelectedRemoteModels] = useState<Set<string>>(new Set());
  const [fetchingModels, setFetchingModels] = useState(false);
  const [fetchModelsError, setFetchModelsError] = useState<string>("");
  const [fetchUnsupported, setFetchUnsupported] = useState(false);
  const [manualModelName, setManualModelName] = useState<string>("");
  const [batchCreating, setBatchCreating] = useState(false);

  // Provider 表单状态
  const [providerForm, setProviderForm] = useState<Partial<LLMProviderConfigWithMeta>>({
    id: "",
    name: "",
    type: "openai_chat_completions",
    base_url: "",
    api_key: "",
    description: "",
    custom_headers: {},
    env: {},
    enabled: true,
    is_default: false,
  });

  // Model 编辑表单状态
  const [modelForm, setModelForm] = useState<Partial<LLMModelConfigWithMeta>>({
    name: "",
    model: "",
    model_type: "chat",
    max_context_size: 128000,
    capabilities: [],
    enabled: true,
    is_default: false,
  });

  const [testResults, setTestResults] = useState<Record<string, ProviderTestResult>>({});

  // 加载数据
  const loadData = useCallback(async () => {
    setLoading((prev) => ({ ...prev, providers: true, models: true }));
    setError("");

    try {
      const [providersRes, modelsRes, defaultsRes] = await Promise.all([
        getProviders(false),
        getModels(false, undefined),
        getModelDefaults(),
      ]);

      setProviders(providersRes.providers);
      setModels(modelsRes.models);
      setModelDefaults(defaultsRes);
      setModelDefaultsDraft(defaultsRes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载配置失败");
    } finally {
      setLoading((prev) => ({ ...prev, providers: false, models: false }));
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // 重置表单
  const resetProviderForm = useCallback(() => {
    setProviderForm({
      id: "",
      name: "",
      type: "openai_chat_completions",
      base_url: "",
      api_key: "",
      description: "",
      custom_headers: {},
      env: {},
      enabled: true,
      is_default: false,
    });
  }, []);

  // Provider 操作
  const handleSaveProvider = useCallback(async () => {
    if (!providerForm.id || !providerForm.name || !providerForm.base_url) {
      setError("请填写所有必填字段");
      return;
    }

    setLoading((prev) => ({ ...prev, save: true }));
    setError("");
    setSuccess("");

    try {
      const data = {
        ...providerForm,
        type: providerForm.type || "openai_chat_completions",
      } as Omit<LLMProviderConfigWithMeta, "created_at" | "updated_at" | "api_key_masked">;

      if (editingProvider) {
        await updateProvider(editingProvider.id, data);
        setSuccess("服务商更新成功");
      } else {
        await createProvider(data);
        setSuccess("服务商创建成功");
      }

      setIsAddProviderOpen(false);
      setEditingProvider(null);
      resetProviderForm();
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setLoading((prev) => ({ ...prev, save: false }));
    }
  }, [providerForm, editingProvider, loadData, resetProviderForm]);

  const handleDeleteProvider = useCallback(async () => {
    if (!deleteProviderTarget) return;

    setLoading((prev) => ({ ...prev, delete: deleteProviderTarget }));
    setError("");

    try {
      await deleteProvider(deleteProviderTarget);
      setSuccess("删除成功");
      await loadData();
      await onModelsChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setLoading((prev) => ({ ...prev, delete: null }));
      setDeleteProviderTarget(null);
    }
  }, [deleteProviderTarget, loadData, onModelsChange]);

  // Model 操作
  const handleSaveModel = useCallback(async () => {
    setLoading((prev) => ({ ...prev, save: true }));
    setError("");
    setSuccess("");

    try {
      if (editingModel) {
        // 编辑模式
        const updates: Record<string, unknown> = {};
        if (modelForm.name) updates.name = modelForm.name;
        if (modelForm.model) updates.model = modelForm.model;
        if (modelForm.model_type) updates.model_type = modelForm.model_type;
        if (modelForm.dimension !== undefined) updates.dimension = modelForm.dimension;
        if (modelForm.max_context_size) updates.max_context_size = modelForm.max_context_size;
        if (modelForm.capabilities !== undefined) {
          const providerType = providers.find(p => p.id === editingModel.provider)?.type;
          const caps = [...modelForm.capabilities];
          if (providerType === "openai_responses" && !caps.includes("always_thinking")) {
            caps.push("always_thinking");
          }
          updates.capabilities = caps;
        }
        if (modelForm.enabled !== undefined) updates.enabled = modelForm.enabled;
        if (modelForm.is_default !== undefined) updates.is_default = modelForm.is_default;

        await updateModel(editingModel.id, updates);
        setSuccess("模型更新成功");
      } else if (addModelProviderId && modelForm.model) {
        // 新建模式
        const modelId = `${addModelProviderId}-${modelForm.model}`;
        const providerType = providers.find(p => p.id === addModelProviderId)?.type;
        const caps = [...(modelForm.capabilities || [])];
        if (providerType === "openai_responses" && !caps.includes("always_thinking")) {
          caps.push("always_thinking");
        }
        await createModel({
          id: modelId,
          name: modelForm.name || modelForm.model,
          provider: addModelProviderId,
          model: modelForm.model,
          model_type: modelForm.model_type || "chat",
          dimension: modelForm.dimension,
          max_context_size: modelForm.max_context_size || inferModelMaxContextSize(providerType as ProviderType),
          capabilities: caps,
          enabled: modelForm.enabled ?? true,
          is_default: modelForm.is_default ?? false,
        });
        setSuccess("模型创建成功");
      } else {
        setError("请填写模型名称和实际模型标识");
        setLoading((prev) => ({ ...prev, save: false }));
        return;
      }

      setIsEditModelOpen(false);
      setEditingModel(null);
      setAddModelProviderId("");
      await loadData();
      onModelsChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setLoading((prev) => ({ ...prev, save: false }));
    }
  }, [editingModel, modelForm, providers, addModelProviderId, loadData, onModelsChange]);

  const handleDeleteModel = useCallback(async () => {
    if (!deleteModelTarget) return;

    setLoading((prev) => ({ ...prev, delete: deleteModelTarget }));
    setError("");

    try {
      await deleteModel(deleteModelTarget);
      setSuccess("删除成功");
      await loadData();
      onModelsChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setLoading((prev) => ({ ...prev, delete: null }));
      setDeleteModelTarget(null);
    }
  }, [deleteModelTarget, loadData, onModelsChange]);

  // 远程模型获取
  const handleFetchModels = useCallback(async (providerId: string) => {
    setFetchModelsProviderId(providerId);
    setIsFetchModelsOpen(true);
    setRemoteModels([]);
    setSelectedRemoteModels(new Set());
    setFetchModelsError("");
    setFetchUnsupported(false);
    setManualModelName("");
    setFetchingModels(true);

    try {
      const result = await fetchProviderModels(providerId);
      if (result.success) {
        setRemoteModels(result.models);
      } else if (result.unsupported) {
        setFetchUnsupported(true);
        setFetchModelsError(result.error_message || "该服务商不支持自动获取模型列表");
      } else {
        setFetchModelsError(result.error_message || "获取模型列表失败");
      }
    } catch (err) {
      const raw = err instanceof Error ? err.message : "";
      let msg = "获取模型列表失败，请检查服务商配置";
      if (raw.includes("404")) {
        msg = "该服务商不支持获取模型列表，请手动添加模型";
      } else if (raw.includes("401") || raw.includes("403")) {
        msg = "API Key 无效或无权限，请检查服务商密钥配置";
      } else if (raw.includes("fetch") || raw.includes("network") || raw.includes("Failed")) {
        msg = "无法连接到服务商，请检查网络和 Base URL 配置";
      }
      setFetchModelsError(msg);
    } finally {
      setFetchingModels(false);
    }
  }, []);

  const toggleRemoteModel = useCallback((modelName: string) => {
    setSelectedRemoteModels((prev) => {
      const next = new Set(prev);
      if (next.has(modelName)) {
        next.delete(modelName);
      } else {
        next.add(modelName);
      }
      return next;
    });
  }, []);

  const handleBatchAddModels = useCallback(async () => {
    if (selectedRemoteModels.size === 0) return;

    // 从 remoteModels 中查找选中的完整模型信息
    const selectedModels: RemoteModelInfo[] = [];
    for (const name of selectedRemoteModels) {
      const rm = remoteModels.find((m) => m.model_name === name);
      if (rm) selectedModels.push(rm);
    }
    if (selectedModels.length === 0) return;

    setBatchCreating(true);
    setError("");

    try {
      await batchCreateModels({
        provider_id: fetchModelsProviderId,
        models: selectedModels,
      });
      setSuccess(`成功添加 ${selectedModels.length} 个模型`);
      setIsFetchModelsOpen(false);
      await loadData();
      onModelsChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "批量添加失败");
    } finally {
      setBatchCreating(false);
    }
  }, [selectedRemoteModels, remoteModels, fetchModelsProviderId, loadData, onModelsChange]);

  const handleManualAddModel = useCallback(async () => {
    if (!manualModelName.trim()) return;

    setBatchCreating(true);
    setError("");

    try {
      await batchCreateModels({
        provider_id: fetchModelsProviderId,
        models: [{ model_name: manualModelName.trim() }],
      });
      setSuccess(`模型 "${manualModelName.trim()}" 添加成功`);
      setManualModelName("");
      await loadData();
      onModelsChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "添加失败");
    } finally {
      setBatchCreating(false);
    }
  }, [manualModelName, fetchModelsProviderId, loadData, onModelsChange]);

  // 批量删除
  const handleBatchDeleteModels = useCallback(async () => {
    if (selectedModels.size === 0) return;

    setBatchDeleting(true);
    setError("");

    const abortController = new AbortController();
    const timeoutId = setTimeout(() => abortController.abort(), 30000);

    try {
      const ids = Array.from(selectedModels);
      let failCount = 0;
      for (let i = 0; i < ids.length; i++) {
        const id = ids[i];
        if (abortController.signal.aborted) {
          failCount += ids.length - i;
          break;
        }
        try {
          await deleteModel(id);
        } catch {
          failCount++;
        }
      }
      if (abortController.signal.aborted) {
        setError("批量删除超时，部分模型可能未删除");
      } else if (failCount > 0) {
        setError(`${ids.length - failCount} 个删除成功，${failCount} 个删除失败`);
      } else {
        setSuccess(`已删除 ${ids.length} 个模型`);
      }
      setSelectedModels(new Set());
      await loadData();
      onModelsChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "批量删除失败");
    } finally {
      clearTimeout(timeoutId);
      setBatchDeleting(false);
    }
  }, [selectedModels, loadData, onModelsChange]);

  // 选择操作
  const toggleModelSelection = useCallback((modelId: string) => {
    setSelectedModels((prev) => {
      const next = new Set(prev);
      if (next.has(modelId)) next.delete(modelId);
      else next.add(modelId);
      return next;
    });
  }, []);

  const toggleProviderModelsSelection = useCallback((providerId: string) => {
    const providerModels = models.filter(m => m.provider === providerId);
    const allSelected = providerModels.every((m) => selectedModels.has(m.id));
    setSelectedModels((prev) => {
      const next = new Set(prev);
      for (const m of providerModels) {
        if (allSelected) next.delete(m.id);
        else next.add(m.id);
      }
      return next;
    });
  }, [models, selectedModels]);

  // 默认模型选择
  const handleSaveModelDefaults = useCallback(async () => {
    setSavingDefaults(true);
    setError("");
    try {
      const next = await updateModelDefaults(modelDefaultsDraft);
      setModelDefaults(next);
      setModelDefaultsDraft(next);
      setSuccess("默认模型已更新");
      onModelsChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "设置失败");
    } finally {
      setSavingDefaults(false);
    }
  }, [modelDefaultsDraft, onModelsChange]);

  const handleTest = useCallback(async (id: string) => {
    setLoading((prev) => ({ ...prev, test: { ...prev.test, [id]: true } }));
    setError("");

    try {
      const result = await testProvider(id);
      setTestResults((prev) => ({ ...prev, [id]: result }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "测试失败");
    } finally {
      setLoading((prev) => ({ ...prev, test: { ...prev.test, [id]: false } }));
    }
  }, []);

  const handleInitialize = useCallback(async () => {
    setLoading((prev) => ({ ...prev, save: true }));
    setError("");

    try {
      await initializeDefaults();
      setSuccess("默认配置初始化成功");
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "初始化失败");
    } finally {
      setLoading((prev) => ({ ...prev, save: false }));
    }
  }, [loadData]);

  // 编辑操作
  const startEditProvider = useCallback((provider: LLMProviderConfigWithMeta) => {
    setEditingProvider(provider);
    setProviderForm({
      ...provider,
      api_key: "",
    });
    setIsAddProviderOpen(true);
  }, []);

  const startEditModel = useCallback((model: LLMModelConfigWithMeta) => {
    setEditingModel(model);
    setAddModelProviderId("");
      setModelForm({
        name: model.name,
        model: model.model,
        model_type: model.model_type || "chat",
        dimension: model.dimension,
        max_context_size: model.max_context_size,
        capabilities: model.capabilities || [],
        enabled: model.enabled,
        is_default: false,
      });
      setIsEditModelOpen(true);
    }, []);

  const startAddModel = useCallback((providerId: string) => {
    const provider = providers.find((p) => p.id === providerId);
    const providerType = provider?.type || "openai_chat_completions";
    setEditingModel(null);
    setAddModelProviderId(providerId);
    const defaults = inferModelDefaults(providerType as ProviderType);
    setModelForm({
      name: "",
      model: "",
      model_type: "chat",
      max_context_size: defaults.max_context_size,
      capabilities: defaults.capabilities,
      enabled: true,
      is_default: false,
    });
    setIsEditModelOpen(true);
  }, [providers]);

  // 工具方法
  const getModelsByProvider = useCallback((providerId: string) => {
    return models.filter(m => m.provider === providerId);
  }, [models]);

  const clearError = useCallback(() => setError(""), []);
  const clearSuccess = useCallback(() => setSuccess(""), []);

  const chatModels = models.filter((model) => (model.model_type ?? "chat") === "chat");
  const embeddingModels = models.filter((model) => model.model_type === "embedding");

  // 模型能力选项
  const capabilityOptions: { value: ModelCapability; label: string }[] = [
    { value: "thinking", label: "推理" },
    { value: "image_in", label: "图像输入" },
    { value: "video_in", label: "视频输入" },
    { value: "always_thinking", label: "始终推理" },
  ];

  return {
    // 数据
    providers,
    models,
    chatModels,
    embeddingModels,
    modelDefaults,
    modelDefaultsDraft,
    savingDefaults,
    loading,
    error,
    success,
    testResults,
    selectedModels,
    batchDeleting,
    
    // Provider 状态
    editingProvider,
    isAddProviderOpen,
    deleteProviderTarget,
    providerForm,
    
    // Model 状态
    editingModel,
    isEditModelOpen,
    deleteModelTarget,
    addModelProviderId,
    modelForm,
    
    // 远程模型状态
    isFetchModelsOpen,
    fetchModelsProviderId,
    remoteModels,
    selectedRemoteModels,
    fetchingModels,
    fetchModelsError,
    fetchUnsupported,
    manualModelName,
    batchCreating,
    
    // 常量
    capabilityOptions,
    
    // Actions
    setIsAddProviderOpen,
    setEditingProvider,
    setIsEditModelOpen,
    setIsFetchModelsOpen,
    setDeleteProviderTarget,
    setDeleteModelTarget,
    setAddModelProviderId,
    setProviderForm,
    setModelForm,
    setManualModelName,
    setSelectedRemoteModels,
    setModelDefaultsDraft,
    
    // Handlers
    loadData,
    handleSaveProvider,
    handleDeleteProvider,
    handleSaveModel,
    handleDeleteModel,
    handleFetchModels,
    toggleRemoteModel,
    handleBatchAddModels,
    handleManualAddModel,
    handleBatchDeleteModels,
    toggleModelSelection,
    toggleProviderModelsSelection,
    handleSaveModelDefaults,
    handleTest,
    handleInitialize,
    startEditProvider,
    startEditModel,
    startAddModel,
    getModelsByProvider,
    resetProviderForm,
    clearError,
    clearSuccess,
  };
}
