import { useEffect, useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  FileText,
  FolderPlus,
  Loader2,
  SquareTerminal,
  Lightbulb,
  Puzzle,
  Plug,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { TemplateFileTreeSelector } from "@/components/TemplateFileTreeSelector";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import {
  listBindableKernelEnvs,
  type KernelEnvItem,
} from "@/lib/api/kernelEnvs";
import {
  listWorkspaceTemplates,
  type WorkspaceTemplateItem,
} from "@/lib/api/workspaces";
import { type NewTaskLifecycleState, type NewTaskStage } from "@/types/workspace";
import { useAuthState } from "@/contexts/AuthContext";
import { saveUserUISettings } from "@/lib/api/uiSettings";
import { TemplateSortableGrid } from "@/components/TemplateSortableGrid";

import { NewWorkspaceProgressBanner } from "./NewWorkspaceProgressBanner";
import { TemplatePreviewFileTree } from "./TemplatePreviewFileTree";

export type EnvChoice =
  | { kind: "none" }
  | { kind: "uv" }
  | { kind: "registered"; kernelName: string; pythonExecutable: string };

interface NewWorkspaceDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (
    title: string,
    description: string | undefined,
    envChoice: EnvChoice,
    templateId?: string,
    initialConversationTitle?: string,
    installCapabilities?: string[],
    templateFiles?: string[],
  ) => Promise<void>;
  lifecycleState?: NewTaskLifecycleState;
  registeredPythonEnvs?: KernelEnvItem[];
  isLoadingRegisteredPythonEnvs?: boolean;
  stage?: NewTaskStage;
  errorMessage?: string | null;
  isSubmitting?: boolean;
}



const ENV_LABEL_MAP: Record<string, string> = {
  none: "不启用 Python",
  uv: "Python 环境",
  registered: "已登记 Python",
  docker: "Docker",
};

export function NewWorkspaceDialog({
  isOpen,
  onClose,
  onConfirm,
  lifecycleState,
  registeredPythonEnvs = [],
  isLoadingRegisteredPythonEnvs = false,
  stage = "idle",
  errorMessage = null,
  isSubmitting = false,
}: NewWorkspaceDialogProps) {
  const [templates, setTemplates] = useState<WorkspaceTemplateItem[]>([]);
  const [isLoadingTemplates, setIsLoadingTemplates] = useState(false);
  const [templateLoadError, setTemplateLoadError] = useState<string | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>("blank-workspace");

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [envKind, setEnvKind] = useState<EnvChoice["kind"]>("none");
  const [selectedKernelName, setSelectedKernelName] = useState("");

  const [previewExpanded, setPreviewExpanded] = useState(false);
  const [capabilitiesExpanded, setCapabilitiesExpanded] = useState(false);
  const [previewingTemplate, setPreviewingTemplate] = useState<WorkspaceTemplateItem | null>(null);

  // 推荐能力勾选状态
  const [selectedCapabilities, setSelectedCapabilities] = useState<Set<string>>(new Set());

  // 模板文件勾选状态
  const [selectedTemplateFiles, setSelectedTemplateFiles] = useState<Set<string>>(new Set());

  // 切换模板时重置预览收起，并重置推荐能力勾选和文件勾选
  useEffect(() => {
    setPreviewExpanded(false);
    setCapabilitiesExpanded(false);
    const template = templates.find((t) => t.template_id === selectedTemplateId);
    if (template) {
      const capIds = (template.recommended_capabilities ?? []).map((c) => c.capability_id);
      setSelectedCapabilities(new Set(capIds));
      setSelectedTemplateFiles(new Set(template.files.map((f) => f.relative_path)));
    } else {
      setSelectedCapabilities(new Set());
      setSelectedTemplateFiles(new Set());
    }
  }, [selectedTemplateId, templates]);

  // 确保 required 能力始终被选中（用户不可取消）
  useEffect(() => {
    const template = templates.find((t) => t.template_id === selectedTemplateId);
    if (!template) return;
    const requiredIds = (template.recommended_capabilities ?? [])
      .filter((c) => c.required)
      .map((c) => c.capability_id);
    if (requiredIds.length === 0) return;
    setSelectedCapabilities((prev) => {
      const next = new Set(prev);
      let changed = false;
      for (const id of requiredIds) {
        if (!next.has(id)) {
          next.add(id);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [selectedCapabilities, selectedTemplateId, templates]);

  const selectableRegisteredEnvs = listBindableKernelEnvs(registeredPythonEnvs);
  const { user } = useAuthState();

  // 加载模板列表
  useEffect(() => {
    if (!isOpen) return;
    setIsLoadingTemplates(true);
    setTemplateLoadError(null);
    listWorkspaceTemplates()
      .then((items) => {
        setTemplates(items);
        const blank = items.find((t) => t.template_id === "blank-workspace");
        if (blank) {
          setSelectedTemplateId("blank-workspace");
        } else if (items.length > 0) {
          setSelectedTemplateId(items[0].template_id);
        }
      })
      .catch((err) => {
        setTemplates([]);
        setTemplateLoadError(err instanceof Error ? err.message : "加载模板列表失败");
      })
      .finally(() => setIsLoadingTemplates(false));
  }, [isOpen]);

  // 拖拽排序后保存
  const handleTemplateReorder = (newItems: WorkspaceTemplateItem[]) => {
    setTemplates(newItems);
    if (user?.id) {
      const order = newItems.map((t) => t.template_id);
      saveUserUISettings(user.id, { templateOrder: order }).catch(() => {
        // 保存失败静默处理
      });
    }
  };

  // 选择模板后只更新标题和描述，不覆盖环境
  useEffect(() => {
    const template = templates.find((t) => t.template_id === selectedTemplateId);
    if (!template) return;
    setTitle(template.default_title);
    setDescription(template.default_description);
  }, [selectedTemplateId, templates]);

  // 打开弹窗时重置（提交中不重置）
  useEffect(() => {
    if (isOpen && !isSubmitting) {
      setTitle("");
      setDescription("");
      setEnvKind("none");
      setSelectedKernelName("");
      setSelectedTemplateId("blank-workspace");
    }
  }, [isOpen, isSubmitting]);

  // 环境类型切换时清理已登记环境选择
  useEffect(() => {
    if (envKind !== "registered") {
      setSelectedKernelName("");
    }
  }, [envKind]);

  useEffect(() => {
    if (envKind !== "registered") {
      return;
    }
    if (
      selectedKernelName &&
      selectableRegisteredEnvs.some((env) => env.name === selectedKernelName)
    ) {
      return;
    }
    setSelectedKernelName(selectableRegisteredEnvs[0]?.name ?? "");
  }, [envKind, selectableRegisteredEnvs, selectedKernelName]);

  const effectiveLifecycleState = lifecycleState ?? {
    stage,
    stageLabel: "",
    showProgress: false,
    isBusy: isSubmitting,
    isError: stage === "error" || Boolean(errorMessage),
    errorMessage,
  };

  const trimmedTitle = title.trim();
  const trimmedDescription = description.trim();

  const selectedRegisteredEnv =
    selectableRegisteredEnvs.find((env) => env.name === selectedKernelName) ?? null;
  const canSubmit =
    trimmedTitle.length > 0 &&
    (envKind !== "registered" || Boolean(selectedRegisteredEnv?.executable));

  const selectedTemplate = templates.find((t) => t.template_id === selectedTemplateId);

  // 模板是否有推荐能力
  const hasRecommendedCapabilities =
    selectedTemplate &&
    selectedTemplate.template_id !== "blank-workspace" &&
    (selectedTemplate.recommended_capabilities?.length ?? 0) > 0;

  const handleConfirm = () => {
    const choice: EnvChoice =
      envKind === "registered" && selectedRegisteredEnv?.executable
        ? {
            kind: "registered",
            kernelName: selectedRegisteredEnv.name,
            pythonExecutable: selectedRegisteredEnv.executable,
          }
        : { kind: envKind === "uv" ? "uv" : "none" };
    void onConfirm(
      trimmedTitle,
      trimmedDescription || undefined,
      choice,
      selectedTemplateId === "blank-workspace" ? undefined : selectedTemplateId,
      selectedTemplate?.initial_conversation_title,
      Array.from(selectedCapabilities),
      selectedTemplateId === "blank-workspace" ? undefined : Array.from(selectedTemplateFiles),
    );
  };

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open && !isSubmitting) {
          onClose();
        }
      }}
    >
      <DialogContent
        className={cn(
          "max-w-2xl p-0 gap-0",
          effectiveLifecycleState.isBusy && "[&>button]:hidden",
        )}
        onEscapeKeyDown={(event) => {
          if (effectiveLifecycleState.isBusy) {
            event.preventDefault();
          } else {
            onClose();
          }
        }}
        onPointerDownOutside={(event) => {
          if (effectiveLifecycleState.isBusy) {
            event.preventDefault();
          }
        }}
      >
        <DialogHeader className="border-b px-6 py-4">
          <DialogTitle className="flex items-center gap-2 text-base">
            <FolderPlus className="h-5 w-5 text-muted-foreground dark:text-muted-foreground" />
            新建工作区
          </DialogTitle>
          <DialogDescription className="text-[11px] leading-5">
            填写基本信息并选择运行环境，模板仅决定初始文件内容。
          </DialogDescription>
        </DialogHeader>

        <div className="min-w-0 max-h-[calc(100vh-12rem)] space-y-4 overflow-y-auto p-6">
          <NewWorkspaceProgressBanner
            showProgress={effectiveLifecycleState.showProgress}
            isError={effectiveLifecycleState.isError}
            stageLabel={effectiveLifecycleState.stageLabel || ""}
            errorMessage={effectiveLifecycleState.errorMessage ?? errorMessage}
          />

          <div className="space-y-2">
            <Label htmlFor="workspace-title">任务名称</Label>
            <Input
              id="workspace-title"
              placeholder="例如：论文阅读、财报分析、代码重构"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              disabled={effectiveLifecycleState.isBusy}
              autoFocus
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="workspace-description">任务说明</Label>
            <Textarea
              id="workspace-description"
              placeholder="可选。简单说明这个工作区主要是做什么的。"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              disabled={effectiveLifecycleState.isBusy}
              rows={3}
            />
          </div>

          <div className="min-w-0 space-y-3 overflow-hidden">
            <div className="flex items-center justify-between">
              <Label>Python 运行环境</Label>
              {selectedTemplate &&
                selectedTemplate.template_id !== "blank-workspace" &&
                selectedTemplate.env_kind &&
                selectedTemplate.env_kind !== "none" && (
                  <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                    <Lightbulb className="h-3 w-3" />
                    推荐环境：{ENV_LABEL_MAP[selectedTemplate.env_kind] ?? selectedTemplate.env_kind}
                  </span>
                )}
            </div>
            <RadioGroup
              value={envKind}
              onValueChange={(value) => setEnvKind(value as EnvChoice["kind"])}
              className="gap-2"
              disabled={effectiveLifecycleState.isBusy}
            >
              <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-border bg-background px-3 py-2">
                <RadioGroupItem value="none" className="mt-0.5" />
                <span className="min-w-0">
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <SquareTerminal className="h-4 w-4 text-muted-foreground" />
                    不启用 Python
                  </span>
                  <span className="mt-0.5 block text-xs leading-5 text-muted-foreground">
                    不创建也不绑定 Python，普通文件、资料整理和对话任务可以直接开始。
                  </span>
                </span>
              </label>
              <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-border bg-background px-3 py-2">
                <RadioGroupItem value="uv" className="mt-0.5" />
                <span className="min-w-0">
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <SquareTerminal className="h-4 w-4 text-muted-foreground" />
                    创建新的 Python 环境
                  </span>
                  <span className="mt-0.5 block text-xs leading-5 text-muted-foreground">
                    在当前工作区创建隔离环境，适合需要 notebook、依赖安装或可复现实验的任务。
                  </span>

                </span>
              </label>
              <label
                className={cn(
                  "flex cursor-pointer items-start gap-3 rounded-lg border border-border bg-background px-3 py-2",
                  selectableRegisteredEnvs.length === 0 && "cursor-not-allowed opacity-60",
                )}
              >
                <RadioGroupItem
                  value="registered"
                  className="mt-0.5"
                  disabled={selectableRegisteredEnvs.length === 0}
                />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <SquareTerminal className="h-4 w-4 text-muted-foreground" />
                    使用已登记 Python
                  </span>
                  <span className="mt-0.5 block text-xs leading-5 text-muted-foreground">
                    绑定本机已登记解释器。依赖安装会影响该解释器对应环境。
                  </span>
                </span>
              </label>
            </RadioGroup>

            {envKind === "registered" ? (
              <div className="min-w-0 max-w-full space-y-2 overflow-hidden pl-7">
                <Select
                  value={selectedKernelName}
                  onValueChange={setSelectedKernelName}
                  disabled={
                    effectiveLifecycleState.isBusy ||
                    selectableRegisteredEnvs.length === 0
                  }
                >
                  <SelectTrigger
                    id="registered-python-choice"
                    className="w-full min-w-0 max-w-full"
                  >
                    <SelectValue placeholder="选择已登记 Python">
                      {selectedRegisteredEnv?.display_name || selectedRegisteredEnv?.name}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent className="w-[var(--radix-select-trigger-width)] max-w-[var(--radix-select-trigger-width)]">
                    {selectableRegisteredEnvs.map((env) => (
                      <SelectItem
                        key={env.name}
                        value={env.name}
                        className="max-w-[var(--radix-select-trigger-width)]"
                        title={env.executable}
                      >
                        <span className="flex min-w-0 max-w-full flex-col overflow-hidden">
                          <span className="truncate" title={env.display_name || env.name}>
                            {env.display_name || env.name}
                          </span>
                          <span
                            className="truncate font-mono text-[11px] text-muted-foreground"
                            title={env.executable}
                          >
                            {env.executable}
                          </span>
                        </span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {selectedRegisteredEnv?.executable ? (
                  <div
                    className="min-w-0 truncate font-mono text-[11px] text-muted-foreground"
                    title={selectedRegisteredEnv.executable}
                  >
                    {selectedRegisteredEnv.executable}
                  </div>
                ) : null}
                <p className="text-xs text-muted-foreground">
                  {isLoadingRegisteredPythonEnvs
                    ? "正在加载已登记 Python..."
                    : selectableRegisteredEnvs.length > 0
                      ? "创建工作区后会把所选解释器登记到该工作区并设为当前 Python。"
                      : "当前没有可用的已登记 Python。"}
                </p>
              </div>
            ) : null}
          </div>

          {/* 模板选择 */}
          <div className="space-y-2">
            <Label>选择模板（可选）</Label>
            {isLoadingTemplates ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                加载模板中...
              </div>
            ) : templateLoadError ? (
              <div className="text-sm text-red-500">加载模板失败：{templateLoadError}</div>
            ) : templates.length === 0 ? (
              <div className="text-sm text-muted-foreground">暂无可用模板</div>
            ) : (
              <>
                <TemplateSortableGrid
                  templates={templates}
                  selectedTemplateId={selectedTemplateId}
                  isBusy={effectiveLifecycleState.isBusy}
                  onSelect={(templateId) => setSelectedTemplateId(templateId)}
                  onPreview={(template) => setPreviewingTemplate(template)}
                  onReorder={handleTemplateReorder}
                />

                {/* 模板预览 */}
                {selectedTemplate &&
                  selectedTemplate.template_id !== "blank-workspace" &&
                  selectedTemplate.files &&
                  selectedTemplate.files.length > 0 && (
                    <div className="mt-3 overflow-hidden rounded-lg border border-border">
                      <button
                        type="button"
                        onClick={() => setPreviewExpanded((v) => !v)}
                        className="flex w-full items-center justify-between border-b border-border bg-muted/40 px-3 py-1.5 text-left"
                      >
                        <span className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
                          <FileText className="h-3 w-3" />
                          选择要导入的文件
                        </span>
                        {previewExpanded ? (
                          <ChevronUp className="h-3 w-3 text-muted-foreground" />
                        ) : (
                          <ChevronDown className="h-3 w-3 text-muted-foreground" />
                        )}
                      </button>
                      {previewExpanded && (
                        <div className="max-h-60 overflow-y-auto px-2 py-2">
                          <TemplateFileTreeSelector
                            files={selectedTemplate.files.map((f) => ({
                              path: f.relative_path,
                              content: f.content,
                            }))}
                            selectedPaths={selectedTemplateFiles}
                            onSelectionChange={setSelectedTemplateFiles}
                          />
                        </div>
                      )}
                    </div>
                  )}

                {/* 推荐能力勾选 */}
                {hasRecommendedCapabilities && (
                  <div className="mt-3 overflow-hidden rounded-lg border border-border">
                    <button
                      type="button"
                      onClick={() => setCapabilitiesExpanded((v) => !v)}
                      className="flex w-full items-center justify-between border-b border-border bg-muted/40 px-3 py-1.5 text-left"
                    >
                      <span className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
                        <Puzzle className="h-3 w-3" />
                        推荐能力
                        <span className="text-[10px] text-muted-foreground/70">
                          ({selectedCapabilities.size} 项已选)
                        </span>
                      </span>
                      {capabilitiesExpanded ? (
                        <ChevronUp className="h-3 w-3 text-muted-foreground" />
                      ) : (
                        <ChevronDown className="h-3 w-3 text-muted-foreground" />
                      )}
                    </button>
                    {capabilitiesExpanded && (
                      <div className="space-y-3 px-3 py-2">
                        {(() => {
                          const allCaps = (selectedTemplate!.recommended_capabilities ?? []).map((c) => ({
                            id: c.capability_id,
                            kind: c.kind,
                            label: c.capability_id,
                            required: c.required,
                          }));

                          const groups: Record<string, { label: string; icon: React.ReactNode; items: typeof allCaps }> = {
                            skill_pack: { label: "技能", icon: <Puzzle className="h-3 w-3" />, items: [] },
                            mcp_server: { label: "连接器", icon: <Plug className="h-3 w-3" />, items: [] },
                            subagent: { label: "专家协作节点", icon: <Puzzle className="h-3 w-3" />, items: [] },
                          };
                          allCaps.forEach((c) => {
                            const g = groups[c.kind] ?? groups.skill_pack;
                            g.items.push(c);
                          });

                          return Object.entries(groups)
                            .filter(([, g]) => g.items.length > 0)
                            .map(([kind, g]) => (
                              <div key={kind} className="space-y-1.5">
                                <div className="flex items-center gap-1 text-[11px] font-medium text-muted-foreground">
                                  {g.icon}
                                  {g.label}
                                </div>
                                {g.items.map((cap) => (
                                  <Checkbox
                                    key={cap.id}
                                    label={cap.label}
                                    checked={selectedCapabilities.has(cap.id)}
                                    onCheckedChange={(checked) => {
                                      if (cap.required && !checked) return;
                                      setSelectedCapabilities((prev) => {
                                        const next = new Set(prev);
                                        if (checked) {
                                          next.add(cap.id);
                                        } else {
                                          next.delete(cap.id);
                                        }
                                        return next;
                                      });
                                    }}
                                    disabled={effectiveLifecycleState.isBusy || cap.required}
                                  />
                                ))}
                              </div>
                            ));
                        })()}
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        <DialogFooter className="border-t px-6 py-4">
          <Button
            variant="outline"
            onClick={onClose}
            disabled={effectiveLifecycleState.isBusy}
          >
            取消
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={effectiveLifecycleState.isBusy || !canSubmit}
          >
            {effectiveLifecycleState.isBusy ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                创建中...
              </>
            ) : (
              "创建工作区"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>

      {/* 模板预览弹窗 */}
      <Dialog
        open={Boolean(previewingTemplate)}
        onOpenChange={(open) => {
          if (!open) setPreviewingTemplate(null);
        }}
      >
        <DialogContent className="max-w-3xl p-0 gap-0">
          <DialogHeader className="border-b px-6 py-4">
            <DialogTitle className="flex items-center gap-2 text-base">
              <FileText className="h-5 w-5 text-muted-foreground" />
              {previewingTemplate?.name}
              <span className="text-xs font-normal text-muted-foreground">
                模板预览
              </span>
            </DialogTitle>
            <DialogDescription className="text-[11px] leading-5">
              {previewingTemplate?.description || "该模板包含以下预置文件"}
            </DialogDescription>
          </DialogHeader>
          <div className="px-6 py-4">
            {previewingTemplate && previewingTemplate.files.length > 0 ? (
              <div className="h-[50vh] overflow-hidden rounded-md border border-border">
                <TemplatePreviewFileTree files={previewingTemplate.files} />
              </div>
            ) : (
              <div className="py-8 text-center text-sm text-muted-foreground">
                该模板不包含文件
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </Dialog>
  );
}
