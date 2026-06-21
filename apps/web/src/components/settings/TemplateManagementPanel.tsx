import { useEffect, useState, useCallback } from "react";
import {


  Loader2,
  AlertCircle,
  FileText,

  RefreshCw,
  Store,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  listWorkspaceTemplates,
  deleteWorkspaceTemplate,
  type WorkspaceTemplateItem,
} from "@/lib/api/workspaces";
import {
  FileUploadToast,
  useFileUploadToast,
} from "@/components/file/FileUploadToast";
import { useAuthState } from "@/contexts/AuthContext";
import { saveUserUISettings } from "@/lib/api/uiSettings";
import { TemplateSortableGrid } from "@/components/TemplateSortableGrid";
import type { SettingsSection } from "@/components/settings/global-settings";

export interface TemplateManagementPanelProps {
  onNavigate?: (section: SettingsSection) => void;
}

export function TemplateManagementPanel({ onNavigate }: TemplateManagementPanelProps) {
  const { toasts, showSuccess, showError: showToastError } = useFileUploadToast();
  const { user } = useAuthState();
  const [templates, setTemplates] = useState<WorkspaceTemplateItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>("");

  const loadTemplates = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const items = await listWorkspaceTemplates(true);
      setTemplates(items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载模板列表失败");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTemplates();
  }, [loadTemplates]);

  const handleDelete = async (templateId: string) => {
    setDeletingId(templateId);
    try {
      await deleteWorkspaceTemplate(templateId);
      setTemplates((prev) => prev.filter((t) => t.template_id !== templateId));
      setConfirmDeleteId(null);
      setError(null);
      showSuccess("模板已删除");
    } catch (err) {
      const message = err instanceof Error ? err.message : "删除失败";
      setError(message);
      showToastError(message);
    } finally {
      setDeletingId(null);
    }
  };

  const confirmTarget = templates.find((t) => t.template_id === confirmDeleteId);

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-6 py-4 border-b border-border">
        <div>
          <h3 className="text-sm font-semibold text-foreground">模板管理</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            浏览所有可用模板，删除自定义模板
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onNavigate?.("template-market")}
          >
            <Store className="h-3.5 w-3.5" />
            <span className="ml-1.5">浏览模板市场</span>
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void loadTemplates()}
            disabled={isLoading}
          >
            {isLoading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
            <span className="ml-1.5">刷新</span>
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {error && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-xs text-destructive">
            <AlertCircle className="h-3.5 w-3.5 shrink-0" />
            {error}
          </div>
        )}

        {isLoading && templates.length === 0 ? (
          <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            加载模板中...
          </div>
        ) : templates.length === 0 ? (
          <div className="flex h-40 flex-col items-center justify-center text-sm text-muted-foreground">
            <FileText className="mb-2 h-8 w-8 opacity-40" />
            <p>尚未安装任何模板</p>
            <p className="text-xs mt-1">前往模板市场浏览和安装</p>
          </div>
        ) : (
          <TemplateSortableGrid
            templates={templates}
            selectedTemplateId={selectedTemplateId}
            isBusy={false}
            onSelect={(templateId) => setSelectedTemplateId(templateId)}
            onPreview={() => {}}
            onReorder={(newItems) => {
              const previousItems = templates;
              setTemplates(newItems);
              if (user?.id) {
                const order = newItems.map((t) => t.template_id);
                saveUserUISettings(user.id, { templateOrder: order }).catch((err) => {
                  setTemplates(previousItems);
                  showToastError(err instanceof Error ? err.message : "保存排序失败，请重试");
                });
              }
            }}
          />
        )}
      </div>

      <Dialog
        open={Boolean(confirmDeleteId)}
        onOpenChange={(open) => {
          if (!open) setConfirmDeleteId(null);
        }}
      >
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-base">确认删除模板</DialogTitle>
            <DialogDescription className="text-xs">
              确定要删除模板「{confirmTarget?.name}」吗？此操作不可恢复。
              系统内置模板无法删除。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setConfirmDeleteId(null)}
            >
              取消
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => {
                if (confirmDeleteId) void handleDelete(confirmDeleteId);
              }}
              disabled={Boolean(deletingId)}
            >
              {deletingId ? (
                <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              ) : null}
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {toasts.map((toast) => (
        <FileUploadToast
          key={toast.id}
          message={toast.message}
          type={toast.type}
        />
      ))}
    </div>
  );
}
