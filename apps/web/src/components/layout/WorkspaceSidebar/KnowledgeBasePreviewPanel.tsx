import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BookOpen,
  CircleAlert,
  Clock,
  Database,
  FileText,
  Loader2,
  Search,
  Settings,
  Trash2,
  Upload,
} from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import knowledgeApi from "@/lib/api/knowledge";
import { getModelDefaults, getModels, type LLMModelConfig } from "@/lib/api/llm";
import { SqlQueryPanel } from "@/components/database/SqlQueryPanel";
import type {
  QueryResult,
  KnowledgeBaseTableInfo,
  KnowledgeBaseRawQueryResponse,
  Document,
  KnowledgeBase,
  KnowledgeBaseSearchMode,
  KnowledgeBaseExtractionMode,
  UpdateKnowledgeBaseRequest,
} from "@/types/knowledge";
import { getNumber, getText } from "./ResourcePreviewShared";
import { CanvasActionMenu } from "@/components/workspace/CanvasActionMenu";

type KbTab = "documents" | "search" | "settings" | "data";

interface KnowledgeResourceNode {
  name: string;
  path: string;
  meta?: Record<string, unknown>;
}

interface KnowledgeBasePreviewPanelProps {
  node: KnowledgeResourceNode;
  onRefresh?: () => Promise<void> | void;
  onClose?: () => void;
  closeLabel?: string;
  onSplitRight?: () => void;
  onSplitDown?: () => void;
}

const SEARCH_MODE_OPTIONS: Array<{ value: KnowledgeBaseSearchMode; label: string }> = [
  { value: "fulltext", label: "全文" },
  { value: "vector", label: "向量" },
  { value: "hybrid", label: "混合" },
];

const EXTRACTION_MODE_OPTIONS: Array<{ value: KnowledgeBaseExtractionMode; label: string }> = [
  { value: "enhanced", label: "增强" },
  { value: "basic", label: "基础" },
  { value: "docling", label: "Docling" },
];

function normalizeSearchMode(value?: string | null): KnowledgeBaseSearchMode {
  if (value === "vector" || value === "hybrid" || value === "fulltext") {
    return value;
  }
  return "fulltext";
}

function formatEmbeddingModel(model: LLMModelConfig): string {
  const dimension = typeof model.dimension === "number" ? ` · ${model.dimension}维` : "";
  return `${model.name || model.model}${dimension}`;
}

function toPositiveInteger(value: string, fallback: number): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function getStatusBadge(status?: string): { label: string; className: string } {
  switch (status) {
    case "draft":
      return {
        label: "待配置",
        className: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-400",
      };
    case "indexing":
      return {
        label: "索引中",
        className: "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-400",
      };
    case "needs_reindex":
      return {
        label: "需重建",
        className: "border-orange-200 bg-orange-50 text-orange-700 dark:border-orange-900 dark:bg-orange-950/30 dark:text-orange-400",
      };
    case "error":
      return {
        label: "异常",
        className: "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400",
      };
    default:
      return {
        label: "可使用",
        className: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-400",
      };
  }
}

export function KnowledgeBasePreviewPanel({
  node,
  onRefresh,
  onClose,
  closeLabel = "返回文件资产",
  onSplitRight,
  onSplitDown,
}: KnowledgeBasePreviewPanelProps) {
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const [activeTab, setActiveTab] = useState<KbTab>("documents");
  const [queryText, setQueryText] = useState("");
  const [queryResults, setQueryResults] = useState<QueryResult[]>([]);
  const [isQuerying, setIsQuerying] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [searchMode, setSearchMode] = useState<"fulltext" | "vector" | "hybrid">(() => {
    try {
      const saved = localStorage.getItem("kb-search-mode");
      if (saved === "fulltext" || saved === "vector" || saved === "hybrid") return saved;
    } catch { /* ignore */ }
    return "fulltext";
  });
  const [isUploading, setIsUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [knowledgeBase, setKnowledgeBase] = useState<KnowledgeBase | null>(null);
  const [isLoadingKnowledgeBase, setIsLoadingKnowledgeBase] = useState(false);
  const [knowledgeBaseError, setKnowledgeBaseError] = useState<string | null>(null);
  const [embeddingModels, setEmbeddingModels] = useState<LLMModelConfig[]>([]);
  const [defaultEmbeddingModelId, setDefaultEmbeddingModelId] = useState<string | null>(null);
  const [isLoadingModels, setIsLoadingModels] = useState(false);

  // 设置 Tab 编辑状态
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editEmbeddingModel, setEditEmbeddingModel] = useState("");
  const [editSearchMode, setEditSearchMode] = useState<KnowledgeBaseSearchMode>("fulltext");
  const [editExtractionMode, setEditExtractionMode] = useState<KnowledgeBaseExtractionMode>("enhanced");
  const [editExtractionMapping, setEditExtractionMapping] = useState<Record<string, string>>({});
  const [editChunkSize, setEditChunkSize] = useState("512");
  const [editChunkOverlap, setEditChunkOverlap] = useState("50");
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  // 原始数据 Tab 状态
  const [kbTables, setKbTables] = useState<KnowledgeBaseTableInfo[]>([]);
  const [loadingKbTables, setLoadingKbTables] = useState(false);
  const [rawSql, setRawSql] = useState('SELECT chunk_id, document_id, chunk_index FROM "chunks" LIMIT 100;');
  const [rawQueryLimit, setRawQueryLimit] = useState("100");
  const [rawRunning, setRawRunning] = useState(false);
  const [rawError, setRawError] = useState<string | null>(null);
  const [rawResult, setRawResult] = useState<KnowledgeBaseRawQueryResponse | null>(null);

  // 文档列表状态
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [docDeleteError, setDocDeleteError] = useState<string | null>(null);
  const [deleteAlertOpen, setDeleteAlertOpen] = useState(false);
  const [docToDelete, setDocToDelete] = useState<string | null>(null);

  const knowledgeBaseId = useMemo(() => {
    const fromMeta = getText(node.meta?.id);
    if (fromMeta) {
      return fromMeta;
    }
    const pathParts = node.path.split("/").filter(Boolean);
    return pathParts[pathParts.length - 1] ?? "";
  }, [node.meta, node.path]);

  const description = getText(node.meta?.description);
  const documentCount = knowledgeBase?.document_count ?? getNumber(node.meta?.document_count) ?? documents.length;
  const effectiveDescription = knowledgeBase?.description ?? description;
  const canUseKnowledgeBase = Boolean(knowledgeBase?.config_complete) && knowledgeBase?.init_status === "ready";
  const canEditIndexConfig = knowledgeBase?.can_edit_index_config ?? documents.length === 0;
  const statusBadge = getStatusBadge(knowledgeBase?.init_status);
  const currentEmbeddingModel = knowledgeBase?.embedding_model
    ? embeddingModels.find((model) => model.id === knowledgeBase.embedding_model) || null
    : null;
  const currentEmbeddingLabel = knowledgeBase?.embedding_model
    ? currentEmbeddingModel
      ? formatEmbeddingModel(currentEmbeddingModel)
      : knowledgeBase.embedding_model
    : defaultEmbeddingModelId
      ? "跟随默认 embedding"
      : "未配置";
  const currentEmbeddingOption = editEmbeddingModel || "__default__";

  const refreshKnowledgeBase = useCallback(async () => {
    if (!knowledgeBaseId) {
      setKnowledgeBase(null);
      return null;
    }
    setIsLoadingKnowledgeBase(true);
    setKnowledgeBaseError(null);
    try {
      const detail = await knowledgeApi.getKnowledgeBase(knowledgeBaseId);
      setKnowledgeBase(detail);
      setEditName(detail.name);
      setEditDescription(detail.description ?? "");
      setEditEmbeddingModel(detail.embedding_model || "");
      setEditSearchMode(normalizeSearchMode(detail.default_search_mode));
      setEditExtractionMode((detail.default_extraction_mode as KnowledgeBaseExtractionMode) || "enhanced");
      setEditExtractionMapping(detail.extraction_mode_mapping || {});
      setEditChunkSize(String(detail.chunk_size || 512));
      setEditChunkOverlap(String(detail.chunk_overlap || 50));
      setSearchMode(normalizeSearchMode(detail.default_search_mode));
      return detail;
    } catch (err) {
      setKnowledgeBaseError(err instanceof Error ? err.message : "加载知识库配置失败");
      return null;
    } finally {
      setIsLoadingKnowledgeBase(false);
    }
  }, [knowledgeBaseId]);

  useEffect(() => {
    void refreshKnowledgeBase();
  }, [refreshKnowledgeBase]);

  useEffect(() => {
    let cancelled = false;

    async function loadModels() {
      setIsLoadingModels(true);
      try {
        const [modelsResponse, defaults] = await Promise.all([
          getModels(true),
          getModelDefaults(),
        ]);
        if (cancelled) return;
        setEmbeddingModels(
          modelsResponse.models.filter((model) => model.model_type === "embedding"),
        );
        setDefaultEmbeddingModelId(defaults.default_embedding_model);
      } catch (err) {
        if (cancelled) return;
        console.error("加载 embedding 模型失败:", err);
        setEmbeddingModels([]);
        setDefaultEmbeddingModelId(null);
      } finally {
        if (!cancelled) setIsLoadingModels(false);
      }
    }

    void loadModels();

    return () => {
      cancelled = true;
    };
  }, []);

  // 加载文档列表
  useEffect(() => {
    if (activeTab !== "documents" || !knowledgeBaseId) {
      return;
    }

    let cancelled = false;

    async function loadDocuments() {
      setLoadingDocs(true);
      setDocDeleteError(null);
      try {
        const docs = await knowledgeApi.listDocuments(knowledgeBaseId);
        if (cancelled) return;
        setDocuments(docs);
      } catch (err) {
        if (cancelled) return;
        console.error("加载文档列表失败:", err);
      } finally {
        if (!cancelled) setLoadingDocs(false);
      }
    }

    void loadDocuments();

    return () => {
      cancelled = true;
    };
  }, [activeTab, knowledgeBaseId]);

  const handleDeleteDoc = useCallback(
    (docId: string) => {
      if (!knowledgeBaseId) return;
      setDocToDelete(docId);
      setDeleteAlertOpen(true);
    },
    [knowledgeBaseId],
  );

  const doDeleteDoc = useCallback(async () => {
    if (!knowledgeBaseId || !docToDelete) return;
    setDocDeleteError(null);
    try {
      await knowledgeApi.deleteDocument(knowledgeBaseId, docToDelete);
      setDocuments((prev) => prev.filter((d) => d.id !== docToDelete));
      await onRefresh?.();
      await refreshKnowledgeBase();
    } catch (err) {
      setDocDeleteError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setDeleteAlertOpen(false);
      setDocToDelete(null);
    }
  }, [knowledgeBaseId, docToDelete, onRefresh, refreshKnowledgeBase]);

  function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function formatDate(dateStr: string): string {
    if (!dateStr) return "--";
    const d = new Date(dateStr);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }

  const handleSearch = useCallback(async () => {
    const query = queryText.trim();
    if (!knowledgeBaseId || !query || isQuerying) {
      return;
    }
    if (!canUseKnowledgeBase) {
      setQueryResults([]);
      setQueryError(knowledgeBase?.config_issue || "需要先配置模型");
      return;
    }

    setIsQuerying(true);
    setQueryError(null);
    try {
      const response = await knowledgeApi.query(knowledgeBaseId, {
        query,
        top_k: 5,
        search_mode: searchMode,
      });
      setQueryResults(response.results || []);
    } catch (error) {
      setQueryResults([]);
      setQueryError(error instanceof Error ? error.message : "搜索失败");
    } finally {
      setIsQuerying(false);
    }
  }, [canUseKnowledgeBase, isQuerying, knowledgeBase?.config_issue, knowledgeBaseId, queryText, searchMode]);

  const handleUploadChange = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const selectedFiles = Array.from(event.target.files ?? []);
      if (!knowledgeBaseId || selectedFiles.length === 0 || isUploading) {
        return;
      }
      if (!canUseKnowledgeBase) {
        setUploadError(knowledgeBase?.config_issue || "需要先配置模型");
        event.target.value = "";
        return;
      }

      setIsUploading(true);
      setUploadError(null);
      setUploadMessage(null);
      try {
        for (const file of selectedFiles) {
          await knowledgeApi.uploadDocument(knowledgeBaseId, file, undefined, {
            extraction_mode: knowledgeBase?.default_extraction_mode
              ? (knowledgeBase.default_extraction_mode as KnowledgeBaseExtractionMode)
              : undefined,
          }).promise;
        }
        setUploadMessage(
          selectedFiles.length === 1
            ? `已上传 ${selectedFiles[0].name}`
            : `已上传 ${selectedFiles.length} 个文件`,
        );
        await onRefresh?.();
        await refreshKnowledgeBase();
      } catch (error) {
        setUploadError(error instanceof Error ? error.message : "上传失败");
      } finally {
        setIsUploading(false);
        event.target.value = "";
      }
    },
    [canUseKnowledgeBase, isUploading, knowledgeBase?.config_issue, knowledgeBase?.default_extraction_mode, knowledgeBaseId, onRefresh, refreshKnowledgeBase],
  );

  // 原始数据 Tab：加载表列表
  useEffect(() => {
    if (activeTab !== "data" || !knowledgeBaseId) {
      return;
    }

    let cancelled = false;

    async function loadTables() {
      setLoadingKbTables(true);
      setRawError(null);
      try {
        const tables = await knowledgeApi.getTables(knowledgeBaseId);
        if (cancelled) return;
        setKbTables(tables);
      } catch (err) {
        if (cancelled) return;
        setRawError(err instanceof Error ? err.message : "加载表列表失败");
      } finally {
        if (!cancelled) setLoadingKbTables(false);
      }
    }

    void loadTables();

    return () => {
      cancelled = true;
    };
  }, [activeTab, knowledgeBaseId]);

  const handleRunRawQuery = useCallback(async () => {
    if (!knowledgeBaseId || !rawSql.trim() || rawRunning) {
      return;
    }
    if (!canUseKnowledgeBase) {
      setRawError(knowledgeBase?.config_issue || "需要先配置模型");
      return;
    }

    setRawRunning(true);
    setRawError(null);
    setRawResult(null);
    try {
      const response = await knowledgeApi.executeRawQuery(
        knowledgeBaseId,
        rawSql.trim()
      );
      setRawResult(response);
    } catch (err) {
      setRawError(err instanceof Error ? err.message : "查询失败");
    } finally {
      setRawRunning(false);
    }
  }, [canUseKnowledgeBase, knowledgeBase?.config_issue, knowledgeBaseId, rawSql, rawRunning]);

  const handleSaveKnowledgeBase = useCallback(async () => {
    if (!knowledgeBaseId) {
      return;
    }
    const nextChunkSize = toPositiveInteger(editChunkSize, knowledgeBase?.chunk_size || 512);
    const nextChunkOverlap = toPositiveInteger(editChunkOverlap, knowledgeBase?.chunk_overlap || 50);
    if (canEditIndexConfig && nextChunkOverlap >= nextChunkSize) {
      setSaveError("分块重叠必须小于分块大小");
      return;
    }

    setIsSaving(true);
    setSaveError(null);
    setSaveMessage(null);
    try {
      const payload: UpdateKnowledgeBaseRequest = {
        name: editName.trim() || undefined,
        description: editDescription.trim() || undefined,
        default_search_mode: editSearchMode,
        default_extraction_mode: editExtractionMode,
        extraction_mode_mapping: Object.keys(editExtractionMapping).length > 0 ? editExtractionMapping : undefined,
      };
      if (canEditIndexConfig) {
        payload.embedding_model = editEmbeddingModel === "__default__"
          ? defaultEmbeddingModelId || ""
          : editEmbeddingModel || "";
        payload.chunk_size = nextChunkSize;
        payload.chunk_overlap = nextChunkOverlap;
      }
      await knowledgeApi.updateKnowledgeBase(knowledgeBaseId, payload);
      setSaveMessage("配置已保存");
      await refreshKnowledgeBase();
      await onRefresh?.();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setIsSaving(false);
    }
  }, [
    canEditIndexConfig,
    defaultEmbeddingModelId,
    editChunkOverlap,
    editChunkSize,
    editDescription,
    editEmbeddingModel,
    editExtractionMode,
    editExtractionMapping,
    editName,
    editSearchMode,
    knowledgeBase?.chunk_overlap,
    knowledgeBase?.chunk_size,
    knowledgeBaseId,
    onRefresh,
    refreshKnowledgeBase,
  ]);

  const tabs: { id: KbTab; label: string; icon: React.ReactNode }[] = [
    { id: "documents", label: "文档", icon: <FileText className="h-3.5 w-3.5" /> },
    { id: "search", label: "搜索", icon: <Search className="h-3.5 w-3.5" /> },
    { id: "settings", label: "设置", icon: <Settings className="h-3.5 w-3.5" /> },
    { id: "data", label: "原始数据", icon: <Database className="h-3.5 w-3.5" /> },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      <div className="border-b border-border px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <BookOpen className="h-4 w-4 shrink-0 text-tertiary" />
              <span className="truncate">{node.name}</span>
            </div>
            <div className="mt-1 text-xs leading-5 text-muted-foreground">
              {documentCount > 0 ? `${documentCount} 个文档` : "知识库资产"}
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
              <span className={`rounded-full border px-2 py-0.5 ${statusBadge.className}`}>
                {statusBadge.label}
              </span>
              <span className="rounded-full border border-border bg-muted px-2 py-0.5">
                {knowledgeBase?.default_search_mode ? SEARCH_MODE_OPTIONS.find((option) => option.value === normalizeSearchMode(knowledgeBase.default_search_mode))?.label ?? "全文" : "全文"}
              </span>
              <span className="rounded-full border border-border bg-muted px-2 py-0.5">
                {currentEmbeddingLabel}
              </span>
            </div>
          </div>
          {onClose ? (
            <CanvasActionMenu
              onClose={onClose}
              closeLabel={closeLabel}
              onSplitRight={onSplitRight}
              onSplitDown={onSplitDown}
            />
          ) : null}
        </div>

        <div className="mt-3 flex gap-1 rounded-lg border border-border bg-muted/40 p-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-xs transition-colors ${
                activeTab === tab.id
                  ? "bg-foreground font-semibold text-background shadow-sm"
                  : "font-medium text-muted-foreground hover:bg-muted/60 hover:text-foreground"
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>
        {knowledgeBaseError ? (
          <Alert className="mt-3">
            <CircleAlert className="h-4 w-4" />
            <AlertDescription>{knowledgeBaseError}</AlertDescription>
          </Alert>
        ) : null}
        {knowledgeBase?.config_issue && knowledgeBase.init_status !== "ready" ? (
          <Alert className="mt-3" variant="destructive">
            <CircleAlert className="h-4 w-4" />
            <AlertDescription>{knowledgeBase.config_issue}</AlertDescription>
          </Alert>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {/* 文档 Tab */}
        {activeTab === "documents" ? (
          <div className="space-y-4">
            {/* 统计卡片 */}
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-lg border border-border bg-muted/20 px-3 py-3 text-center">
                <div className="text-lg font-semibold text-foreground">{documentCount}</div>
                <div className="text-[11px] text-muted-foreground mt-0.5">文档数量</div>
              </div>
              <div className="rounded-lg border border-border bg-muted/20 px-3 py-3 text-center">
                <div className="text-lg font-semibold text-foreground">
                  {knowledgeBase?.embedding_model ? (
                    <span className="text-sm">已启用</span>
                  ) : (
                    <span className="text-sm text-muted-foreground">未配置</span>
                  )}
                </div>
                <div className="text-[11px] text-muted-foreground mt-0.5">语义检索</div>
              </div>
            </div>

            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-foreground">
                  知识库文档
                </div>
                {effectiveDescription ? (
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    {effectiveDescription}
                  </p>
                ) : null}
              </div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => uploadInputRef.current?.click()}
                disabled={!knowledgeBaseId || isUploading || !canUseKnowledgeBase}
              >
                {isUploading ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Upload className="mr-1.5 h-3.5 w-3.5" />
                )}
                上传文档
              </Button>
            </div>

            <input
              ref={uploadInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={handleUploadChange}
              aria-label="上传知识库文档"
            />

            {uploadMessage ? (
              <div className="rounded-md border border-success/20 bg-success-container px-3 py-2 text-xs text-success">
                {uploadMessage}
              </div>
            ) : null}
            {uploadError ? (
              <div className="rounded-md border border-error/20 bg-error-container px-3 py-2 text-xs text-error">
                {uploadError}
              </div>
            ) : null}

            {docDeleteError ? (
              <div className="rounded-md border border-error/20 bg-error-container px-3 py-2 text-xs text-error">
                {docDeleteError}
              </div>
            ) : null}

            {loadingDocs ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : documents.length > 0 ? (
              <div className="space-y-2">
                {documents.map((doc) => (
                  <div
                    key={doc.id}
                    className="flex items-center justify-between gap-3 rounded-lg border border-border bg-muted/20 px-3 py-2.5"
                  >
                    <div className="flex min-w-0 items-center gap-2.5">
                      <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                      <div className="min-w-0">
                        <p className="truncate text-xs font-medium text-foreground">
                          {doc.filename}
                        </p>
                        <div className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
                          <span>{formatFileSize(doc.file_size)}</span>
                          <span>·</span>
                          <span>{doc.chunk_count} 片段</span>
                          <span>·</span>
                          <span className="flex items-center gap-0.5">
                            <Clock className="h-3 w-3" />
                            {formatDate(doc.created_at)}
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                          doc.status === "completed"
                            ? "bg-success/10 text-success"
                            : doc.status === "processing"
                              ? "bg-info/10 text-info"
                              : doc.status === "failed"
                                ? "bg-error/10 text-error"
                                : "bg-muted text-muted-foreground"
                        }`}
                      >
                        {doc.status === "completed"
                          ? "已完成"
                          : doc.status === "processing"
                            ? "处理中"
                            : doc.status === "failed"
                              ? "失败"
                              : "待处理"}
                      </span>
                      <button
                        type="button"
                        onClick={() => void handleDeleteDoc(doc.id)}
                        className="rounded p-1 text-muted-foreground hover:bg-error/10 hover:text-error transition-colors"
                        title="删除文档"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-center rounded-lg border border-dashed border-border bg-muted/10">
                <BookOpen className="mb-3 h-8 w-8 opacity-30" />
                <p className="text-sm text-muted-foreground">暂无文档</p>
                <p className="mt-1 text-xs text-muted-foreground/60">点击"上传文档"按钮添加 PDF、Markdown、TXT 等格式</p>
              </div>
            )}
          </div>
        ) : null}

        {/* 搜索 Tab */}
        {activeTab === "search" ? (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="text-sm font-medium text-foreground">知识库搜索</div>
            </div>
            <div className="flex gap-1 rounded-md border border-border bg-muted/40 p-0.5">
              {[
                { key: "fulltext" as const, label: "全文" },
                { key: "vector" as const, label: "向量" },
                { key: "hybrid" as const, label: "混合" },
              ].map((mode) => (
                <button
                  key={mode.key}
                  type="button"
                  onClick={() => {
                    setSearchMode(mode.key);
                    try { localStorage.setItem("kb-search-mode", mode.key); } catch { /* noop */ }
                  }}
                  className={`flex-1 rounded px-2 py-1 text-xs transition-colors ${
                    searchMode === mode.key
                      ? "bg-foreground font-semibold text-background shadow-sm"
                      : "font-medium text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                  }`}
                >
                  {mode.label}
                </button>
              ))}
            </div>
            <div className="flex gap-2">
              <Input
                value={queryText}
                onChange={(event) => {
                  setQueryText(event.target.value);
                  setQueryError(null);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    void handleSearch();
                  }
                }}
                placeholder="输入关键词..."
                disabled={!knowledgeBaseId || isQuerying || !canUseKnowledgeBase}
                className="h-9"
              />
              <Button
                type="button"
                size="sm"
                className="h-9 px-4 gap-1.5"
                onClick={() => void handleSearch()}
                disabled={!knowledgeBaseId || !queryText.trim() || isQuerying || !canUseKnowledgeBase}
              >
                {isQuerying ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Search className="h-3.5 w-3.5" />
                )}
                <span className="hidden sm:inline">搜索</span>
              </Button>
            </div>

            {queryError ? (
              <div className="flex items-start gap-2 rounded-md border border-error/20 bg-error-container px-3 py-2 text-xs text-error">
                <CircleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{queryError}</span>
              </div>
            ) : null}

            <div className="space-y-2">
              {queryResults.map((result, index) => (
                <div
                  key={`${result.document_id}:${result.chunk_index}:${index}`}
                  className="rounded-lg border border-border bg-background px-4 py-3 hover:shadow-sm hover:border-muted-foreground/20 transition-all cursor-default"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-2 text-xs font-medium text-foreground">
                      <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      <span className="truncate">{result.document_name}</span>
                    </div>
                    <span className="shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
                      {result.score.toFixed(3)}
                    </span>
                  </div>
                  <p className="mt-2 line-clamp-3 text-xs leading-5 text-muted-foreground">
                    {result.content}
                  </p>
                </div>
              ))}
              {!isQuerying && queryText.trim() && queryResults.length === 0 && !queryError ? (
                <div className="rounded-lg border border-dashed border-border bg-muted/10 px-3 py-6 text-center text-xs text-muted-foreground">
                  暂无匹配结果
                </div>
              ) : null}
            </div>
          </div>
        ) : null}

        {/* 设置 Tab */}
        {activeTab === "settings" ? (
          <div className="space-y-4">
            <div className="text-sm font-medium text-foreground">知识库设置</div>
            {isLoadingKnowledgeBase ? (
              <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                加载配置...
              </div>
            ) : null}
            <div className="grid gap-3 rounded-lg border border-border bg-muted/20 px-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="kb-edit-name" className="text-xs text-muted-foreground">
                  知识库名称
                </Label>
                <Input
                  id="kb-edit-name"
                  value={editName || node.name}
                  onChange={(e) => setEditName(e.target.value)}
                  className="h-8 text-xs"
                  disabled={!knowledgeBaseId || isSaving}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="kb-edit-desc" className="text-xs text-muted-foreground">
                  说明
                </Label>
                <Input
                  id="kb-edit-desc"
                  value={editDescription || (effectiveDescription ?? "")}
                  onChange={(e) => setEditDescription(e.target.value)}
                  className="h-8 text-xs"
                  disabled={!knowledgeBaseId || isSaving}
                  placeholder="暂无说明"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="kb-edit-embedding" className="text-xs text-muted-foreground">
                  Embedding 模型
                </Label>
                <Select
                  value={currentEmbeddingOption}
                  onValueChange={(value) => setEditEmbeddingModel(value === "__default__" ? "" : value)}
                  disabled={!knowledgeBaseId || isSaving || isLoadingModels || !canEditIndexConfig}
                >
                  <SelectTrigger id="kb-edit-embedding" className="h-8 text-xs">
                    <SelectValue placeholder="选择 embedding 模型" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__default__">跟随默认 embedding</SelectItem>
                    {embeddingModels.map((model) => (
                      <SelectItem key={model.id} value={model.id}>
                        {formatEmbeddingModel(model)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-[11px] leading-5 text-muted-foreground">
                  {isLoadingModels
                    ? "正在读取模型配置。"
                    : canEditIndexConfig
                    ? "空知识库可在这里先完成模型配置。"
                    : "已有文档后不能直接切换模型。"}
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="kb-edit-search-mode" className="text-xs text-muted-foreground">
                  默认检索策略
                </Label>
                <Select
                  value={editSearchMode}
                  onValueChange={(value) => setEditSearchMode(value as KnowledgeBaseSearchMode)}
                  disabled={!knowledgeBaseId || isSaving}
                >
                  <SelectTrigger id="kb-edit-search-mode" className="h-8 text-xs">
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
              <div className="space-y-2">
                <Label htmlFor="kb-edit-extraction-mode" className="text-xs text-muted-foreground">
                  默认文档解析模式
                </Label>
                <Select
                  value={editExtractionMode}
                  onValueChange={(value) => setEditExtractionMode(value as KnowledgeBaseExtractionMode)}
                  disabled={!knowledgeBaseId || isSaving}
                >
                  <SelectTrigger id="kb-edit-extraction-mode" className="h-8 text-xs">
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
                <p className="text-[11px] leading-5 text-muted-foreground">
                  优先使用增强模式解析，失败时自动回退到基础模式。
                </p>
              </div>
              <div className="space-y-2">
                <Label className="text-xs text-muted-foreground">
                  文件类型解析映射
                </Label>
                <div className="space-y-2 rounded-md border border-border/60 p-3">
                  <div className="flex items-center gap-2">
                    <span className="min-w-[60px] text-xs font-medium">PDF</span>
                    <Select
                      value={editExtractionMapping[".pdf"] || "__default__"}
                      onValueChange={(value) =>
                        setEditExtractionMapping((prev) => {
                          const next = { ...prev };
                          if (value && value !== "__default__") next[".pdf"] = value;
                          else delete next[".pdf"];
                          return next;
                        })
                      }
                      disabled={!knowledgeBaseId || isSaving}
                    >
                      <SelectTrigger className="h-8 flex-1 text-xs">
                        <SelectValue placeholder="使用默认" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__default__">使用默认</SelectItem>
                        {EXTRACTION_MODE_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="min-w-[60px] text-xs font-medium">DOCX</span>
                    <Select
                      value={editExtractionMapping[".docx"] || "__default__"}
                      onValueChange={(value) =>
                        setEditExtractionMapping((prev) => {
                          const next = { ...prev };
                          if (value && value !== "__default__") next[".docx"] = value;
                          else delete next[".docx"];
                          return next;
                        })
                      }
                      disabled={!knowledgeBaseId || isSaving}
                    >
                      <SelectTrigger className="h-8 flex-1 text-xs">
                        <SelectValue placeholder="使用默认" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__default__">使用默认</SelectItem>
                        {EXTRACTION_MODE_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <p className="text-[11px] leading-5 text-muted-foreground">
                  未配置映射的文件类型将使用上方默认解析模式。表格文件建议放到工作区处理。
                </p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="kb-edit-chunk-size" className="text-xs text-muted-foreground">
                    分块大小
                  </Label>
                  <Input
                    id="kb-edit-chunk-size"
                    type="number"
                    min={64}
                    max={8192}
                    value={editChunkSize}
                    onChange={(e) => setEditChunkSize(e.target.value)}
                    className="h-8 text-xs"
                    disabled={!knowledgeBaseId || isSaving || !canEditIndexConfig}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="kb-edit-chunk-overlap" className="text-xs text-muted-foreground">
                    重叠
                  </Label>
                  <Input
                    id="kb-edit-chunk-overlap"
                    type="number"
                    min={0}
                    max={4096}
                    value={editChunkOverlap}
                    onChange={(e) => setEditChunkOverlap(e.target.value)}
                    className="h-8 text-xs"
                    disabled={!knowledgeBaseId || isSaving || !canEditIndexConfig}
                  />
                </div>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">文档数量</span>
                <span className="font-medium text-foreground">{documentCount}</span>
              </div>
              <Button
                type="button"
                size="sm"
                className="mt-1"
                disabled={!knowledgeBaseId || isSaving}
                onClick={() => void handleSaveKnowledgeBase()}
              >
                {isSaving ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : null}
                保存
              </Button>
              {saveMessage ? (
                <div className="rounded-md border border-success/20 bg-success-container px-3 py-2 text-xs text-success">
                  {saveMessage}
                </div>
              ) : null}
              {saveError ? (
                <div className="rounded-md border border-error/20 bg-error-container px-3 py-2 text-xs text-error">
                  {saveError}
                </div>
              ) : null}
            </div>

            <div className="rounded-lg border border-border bg-background px-4 py-4">
              <div className="text-sm font-medium text-foreground">上传文档</div>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                上传文档会写入当前知识库。支持 PDF、Markdown、TXT 等格式。
              </p>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="mt-3"
                onClick={() => uploadInputRef.current?.click()}
                disabled={!knowledgeBaseId || isUploading || !canUseKnowledgeBase}
              >
                {isUploading ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Upload className="mr-1.5 h-3.5 w-3.5" />
                )}
                上传文档
              </Button>
              {!canUseKnowledgeBase ? (
                <Alert className="mt-3">
                  <CircleAlert className="h-4 w-4" />
                  <AlertDescription>
                    {knowledgeBase?.config_issue || "需要先完成模型配置"}
                  </AlertDescription>
                </Alert>
              ) : null}
              <input
                ref={uploadInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={handleUploadChange}
                aria-label="上传知识库文档"
              />
              {uploadMessage ? (
                <div className="mt-3 rounded-md border border-success/20 bg-success-container px-3 py-2 text-xs text-success">
                  {uploadMessage}
                </div>
              ) : null}
              {uploadError ? (
                <div className="mt-3 rounded-md border border-error/20 bg-error-container px-3 py-2 text-xs text-error">
                  {uploadError}
                </div>
              ) : null}
            </div>
          </div>
        ) : null}

        {/* 原始数据 Tab */}
        {activeTab === "data" ? (
          <div className="flex h-full min-h-0 flex-col gap-3">
            {/* 表列表 */}
            {loadingKbTables ? (
              <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />
                加载表结构...
              </div>
            ) : kbTables.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {kbTables.map((table) => (
                  <button
                    key={table.name}
                    type="button"
                    onClick={() =>
                      setRawSql(
                        `SELECT * FROM "${table.name.replace(/"/g, "\"\"")}" LIMIT 100;`
                      )
                    }
                    className="rounded-md border border-border bg-muted/40 px-2 py-1 text-[11px] text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                    title={`${table.name} (${table.columns.map((c) => c.name).join(", ")})`}
                  >
                    {table.name}
                  </button>
                ))}
              </div>
            ) : null}

            {/* SQL 编辑器 */}
            <div className="flex-shrink-0">
              <SqlQueryPanel
                sql={rawSql}
                onSqlChange={setRawSql}
                queryLimitInput={rawQueryLimit}
                onLimitChange={setRawQueryLimit}
                runningAction={rawRunning ? "query" : null}
                canExecute={false}
                disabled={!knowledgeBaseId || loadingKbTables}
                error={rawError}
                onRunQuery={handleRunRawQuery}
                onRunExecute={() => {}}
              />
            </div>

            {/* 结果表格 */}
            <div className="min-h-0 flex-1 overflow-hidden flex flex-col">
              {rawResult ? (
                <>
                  <div className="min-h-0 flex-1 overflow-auto">
                    {rawResult.columns.length === 0 ? (
                      <div className="px-4 py-6 text-center text-[11px] text-muted-foreground">
                        查询已执行，但当前结果没有可展示的列。
                      </div>
                    ) : (
                      <div className="overflow-auto">
                        <table
                          className="w-full text-left text-[11px]"
                          style={{ tableLayout: "auto" }}
                        >
                          <thead className="sticky top-0 bg-muted/60">
                            <tr>
                              {rawResult.columns.map((column, colIdx) => (
                                <th
                                  key={`h-${colIdx}`}
                                  className="border-b border-border px-2 py-1.5 font-medium text-muted-foreground whitespace-nowrap"
                                >
                                  {column}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {rawResult.rows.map((row, index) => (
                              <tr
                                key={`${index}`}
                                className="border-b border-border/60 last:border-b-0"
                              >
                                {rawResult.columns.map((column, columnIndex) => {
                                  const value = row[column];
                                  const display =
                                    value === null || value === undefined
                                      ? "NULL"
                                      : typeof value === "string"
                                        ? value
                                        : typeof value === "number" || typeof value === "boolean"
                                          ? String(value)
                                          : JSON.stringify(value);
                                  return (
                                    <td
                                      key={`c${columnIndex}-r${index}`}
                                      className="px-2 py-1.5 align-top font-mono text-[10px] text-foreground max-w-[240px] truncate"
                                      title={display}
                                    >
                                      {display}
                                    </td>
                                  );
                                })}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                  <div className="flex-shrink-0 border-t border-border px-3 py-1.5 flex items-center gap-3 text-[11px] text-muted-foreground bg-muted/20">
                    <span className="flex items-center gap-1">
                      <span className="font-medium text-foreground">{rawResult.row_count}</span>
                      <span>行</span>
                    </span>
                  </div>
                </>
              ) : (
                <div className="flex h-full items-center justify-center px-6 text-center text-[12px] text-muted-foreground">
                  执行 SQL 后结果将显示在这里。
                </div>
              )}
            </div>
          </div>
        ) : null}
      </div>

      <AlertDialog open={deleteAlertOpen} onOpenChange={setDeleteAlertOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>
              确定要删除这个文档吗？此操作不可撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setDocToDelete(null)}>
              取消
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={doDeleteDoc}
              className="bg-destructive text-destructive-foreground"
            >
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
