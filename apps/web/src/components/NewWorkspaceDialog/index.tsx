import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  FileText,
  Folder,
  FolderOpen,
  FolderPlus,
  Loader2,
  SquareTerminal,
  Lightbulb,
  Puzzle,
  Plug,
  Upload,
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
import {
  TemplateFileTreeSelector,
  DEFAULT_EXCLUDE_RULES,
  isFileExcluded,
} from "@/components/TemplateFileTreeSelector";
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
  previewImportFolder,
  uploadImportFolder,
  type FolderImportTreeItem,
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
    options: {
      templateId?: string;
      initialConversationTitle?: string;
      installCapabilities?: string[];
      templateFiles?: string[];
      sourceFolderPath?: string;
      tempUploadId?: string;
      importFiles?: string[];
    },
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

  // 文件夹导入状态
  type CreationMode = "blank" | "template" | "folder";
  const [creationMode, setCreationMode] = useState<CreationMode>("blank");
  const [selectedFolderPath, setSelectedFolderPath] = useState<string | null>(null);
  const [folderTree, setFolderTree] = useState<FolderImportTreeItem[]>([]);
  const folderTreeFiles = useMemo(
    () => folderTree.map((f) => ({ path: f.relative_path })),
    [folderTree],
  );
  const [selectedImportFiles, setSelectedImportFiles] = useState<Set<string>>(new Set());
  const [isScanningFolder, setIsScanningFolder] = useState(false);
  const [folderScanError, setFolderScanError] = useState<string | null>(null);
  const [folderImportExpanded, setFolderImportExpanded] = useState(false);
  const [webFolderFiles, setWebFolderFiles] = useState<File[]>([]);
  const [isUploadingFiles, setIsUploadingFiles] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const dragCounterRef = useRef(0);
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const [isReadingFolder, setIsReadingFolder] = useState(false);
  const [readProgress, setReadProgress] = useState<{ current: number; total: number } | null>(null);

  const isDesktop = typeof window !== "undefined" && window.__AIASYS_DESKTOP__?.selectFolder !== undefined;

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

  const selectableRegisteredEnvs = useMemo(
    () => listBindableKernelEnvs(registeredPythonEnvs),
    [registeredPythonEnvs],
  );
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
    if (creationMode !== "template") return;
    const template = templates.find((t) => t.template_id === selectedTemplateId);
    if (!template) return;
    setTitle(template.default_title);
    setDescription(template.default_description);
  }, [creationMode, selectedTemplateId, templates]);

  // 打开弹窗时重置（提交中不重置）
  useEffect(() => {
    if (isOpen && !isSubmitting) {
      setTitle("");
      setDescription("");
      setEnvKind("none");
      setSelectedKernelName("");
      setSelectedTemplateId("blank-workspace");
      setCreationMode("blank");
      setSelectedFolderPath(null);
      setFolderTree([]);
      setSelectedImportFiles(new Set());
      setIsScanningFolder(false);
      setFolderScanError(null);
      setFolderImportExpanded(false);
      setWebFolderFiles([]);
      setIsUploadingFiles(false);
      setUploadProgress(0);
      setReadProgress(null);
      setIsDraggingOver(false);
      dragCounterRef.current = 0;
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

  const effectiveLifecycleState = useMemo(
    () =>
      lifecycleState ?? {
        stage,
        stageLabel: "",
        showProgress: false,
        isBusy: isSubmitting,
        isError: stage === "error" || Boolean(errorMessage),
        errorMessage,
        progress: undefined,
      },
    [lifecycleState, stage, isSubmitting, errorMessage],
  );

  const trimmedTitle = title.trim();
  const trimmedDescription = description.trim();

  const selectedRegisteredEnv =
    selectableRegisteredEnvs.find((env) => env.name === selectedKernelName) ?? null;
  const canSubmit =
    trimmedTitle.length > 0 &&
    (envKind !== "registered" || Boolean(selectedRegisteredEnv?.executable)) &&
    (creationMode !== "folder" ||
      (!isUploadingFiles &&
        ((isDesktop && Boolean(selectedFolderPath && selectedImportFiles.size > 0)) ||
          (!isDesktop && webFolderFiles.length > 0 && selectedImportFiles.size > 0))));

  const selectedTemplate = templates.find((t) => t.template_id === selectedTemplateId);

  // 递归读取 FileSystemDirectoryHandle（showDirectoryPicker 返回的句柄）
  const readDirectoryHandle = async (
    dirHandle: FileSystemDirectoryHandle,
    prefix: string,
  ): Promise<{ files: File[]; tree: FolderImportTreeItem[] }> => {
    const files: File[] = [];
    const tree: FolderImportTreeItem[] = [];

    tree.push({ relative_path: prefix, is_directory: true });

    for await (const [_name, entry] of dirHandle as unknown as AsyncIterable<[string, FileSystemHandle]>) {
      const relPath = prefix ? `${prefix}/${entry.name}` : entry.name;
      if (entry.kind === "file") {
        const file = await (entry as FileSystemFileHandle).getFile();
        Object.defineProperty(file, "webkitRelativePath", {
          value: relPath,
          writable: false,
        });
        files.push(file);
        tree.push({ relative_path: relPath, is_directory: false, size: file.size });
      } else if (entry.kind === "directory") {
        const subDirHandle = entry as FileSystemDirectoryHandle;
        const sub = await readDirectoryHandle(subDirHandle, relPath);
        files.push(...sub.files);
        tree.push(...sub.tree);
      }
    }

    return { files, tree };
  };

  const buildFolderTreeFromFiles = (files: File[]): FolderImportTreeItem[] => {
    const dirSet = new Set<string>();
    const items: FolderImportTreeItem[] = [];
    for (const file of files) {
      const relPath = file.webkitRelativePath || file.name;
      const parts = relPath.split("/");
      let current = "";
      for (let i = 0; i < parts.length - 1; i++) {
        current = current ? `${current}/${parts[i]}` : parts[i];
        if (!dirSet.has(current)) {
          dirSet.add(current);
          items.push({ relative_path: current, is_directory: true });
        }
      }
      items.push({
        relative_path: relPath,
        is_directory: false,
        size: file.size,
      });
    }
    return items.sort((a, b) => a.relative_path.localeCompare(b.relative_path));
  };

  const applyDefaultExclusions = (files: File[]): Set<string> => {
    const selected = new Set<string>();
    for (const file of files) {
      const relPath = file.webkitRelativePath || file.name;
      if (!isFileExcluded(relPath, DEFAULT_EXCLUDE_RULES)) {
        selected.add(relPath);
      }
    }
    return selected;
  };

  const handleWebFolderChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    if (files.length === 0) return;
    setWebFolderFiles(files);
    const tree = buildFolderTreeFromFiles(files);
    setFolderTree(tree);
    setSelectedImportFiles(applyDefaultExclusions(files));
    setFolderImportExpanded(true);
    setFolderScanError(null);
  };

  const handleSelectFolder = async () => {
    if (!isDesktop) {
      // Web 端：优先使用 showDirectoryPicker（Chrome/Edge 弹窗式选择）
      if (typeof window !== "undefined" && (window as unknown as Record<string, unknown>).showDirectoryPicker) {
        try {
          const dirHandle = await (window as unknown as { showDirectoryPicker: (options?: { mode?: string }) => Promise<FileSystemDirectoryHandle> }).showDirectoryPicker({
            mode: "read",
          });
          setSelectedFolderPath(dirHandle.name);
          setWebFolderFiles([]);
          setFolderTree([]);
          setSelectedImportFiles(new Set());
          setFolderScanError(null);
          setIsScanningFolder(true);
          try {
            const { files, tree } = await readDirectoryHandle(dirHandle, dirHandle.name);
            setWebFolderFiles(files);
            setFolderTree(tree);
            setSelectedImportFiles(applyDefaultExclusions(files));
            setFolderImportExpanded(true);
          } catch (err) {
            setFolderScanError(err instanceof Error ? err.message : "读取文件夹失败");
          } finally {
            setIsScanningFolder(false);
          }
          return;
        } catch (err) {
          // 用户取消选择时静默处理
          if ((err as Error).name === "AbortError") return;
          // 降级到 input
        }
      }
      // 降级：使用 webkitdirectory input
      fileInputRef.current?.click();
      return;
    }
    const desktop = window.__AIASYS_DESKTOP__;
    if (!desktop?.selectFolder) {
      setFolderScanError("当前环境不支持选择本地文件夹");
      return;
    }
    try {
      const result = await desktop.selectFolder({ title: "选择要导入的文件夹" });
      if (result.canceled || result.filePaths.length === 0) return;
      const path = result.filePaths[0];
      setSelectedFolderPath(path);
      setWebFolderFiles([]);
      setFolderTree([]);
      setSelectedImportFiles(new Set());
      setFolderScanError(null);
      setIsScanningFolder(true);
      try {
        const preview = await previewImportFolder(path);
        setFolderTree(preview.files);
        setSelectedImportFiles(new Set(preview.default_selected_files));
        setFolderImportExpanded(true);
      } catch (err) {
        setFolderScanError(err instanceof Error ? err.message : "扫描文件夹失败");
      } finally {
        setIsScanningFolder(false);
      }
    } catch (err) {
      setFolderScanError(err instanceof Error ? err.message : "选择文件夹失败");
    }
  };

  // ── 拖拽文件夹读取 ──

  const readEntryAsFiles = useCallback(
    async (
      entry: FileSystemEntry,
      path: string,
      onProgress?: (count: number) => void,
    ): Promise<File[]> => {
      const files: File[] = [];
      if (entry.isFile) {
        const file = await new Promise<File>((resolve) => {
          (entry as FileSystemFileEntry).file(resolve);
        });
        Object.defineProperty(file, "webkitRelativePath", {
          value: path ? `${path}/${file.name}` : file.name,
          writable: false,
        });
        files.push(file);
        onProgress?.(1);
      } else if (entry.isDirectory) {
        const dirEntry = entry as FileSystemDirectoryEntry;
        const reader = dirEntry.createReader();
        const entries = await new Promise<FileSystemEntry[]>((resolve) => {
          const results: FileSystemEntry[] = [];
          const readBatch = () => {
            reader.readEntries((batch) => {
              if (batch.length === 0) {
                resolve(results);
              } else {
                results.push(...batch);
                readBatch();
              }
            });
          };
          readBatch();
        });
        for (const child of entries) {
          const childPath = path ? `${path}/${entry.name}` : entry.name;
          files.push(...(await readEntryAsFiles(child, childPath, onProgress)));
        }
      }
      return files;
    },
    [],
  );

  const handleDrop = useCallback(
    async (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounterRef.current = 0;
      setIsDraggingOver(false);

      if (isReadingFolder || isUploadingFiles || effectiveLifecycleState.isBusy) return;
      const items = e.dataTransfer.items;
      if (!items || items.length === 0) return;

      setIsReadingFolder(true);
      setFolderScanError(null);
      setReadProgress({ current: 0, total: 0 });
      try {
        const files: File[] = [];
        let count = 0;
        for (const item of items) {
          const entry = item.webkitGetAsEntry();
          if (entry) {
            const entryFiles = await readEntryAsFiles(entry, "", (n) => {
              count += n;
              setReadProgress({ current: count, total: 0 });
            });
            files.push(...entryFiles);
          }
        }
        setReadProgress(null);
        if (files.length === 0) {
          setFolderScanError('未能读取文件夹内容，请尝试使用"选择文件夹"按钮');
          return;
        }
        setWebFolderFiles(files);
        setSelectedFolderPath(null);
        const tree = buildFolderTreeFromFiles(files);
        setFolderTree(tree);
        setSelectedImportFiles(applyDefaultExclusions(files));
        setFolderImportExpanded(true);
      } catch (err) {
        setFolderScanError(err instanceof Error ? err.message : "读取文件夹失败");
      } finally {
        setIsReadingFolder(false);
      }
    },
    [isReadingFolder],
  );

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDragEnter = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (effectiveLifecycleState.isBusy || isScanningFolder) return;
    dragCounterRef.current += 1;
    if (dragCounterRef.current === 1) {
      setIsDraggingOver(true);
    }
  }, [effectiveLifecycleState.isBusy, isScanningFolder]);

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current -= 1;
    if (dragCounterRef.current === 0) {
      setIsDraggingOver(false);
    }
  }, []);

  // 拖拽结束时清理（防止 dragleave 未触发导致状态卡住）
  useEffect(() => {
    return () => {
      dragCounterRef.current = 0;
      setIsDraggingOver(false);
    };
  }, []);

  // 模板是否有推荐能力
  const hasRecommendedCapabilities =
    selectedTemplate &&
    selectedTemplate.template_id !== "blank-workspace" &&
    (selectedTemplate.recommended_capabilities?.length ?? 0) > 0;

  const handleConfirm = async () => {
    const choice: EnvChoice =
      envKind === "registered" && selectedRegisteredEnv?.executable
        ? {
            kind: "registered",
            kernelName: selectedRegisteredEnv.name,
            pythonExecutable: selectedRegisteredEnv.executable,
          }
        : { kind: envKind === "uv" ? "uv" : "none" };

    if (creationMode === "folder") {
      if (!isDesktop) {
        // Web 版：先上传文件，再创建
        const filesToUpload = webFolderFiles.filter((f) => {
          const relPath = f.webkitRelativePath || f.name;
          return selectedImportFiles.has(relPath);
        });
        if (filesToUpload.length === 0) {
          setFolderScanError("请至少选择一个文件");
          return;
        }
        setIsUploadingFiles(true);
        setUploadProgress(0);
        try {
          const result = await uploadImportFolder(filesToUpload, (percent) => {
            setUploadProgress(percent);
          });
          await onConfirm(trimmedTitle, trimmedDescription || undefined, choice, {
            tempUploadId: result.upload_id,
            importFiles: Array.from(selectedImportFiles),
          });
        } catch (err) {
          setFolderScanError(err instanceof Error ? err.message : "上传文件失败");
        } finally {
          setIsUploadingFiles(false);
        }
        return;
      }

      void onConfirm(trimmedTitle, trimmedDescription || undefined, choice, {
        sourceFolderPath: selectedFolderPath ?? undefined,
        importFiles: Array.from(selectedImportFiles),
      });
      return;
    }

    void onConfirm(trimmedTitle, trimmedDescription || undefined, choice, {
      templateId: selectedTemplateId === "blank-workspace" ? undefined : selectedTemplateId,
      initialConversationTitle: selectedTemplate?.initial_conversation_title,
      installCapabilities: Array.from(selectedCapabilities),
      templateFiles:
        selectedTemplateId === "blank-workspace" ? undefined : Array.from(selectedTemplateFiles),
    });
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
            progress={effectiveLifecycleState.progress}
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

          {/* 创建方式选择 */}
          <div className="space-y-2">
            <Label>创建方式</Label>
            <RadioGroup
              value={creationMode}
              onValueChange={(value) => setCreationMode(value as CreationMode)}
              className="gap-2"
              disabled={effectiveLifecycleState.isBusy}
            >
              <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-border bg-background px-3 py-2">
                <RadioGroupItem value="blank" className="mt-0.5" />
                <span className="min-w-0">
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <FolderPlus className="h-4 w-4 text-muted-foreground" />
                    空白任务
                  </span>
                  <span className="mt-0.5 block text-xs leading-5 text-muted-foreground">
                    创建一个空工作区，适合从零开始的任务。
                  </span>
                </span>
              </label>
              <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-border bg-background px-3 py-2">
                <RadioGroupItem value="template" className="mt-0.5" />
                <span className="min-w-0">
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <FileText className="h-4 w-4 text-muted-foreground" />
                    从模板创建
                  </span>
                  <span className="mt-0.5 block text-xs leading-5 text-muted-foreground">
                    基于模板预置文件和能力快速开始。
                  </span>
                </span>
              </label>
              <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-border bg-background px-3 py-2">
                <RadioGroupItem value="folder" className="mt-0.5" />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <Folder className="h-4 w-4 text-muted-foreground" />
                    从文件夹导入
                  </span>
                  <span className="mt-0.5 block text-xs leading-5 text-muted-foreground">
                    选择本地文件夹，复制到工作区。原文件夹不会被修改。
                  </span>
                </span>
              </label>
            </RadioGroup>
          </div>

          {/* 文件夹导入区域 */}
          {creationMode === "folder" && (
            <div
              className={cn(
                "rounded-lg border-2 border-dashed border-border bg-muted/10 p-5 text-center transition-colors",
                isDraggingOver && "border-primary/50 bg-primary/5",
              )}
              onDragOver={handleDragOver}
              onDragEnter={handleDragEnter}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              {/* 拖拽悬浮提示 */}
              {isDraggingOver && (
                <div className="flex items-center justify-center gap-2 py-2 text-sm font-medium text-primary">
                  <Upload className="h-5 w-5" />
                  释放以导入文件夹
                </div>
              )}

              {/* 读取进度 */}
              {isReadingFolder && (
                <div className="space-y-2">
                  <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    正在读取文件夹...
                    {readProgress && readProgress.current > 0 && (
                      <span>{readProgress.current} 个文件</span>
                    )}
                  </div>
                  <div className="mx-auto h-1.5 w-48 rounded-full bg-muted">
                    <div className="h-1.5 rounded-full bg-primary/60 animate-pulse" />
                  </div>
                </div>
              )}

              {/* 常态提示 */}
              {!isReadingFolder && !isDraggingOver && !selectedFolderPath && webFolderFiles.length === 0 && (
                <div className="space-y-3 py-2">
                  <Folder className="mx-auto h-8 w-8 text-muted-foreground/50" />
                  <p className="text-xs text-muted-foreground">
                    拖拽文件夹到此处，或点击下方按钮选择
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleSelectFolder}
                    disabled={effectiveLifecycleState.isBusy || isScanningFolder || isUploadingFiles}
                  >
                    {isScanningFolder ? (
                      <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <FolderOpen className="mr-2 h-3.5 w-3.5" />
                    )}
                    选择文件夹
                  </Button>
                </div>
              )}

              {/* 已选择提示（有文件时显示在拖拽区底部） */}
              {(selectedFolderPath || webFolderFiles.length > 0) && !isReadingFolder && (
                <div className="text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">已选择：</span>
                  {selectedFolderPath ?? webFolderFiles[0]?.webkitRelativePath.split("/")[0] ?? "文件夹"}
                  {webFolderFiles.length > 1 && (
                    <span className="ml-1 text-[10px]">(+{webFolderFiles.length - 1} 个文件夹)</span>
                  )}
                  <span className="ml-1 text-[10px]">
                    ({webFolderFiles.length} 个文件)
                  </span>
                </div>
              )}

              {isUploadingFiles && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>正在上传文件...</span>
                    <span>{uploadProgress}%</span>
                  </div>
                  <div className="h-1.5 w-full rounded-full bg-muted">
                    <div
                      className="h-1.5 rounded-full bg-primary transition-all"
                      style={{ width: `${uploadProgress}%` }}
                    />
                  </div>
                </div>
              )}

              {folderScanError && (
                <div className="text-xs text-red-500">{folderScanError}</div>
              )}

              <input
                ref={fileInputRef}
                type="file"
                // @ts-expect-error webkitdirectory not in React HTMLInputElement types
                webkitdirectory=""
                directory=""
                className="hidden"
                onChange={handleWebFolderChange}
              />

              {folderTree.length > 0 && (
                <div className="overflow-hidden rounded-lg border border-border">
                  <button
                    type="button"
                    onClick={() => setFolderImportExpanded((v) => !v)}
                    className="flex w-full items-center justify-between border-b border-border bg-muted/40 px-3 py-1.5 text-left"
                  >
                    <span className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
                      <FileText className="h-3 w-3" />
                      选择要导入的文件
                      <span className="text-[10px] text-muted-foreground/70">
                        ({selectedImportFiles.size} 项已选)
                      </span>
                    </span>
                    {folderImportExpanded ? (
                      <ChevronUp className="h-3 w-3 text-muted-foreground" />
                    ) : (
                      <ChevronDown className="h-3 w-3 text-muted-foreground" />
                    )}
                  </button>
                  {folderImportExpanded && (
                    <div className="max-h-60 overflow-y-auto px-2 py-2">
                      <TemplateFileTreeSelector
                        files={folderTreeFiles}
                        selectedPaths={selectedImportFiles}
                        onSelectionChange={setSelectedImportFiles}
                      />
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

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
                    {selectableRegisteredEnvs.length === 0
                      ? "当前没有可用的已登记 Python，请先在执行资源中登记本机解释器。"
                      : "绑定本机已登记解释器。依赖安装会影响该解释器对应环境。"}
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

          {creationMode === "template" && (
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
          )}
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
