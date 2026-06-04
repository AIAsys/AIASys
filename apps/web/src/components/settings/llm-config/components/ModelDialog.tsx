/**
 * Model 编辑/新建对话框
 */

import { useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { Loader2 } from "lucide-react";
import { inferModelDefaults, type LLMModelConfigWithMeta, type ModelCapability, type ModelType, type ProviderType } from "@/lib/api/llm";
import type { LoadingState } from "../hooks/useLLMConfig";

interface ModelDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  editingModel: LLMModelConfigWithMeta | null;
  addModelProviderId: string;
  modelForm: Partial<LLMModelConfigWithMeta>;
  providers: { id: string; type: string }[];
  loading: LoadingState;
  capabilityOptions: { value: ModelCapability; label: string }[];
  onFormChange: (form: Partial<LLMModelConfigWithMeta>) => void;
  onSave: () => void;
}

export function ModelDialog({
  isOpen,
  onOpenChange,
  editingModel,
  addModelProviderId,
  modelForm,
  providers,
  loading,
  capabilityOptions,
  onFormChange,
  onSave,
}: ModelDialogProps) {
  const isCreate = !editingModel;
  const providerType = useMemo(() => {
    if (editingModel) {
      return providers.find(p => p.id === editingModel.provider)?.type;
    }
    if (addModelProviderId) {
      return providers.find(p => p.id === addModelProviderId)?.type;
    }
    return undefined;
  }, [editingModel, addModelProviderId, providers]);
  const isResponsesProvider = providerType === "openai_responses";
  const isEmbedding = modelForm.model_type === "embedding";

  // 新建模式下，根据接口格式和模型类型推断默认值
  const handleModelChange = (value: string) => {
    const defaults = inferModelDefaults(providerType as ProviderType);
    onFormChange({
      ...modelForm,
      model: value,
      name: modelForm.name || value,
      max_context_size: isEmbedding ? 8192 : defaults.max_context_size,
      capabilities: isEmbedding ? [] : defaults.capabilities,
    });
  };

  const handleModelTypeChange = (type: ModelType) => {
    const defaults = inferModelDefaults(providerType as ProviderType);
    onFormChange({
      ...modelForm,
      model_type: type,
      max_context_size: type === "embedding" ? 8192 : defaults.max_context_size,
      capabilities: type === "embedding" ? [] : defaults.capabilities,
      dimension: type === "embedding" ? modelForm.dimension : undefined,
    });
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{isCreate ? "新建模型" : "编辑模型"}</DialogTitle>
          <DialogDescription>
            {isCreate
              ? "添加一个新模型到当前供应商"
              : "修改模型的显示名称、上下文大小和能力配置"}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="model-type">模型类型</Label>
            <select
              id="model-type"
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              value={modelForm.model_type || "chat"}
              onChange={(e) => handleModelTypeChange(e.target.value as ModelType)}
            >
              <option value="chat">对话模型 (Chat)</option>
              <option value="embedding">Embedding 模型</option>
            </select>
          </div>
          {isCreate ? (
            <>
              <div className="space-y-2">
                <Label htmlFor="model-id">实际模型标识（API 中使用的名称）</Label>
                <Input
                  id="model-id"
                  value={modelForm.model || ""}
                  onChange={(e) => handleModelChange(e.target.value)}
                  placeholder="例如 gpt-4o、claude-opus-4 等"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="model-name">显示名称</Label>
                <Input
                  id="model-name"
                  value={modelForm.name || ""}
                  onChange={(e) => onFormChange({ ...modelForm, name: e.target.value })}
                  placeholder="显示名称"
                />
              </div>
            </>
          ) : (
            <>
              <div className="space-y-2">
                <Label className="text-muted-foreground">模型 ID</Label>
                <p className="text-sm font-mono bg-muted px-3 py-2 rounded">{editingModel?.id}</p>
              </div>
              <div className="space-y-2">
                <Label className="text-muted-foreground">模型名称</Label>
                <p className="text-sm font-mono bg-muted px-3 py-2 rounded">{editingModel?.model}</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="model-name">显示名称</Label>
                <Input
                  id="model-name"
                  value={modelForm.name}
                  onChange={(e) => onFormChange({ ...modelForm, name: e.target.value })}
                  placeholder="显示名称"
                />
              </div>
            </>
          )}
          {isEmbedding && (
            <div className="space-y-2">
              <Label htmlFor="model-dimension">向量维度 (dimension)</Label>
              <Input
                id="model-dimension"
                type="number"
                min={1}
                value={modelForm.dimension ?? ""}
                onChange={(e) => {
                  const val = e.target.value;
                  onFormChange({ ...modelForm, dimension: val ? parseInt(val) : undefined });
                }}
                placeholder="例如 1024、1536、4096（留空将自动探测）"
              />
              <p className="text-xs text-muted-foreground">
                不填写时，系统会在保存时自动发送一次探测请求获取维度。
              </p>
            </div>
          )}
          <div className="space-y-2">
            <Label htmlFor="model-context">最大上下文长度</Label>
            <Input
              id="model-context"
              type="number"
              value={modelForm.max_context_size}
              onChange={(e) => onFormChange({ ...modelForm, max_context_size: parseInt(e.target.value) || (isEmbedding ? 8192 : 128000) })}
              placeholder={isEmbedding ? "8192" : "128000"}
            />
            <p className="text-xs leading-5 text-muted-foreground">
              这里配置的是模型最大上下文窗口，不是自动压缩阈值。自动压缩的触发比例和保留回复空间请到我的默认配置里调整。
            </p>
            <p className="text-xs leading-5 text-muted-foreground">
              远程模型列表返回上下文长度时会自动带入。不确定时可以先用默认值，保存后再手动修正。
            </p>
          </div>
          {!isEmbedding && (
            <div className="space-y-2">
              <Label>模型能力</Label>
              <div className="flex flex-wrap gap-4">
                {capabilityOptions.map((cap) => {
                  const forceChecked = isResponsesProvider && cap.value === "always_thinking";
                  const isChecked = forceChecked || modelForm.capabilities?.includes(cap.value);
                  return (
                    <div key={cap.value} className="flex items-center space-x-2">
                      <Checkbox
                        id={`cap-${cap.value}`}
                        checked={isChecked}
                        disabled={forceChecked}
                        onCheckedChange={(checked) => {
                          const current = modelForm.capabilities || [];
                          if (checked) {
                            onFormChange({ ...modelForm, capabilities: [...current, cap.value] });
                          } else {
                            onFormChange({ ...modelForm, capabilities: current.filter(c => c !== cap.value) });
                          }
                        }}
                      />
                      <Label
                        htmlFor={`cap-${cap.value}`}
                        className={`text-sm font-normal cursor-pointer ${forceChecked ? "text-muted-foreground" : ""}`}
                      >
                        {cap.label}{forceChecked ? "（Responses API 强制启用）" : ""}
                      </Label>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <Switch
                id="model-enabled"
                checked={modelForm.enabled}
                onCheckedChange={(v) => onFormChange({ ...modelForm, enabled: v })}
              />
              <Label htmlFor="model-enabled">启用</Label>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={onSave} disabled={loading.save || (isCreate && !modelForm.model)}>
            {loading.save && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            {isCreate ? "创建" : "保存"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
