import { FileText, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { AddGraphDocumentResponse, UploadGraphDocumentResponse } from "@/types/graphrag";
import { EmptyState, formatGraphNumber } from "../shared";

interface ResultsPanelProps {
  uploadResult: UploadGraphDocumentResponse | null;
  documentResult: AddGraphDocumentResponse | null;
  onOpenUpload: () => void;
  onOpenText: () => void;
}

export function ResultsPanel({
  uploadResult,
  documentResult,
  onOpenUpload,
  onOpenText,
}: ResultsPanelProps) {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="rounded-3xl border border-success/20 bg-success-container/70 p-5">
        <div className="flex items-center gap-2 text-base font-semibold text-foreground">
          <Upload className="h-4 w-4" />
          最近文件构图结果
        </div>
        {uploadResult ? (
          <div className="mt-4 space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-2xl bg-white px-4 py-3 shadow-sm">
                <div className="text-xs uppercase tracking-[0.18em] text-success">
                  doc_id
                </div>
                <div className="mt-1 text-sm font-medium text-foreground">
                  {uploadResult.doc_id}
                </div>
              </div>
              <div className="rounded-2xl bg-white px-4 py-3 shadow-sm">
                <div className="text-xs uppercase tracking-[0.18em] text-success">
                  文件
                </div>
                <div className="mt-1 text-sm font-medium text-foreground">
                  {uploadResult.filename}
                </div>
              </div>
              <div className="rounded-2xl bg-white px-4 py-3 shadow-sm">
                <div className="text-xs uppercase tracking-[0.18em] text-success">
                  实体 / 关系
                </div>
                <div className="mt-1 text-sm font-medium text-foreground">
                  {formatGraphNumber(uploadResult.entity_count)} / {formatGraphNumber(uploadResult.relation_count)}
                </div>
              </div>
              <div className="rounded-2xl bg-white px-4 py-3 shadow-sm">
                <div className="text-xs uppercase tracking-[0.18em] text-success">
                  解析模式
                </div>
                <div className="mt-1 text-sm font-medium text-foreground">
                  {uploadResult.extraction_mode}
                </div>
              </div>
            </div>
            <Button
              type="button"
              variant="outline"
              className="gap-2"
              onClick={onOpenUpload}
            >
              <Upload className="h-4 w-4" />
              继续文件构图
            </Button>
          </div>
        ) : (
          <EmptyState
            title="还没有文件构图结果"
            description="先切到「文件构图」上传一个文档，结果会自动沉淀到这里。"
          />
        )}
      </div>

      <div className="rounded-3xl border border-info/20 bg-info-container/70 p-5">
        <div className="flex items-center gap-2 text-base font-semibold text-foreground">
          <FileText className="h-4 w-4" />
          最近文本构图结果
        </div>
        {documentResult ? (
          <div className="mt-4 space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-2xl bg-white px-4 py-3 shadow-sm">
                <div className="text-xs uppercase tracking-[0.18em] text-info">
                  doc_id
                </div>
                <div className="mt-1 text-sm font-medium text-foreground">
                  {documentResult.doc_id}
                </div>
              </div>
              <div className="rounded-2xl bg-white px-4 py-3 shadow-sm">
                <div className="text-xs uppercase tracking-[0.18em] text-info">
                  实体
                </div>
                <div className="mt-1 text-sm font-medium text-foreground">
                  {formatGraphNumber(documentResult.entity_count)}
                </div>
              </div>
              <div className="rounded-2xl bg-white px-4 py-3 shadow-sm">
                <div className="text-xs uppercase tracking-[0.18em] text-info">
                  关系
                </div>
                <div className="mt-1 text-sm font-medium text-foreground">
                  {formatGraphNumber(documentResult.relation_count)}
                </div>
              </div>
              <div className="rounded-2xl bg-white px-4 py-3 shadow-sm">
                <div className="text-xs uppercase tracking-[0.18em] text-info">
                  合并实体
                </div>
                <div className="mt-1 text-sm font-medium text-foreground">
                  {formatGraphNumber(documentResult.merged_entities)}
                </div>
              </div>
            </div>
            <Button
              type="button"
              variant="outline"
              className="gap-2"
              onClick={onOpenText}
            >
              <FileText className="h-4 w-4" />
              继续文本构图
            </Button>
          </div>
        ) : (
          <EmptyState
            title="还没有文本构图结果"
            description="先切到「文本构图」提交一段内容，结果会自动沉淀到这里。"
          />
        )}
      </div>
    </div>
  );
}
