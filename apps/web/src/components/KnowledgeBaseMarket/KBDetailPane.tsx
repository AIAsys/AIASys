import {
  AlertCircle,
  ChevronLeft,
  Database,
  FileText,
  Loader2,
  Search,
  Trash2,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { KnowledgeBase, Document } from "@/types/knowledge";
import { DocumentStatusBadge } from "./DocumentStatusBadge";
import { formatDate, formatFileSize, getFileIcon, getStatusBadge } from "./utils";
import { SEARCH_MODE_OPTIONS, normalizeSearchMode } from "./constants";

interface KBDetailPaneProps {
  selectedKB: KnowledgeBase;
  documents: Document[];
  isLoadingDocs: boolean;
  documentChunkCount: number;
  isSplitLayout: boolean;
  onBack: () => void;
  onUpload: () => void;
  onQuery: () => void;
  onDeleteDoc: (docId: string) => void;
}

export function KBDetailPane({
  selectedKB,
  documents,
  isLoadingDocs,
  documentChunkCount,
  isSplitLayout,
  onBack,
  onUpload,
  onQuery,
  onDeleteDoc,
}: KBDetailPaneProps) {
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
