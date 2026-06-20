import { useRef } from "react";
import {
  AlertCircle,
  Loader2,
  Search,
  Upload,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
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
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription } from "@/components/ui/alert";
import type { LLMModelConfig } from "@/lib/api/llm";
import type { Document, KnowledgeBaseExtractionMode, KnowledgeBaseSearchMode, UploadDocumentResponse } from "@/types/knowledge";
import { formatEmbeddingModel, getFileIcon, formatFileSize } from "./utils";
import { SEARCH_MODE_OPTIONS, EXTRACTION_MODE_OPTIONS } from "./constants";

const SEARCH_MODE_DESCRIPTIONS: Record<KnowledgeBaseSearchMode, string> = {
  fulltext: "基于关键词的精确匹配，速度快",
  vector: "基于语义相似度搜索，能理解同义词",
  hybrid: "同时使用全文和向量检索，效果最好",
};

interface CreateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  createName: string;
  onCreateNameChange: (value: string) => void;
  createDescription: string;
  onCreateDescriptionChange: (value: string) => void;
  createEmbeddingModel: string;
  onCreateEmbeddingModelChange: (value: string) => void;
  createSearchMode: KnowledgeBaseSearchMode;
  onCreateSearchModeChange: (value: KnowledgeBaseSearchMode) => void;
  createChunkSize: string;
  onCreateChunkSizeChange: (value: string) => void;
  createChunkOverlap: string;
  onCreateChunkOverlapChange: (value: string) => void;
  embeddingModels: LLMModelConfig[];
  isLoadingModels: boolean;
  isCreating: boolean;
  onCreate: () => void;
}

export function CreateDialog({
  open,
  onOpenChange,
  createName,
  onCreateNameChange,
  createDescription,
  onCreateDescriptionChange,
  createEmbeddingModel,
  onCreateEmbeddingModelChange,
  createSearchMode,
  onCreateSearchModeChange,
  createChunkSize,
  onCreateChunkSizeChange,
  createChunkOverlap,
  onCreateChunkOverlapChange,
  embeddingModels,
  isLoadingModels,
  isCreating,
  onCreate,
}: CreateDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="flex flex-col h-[90vh] overflow-hidden p-0 sm:max-w-[620px]"
        data-testid="knowledge-base-create-dialog"
      >
        <DialogHeader className="shrink-0 px-6 pt-6">
          <DialogTitle>新建知识库</DialogTitle>
          <DialogDescription>创建一个新的知识库，并设置默认导入配置。</DialogDescription>
        </DialogHeader>
        <div className="flex-1 min-h-0 space-y-5 overflow-y-auto px-6 py-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">名称</label>
            <Input
              placeholder="输入知识库名称"
              value={createName}
              onChange={(e) => onCreateNameChange(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">描述（可选）</label>
            <Textarea
              placeholder="输入知识库描述"
              value={createDescription}
              onChange={(e) => onCreateDescriptionChange(e.target.value)}
              rows={3}
            />
          </div>
          <div className="grid gap-4 rounded-xl border border-border bg-muted/60 p-4 sm:grid-cols-2">
            <div className="space-y-2 sm:col-span-2">
              <label className="text-sm font-medium">Embedding 模型</label>
              <Select
                value={createEmbeddingModel || "__default__"}
                onValueChange={(value) => {
                  onCreateEmbeddingModelChange(value === "__default__" ? "" : value);
                }}
              >
                <SelectTrigger>
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
                Embedding 模型将文档转换为向量，用于语义检索。不配置则只能使用全文搜索。
              </p>
              {isLoadingModels ? (
                <p className="text-xs leading-5 text-muted-foreground">正在读取模型配置…</p>
              ) : embeddingModels.length === 0 ? (
                <p className="text-xs leading-5 text-muted-foreground">
                  当前未配置 embedding 模型，可先到设置中完成配置。
                </p>
              ) : null}
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">默认检索策略</label>
              <Select
                value={createSearchMode}
                onValueChange={(value) => onCreateSearchModeChange(value as KnowledgeBaseSearchMode)}
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
              <p className="text-xs leading-5 text-muted-foreground">
                {SEARCH_MODE_DESCRIPTIONS[createSearchMode]}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <label className="text-sm font-medium">分块大小</label>
                <Input
                  type="number"
                  min={64}
                  max={8192}
                  value={createChunkSize}
                  onChange={(event) => onCreateChunkSizeChange(event.target.value)}
                />
                <p className="text-xs leading-5 text-muted-foreground">
                  文档切分成片段的大小，默认 512 适合大多数场景
                </p>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">重叠</label>
                <Input
                  type="number"
                  min={0}
                  max={4096}
                  value={createChunkOverlap}
                  onChange={(event) => onCreateChunkOverlapChange(event.target.value)}
                />
                <p className="text-xs leading-5 text-muted-foreground">
                  相邻片段重叠字数，避免内容截断，默认 50
                </p>
              </div>
            </div>
          </div>
        </div>
        <DialogFooter className="shrink-0 px-6 py-4">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isCreating}>
            取消
          </Button>
          <Button onClick={onCreate} disabled={!createName.trim() || isCreating}>
            {isCreating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            创建
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface UploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  documents: Document[];
  uploadFiles: File[];
  uploadProgress: Record<string, number>;
  uploadExtractionMode: KnowledgeBaseExtractionMode;
  onUploadExtractionModeChange: (value: KnowledgeBaseExtractionMode) => void;
  uploadSearchMode: KnowledgeBaseSearchMode;
  onUploadSearchModeChange: (value: KnowledgeBaseSearchMode) => void;
  uploadEmbeddingModel: string;
  onUploadEmbeddingModelChange: (value: string) => void;
  uploadChunkSize: string;
  onUploadChunkSizeChange: (value: string) => void;
  uploadChunkOverlap: string;
  onUploadChunkOverlapChange: (value: string) => void;
  uploadResults: UploadDocumentResponse[];
  isUploading: boolean;
  embeddingModels: LLMModelConfig[];
  onFileSelect: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onRemoveFile: (fileName: string) => void;
  onUpload: () => void;
  onCancelUpload: () => void;
  onClearFiles: () => void;
}

export function UploadDialog({
  open,
  onOpenChange,
  documents,
  uploadFiles,
  uploadProgress,
  uploadExtractionMode,
  onUploadExtractionModeChange,
  uploadSearchMode,
  onUploadSearchModeChange,
  uploadEmbeddingModel,
  onUploadEmbeddingModelChange,
  uploadChunkSize,
  onUploadChunkSizeChange,
  uploadChunkOverlap,
  onUploadChunkOverlapChange,
  uploadResults,
  isUploading,
  embeddingModels,
  onFileSelect,
  onRemoveFile,
  onUpload,
  onCancelUpload,
  onClearFiles,
}: UploadDialogProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="flex flex-col h-[90vh] overflow-hidden p-0 sm:max-w-[720px]"
        data-testid="knowledge-base-upload-dialog"
      >
        <DialogHeader className="shrink-0 px-6 pt-6">
          <DialogTitle>上传文档</DialogTitle>
          <DialogDescription>选择文件，并设置本次导入使用的解析和索引配置。</DialogDescription>
        </DialogHeader>
        <div className="flex-1 min-h-0 space-y-5 overflow-y-auto px-6 py-4">
          <input
            type="file"
            multiple
            className="hidden"
            ref={fileInputRef}
            onChange={onFileSelect}
          />
          <Button
            variant="outline"
            className="h-24 w-full border-dashed"
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            data-testid="knowledge-base-file-picker"
          >
            <div className="flex flex-col items-center gap-2">
              <Upload className="h-6 w-6" />
              <span>点击选择文件</span>
            </div>
          </Button>

          <div className="grid gap-4 rounded-xl border border-border bg-muted/60 p-4 sm:grid-cols-2">
            <div className="space-y-2">
              <label className="text-sm font-medium">解析策略</label>
              <Select
                value={uploadExtractionMode}
                onValueChange={(value) => onUploadExtractionModeChange(value as KnowledgeBaseExtractionMode)}
              >
                <SelectTrigger data-testid="knowledge-base-upload-extraction-mode">
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
              <label className="text-sm font-medium">检索策略</label>
              <Select
                value={uploadSearchMode}
                onValueChange={(value) => onUploadSearchModeChange(value as KnowledgeBaseSearchMode)}
              >
                <SelectTrigger data-testid="knowledge-base-upload-search-mode">
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
            <div className="space-y-2 sm:col-span-2">
              <label className="text-sm font-medium">Embedding 模型</label>
              <Select
                value={uploadEmbeddingModel || "__none__"}
                onValueChange={(value) => onUploadEmbeddingModelChange(value === "__none__" ? "" : value)}
                disabled={documents.length > 0}
              >
                <SelectTrigger data-testid="knowledge-base-upload-embedding-model">
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
                {documents.length > 0
                  ? "已有文档的知识库需通过重建索引切换 embedding 模型。"
                  : "空知识库可以在首次导入前指定 embedding 模型。"}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:col-span-2">
              <div className="space-y-2">
                <label className="text-sm font-medium">分块大小</label>
                <Input
                  type="number"
                  min={64}
                  max={8192}
                  value={uploadChunkSize}
                  onChange={(event) => onUploadChunkSizeChange(event.target.value)}
                  disabled={isUploading}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">重叠</label>
                <Input
                  type="number"
                  min={0}
                  max={4096}
                  value={uploadChunkOverlap}
                  onChange={(event) => onUploadChunkOverlapChange(event.target.value)}
                  disabled={isUploading}
                />
              </div>
            </div>
          </div>

          {uploadFiles.length > 0 ? (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">已选择 {uploadFiles.length} 个文件</span>
                {!isUploading ? (
                  <Button variant="ghost" size="sm" onClick={onClearFiles}>
                    清空
                  </Button>
                ) : null}
              </div>
              <div className="max-h-[200px] space-y-2 overflow-y-auto">
                {uploadFiles.map((file) => (
                  <div key={file.name} className="flex items-center gap-3 rounded bg-muted p-2">
                    {getFileIcon(file.name)}
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm">{file.name}</p>
                      <p className="text-xs text-muted-foreground">{formatFileSize(file.size)}</p>
                      {uploadProgress[file.name] !== undefined ? (
                        <div className="mt-1 flex items-center gap-2">
                          <Progress value={uploadProgress[file.name]} className="h-1 flex-1" />
                          <span className="text-[10px]">{Math.round(uploadProgress[file.name])}%</span>
                        </div>
                      ) : null}
                    </div>
                    {!isUploading ? (
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onRemoveFile(file.name)}>
                        <X className="h-4 w-4" />
                      </Button>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {uploadResults.length > 0 ? (
            <div className="space-y-2 rounded-xl border border-border bg-white p-3">
              <div className="text-sm font-medium text-foreground">导入结果</div>
              <div className="max-h-48 space-y-2 overflow-y-auto">
                {uploadResults.map((result) => (
                  <div
                    key={`${result.filename}-${result.document_id || result.message}`}
                    className={cn(
                      "rounded-lg border px-3 py-2 text-sm",
                      result.success
                        ? "border-success/20 bg-success-container/50 text-success"
                        : "border-destructive/20 bg-destructive/5 text-destructive",
                    )}
                  >
                    <div className="font-medium">{result.filename}</div>
                    <div className="mt-1 text-xs">{result.message}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {documents.length === 0 && !uploadEmbeddingModel && (
            <Alert>
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                未指定 embedding 模型时，本次导入仍会建立全文索引。
              </AlertDescription>
            </Alert>
          )}
        </div>
        <DialogFooter className="shrink-0 px-6 py-4">
          <Button
            variant="outline"
            onClick={isUploading ? onCancelUpload : () => onOpenChange(false)}
          >
            {isUploading ? "取消上传" : "取消"}
          </Button>
          <Button onClick={onUpload} disabled={uploadFiles.length === 0 || isUploading}>
            {isUploading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            开始导入
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface QueryDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  queryText: string;
  onQueryTextChange: (value: string) => void;
  querySearchMode: KnowledgeBaseSearchMode;
  onQuerySearchModeChange: (value: KnowledgeBaseSearchMode) => void;
  queryResults: Array<{ content: string; score: number }>;
  isQuerying: boolean;
  onQuery: () => void;
}

export function QueryDialog({
  open,
  onOpenChange,
  queryText,
  onQueryTextChange,
  querySearchMode,
  onQuerySearchModeChange,
  queryResults,
  isQuerying,
  onQuery,
}: QueryDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex flex-col h-[85vh] overflow-hidden p-0 sm:max-w-[600px]">
        <DialogHeader className="shrink-0 px-6 pt-6">
          <DialogTitle>检索知识库</DialogTitle>
          <DialogDescription>输入问题，检索相关知识片段</DialogDescription>
        </DialogHeader>
        <div className="flex-1 min-h-0 space-y-4 overflow-y-auto px-6 py-4">
          <div className="flex gap-1 rounded-md border border-border bg-muted/40 p-0.5">
            {SEARCH_MODE_OPTIONS.map((mode) => (
              <button
                key={mode.value}
                type="button"
                onClick={() => {
                  onQuerySearchModeChange(mode.value);
                  try { localStorage.setItem("kb-search-mode", mode.value); } catch { /* noop */ }
                }}
                className={`flex-1 rounded px-2 py-1 text-xs font-medium transition-colors ${
                  querySearchMode === mode.value
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {mode.label}
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            <Input
              placeholder="输入检索内容..."
              value={queryText}
              onChange={(e) => onQueryTextChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  void onQuery();
                }
              }}
            />
            <Button onClick={() => void onQuery()} disabled={isQuerying || !queryText.trim()}>
              {isQuerying ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Search className="h-4 w-4" />
              )}
            </Button>
          </div>

          {queryResults.length > 0 ? (
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">找到 {queryResults.length} 个相关片段</p>
              {queryResults.map((result, idx) => (
                <div key={`result-${idx}`} className="rounded-lg bg-muted p-3 text-sm">
                  <div className="mb-1 flex items-center justify-between">
                    <span className="text-xs font-medium">片段 {idx + 1}</span>
                    <span className="text-xs text-muted-foreground">
                      相关度: {(result.score * 100).toFixed(1)}%
                    </span>
                  </div>
                  <p className="line-clamp-4 text-muted-foreground">{result.content}</p>
                </div>
              ))}
            </div>
          ) : null}
        </div>
        <DialogFooter className="shrink-0 px-6 py-4">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface DeleteConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  deleteKind: "kb" | "doc";
  isDeleting: boolean;
  onConfirm: () => void;
}

export function DeleteConfirmDialog({
  open,
  onOpenChange,
  deleteKind,
  isDeleting,
  onConfirm,
}: DeleteConfirmDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={(v) => { if (!isDeleting) onOpenChange(v); }}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>确认删除</AlertDialogTitle>
          <AlertDialogDescription>
            {deleteKind === "kb"
              ? "确定要删除这个知识库吗？此操作不可恢复。"
              : "确定要删除这个文档吗？此操作不可恢复。"}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isDeleting} onClick={() => { if (!isDeleting) onOpenChange(false); }}>
            取消
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={() => void onConfirm()}
            disabled={isDeleting}
            className="bg-destructive text-destructive-foreground"
          >
            {isDeleting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            删除
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
