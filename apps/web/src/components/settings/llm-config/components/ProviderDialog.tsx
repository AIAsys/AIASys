/**
 * Provider 添加/编辑对话框
 */

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
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Loader2, Plus } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import type { LLMProviderConfigWithMeta } from "@/lib/api/llm";
import type { ProviderType } from "@/lib/api/llm";
import type { LoadingState } from "../hooks/useLLMConfig";

interface ProviderDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  editingProvider: LLMProviderConfigWithMeta | null;
  providerForm: Partial<LLMProviderConfigWithMeta>;
  loading: LoadingState;
  onFormChange: (form: Partial<LLMProviderConfigWithMeta>) => void;
  onSave: () => void;
  onReset: () => void;
}

function serializeJsonField(value: Record<string, string> | undefined): string {
  if (!value || Object.keys(value).length === 0) return "";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "";
  }
}

function parseJsonField(input: string): Record<string, string> | undefined {
  const trimmed = input.trim();
  if (!trimmed) return undefined;
  try {
    const parsed = JSON.parse(trimmed);
    if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
      // 确保所有值都是字符串
      const result: Record<string, string> = {};
      for (const [key, val] of Object.entries(parsed)) {
        result[key] = String(val);
      }
      return result;
    }
    return undefined;
  } catch {
    return undefined;
  }
}

const PROVIDER_TYPES: { value: ProviderType; label: string }[] = [
  { value: "openai_chat_completions", label: "OpenAI Chat Completions" },
  { value: "openai_responses", label: "OpenAI Responses" },
  { value: "anthropic_messages", label: "Anthropic Messages" },
];

export function ProviderDialog({
  isOpen,
  onOpenChange,
  editingProvider,
  providerForm,
  loading,
  onFormChange,
  onSave,
  onReset,
}: ProviderDialogProps) {
  const handleOpenChange = (open: boolean) => {
    if (!open) {
      onReset();
    }
    onOpenChange(open);
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button onClick={onReset}>
          <Plus className="w-4 h-4 mr-2" />
          添加服务商
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{editingProvider ? "编辑服务商" : "添加服务商"}</DialogTitle>
          <DialogDescription>
            配置 LLM 服务商的 API 连接信息
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="provider-id">ID</Label>
            <Input
              id="provider-id"
              value={providerForm.id}
              onChange={(e) => onFormChange({ ...providerForm, id: e.target.value })}
              placeholder="my-provider"
              disabled={!!editingProvider}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="provider-name">名称</Label>
            <Input
              id="provider-name"
              value={providerForm.name}
              onChange={(e) => onFormChange({ ...providerForm, name: e.target.value })}
              placeholder="My Provider"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="provider-url">Base URL</Label>
            <Input
              id="provider-url"
              value={providerForm.base_url}
              onChange={(e) => onFormChange({ ...providerForm, base_url: e.target.value })}
              placeholder="https://api.openai.com/v1"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="provider-type">类型</Label>
            <Select
              value={providerForm.type || "openai_chat_completions"}
              onValueChange={(v) => onFormChange({ ...providerForm, type: v as ProviderType })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PROVIDER_TYPES.map((type) => (
                  <SelectItem key={type.value} value={type.value}>
                    {type.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="provider-key">
              API Key
              {editingProvider && " (留空表示不修改)"}
            </Label>
            <Input
              id="provider-key"
              type="password"
              value={providerForm.api_key || ""}
              onChange={(e) => onFormChange({ ...providerForm, api_key: e.target.value })}
              placeholder="sk-..."
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="provider-description">描述（可选）</Label>
            <Input
              id="provider-description"
              value={providerForm.description || ""}
              onChange={(e) => onFormChange({ ...providerForm, description: e.target.value })}
              placeholder="例如：公司内部 Kimi Code API"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="provider-custom-headers">
              自定义请求头（可选，JSON 格式）
            </Label>
            <Textarea
              id="provider-custom-headers"
              value={serializeJsonField(providerForm.custom_headers)}
              onChange={(e) => {
                const parsed = parseJsonField(e.target.value);
                onFormChange({ ...providerForm, custom_headers: parsed });
              }}
              placeholder={`{\n  "X-Custom-Header": "value"\n}`}
              className="min-h-[80px] font-mono text-sm resize-none"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="provider-env">
              环境变量（可选，JSON 格式）
            </Label>
            <Textarea
              id="provider-env"
              value={serializeJsonField(providerForm.env)}
              onChange={(e) => {
                const parsed = parseJsonField(e.target.value);
                onFormChange({ ...providerForm, env: parsed });
              }}
              placeholder={`{\n  "HTTPS_PROXY": "http://proxy.example.com:8080"\n}`}
              className="min-h-[80px] font-mono text-sm resize-none"
            />
          </div>
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <Switch
                id="provider-enabled"
                checked={providerForm.enabled}
                onCheckedChange={(v) => onFormChange({ ...providerForm, enabled: v })}
              />
              <Label htmlFor="provider-enabled">启用</Label>
            </div>
            <div className="flex items-center space-x-2">
              <Switch
                id="provider-default"
                checked={providerForm.is_default}
                onCheckedChange={(v) => onFormChange({ ...providerForm, is_default: v })}
              />
              <Label htmlFor="provider-default">设为默认</Label>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            取消
          </Button>
          <Button onClick={onSave} disabled={loading.save}>
            {loading.save && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
