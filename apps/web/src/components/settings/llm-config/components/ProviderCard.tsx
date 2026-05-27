/**
 * Provider 卡片组件（新版）
 *
 * 对齐项目圆角大卡片 + 圆角列表项设计风格
 */

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Loader2,
  Trash2,
  Edit2,
  TestTube,
  Plus,
  Cpu,
  CheckCircle2,
  XCircle,
  AlertCircle,
} from "lucide-react";
import type { LLMProviderConfigWithMeta, LLMModelConfigWithMeta, ProviderTestResult } from "@/lib/api/llm";
import type { LoadingState } from "../hooks/useLLMConfig";

interface ProviderCardProps {
  provider: LLMProviderConfigWithMeta;
  models: LLMModelConfigWithMeta[];
  loading: LoadingState;
  testResult?: ProviderTestResult;
  selectedModels: Set<string>;
  onTest: (id: string) => void;
  onEdit: (provider: LLMProviderConfigWithMeta) => void;
  onDelete: (id: string) => void;
  onFetchModels: (id: string) => void;
  onAddModel: (providerId: string) => void;
  onEditModel: (model: LLMModelConfigWithMeta) => void;
  onDeleteModel: (id: string) => void;
  onToggleModelSelection: (id: string) => void;
  onToggleProviderSelection: (providerId: string) => void;
  onBatchDelete: () => void;
  batchDeleting: boolean;
  defaultChatModelId?: string | null;
  defaultEmbeddingModelId?: string | null;
}

function TestStatusBadge({ result }: { result?: ProviderTestResult }) {
  if (!result) return null;

  if (result.status === "success") {
    return (
      <Badge variant="default" className="bg-success text-white text-[10px]">
        <CheckCircle2 className="w-3 h-3 mr-1" />
        {result.latency_ms}ms
      </Badge>
    );
  } else if (result.status === "timeout") {
    return (
      <Badge variant="outline" className="text-warning border-warning text-[10px]">
        <AlertCircle className="w-3 h-3 mr-1" />
        超时
      </Badge>
    );
  } else {
    return (
      <Badge variant="default" className="bg-error text-white text-[10px]">
        <XCircle className="w-3 h-3 mr-1" />
        失败
      </Badge>
    );
  }
}

export function ProviderCard({
  provider,
  models,
  loading,
  testResult,
  selectedModels,
  onTest,
  onEdit,
  onDelete,
  onFetchModels,
  onAddModel,
  onEditModel,
  onDeleteModel,
  onToggleModelSelection,
  onToggleProviderSelection,
  onBatchDelete,
  batchDeleting,
  defaultChatModelId,
  defaultEmbeddingModelId,
}: ProviderCardProps) {
  const providerModels = models.filter((m) => m.provider === provider.id);
  const allSelected = providerModels.length > 0 && providerModels.every((m) => selectedModels.has(m.id));
  const selectedCount = providerModels.filter((m) => selectedModels.has(m.id)).length;

  return (
    <div className="rounded-2xl border border-border bg-background overflow-hidden">
      {/* Provider 头部信息 */}
      <div className="px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1 space-y-1.5">
            {/* 名称 + Badges */}
            <div className="flex items-center flex-wrap gap-1.5">
              <h3 className="text-sm font-semibold text-foreground">{provider.name}</h3>
              {provider.is_default && (
                <Badge variant="default" className="text-[10px] px-1.5 py-0">默认</Badge>
              )}
              {provider.enabled ? (
                <Badge variant="outline" className="text-success text-[10px] px-1.5 py-0">已启用</Badge>
              ) : (
                <Badge variant="secondary" className="text-[10px] px-1.5 py-0">已禁用</Badge>
              )}
              <TestStatusBadge result={testResult} />
            </div>
            {/* 元信息 */}
            <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
              <span className="font-mono">{provider.id}</span>
              <span className="opacity-40">·</span>
              <span>{provider.type}</span>
              <span className="opacity-40">·</span>
              <span className="truncate">{provider.base_url}</span>
            </div>
            {provider.description ? (
              <p className="text-[11px] text-muted-foreground line-clamp-1">
                {provider.description}
              </p>
            ) : null}
          </div>
          {/* 操作按钮组 */}
          <div className="flex items-center gap-0.5 shrink-0">
            <button
              type="button"
              onClick={() => onTest(provider.id)}
              disabled={loading.test[provider.id]}
              title="测试连通性"
              className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors disabled:opacity-50"
            >
              {loading.test[provider.id] ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <TestTube className="w-3.5 h-3.5" />
              )}
            </button>
            <button
              type="button"
              onClick={() => onEdit(provider)}
              title="编辑服务商"
              className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            >
              <Edit2 className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() => onDelete(provider.id)}
              disabled={loading.delete === provider.id}
              title="删除服务商"
              className="p-1.5 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors disabled:opacity-50"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* 模型列表区 */}
      <div className="border-t border-border px-5 py-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Cpu className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="text-xs font-medium text-foreground">模型</span>
            <span className="text-[11px] text-muted-foreground">
              {providerModels.length > 0 ? `${providerModels.length} 个` : "未配置"}
            </span>
            {providerModels.length > 0 && (
              <div className="flex items-center gap-1 ml-1">
                <Checkbox
                  id={`select-all-${provider.id}`}
                  checked={allSelected}
                  onCheckedChange={() => onToggleProviderSelection(provider.id)}
                  className="w-3.5 h-3.5"
                />
                <label htmlFor={`select-all-${provider.id}`} className="text-[11px] text-muted-foreground cursor-pointer">
                  全选
                </label>
              </div>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            {selectedCount > 0 && (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-[11px] bg-destructive/10 text-destructive hover:text-destructive hover:bg-destructive/20 font-medium"
                onClick={onBatchDelete}
                disabled={batchDeleting}
              >
                {batchDeleting && <Loader2 className="w-3 h-3 mr-1 animate-spin" />}
                <Trash2 className="w-3 h-3 mr-1" />
                删除 ({selectedCount})
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-[11px]"
              onClick={() => onAddModel(provider.id)}
            >
              <Plus className="w-3 h-3 mr-1" />
              手动添加
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-[11px]"
              onClick={() => onFetchModels(provider.id)}
            >
              <Plus className="w-3 h-3 mr-1" />
              获取模型
            </Button>
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          {providerModels.map((model) => (
            <ModelRow
              key={model.id}
              model={model}
              isSelected={selectedModels.has(model.id)}
              onToggle={() => onToggleModelSelection(model.id)}
              onEdit={() => onEditModel(model)}
              onDelete={() => onDeleteModel(model.id)}
              isDefaultChat={model.id === defaultChatModelId}
              isDefaultEmbedding={model.id === defaultEmbeddingModelId}
            />
          ))}
          {providerModels.length === 0 && (
            <div className="text-center py-5 rounded-xl border border-dashed border-border bg-muted/20">
              <p className="text-[12px] text-muted-foreground">
                暂无模型配置
              </p>
              <div className="mt-1.5 flex items-center gap-2 justify-center">
                <button
                  type="button"
                  onClick={() => onAddModel(provider.id)}
                  className="text-[11px] text-foreground underline-offset-4 hover:underline"
                >
                  手动添加模型
                </button>
                <span className="text-muted-foreground opacity-40">·</span>
                <button
                  type="button"
                  onClick={() => onFetchModels(provider.id)}
                  className="text-[11px] text-foreground underline-offset-4 hover:underline"
                >
                  获取远程模型列表
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

interface ModelRowProps {
  model: LLMModelConfigWithMeta;
  isSelected: boolean;
  onToggle: () => void;
  onEdit: () => void;
  onDelete: () => void;
  isDefaultChat: boolean;
  isDefaultEmbedding: boolean;
}

function ModelRow({
  model,
  isSelected,
  onToggle,
  onEdit,
  onDelete,
  isDefaultChat,
  isDefaultEmbedding,
}: ModelRowProps) {
  return (
    <div
      className={`group flex items-center gap-2.5 py-2 px-3 rounded-xl border transition-colors ${
        isSelected
          ? "border-primary/20 bg-primary/[0.04]"
          : "border-border/40 bg-muted/20 hover:bg-muted/40"
      }`}
    >
      <Checkbox
        checked={isSelected}
        onCheckedChange={onToggle}
        className="flex-shrink-0 w-3.5 h-3.5"
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-[13px] font-medium truncate">{model.name}</span>
          {model.model_type === "embedding" ? (
            <Badge variant="outline" className="text-[10px] px-1 py-0 text-info border-info/20">
              Embedding{model.dimension ? ` · ${model.dimension}d` : ""}
            </Badge>
          ) : (
            <Badge variant="outline" className="text-[10px] px-1 py-0 text-tertiary border-info/20">
              对话
            </Badge>
          )}
          {isDefaultChat && (
            <Badge variant="default" className="text-[10px] px-1 py-0">聊天默认</Badge>
          )}
          {isDefaultEmbedding && (
            <Badge variant="default" className="text-[10px] px-1 py-0">Embedding 默认</Badge>
          )}
          {!model.enabled && (
            <Badge variant="secondary" className="text-[10px] px-1 py-0">已禁用</Badge>
          )}
        </div>
        <div className="text-[11px] text-muted-foreground truncate mt-0.5">
          {model.model}
          <span className="mx-1 opacity-40">·</span>
          {model.max_context_size?.toLocaleString()} tokens
        </div>
      </div>
      <div className="flex items-center gap-0.5 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          type="button"
          onClick={onEdit}
          title="编辑模型"
          className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
        >
          <Edit2 className="w-3 h-3" />
        </button>
        <button
          type="button"
          onClick={onDelete}
          title="删除模型"
          className="p-1 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
        >
          <Trash2 className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}
