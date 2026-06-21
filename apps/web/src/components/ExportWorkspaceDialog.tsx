import { useState, useEffect, useCallback, useRef } from "react";
import { Download, Settings2, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import {
  FileUploadToast,
  useFileUploadToast,
} from "@/components/file/FileUploadToast";
import {
  TemplateFileTreeSelector,
  isFileExcluded,
  DEFAULT_EXCLUDE_RULES,
  type ExcludeRule,
} from "@/components/TemplateFileTreeSelector";
import {
  exportWorkspace,
  type ExportWorkspacePayload,
} from "@/lib/api/workspaces";
import { API_ENDPOINTS } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";
import type { FileInfo, FileListResponse } from "@/types/api";

async function fetchWorkspaceFiles(workspaceId: string): Promise<FileInfo[]> {
  const files: FileInfo[] = [];
  let offset = 0;
  let hasMore = true;

  while (hasMore) {
    const data = await apiRequest<FileListResponse>(
      API_ENDPOINTS.WORKSPACE_FILE_LIST(workspaceId, {
        recursive: true,
        limit: 500,
        offset,
      }),
      { timeoutMs: 30000 },
    );
    files.push(...(data.files || []));
    if (data.has_more && typeof data.next_offset === "number") {
      offset = data.next_offset;
    } else {
      hasMore = false;
    }
  }

  return files;
}

async function fetchExportIgnore(workspaceId: string): Promise<string[]> {
  try {
    const res = await apiRequest<{ content: string }>(
      API_ENDPOINTS.WORKSPACE_FILE_CONTENT(workspaceId, ".aiasys/.exportignore"),
    );
    return res.content
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.length > 0 && !line.startsWith("#"));
  } catch {
    return [];
  }
}

interface ExportWorkspaceDialogProps {
  workspaceId: string;
  workspaceTitle: string;
  isOpen: boolean;
  onClose: () => void;
}

export function ExportWorkspaceDialog({
  workspaceId,
  workspaceTitle,
  isOpen,
  onClose,
}: ExportWorkspaceDialogProps) {
  const { toasts, showSuccess, showError: showToastError } = useFileUploadToast();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [workspaceFiles, setWorkspaceFiles] = useState<FileInfo[]>([]);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
  const [excludeRules, setExcludeRules] = useState<ExcludeRule[]>(
    DEFAULT_EXCLUDE_RULES.map((r) => ({ ...r })),
  );
  const [customRuleInput, setCustomRuleInput] = useState("");
  const [includeConversations, setIncludeConversations] = useState(false);

  const [activePreviewPath, setActivePreviewPath] = useState<string | null>(null);
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);

  const workspaceTitleRef = useRef(workspaceTitle);
  workspaceTitleRef.current = workspaceTitle;

  // 打开弹窗时加载文件列表和 .exportignore
  useEffect(() => {
    if (!isOpen) return;

    setWorkspaceFiles([]);
    setSelectedPaths(new Set());
    setError(null);
    setIsLoadingFiles(true);
    setIncludeConversations(false);
    setActivePreviewPath(null);
    setPreviewContent(null);
    setCustomRuleInput("");

    // 先读取 .exportignore，再加载文件列表
    fetchExportIgnore(workspaceId)
      .then((ignorePatterns) => {
        const baseRules = DEFAULT_EXCLUDE_RULES.map((r) => ({ ...r }));
        const userRules: ExcludeRule[] = ignorePatterns.map((pattern, i) => ({
          id: `user-${i}`,
          pattern,
          enabled: true,
        }));
        setExcludeRules([...baseRules, ...userRules]);
      })
      .catch(() => {
        setExcludeRules(DEFAULT_EXCLUDE_RULES.map((r) => ({ ...r })));
      })
      .finally(() => {
        fetchWorkspaceFiles(workspaceId)
          .then((files) => {
            setWorkspaceFiles(files);
          })
          .catch(() => {
            setError("加载工作区文件列表失败");
          })
          .finally(() => {
            setIsLoadingFiles(false);
          });
      });
  }, [isOpen, workspaceId]);

  // 当文件列表或排除规则变化时，更新选中状态
  useEffect(() => {
    if (workspaceFiles.length === 0) return;
    const next = new Set<string>();
    for (const file of workspaceFiles) {
      const shouldExclude = isFileExcluded(file.name, excludeRules);
      if (!shouldExclude) {
        next.add(file.name);
      }
    }
    setSelectedPaths(next);
  }, [workspaceFiles, excludeRules]);

  const handleTogglePreview = useCallback(
    async (path: string) => {
      if (activePreviewPath === path) {
        setActivePreviewPath(null);
        setPreviewContent(null);
        return;
      }
      setActivePreviewPath(path);
      setPreviewContent(null);
      setIsPreviewLoading(true);
      try {
        const res = await apiRequest<{ content: string }>(
          API_ENDPOINTS.WORKSPACE_FILE_CONTENT(workspaceId, path),
        );
        setPreviewContent(res.content);
      } catch {
        setPreviewContent(null);
      } finally {
        setIsPreviewLoading(false);
      }
    },
    [activePreviewPath, workspaceId],
  );

  const handleToggleRule = useCallback((ruleId: string) => {
    setExcludeRules((prev) =>
      prev.map((r) => (r.id === ruleId ? { ...r, enabled: !r.enabled } : r)),
    );
  }, []);

  const handleAddCustomRule = useCallback(() => {
    const pattern = customRuleInput.trim();
    if (!pattern) return;
    const newRule: ExcludeRule = {
      id: `custom-${Date.now()}`,
      pattern,
      enabled: true,
    };
    setExcludeRules((prev) => [...prev, newRule]);
    setCustomRuleInput("");
  }, [customRuleInput]);

  const handleRemoveCustomRule = useCallback((ruleId: string) => {
    setExcludeRules((prev) => prev.filter((r) => r.id !== ruleId));
  }, []);

  const handleSubmit = async () => {
    if (selectedPaths.size === 0) {
      setError("请至少选择一个文件");
      return;
    }
    setError(null);
    setIsSubmitting(true);
    try {
      const enabledRules = excludeRules.filter((r) => r.enabled);
      const payload: ExportWorkspacePayload = {
        include_conversations: includeConversations,
        selected_files: Array.from(selectedPaths),
        exclude_rules: enabledRules.map((r) => r.pattern),
      };
      const blob = await exportWorkspace(workspaceId, payload);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${workspaceTitleRef.current || "workspace"}_export.zip`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      showSuccess("工作区已导出");
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : "导出失败";
      setError(message);
      showToastError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleOpenChange = (open: boolean) => {
    if (!open && !isSubmitting) {
      onClose();
    }
  };

  const selectableFiles = workspaceFiles.map((f) => ({
    path: f.name,
  }));

  const enabledRules = excludeRules.filter((r) => r.enabled);

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-lg max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <Download className="h-5 w-5 text-muted-foreground" />
            导出工作区
          </DialogTitle>
          <DialogDescription className="text-[11px] leading-5">
            将当前工作区打包为 ZIP 文件，可迁移到其他设备。
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto space-y-4 py-2">
          {error && (
            <div className="rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-xs text-destructive">
              {error}
            </div>
          )}

          {/* 文件选择 */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>选择要导出的文件</Label>
              <Popover>
                <PopoverTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 gap-1 text-[11px]"
                    disabled={isLoadingFiles || workspaceFiles.length === 0}
                  >
                    <Settings2 className="h-3 w-3" />
                    排除规则
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-64 p-2" align="end">
                  <div className="space-y-1.5 max-h-[320px] overflow-y-auto">
                    <p className="text-[10px] text-muted-foreground font-medium">
                      排除规则（类 gitignore 语法）
                    </p>
                    {excludeRules.map((rule) => (
                      <div key={rule.id} className="flex items-center gap-2">
                        <Checkbox
                          checked={rule.enabled}
                          onCheckedChange={() => handleToggleRule(rule.id)}
                          className="h-3.5 w-3.5 shrink-0"
                        />
                        <span className="text-[11px] flex-1 truncate">
                          {rule.label || rule.pattern}
                        </span>
                        <span className="text-[10px] text-muted-foreground font-mono shrink-0">
                          {rule.pattern}
                        </span>
                        {!rule.isDefault && (
                          <button
                            type="button"
                            onClick={() => handleRemoveCustomRule(rule.id)}
                            className="shrink-0 text-muted-foreground hover:text-destructive"
                            title="删除规则"
                          >
                            <Trash2 className="h-3 w-3" />
                          </button>
                        )}
                      </div>
                    ))}
                    <div className="border-t border-border pt-1.5 mt-1.5 space-y-1.5">
                      <p className="text-[10px] text-muted-foreground font-medium">
                        添加自定义规则
                      </p>
                      <div className="flex gap-1">
                        <Input
                          value={customRuleInput}
                          onChange={(e) => setCustomRuleInput(e.target.value)}
                          placeholder="如 *.bak、temp/"
                          className="h-7 text-[11px]"
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              e.preventDefault();
                              handleAddCustomRule();
                            }
                          }}
                        />
                        <Button
                          type="button"
                          size="sm"
                          className="h-7 px-2 text-[11px]"
                          onClick={handleAddCustomRule}
                        >
                          添加
                        </Button>
                      </div>
                    </div>
                  </div>
                </PopoverContent>
              </Popover>
            </div>

            {enabledRules.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {enabledRules.map((rule) => (
                  <span
                    key={rule.id}
                    className="inline-flex items-center rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary"
                  >
                    {rule.label || rule.pattern}
                  </span>
                ))}
              </div>
            )}

            <div className="rounded-md border border-border bg-muted/20 p-2 max-h-[240px] overflow-y-auto">
              {isLoadingFiles ? (
                <div className="py-4 text-center text-xs text-muted-foreground">
                  加载文件列表...
                </div>
              ) : (
                <TemplateFileTreeSelector
                  files={selectableFiles}
                  selectedPaths={selectedPaths}
                  onSelectionChange={setSelectedPaths}
                  activePreviewPath={activePreviewPath}
                  onTogglePreview={handleTogglePreview}
                  previewContent={previewContent}
                  isPreviewLoading={isPreviewLoading}
                />
              )}
            </div>
          </div>

          {/* 包含对话记录 */}
          <div className="flex items-center justify-between rounded-md border border-border bg-muted/20 px-3 py-2">
            <div className="space-y-0.5">
              <Label className="text-[11px]">包含对话记录</Label>
              <p className="text-[10px] text-muted-foreground">
                导出所有对话的完整消息内容
              </p>
            </div>
            <Switch
              checked={includeConversations}
              onCheckedChange={setIncludeConversations}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={isSubmitting}>
            取消
          </Button>
          <Button
            onClick={() => void handleSubmit()}
            disabled={isSubmitting || selectedPaths.size === 0}
          >
            {isSubmitting ? "导出中..." : "导出工作区"}
          </Button>
        </DialogFooter>
        {toasts.map((toast) => (
          <FileUploadToast
            key={toast.id}
            message={toast.message}
            type={toast.type}
          />
        ))}
      </DialogContent>
    </Dialog>
  );
}
