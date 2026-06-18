/**
 * UnifiedDocumentUploadDialog
 *
 * 统一文档入口：用户只需选择一次文件，就能同时导入到知识库（分块+向量/全文索引）
 * 和知识图谱（实体/关系抽取），而不必在两个独立工具箱之间重复上传。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BookOpen,
  CheckCircle2,
  FileCog,
  Loader2,
  Network,
  Upload,
  X,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { knowledgeApi } from "@/lib/api/knowledge";
import { createGraphragApi } from "@/lib/api/graphrag";
import { getModelDefaults, getModels, type LLMModelConfig } from "@/lib/api/llm";
import type {
  Document,
  KnowledgeBase,
  KnowledgeBaseExtractionMode,
  KnowledgeBaseSearchMode,
} from "@/types/knowledge";
import type { GraphExtractionMode } from "@/types/graphrag";
import {
  SEARCH_MODE_OPTIONS,
  EXTRACTION_MODE_OPTIONS,
  normalizeSearchMode,
} from "@/components/KnowledgeBaseMarket/constants";
import { formatEmbeddingModel, formatFileSize, getFileIcon } from "@/components/KnowledgeBaseMarket/utils";

type UploadTarget = "knowledge_base" | "knowledge_graph";

interface FileResult {
  filename: string;
  target: UploadTarget;
  success: boolean;
  message: string;
}

interface UnifiedDocumentUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspaceId?: string | null;
  graphId?: string | null;
  /** 上传成功后的回调，用于刷新外部列表 */
  onUploaded?: () => void;
}

const GRAPH_EXTRACTION_OPTIONS: Array<{
  value: GraphExtractionMode;
  label: string;
}> = [
  { value: "basic", label: "basic" },
  { value: "enhanced", label: "enhanced" },
  { value: "docling", label: "docling" },
];

const ACCEPTED_FILE_TYPES =
  ".txt,.md,.markdown,.pdf,.doc,.docx,.xlsx,.xlsm,.csv,.json,.yaml,.yml,.toml,.ini,.log";

function isKbReady(kb: KnowledgeBase | null): boolean {
  return Boolean(kb?.config_complete) && kb?.init_status === "ready";
}

export function UnifiedDocumentUploadDialog({
  open,
  onOpenChange,
  workspaceId,
  graphId,
  onUploaded,
}: UnifiedDocumentUploadDialogProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // ── 文件列表 ──
  const [files, setFiles] = useState<File[]>([]);

  // ── 目标选择 ──
  const [targets, setTargets] = useState<Set<UploadTarget>>(
    new Set(["knowledge_base", "knowledge_graph"]),
  );

  // ── 知识库配置 ──
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [isLoadingKBs, setIsLoadingKBs] = useState(false);
  const [selectedKBId, setSelectedKBId] = useState<string>("");
  const [kbDocuments, setKbDocuments] = useState<Document[]>([]);
  const [embeddingModels, setEmbeddingModels] = useState<LLMModelConfig[]>([]);
  const [defaultEmbeddingModelId, setDefaultEmbeddingModelId] = useState<string | null>(null);

  // ── 共享配置 ──
  const [extractionMode, setExtractionMode] = useState<KnowledgeBaseExtractionMode>("enhanced");

  // ── 知识库索引配置 ──
  const [searchMode, setSearchMode] = useState<KnowledgeBaseSearchMode>("fulltext");
  const [chunkSize, setChunkSize] = useState("512");
  const [chunkOverlap, setChunkOverlap] = useState("50");
  const [embeddingModel, setEmbeddingModel] = useState("");

  // ── 图谱配置 ──
  const [graphExtractionMode, setGraphExtractionMode] = useState<GraphExtractionMode>("enhanced");
  const [resolveEntities, setResolveEntities] = useState(true);

  // ── 上传状态 ──
  const [isUploading, setIsUploading] = useState(false);
  const [results, setResults] = useState<FileResult[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const selectedKB = useMemo(
    () => knowledgeBases.find((kb) => kb.id === selectedKBId) ?? null,
    [knowledgeBases, selectedKBId],
  );

  const kbReady = isKbReady(selectedKB);
  const canEditIndexConfig = selectedKB?.can_edit_index_config ?? (kbDocuments.length === 0);

  // ── 加载知识库列表 ──
  const loadKnowledgeBases = useCallback(async () => {
    setIsLoadingKBs(true);
    try {
      const data = await knowledgeApi.listKnowledgeBases();
      setKnowledgeBases(data);
      // 自动选中第一个 ready 的知识库
      const firstReady = data.find((kb) => isKbReady(kb));
      setSelectedKBId(firstReady?.id ?? data[0]?.id ?? "");
    } catch (err) {
      console.error("加载知识库列表失败:", err);
    } finally {
      setIsLoadingKBs(false);
    }
  }, []);

  // ── 加载 embedding 模型列表 ──
  const loadEmbeddingModels = useCallback(async () => {
    try {
      const [modelsResponse, defaults] = await Promise.all([
        getModels(true),
        getModelDefaults(),
      ]);
      setEmbeddingModels(
        modelsResponse.models.filter((model) => model.model_type === "embedding"),
      );
      setDefaultEmbeddingModelId(defaults.default_embedding_model);
    } catch (err) {
      console.error("加载 embedding 模型失败:", err);
      setEmbeddingModels([]);
      setDefaultEmbeddingModelId(null);
    }
  }, []);

  // ── 加载选中知识库的文档列表（用于判断 can_edit_index_config） ──
  useEffect(() => {
    if (!open || !selectedKBId) {
      setKbDocuments([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const docs = await knowledgeApi.listDocuments(selectedKBId);
        if (!cancelled) setKbDocuments(docs);
      } catch {
        if (!cancelled) setKbDocuments([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, selectedKBId]);

  // ── 对话框打开时加载数据 ──
  useEffect(() => {
    if (!open) return;
    void loadKnowledgeBases();
    void loadEmbeddingModels();
    // 重置状态
    setFiles([]);
    setResults([]);
    setUploadError(null);
  }, [open, loadKnowledgeBases, loadEmbeddingModels]);

  // ── 选中知识库后同步索引配置 ──
  useEffect(() => {
    if (!selectedKB) return;
    setSearchMode(normalizeSearchMode(selectedKB.default_search_mode));
    setChunkSize(String(selectedKB.chunk_size || 512));
    setChunkOverlap(String(selectedKB.chunk_overlap || 50));
    setEmbeddingModel(selectedKB.embedding_model || defaultEmbeddingModelId || "");
    setExtractionMode(
      (selectedKB.default_extraction_mode as KnowledgeBaseExtractionMode) || "enhanced",
    );
  }, [selectedKB, defaultEmbeddingModelId]);

  // ── 文件选择 ──
  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(e.target.files ?? []);
    setFiles((prev) => {
      const existing = new Set(prev.map((f) => f.name));
      return [...prev, ...selected.filter((f) => !existing.has(f.name))];
    });
    e.target.value = "";
  }, []);

  const handleRemoveFile = useCallback((fileName: string) => {
    setFiles((prev) => prev.filter((f) => f.name !== fileName));
  }, []);

  const toggleTarget = useCallback((target: UploadTarget) => {
    setTargets((prev) => {
      const next = new Set(prev);
      if (next.has(target)) {
        // 至少保留一个目标
        if (next.size > 1) next.delete(target);
      } else {
        next.add(target);
      }
      return next;
    });
  }, []);

  // ── 上传执行 ──
  const handleUpload = useCallback(async () => {
    if (files.length === 0 || isUploading) return;

    const wantKB = targets.has("knowledge_base");
    const wantGraph = targets.has("knowledge_graph");

    if (wantKB && !selectedKBId) {
      setUploadError("请先选择一个知识库");
      return;
    }
    if (wantKB && selectedKB && !kbReady) {
      setUploadError(selectedKB.config_issue || "选中的知识库尚未就绪，请先完成配置");
      return;
    }

    setIsUploading(true);
    setUploadError(null);
    setResults([]);

    const fileResults: FileResult[] = [];
    const graphApi = wantGraph
      ? createGraphragApi({ workspaceId: workspaceId || undefined, graphId: graphId || undefined })
      : null;

    const parsedChunkSize = Number.parseInt(chunkSize, 10) || (selectedKB?.chunk_size || 512);
    const parsedChunkOverlap = Number.parseInt(chunkOverlap, 10) || (selectedKB?.chunk_overlap || 50);

    for (const file of files) {
      // ── 知识库上传 ──
      if (wantKB && selectedKBId) {
        try {
          await knowledgeApi.uploadDocuments(selectedKBId, [file], {
            extraction_mode: extractionMode,
            embedding_model: kbDocuments.length === 0 ? embeddingModel : undefined,
            chunk_size: parsedChunkSize,
            chunk_overlap: parsedChunkOverlap,
            search_mode: searchMode,
          });
          fileResults.push({
            filename: file.name,
            target: "knowledge_base",
            success: true,
            message: "已导入知识库",
          });
        } catch (err) {
          fileResults.push({
            filename: file.name,
            target: "knowledge_base",
            success: false,
            message: err instanceof Error ? err.message : "导入知识库失败",
          });
        }
      }

      // ── 知识图谱上传 ──
      if (wantGraph && graphApi) {
        try {
          const response = await graphApi.uploadDocument(file, {
            resolve_entities: resolveEntities,
            extraction_mode: graphExtractionMode,
          });
          fileResults.push({
            filename: file.name,
            target: "knowledge_graph",
            success: true,
            message: `已构图：${response.entity_count} 实体、${response.relation_count} 关系`,
          });
        } catch (err) {
          fileResults.push({
            filename: file.name,
            target: "knowledge_graph",
            success: false,
            message: err instanceof Error ? err.message : "导入知识图谱失败",
          });
        }
      }
    }

    setResults(fileResults);
    setIsUploading(false);

    // 全部成功则清空文件列表并通知外部刷新
    const allSuccess = fileResults.length > 0 && fileResults.every((r) => r.success);
    if (allSuccess) {
      setFiles([]);
      onUploaded?.();
    }
  }, [
    files,
    isUploading,
    targets,
    selectedKBId,
    selectedKB,
    kbReady,
    workspaceId,
    graphId,
    chunkSize,
    chunkOverlap,
    extractionMode,
    embeddingModel,
    kbDocuments.length,
    searchMode,
    resolveEntities,
    graphExtractionMode,
    onUploaded,
  ]);

  const canUpload = files.length > 0 && !isUploading && targets.size > 0;

  return (
    <Dialog open={open} onOpenChange={(v) => !isUploading && onOpenChange(v)}>
      <DialogContent
        className="flex max-h-[90vh] flex-col overflow-hidden p-0 sm:max-w-[680px]"
        data-testid="unified-document-upload-dialog"
      >
        <DialogHeader className="shrink-0 px-6 pt-6">
          <DialogTitle className="flex items-center gap-2">
            <Upload className="h-5 w-5" />
            导入文档
          </DialogTitle>
          <DialogDescription>
            一次选择文件，同时导入到知识库和知识图谱，无需重复上传。
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-6 py-4">
          {/* ── 文件选择区 ── */}
          <input
            type="file"
            multiple
            className="hidden"
            ref={fileInputRef}
            accept={ACCEPTED_FILE_TYPES}
            onChange={handleFileSelect}
          />
          <Button
            variant="outline"
            className="h-24 w-full border-dashed"
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
          >
            <div className="flex flex-col items-center gap-2">
              <Upload className="h-6 w-6" />
              <span>点击选择文件（支持多选）</span>
            </div>
          </Button>

          {files.length > 0 ? (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">已选择 {files.length} 个文件</span>
                {!isUploading ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setFiles([])}
                  >
                    清空
                  </Button>
                ) : null}
              </div>
              <div className="max-h-[160px] space-y-2 overflow-y-auto">
                {files.map((file) => (
                  <div
                    key={file.name}
                    className="flex items-center gap-3 rounded-lg border border-border bg-muted/40 p-2"
                  >
                    {getFileIcon(file.name)}
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm">{file.name}</p>
                      <p className="text-xs text-muted-foreground">{formatFileSize(file.size)}</p>
                    </div>
                    {!isUploading ? (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        onClick={() => handleRemoveFile(file.name)}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {/* ── 目标选择 ── */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">导入目标</Label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => toggleTarget("knowledge_base")}
                className={cn(
                  "flex items-start gap-3 rounded-xl border p-4 text-left transition-colors",
                  targets.has("knowledge_base")
                    ? "border-primary bg-primary/5"
                    : "border-border bg-muted/40 hover:bg-muted/60",
                )}
              >
                <Checkbox
                  checked={targets.has("knowledge_base")}
                  onCheckedChange={() => toggleTarget("knowledge_base")}
                  className="mt-0.5"
                />
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 text-sm font-medium">
                    <BookOpen className="h-4 w-4 text-tertiary" />
                    知识库
                  </div>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    分块索引，支持全文/向量/混合检索
                  </p>
                </div>
              </button>

              <button
                type="button"
                onClick={() => toggleTarget("knowledge_graph")}
                className={cn(
                  "flex items-start gap-3 rounded-xl border p-4 text-left transition-colors",
                  targets.has("knowledge_graph")
                    ? "border-primary bg-primary/5"
                    : "border-border bg-muted/40 hover:bg-muted/60",
                )}
              >
                <Checkbox
                  checked={targets.has("knowledge_graph")}
                  onCheckedChange={() => toggleTarget("knowledge_graph")}
                  className="mt-0.5"
                />
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 text-sm font-medium">
                    <Network className="h-4 w-4 text-tertiary" />
                    知识图谱
                  </div>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    抽取实体和关系，构建知识网络
                  </p>
                </div>
              </button>
            </div>
          </div>

          {/* ── 知识库配置 ── */}
          {targets.has("knowledge_base") ? (
            <div className="space-y-4 rounded-xl border border-border bg-muted/30 p-4">
              <div className="flex items-center gap-2 text-sm font-medium">
                <BookOpen className="h-4 w-4 text-tertiary" />
                知识库配置
              </div>

              <div className="space-y-2">
                <Label className="text-xs text-muted-foreground">目标知识库</Label>
                {isLoadingKBs ? (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    加载中...
                  </div>
                ) : knowledgeBases.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    暂无可用知识库，请先创建。
                  </p>
                ) : (
                  <Select
                    value={selectedKBId || "__none__"}
                    onValueChange={(value) =>
                      setSelectedKBId(value === "__none__" ? "" : value)
                    }
                    disabled={isUploading}
                  >
                    <SelectTrigger data-testid="unified-upload-kb-select">
                      <SelectValue placeholder="选择知识库" />
                    </SelectTrigger>
                    <SelectContent>
                      {knowledgeBases.map((kb) => (
                        <SelectItem key={kb.id} value={kb.id}>
                          {kb.name}
                          {!isKbReady(kb) ? "（未就绪）" : ""}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
                {selectedKB && !kbReady ? (
                  <p className="text-xs text-error">
                    {selectedKB.config_issue || "该知识库尚未就绪"}
                  </p>
                ) : null}
              </div>

              {selectedKB ? (
                <>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-2">
                      <Label className="text-xs text-muted-foreground">解析策略</Label>
                      <Select
                        value={extractionMode}
                        onValueChange={(value) =>
                          setExtractionMode(value as KnowledgeBaseExtractionMode)
                        }
                        disabled={isUploading}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {EXTRACTION_MODE_OPTIONS.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label className="text-xs text-muted-foreground">检索策略</Label>
                      <Select
                        value={searchMode}
                        onValueChange={(value) =>
                          setSearchMode(value as KnowledgeBaseSearchMode)
                        }
                        disabled={isUploading}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {SEARCH_MODE_OPTIONS.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  {canEditIndexConfig ? (
                    <div className="space-y-2">
                      <Label className="text-xs text-muted-foreground">Embedding 模型</Label>
                      <Select
                        value={embeddingModel || "__none__"}
                        onValueChange={(value) =>
                          setEmbeddingModel(value === "__none__" ? "" : value)
                        }
                        disabled={isUploading}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="选择 embedding 模型" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__none__">不指定</SelectItem>
                          {embeddingModels.map((model) => (
                            <SelectItem key={model.id} value={model.id}>
                              {formatEmbeddingModel(model)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <p className="text-xs leading-5 text-muted-foreground">
                        {kbDocuments.length > 0
                          ? "已有文档后不能切换 embedding 模型。"
                          : "空知识库可在首次导入前指定 embedding 模型。"}
                      </p>
                    </div>
                  ) : null}

                  {canEditIndexConfig ? (
                    <div className="grid grid-cols-2 gap-3">
                      <div className="space-y-2">
                        <Label className="text-xs text-muted-foreground">分块大小</Label>
                        <Input
                          type="number"
                          min={64}
                          max={8192}
                          value={chunkSize}
                          onChange={(e) => setChunkSize(e.target.value)}
                          disabled={isUploading}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-xs text-muted-foreground">重叠</Label>
                        <Input
                          type="number"
                          min={0}
                          max={4096}
                          value={chunkOverlap}
                          onChange={(e) => setChunkOverlap(e.target.value)}
                          disabled={isUploading}
                        />
                      </div>
                    </div>
                  ) : null}
                </>
              ) : null}
            </div>
          ) : null}

          {/* ── 知识图谱配置 ── */}
          {targets.has("knowledge_graph") ? (
            <div className="space-y-4 rounded-xl border border-border bg-muted/30 p-4">
              <div className="flex items-center gap-2 text-sm font-medium">
                <Network className="h-4 w-4 text-tertiary" />
                知识图谱配置
              </div>

              {graphId ? (
                <div className="flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-xs text-muted-foreground">
                  <FileCog className="h-3.5 w-3.5" />
                  目标图谱：<span className="font-medium text-foreground">{graphId}</span>
                  {workspaceId ? (
                    <span className="text-muted-foreground/60">（工作区 {workspaceId}）</span>
                  ) : null}
                </div>
              ) : (
                <Alert>
                  <AlertDescription>
                    当前没有选中的知识图谱。请先从工作区侧边栏打开一个图谱资产，或在 URL 中指定 graph_id。
                  </AlertDescription>
                </Alert>
              )}

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label className="text-xs text-muted-foreground">解析模式</Label>
                  <Select
                    value={graphExtractionMode}
                    onValueChange={(value) =>
                      setGraphExtractionMode(value as GraphExtractionMode)
                    }
                    disabled={isUploading}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {GRAPH_EXTRACTION_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="flex items-center gap-3 rounded-lg border border-border bg-background px-3 py-2.5">
                <Checkbox
                  id="unified-upload-resolve-entities"
                  checked={resolveEntities}
                  onCheckedChange={(checked) => setResolveEntities(checked === true)}
                  disabled={isUploading}
                />
                <Label
                  htmlFor="unified-upload-resolve-entities"
                  className="cursor-pointer text-sm text-muted-foreground"
                >
                  自动实体消歧（合并同义实体）
                </Label>
              </div>
            </div>
          ) : null}

          {/* ── 上传错误 ── */}
          {uploadError ? (
            <Alert variant="destructive">
              <XCircle className="h-4 w-4" />
              <AlertDescription>{uploadError}</AlertDescription>
            </Alert>
          ) : null}

          {/* ── 上传结果 ── */}
          {results.length > 0 ? (
            <div className="space-y-2 rounded-xl border border-border bg-background p-3">
              <div className="text-sm font-medium text-foreground">导入结果</div>
              <div className="max-h-[200px] space-y-1.5 overflow-y-auto">
                {results.map((result, index) => (
                  <div
                    key={`${result.filename}-${result.target}-${index}`}
                    className={cn(
                      "flex items-start gap-2 rounded-lg border px-3 py-2 text-sm",
                      result.success
                        ? "border-success/20 bg-success-container/50 text-success"
                        : "border-destructive/20 bg-destructive/5 text-destructive",
                    )}
                  >
                    {result.success ? (
                      <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    ) : (
                      <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    )}
                    <div className="min-w-0 flex-1">
                      <span className="font-medium">{result.filename}</span>
                      <span className="ml-1.5 text-xs opacity-70">
                        {result.target === "knowledge_base" ? "知识库" : "知识图谱"}
                      </span>
                      <p className="mt-0.5 text-xs">{result.message}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <DialogFooter className="shrink-0 px-6 py-4">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isUploading}
          >
            取消
          </Button>
          <Button
            onClick={() => void handleUpload()}
            disabled={!canUpload}
          >
            {isUploading ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Upload className="mr-2 h-4 w-4" />
            )}
            开始导入
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
