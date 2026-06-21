import { useState, useEffect, useCallback, useRef } from "react";
import {
  Loader2,
  LayoutTemplate,
  FilePlus,
  BookOpen,
  Code2,
  BarChart3,
  Trophy,
  Settings2,
  Trash2,
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";
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
  exportWorkspaceAsTemplate,
  type ExportWorkspaceTemplatePayload,
} from "@/lib/api/workspaces";
import { API_ENDPOINTS } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";
import type { FileInfo, FileListResponse } from "@/types/api";

const ICON_OPTIONS = [
  { value: "file-plus", label: "文件", icon: FilePlus },
  { value: "book-open", label: "书籍", icon: BookOpen },
  { value: "code-2", label: "代码", icon: Code2 },
  { value: "bar-chart-3", label: "图表", icon: BarChart3 },
  { value: "trophy", label: "奖杯", icon: Trophy },
];

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

interface SaveWorkspaceAsTemplateDialogProps {
  workspaceId: string;
  workspaceTitle: string;
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export function SaveWorkspaceAsTemplateDialog({
  workspaceId,
  workspaceTitle,
  isOpen,
  onClose,
  onSuccess,
}: SaveWorkspaceAsTemplateDialogProps) {
  const { toasts, showSuccess, showError: showToastError } = useFileUploadToast();
  const [name, setName] = useState(workspaceTitle || "");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("自定义");
  const [icon, setIcon] = useState("file-plus");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [workspaceFiles, setWorkspaceFiles] = useState<FileInfo[]>([]);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
  const [includeEnvVars, setIncludeEnvVars] = useState(false);

  const [activePreviewPath, setActivePreviewPath] = useState<string | null>(null);
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [excludeRules, setExcludeRules] = useState<ExcludeRule[]>(
    DEFAULT_EXCLUDE_RULES.map((r) => ({ ...r })),
  );
  const [customRuleInput, setCustomRuleInput] = useState("");

  useEffect(() => {
    if (!isOpen) return;
    // 重置所有表单和状态，避免上次操作的残留
    setWorkspaceFiles([]);
    setName(workspaceTitleRef.current || "");
    setDescription("");
    setCategory("自定义");
    setIcon("file-plus");
    setError(null);
    setIncludeEnvVars(false);
    setActivePreviewPath(null);
    setPreviewContent(null);
    setExcludeRules(DEFAULT_EXCLUDE_RULES.map((r) => ({ ...r })));
    setCustomRuleInput("");
    setIsLoadingFiles(true);
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
  }, [isOpen, workspaceId]);

  // 使用 ref 存储 workspaceTitle，避免作为 useEffect 依赖
  const workspaceTitleRef = useRef(workspaceTitle);
  workspaceTitleRef.current = workspaceTitle;

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
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError("模板名称不能为空");
      return;
    }
    setError(null);
    setIsSubmitting(true);
    try {
      const payload: ExportWorkspaceTemplatePayload = {
        name: trimmedName,
        description: description.trim(),
        category: category.trim() || "自定义",
        icon: icon.trim() || "file-plus",
        files: Array.from(selectedPaths),
        includeEnvVars,
      };
      await exportWorkspaceAsTemplate(workspaceId, payload);
      showSuccess("模板已保存");
      setName(workspaceTitle || "");
      setDescription("");
      setCategory("自定义");
      setIcon("file-plus");
      setSelectedPaths(new Set());
      setIncludeEnvVars(false);
      setError(null);
      onSuccess?.();
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : "导出模板失败";
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
            <LayoutTemplate className="h-5 w-5 text-muted-foreground" />
            保存为模板
          </DialogTitle>
          <DialogDescription className="text-[11px] leading-5">
            将当前工作区导出为自定义模板，方便日后复用。
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto space-y-4 py-2">
          {error && (
            <div className="rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-xs text-destructive">
              {error}
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="template-name">模板名称</Label>
            <Input
              id="template-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如：竞赛研究标准模板"
              disabled={isSubmitting}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="template-description">描述</Label>
            <Textarea
              id="template-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="简单说明这个模板的用途"
              rows={2}
              disabled={isSubmitting}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="template-category">分类</Label>
              <Input
                id="template-category"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="自定义"
                disabled={isSubmitting}
              />
            </div>
            <div className="space-y-1.5">
              <Label>图标</Label>
              <div className="flex gap-2">
                {ICON_OPTIONS.map((option) => {
                  const IconComponent = option.icon;
                  const isSelected = icon === option.value;
                  return (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setIcon(option.value)}
                      title={option.label}
                      className={cn(
                        "flex h-9 w-9 items-center justify-center rounded-md border transition-colors",
                        isSelected
                          ? "border-primary bg-primary/10 text-primary"
                          : "border-border bg-background text-muted-foreground hover:bg-muted",
                      )}
                    >
                      <IconComponent className="h-4 w-4" />
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>选择要保存的文件</Label>
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

          <div className="flex items-center justify-between rounded-md border border-border bg-muted/20 px-3 py-2">
            <div className="space-y-0.5">
              <Label className="text-[11px]">包含环境变量</Label>
              <p className="text-[10px] text-muted-foreground">
                默认关闭，防止敏感信息泄露
              </p>
            </div>
            <Switch
              checked={includeEnvVars}
              onCheckedChange={setIncludeEnvVars}
              disabled={isSubmitting}
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={onClose}
            disabled={isSubmitting}
          >
            取消
          </Button>
          <Button
            onClick={() => void handleSubmit()}
            disabled={isSubmitting || !name.trim() || selectedPaths.size === 0}
          >
            {isSubmitting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                保存中...
              </>
            ) : (
              "保存为模板"
            )}
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
