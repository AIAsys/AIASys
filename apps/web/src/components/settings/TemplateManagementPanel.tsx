import { useEffect, useState, useCallback } from "react";
import {
  FilePlus,
  Trash2,
  Loader2,
  AlertCircle,
  FileText,
  Puzzle,
  RefreshCw,
  Store,
} from "lucide-react";
import { TEMPLATE_ICON_MAP } from "@/lib/templateIcons";
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
import { useFileUploadToast } from "@/components/file/FileUploadToast";
import type { SettingsSection } from "@/components/settings/global-settings";

export interface TemplateManagementPanelProps {
  onNavigate?: (section: SettingsSection) => void;
}

export function TemplateManagementPanel({ onNavigate }: TemplateManagementPanelProps) {
  const { showSuccess, showError: showToastError } = useFileUploadToast();
  const [templates, setTemplates] = useState<WorkspaceTemplateItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

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
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {templates.map((template) => {
              const capCount = (template.recommended_capabilities ?? []).length;
              return (
                <div
                  key={template.template_id}
                  className="group flex flex-col rounded-lg border border-border bg-background p-4 transition-shadow hover:shadow-sm"
                >
                  <div className="flex items-start gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
                      {TEMPLATE_ICON_MAP[template.icon] ?? (
                        <FilePlus className="h-5 w-5" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-sm font-medium text-foreground">
                          {template.name}
                        </span>
                        <span className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                          {template.category}
                        </span>
                      </div>
                      <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                        {template.description || "无描述"}
                      </p>
                    </div>
                  </div>

                  <div className="mt-3 flex items-center gap-3 text-[11px] text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <FileText className="h-3 w-3" />
                      {template.files?.length ?? 0} 个文件
                    </span>
                    {capCount > 0 && (
                      <span className="flex items-center gap-1">
                        <Puzzle className="h-3 w-3" />
                        {capCount} 项能力
                      </span>
                    )}
                  </div>

                  {!template.is_builtin && (
                    <div className="mt-3 flex items-center justify-end gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs text-destructive hover:text-destructive hover:bg-destructive/5"
                        onClick={() => setConfirmDeleteId(template.template_id)}
                        disabled={deletingId === template.template_id}
                      >
                        {deletingId === template.template_id ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <Trash2 className="h-3 w-3" />
                        )}
                        <span className="ml-1">删除</span>
                      </Button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
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
    </div>
  );
}
