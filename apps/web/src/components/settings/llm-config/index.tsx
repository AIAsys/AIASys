/**
 * LLM 配置面板
 *
 * 管理服务商配置（base_url + api_key）和模型配置
 */

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Loader2 } from "lucide-react";
import { useLLMConfig } from "./hooks/useLLMConfig";
import { ProviderDialog } from "./components/ProviderDialog";
import { ModelDialog } from "./components/ModelDialog";
import { FetchModelsDialog } from "./components/FetchModelsDialog";
import { ProviderCard } from "./components/ProviderCard";
import { DeleteConfirmDialog } from "./components/DeleteConfirmDialog";

interface LLMConfigPanelProps {
  onModelsChange?: () => void | Promise<void>;
}

const NO_DEFAULT_MODEL = "__none__";

export default function LLMConfigPanel({ onModelsChange }: LLMConfigPanelProps = {}) {
  const {
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
    editingProvider,
    isAddProviderOpen,
    deleteProviderTarget,
    providerForm,
    editingModel,
    isEditModelOpen,
    deleteModelTarget,
    addModelProviderId,
    modelForm,
    isFetchModelsOpen,
    fetchModelsProviderId,
    remoteModels,
    selectedRemoteModels,
    fetchingModels,
    fetchModelsError,
    fetchUnsupported,
    manualModelName,
    batchCreating,
    capabilityOptions,
    setIsAddProviderOpen,
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
    setEditingProvider,
  } = useLLMConfig({ onModelsChange });

  return (
    <div className="flex flex-col">
      {/* Main Content */}
      <main>
        <div className="px-6 py-4">
          {/* 提示信息 */}
          {error && (
            <Alert variant="destructive" className="mb-6">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          {success && (
            <Alert className="mb-6 bg-success-container border-success/20">
              <AlertDescription className="text-success">{success}</AlertDescription>
            </Alert>
          )}
          
          {/* 初始化默认配置按钮 */}
          <div className="mb-4 flex items-center justify-end">
            <Button
              variant="outline"
              size="sm"
              onClick={handleInitialize}
              disabled={loading.save}
            >
              {loading.save ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              初始化默认配置
            </Button>
          </div>

          <Card className="mb-6">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">默认模型</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-foreground" htmlFor="default-chat-model">
                    默认 Chat 模型
                  </label>
                  <Select
                    value={modelDefaultsDraft.default_chat_model ?? NO_DEFAULT_MODEL}
                    disabled={savingDefaults || loading.models}
                    onValueChange={(value) =>
                      setModelDefaultsDraft({
                        ...modelDefaultsDraft,
                        default_chat_model: value === NO_DEFAULT_MODEL ? null : value,
                      })
                    }
                  >
                    <SelectTrigger id="default-chat-model" className="h-9">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={NO_DEFAULT_MODEL}>未设置</SelectItem>
                      {chatModels.map((model) => (
                        <SelectItem key={model.id} value={model.id}>
                          {model.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-foreground" htmlFor="default-embedding-model">
                    默认 Embedding 模型
                  </label>
                  <Select
                    value={modelDefaultsDraft.default_embedding_model ?? NO_DEFAULT_MODEL}
                    disabled={savingDefaults || loading.models}
                    onValueChange={(value) =>
                      setModelDefaultsDraft({
                        ...modelDefaultsDraft,
                        default_embedding_model: value === NO_DEFAULT_MODEL ? null : value,
                      })
                    }
                  >
                    <SelectTrigger id="default-embedding-model" className="h-9">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={NO_DEFAULT_MODEL}>未设置</SelectItem>
                      {embeddingModels.map((model) => (
                        <SelectItem key={model.id} value={model.id}>
                          {model.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="flex items-center justify-between gap-3 text-sm text-muted-foreground">
                <div>
                  新建知识库默认会跟随这里的 embedding 选择。当前会话与工作区的聊天执行默认会从这里的 chat 模型继续往下继承。
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={
                    savingDefaults ||
                    (
                      modelDefaults.default_chat_model === modelDefaultsDraft.default_chat_model &&
                      modelDefaults.default_embedding_model === modelDefaultsDraft.default_embedding_model
                    )
                  }
                  onClick={handleSaveModelDefaults}
                >
                  {savingDefaults ? (
                    <>
                      <Loader2 className="mr-2 w-4 h-4 animate-spin" />
                      保存中
                    </>
                  ) : (
                    "保存默认模型"
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
          
          {/* Providers Section */}
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-lg font-semibold">服务商配置</h2>
              <ProviderDialog
                isOpen={isAddProviderOpen}
                onOpenChange={setIsAddProviderOpen}
                editingProvider={editingProvider}
                providerForm={providerForm}
                loading={loading}
                onFormChange={setProviderForm}
                onSave={handleSaveProvider}
                onReset={() => { resetProviderForm(); setEditingProvider(null); }}
              />
            </div>
            
            {loading.providers ? (
              <div className="flex justify-center py-8">
                <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <div className="grid gap-4">
                {providers.map((provider) => (
                  <ProviderCard
                    key={provider.id}
                    provider={provider}
                    models={getModelsByProvider(provider.id)}
                    loading={loading}
                    testResult={testResults[provider.id]}
                    selectedModels={selectedModels}
                    onTest={handleTest}
                    onEdit={startEditProvider}
                    onDelete={setDeleteProviderTarget}
                    onFetchModels={handleFetchModels}
                    onAddModel={startAddModel}
                    onEditModel={startEditModel}
                    onDeleteModel={setDeleteModelTarget}
                    onToggleModelSelection={toggleModelSelection}
                    onToggleProviderSelection={toggleProviderModelsSelection}
                    onBatchDelete={handleBatchDeleteModels}
                    batchDeleting={batchDeleting}
                    defaultChatModelId={modelDefaults.default_chat_model}
                    defaultEmbeddingModelId={modelDefaults.default_embedding_model}
                  />
                ))}
                {providers.length === 0 && (
                  <div className="text-center py-8 text-muted-foreground">
                    暂无服务商配置，点击&quot;添加服务商&quot;创建
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </main>
      
      {/* Delete Confirmations */}
      <DeleteConfirmDialog
        isOpen={!!deleteProviderTarget}
        onOpenChange={() => setDeleteProviderTarget(null)}
        title="确认删除服务商"
        description="确定要删除这个服务商吗？其下的所有模型配置也会被删除。此操作不可撤销。"
        onConfirm={handleDeleteProvider}
        isLoading={!!loading.delete}
      />
      
      <DeleteConfirmDialog
        isOpen={!!deleteModelTarget}
        onOpenChange={() => setDeleteModelTarget(null)}
        title="确认删除模型"
        description="确定要删除这个模型配置吗？此操作不可撤销。"
        onConfirm={handleDeleteModel}
        isLoading={!!loading.delete}
      />
      
      {/* Model Edit Dialog */}
      <ModelDialog
        isOpen={isEditModelOpen}
        onOpenChange={(open) => { if (!open) setAddModelProviderId(""); setIsEditModelOpen(open); }}
        editingModel={editingModel}
        addModelProviderId={addModelProviderId}
        modelForm={modelForm}
        providers={providers}
        loading={loading}
        capabilityOptions={capabilityOptions}
        onFormChange={setModelForm}
        onSave={handleSaveModel}
      />
      
      {/* Fetch Remote Models Dialog */}
      <FetchModelsDialog
        isOpen={isFetchModelsOpen}
        onOpenChange={setIsFetchModelsOpen}
        providerId={fetchModelsProviderId}
        remoteModels={remoteModels}
        selectedModels={selectedRemoteModels}
        models={models}
        fetching={fetchingModels}
        error={fetchModelsError}
        unsupported={fetchUnsupported}
        manualModelName={manualModelName}
        batchCreating={batchCreating}
        onManualModelNameChange={setManualModelName}
        onToggleModel={toggleRemoteModel}
        onSelectAll={(allNew) => setSelectedRemoteModels(new Set(allNew))}
        onBatchAdd={handleBatchAddModels}
        onManualAdd={handleManualAddModel}
      />
    </div>
  );
}
