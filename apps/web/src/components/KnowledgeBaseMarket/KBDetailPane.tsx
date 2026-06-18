import { useEffect, useState } from "react";
import {
  AlertCircle,
  ChevronLeft,
  Database,
  FileText,
  Loader2,
  Search,
  Settings,
  Trash2,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type {
  Document,
  KnowledgeBase,
  KnowledgeBaseExtractionMode,
  KnowledgeBaseSearchMode,
  UpdateKnowledgeBaseRequest,
} from "@/types/knowledge";
import type { LLMModelConfig } from "@/lib/api/llm";
import { DocumentStatusBadge } from "./DocumentStatusBadge";
import {
  formatDate,
  formatFileSize,
  formatEmbeddingModel,
  getFileIcon,
  getStatusBadge,
  toPositiveInteger,
} from "./utils";
import {
  SEARCH_MODE_OPTIONS,
  EXTRACTION_MODE_OPTIONS,
  normalizeSearchMode,
} from "./constants";

interface KBDetailPaneProps {
  selectedKB: KnowledgeBase;
  documents: Document[];
  isLoadingDocs: boolean;
  documentChunkCount: number;
  isSplitLayout: boolean;
  embeddingModels: LLMModelConfig[];
  defaultEmbeddingModelId: string | null;
  isLoadingModels: boolean;
  onBack: () => void;
  onUpload: () => void;
  onQuery: () => void;
  onDeleteDoc: (docId: string) => void;
  onSaveConfig: (
    kbId: string,
    payload: UpdateKnowledgeBaseRequest,
  ) => Promise<void>;
}

export function KBDetailPane({
  selectedKB,
  documents,
  isLoadingDocs,
  documentChunkCount,
  isSplitLayout,
  embeddingModels,
  defaultEmbeddingModelId,
  isLoadingModels,
  onBack,
  onUpload,
  onQuery,
  onDeleteDoc,
  onSaveConfig,
}: KBDetailPaneProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editEmbeddingModel, setEditEmbeddingModel] = useState("");
  const [editSearchMode, setEditSearchMode] = useState<KnowledgeBaseSearchMode>("fulltext");
  const [editExtractionMode, setEditExtractionMode] = useState<KnowledgeBaseExtractionMode>("enhanced");
  const [editChunkSize, setEditChunkSize] = useState("512");
  const [editChunkOverlap, setEditChunkOverlap] = useState("50");
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  const canEditIndexConfig = selectedKB.can_edit_index_config ?? documents.length === 0;

  // 切换知识库时收起编辑区域
  useEffect(() => {
    setIsEditing(false);
    setSaveError(null);
    setSaveMessage(null);
  }, [selectedKB.id]);

  const startEditing = () => {
    setEditName(selectedKB.name);
    setEditDescription(selectedKB.description ?? "");
    setEditEmbeddingModel(selectedKB.embedding_model || "");
    setEditSearchMode(normalizeSearchMode(selectedKB.default_search_mode));
    setEditExtractionMode(
      (selectedKB.default_extraction_mode as KnowledgeBaseExtractionMode) || "enhanced",
    );
    setEditChunkSize(String(selectedKB.chunk_size || 512));
    setEditChunkOverlap(String(selectedKB.chunk_overlap || 50));
    setSaveError(null);
    setSaveMessage(null);
    setIsEditing(true);
  };

  const cancelEditing = () => {
    setIsEditing(false);
    setSaveError(null);
    setSaveMessage(null);
  };

  const handleSave = async () => {
    const nextChunkSize = toPositiveInteger(editChunkSize, selectedKB.chunk_size || 512);
    const nextChunkOverlap = toPositiveInteger(editChunkOverlap, selectedKB.chunk_overlap || 50);
    if (canEditIndexConfig && nextChunkOverlap >= nextChunkSize) {
      setSaveError("分块重叠必须小于分块大小");
      return;
    }

    const payload: UpdateKnowledgeBaseRequest = {
      name: editName.trim() || undefined,
      description: editDescription.trim() || undefined,
      default_search_mode: editSearchMode,
      default_extraction_mode: editExtractionMode,
    };
    if (canEditIndexConfig) {
      payload.embedding_model = editEmbeddingModel || defaultEmbeddingModelId || "";
      payload.chunk_size = nextChunkSize;
      payload.chunk_overlap = nextChunkOverlap;
    }

    setIsSaving(true);
    setSaveError(null);
    setSaveMessage(null);
    try {
      await onSaveConfig(selectedKB.id, payload);
      setSaveMessage("配置已保存");
      setIsEditing(false);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <>
      <div className="border-b border-border/80 px-6 py-6">
        {!isSplitLayout ? (
          <div className="mb-3 flex items-center gap-2">
            <Button variant="ghost" size="sm" className="h-7 px-2" onClick={onBack}>
              <ChevronLeft className="mr-1 h-4 w-4" />
              返回
            </Button>
          </div>
        ) : null}

        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="space-y-2">
            <div className="inline-flex items-center rounded-full border border-info/20 bg-info-container px-3 py-1 text-xs text-info">
              当前知识库
            </div>
            <div className="text-2xl font-semibold text-foreground">{selectedKB.name}</div>
            <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
              {selectedKB.description || "暂无描述"}
            </p>
            <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
              <span
                className={`rounded-full border px-2.5 py-1 ${getStatusBadge(selectedKB).className}`}
              >
                {getStatusBadge(selectedKB).label}
              </span>
              <span className="rounded-full border border-border bg-muted px-2.5 py-1">
                {selectedKB.embedding_model || "未配置 embedding"}
              </span>
              <span className="rounded-full border border-border bg-muted px-2.5 py-1">
                默认检索：
                {
                  SEARCH_MODE_OPTIONS.find(
                    (option) =>
                      option.value === normalizeSearchMode(selectedKB.default_search_mode),
                  )?.label
                }
              </span>
              <span className="rounded-full border border-border bg-muted px-2.5 py-1">
                分块 {selectedKB.chunk_size}/{selectedKB.chunk_overlap}
              </span>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={onQuery}
              disabled={!selectedKB.config_complete || selectedKB.init_status !== "ready"}
            >
              <Search className="mr-1.5 h-3.5 w-3.5" />
              检索
            </Button>
            <Button
              size="sm"
              onClick={onUpload}
              disabled={!selectedKB.config_complete || selectedKB.init_status !== "ready"}
            >
              <Upload className="mr-1.5 h-3.5 w-3.5" />
              上传文档
            </Button>
          </div>
        </div>

        {!selectedKB.config_complete || selectedKB.init_status !== "ready" ? (
          <Alert className="mt-4">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              {selectedKB.config_issue || "需要先完成模型配置"}
            </AlertDescription>
          </Alert>
        ) : null}

        <div className="mt-5 grid gap-3 md:grid-cols-3">
          <div className="rounded-2xl border border-border bg-muted/80 p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">文档数</div>
            <div className="mt-2 text-2xl font-semibold text-foreground">{documents.length}</div>
          </div>
          <div className="rounded-2xl border border-border bg-muted/80 p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">片段数</div>
            <div className="mt-2 text-2xl font-semibold text-foreground">
              {documentChunkCount}
            </div>
          </div>
          <div className="rounded-2xl border border-border bg-muted/80 p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
              最近更新
            </div>
            <div className="mt-2 text-sm font-semibold text-foreground">
              {formatDate(selectedKB.updated_at || selectedKB.created_at)}
            </div>
          </div>
        </div>

        {/* 编辑设置入口 */}
        <div className="mt-5">
          {!isEditing ? (
            <Button variant="outline" size="sm" onClick={startEditing}>
              <Settings className="mr-1.5 h-3.5 w-3.5" />
              编辑设置
            </Button>
          ) : null}

          {isEditing ? (
            <TooltipProvider>
              <div className="rounded-2xl border border-border bg-muted/40 p-5">
                <div className="mb-4 flex items-center justify-between">
                  <div className="text-sm font-semibold text-foreground">编辑知识库配置</div>
                  <Button variant="ghost" size="sm" className="h-7 px-2" onClick={cancelEditing} disabled={isSaving}>
                    取消
                  </Button>
                </div>

                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="kb-detail-edit-name" className="text-xs text-muted-foreground">
                      名称
                    </Label>
                    <Input
                      id="kb-detail-edit-name"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      disabled={isSaving}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="kb-detail-edit-desc" className="text-xs text-muted-foreground">
                      描述
                    </Label>
                    <Textarea
                      id="kb-detail-edit-desc"
                      value={editDescription}
                      onChange={(e) => setEditDescription(e.target.value)}
                      rows={2}
                      disabled={isSaving}
                      placeholder="输入知识库描述"
                    />
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center gap-1">
                      <Label htmlFor="kb-detail-edit-embedding" className="text-xs text-muted-foreground">
                        Embedding 模型
                      </Label>
                      {!canEditIndexConfig ? (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <AlertCircle className="h-3 w-3 cursor-help text-amber-500" />
                          </TooltipTrigger>
                          <TooltipContent>
                            已有文档时不能切换 Embedding 模型，请先清空文档
                          </TooltipContent>
                        </Tooltip>
                      ) : null}
                    </div>
                    <Select
                      value={editEmbeddingModel || "__default__"}
                      onValueChange={(value) =>
                        setEditEmbeddingModel(value === "__default__" ? "" : value)
                      }
                      disabled={isSaving || isLoadingModels || !canEditIndexConfig}
                    >
                      <SelectTrigger id="kb-detail-edit-embedding">
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
                    <p className="text-xs leading-5 text-muted-foreground">
                      {!canEditIndexConfig
                        ? "已有文档时不能切换 Embedding 模型，请先清空文档"
                        : isLoadingModels
                          ? "正在读取模型配置…"
                          : "空知识库可在这里切换 Embedding 模型。"}
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="kb-detail-edit-search-mode" className="text-xs text-muted-foreground">
                      默认检索策略
                    </Label>
                    <Select
                      value={editSearchMode}
                      onValueChange={(value) =>
                        setEditSearchMode(value as KnowledgeBaseSearchMode)
                      }
                      disabled={isSaving}
                    >
                      <SelectTrigger id="kb-detail-edit-search-mode">
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
                    <Label htmlFor="kb-detail-edit-extraction-mode" className="text-xs text-muted-foreground">
                      默认解析模式
                    </Label>
                    <Select
                      value={editExtractionMode}
                      onValueChange={(value) =>
                        setEditExtractionMode(value as KnowledgeBaseExtractionMode)
                      }
                      disabled={isSaving}
                    >
                      <SelectTrigger id="kb-detail-edit-extraction-mode">
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

                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-2">
                      <Label htmlFor="kb-detail-edit-chunk-size" className="text-xs text-muted-foreground">
                        分块大小
                      </Label>
                      <Input
                        id="kb-detail-edit-chunk-size"
                        type="number"
                        min={64}
                        max={8192}
                        value={editChunkSize}
                        onChange={(e) => setEditChunkSize(e.target.value)}
                        disabled={isSaving || !canEditIndexConfig}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="kb-detail-edit-chunk-overlap" className="text-xs text-muted-foreground">
                        重叠
                      </Label>
                      <Input
                        id="kb-detail-edit-chunk-overlap"
                        type="number"
                        min={0}
                        max={4096}
                        value={editChunkOverlap}
                        onChange={(e) => setEditChunkOverlap(e.target.value)}
                        disabled={isSaving || !canEditIndexConfig}
                      />
                    </div>
                  </div>
                  {!canEditIndexConfig ? (
                    <p className="text-xs leading-5 text-muted-foreground">
                      已有文档时分块配置不可修改，请先清空文档。
                    </p>
                  ) : null}

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

                  <div className="flex items-center gap-2">
                    <Button size="sm" onClick={() => void handleSave()} disabled={isSaving}>
                      {isSaving ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : null}
                      保存
                    </Button>
                    <Button variant="outline" size="sm" onClick={cancelEditing} disabled={isSaving}>
                      取消
                    </Button>
                  </div>
                </div>
              </div>
            </TooltipProvider>
          ) : null}
        </div>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="p-6">
          {isLoadingDocs ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-5 w-5 animate-spin text-primary" />
            </div>
          ) : documents.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-border bg-muted/70 px-6 py-14 text-center">
              <FileText className="mx-auto mb-3 h-10 w-10 text-muted-foreground/50" />
              <p className="text-sm font-medium text-muted-foreground">当前知识库暂无文档</p>
              <p className="mt-1 text-xs text-muted-foreground">
                点击上方“上传文档”按钮开始构建内容。
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {documents.map((doc) => (
                <div
                  key={doc.id}
                  className="flex items-center justify-between gap-3 rounded-2xl border border-border bg-white p-4 transition hover:bg-muted"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-border bg-muted">
                      {getFileIcon(doc.filename)}
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-foreground">
                        {doc.filename}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {formatFileSize(doc.file_size)} · {doc.chunk_count} 个片段 ·{" "}
                        {formatDate(doc.created_at)}
                      </p>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <DocumentStatusBadge status={doc.status} />
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-muted-foreground hover:text-destructive"
                      onClick={() => onDeleteDoc(doc.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </ScrollArea>
    </>
  );
}

export function KBDetailEmpty() {
  return (
    <div className="flex min-h-[420px] flex-1 items-center justify-center px-6 py-12">
      <div className="max-w-sm text-center">
        <Database className="mx-auto mb-4 h-12 w-12 text-muted-foreground" />
        <h3 className="text-lg font-semibold text-foreground">选择一个知识库开始浏览</h3>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          资源目录已经固定在左侧，主画布只展示当前知识库的文档、检索和维护操作。
        </p>
      </div>
    </div>
  );
}
