import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Pencil, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  createRole,
  updateRole,
} from "@/lib/api/roles";
import type { RoleDetail } from "@/lib/api/roles";

const NAME_PATTERN = /^[a-zA-Z][a-zA-Z0-9_-]*$/;

interface RoleFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: "create" | "edit";
  initialData?: RoleDetail;
  workspaceId: string;
  scope: "global" | "workspace";
  onSuccess: () => void;
  onSubmitRole?: (
    mode: "create" | "edit",
    payload: {
      name: string;
      description: string;
      system_prompt: string;
      model: string | null;
      scope: "global" | "workspace";
    },
    initialName?: string,
  ) => Promise<void>;
}

export function RoleFormDialog({
  open,
  onOpenChange,
  mode,
  initialData,
  workspaceId,
  scope,
  onSuccess,
  onSubmitRole,
}: RoleFormDialogProps) {
  const isEdit = mode === "edit";

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [model, setModel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // 编辑时预填充
  useEffect(() => {
    if (isEdit && initialData) {
      setName(initialData.name);
      setDescription(initialData.description || "");
      setSystemPrompt(initialData.system_prompt || "");
      setModel(initialData.model || "");
    } else if (!isEdit) {
      setName("");
      setDescription("");
      setSystemPrompt("");
      setModel("");
    }
    setError(null);
  }, [isEdit, initialData, open]);

  const canSubmit = useMemo(() => {
    return (
      name.trim() &&
      description.trim() &&
      systemPrompt.trim() &&
      !submitting
    );
  }, [name, description, systemPrompt, submitting]);

  const validate = useCallback((): string | null => {
    const n = name.trim();
    const d = description.trim();
    const sp = systemPrompt.trim();

    if (!n) return "请输入角色名称";
    if (!NAME_PATTERN.test(n)) {
      return "名称格式无效：需英文字母开头，仅包含字母、数字、下划线、连字符";
    }
    if (n.length > 64) return "名称长度不能超过 64 个字符";
    if (!d) return "请输入描述";
    if (!sp) return "请输入 System Prompt";
    return null;
  }, [name, description, systemPrompt]);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const err = validate();
      if (err) {
        setError(err);
        return;
      }
      setError(null);
      setSubmitting(true);

      try {
        if (onSubmitRole) {
          await onSubmitRole(
            mode,
            {
              name: name.trim(),
              description: description.trim(),
              system_prompt: systemPrompt.trim(),
              model: model.trim() || null,
              scope,
            },
            initialData?.name,
          );
        } else if (isEdit && initialData) {
          await updateRole(
            workspaceId,
            initialData.name,
            {
              description: description.trim(),
              system_prompt: systemPrompt.trim(),
              model: model.trim() || null,
            },
          );
        } else {
          await createRole(workspaceId, {
            name: name.trim(),
            description: description.trim(),
            system_prompt: systemPrompt.trim(),
            model: model.trim() || null,
            scope: "workspace",
          });
        }

        onOpenChange(false);
        onSuccess();
      } catch (err) {
        setError(
          err instanceof Error ? err.message : `${isEdit ? "保存" : "创建"}失败`,
        );
      } finally {
        setSubmitting(false);
      }
    },
    [
      isEdit,
      initialData,
      mode,
      name,
      description,
      systemPrompt,
      model,
      scope,
      workspaceId,
      validate,
      onOpenChange,
      onSubmitRole,
      onSuccess,
    ],
  );

  const handleClose = useCallback(() => {
    if (submitting) return;
    onOpenChange(false);
  }, [submitting, onOpenChange]);

  const createDescription =
    scope === "global"
      ? "创建一个协作专家，并加入我的默认"
      : "创建一个协作专家，并启用到当前工作区";

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-hidden flex flex-col bg-background">
        <form
          onSubmit={handleSubmit}
          className="flex flex-col h-full overflow-hidden"
        >
          <DialogHeader className="shrink-0">
            <DialogTitle className="flex items-center gap-2">
              {isEdit ? (
                <>
                  <Pencil className="h-4 w-4" />
                  编辑协作专家
                </>
              ) : (
                <>
                  <Plus className="h-4 w-4" />
                  新建协作专家
                </>
              )}
            </DialogTitle>
            <DialogDescription>
              {isEdit
                ? "修改当前协作专家的配置"
                : createDescription}
            </DialogDescription>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto min-h-0 pr-1 space-y-4 py-4">
            {error && (
              <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </div>
            )}

            {/* 名称 */}
            <div className="grid gap-2">
              <Label htmlFor="role-name">
                名称 <span className="text-destructive">*</span>
              </Label>
              {isEdit ? (
                <div className="rounded-md border border-border bg-muted/50 px-3 py-2 text-sm text-foreground">
                  {name}
                </div>
              ) : (
                <Input
                  id="role-name"
                  placeholder="custom_role"
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    if (error) setError(null);
                  }}
                  disabled={submitting}
                  maxLength={64}
                />
              )}
              {!isEdit && (
                <p className="text-xs text-muted-foreground">
                  英文字母开头，仅包含字母、数字、下划线、连字符，长度不超过64
                </p>
              )}
            </div>

            {/* 描述 */}
            <div className="grid gap-2">
              <Label htmlFor="role-description">
                描述 <span className="text-destructive">*</span>
              </Label>
              <Input
                id="role-description"
                placeholder="一句话描述这个角色的职责"
                value={description}
                onChange={(e) => {
                  setDescription(e.target.value);
                  if (error) setError(null);
                }}
                disabled={submitting}
              />
            </div>

            {/* System Prompt */}
            <div className="grid gap-2">
              <Label htmlFor="role-system-prompt">
                系统提示词 <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id="role-system-prompt"
                placeholder="输入完整的角色定义和指令..."
                value={systemPrompt}
                onChange={(e) => {
                  setSystemPrompt(e.target.value);
                  if (error) setError(null);
                }}
                disabled={submitting}
                className="h-48 resize-y"
              />
            </div>

            {/* 模型 */}
            <div className="grid gap-2">
              <Label htmlFor="role-model">模型（可选）</Label>
              <Input
                id="role-model"
                placeholder="留空则继承 Host 模型"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                disabled={submitting}
              />
            </div>
          </div>

          <DialogFooter className="shrink-0 pt-4 border-t border-border">
            <Button
              type="button"
              variant="outline"
              onClick={handleClose}
              disabled={submitting}
            >
              取消
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {submitting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {isEdit ? "保存中..." : "创建中..."}
                </>
              ) : isEdit ? (
                "保存更改"
              ) : (
                "创建角色"
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
