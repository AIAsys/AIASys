import { FileText, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import type { AddGraphDocumentResponse } from "@/types/graphrag";
import { formatGraphNumber } from "../shared";

interface TextFormProps {
  documentText: string;
  documentId: string;
  resolveEntities: boolean;
  isSubmittingDocument: boolean;
  documentError: string | null;
  documentResult: AddGraphDocumentResponse | null;
  onTextChange: (text: string) => void;
  onIdChange: (id: string) => void;
  onResolveEntitiesChange: (value: boolean) => void;
  onSubmit: (e: React.FormEvent) => void;
}

export function TextForm({
  documentText,
  documentId,
  resolveEntities,
  isSubmittingDocument,
  documentError,
  documentResult,
  onTextChange,
  onIdChange,
  onResolveEntitiesChange,
  onSubmit,
}: TextFormProps) {
  return (
    <div id="graph-text-workbench" className="scroll-mt-24">
      <div className="mb-4">
        <div className="flex items-center gap-2 text-base font-semibold text-foreground">
          <FileText className="h-4 w-4" />
          文本构图
        </div>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          保留纯文本入口，适合联调、验收和小样本文档验证。
        </p>
      </div>

      <form className="space-y-4" onSubmit={onSubmit}>
        <div className="space-y-2">
          <Label htmlFor="graph-document-id">文档 ID</Label>
          <Input
            id="graph-document-id"
            value={documentId}
            onChange={(e) => onIdChange(e.target.value)}
            placeholder="例如 graphrag_frontend_demo_001"
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="graph-document-text">文档内容</Label>
          <Textarea
            id="graph-document-text"
            value={documentText}
            onChange={(e) => onTextChange(e.target.value)}
            placeholder="粘贴一段待构图文本，例如人物、设备、组织和关系描述。"
            className="min-h-[220px]"
          />
        </div>

        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-muted p-3">
          <Checkbox
            id="graph-resolve-entities"
            checked={resolveEntities}
            onCheckedChange={(checked) => onResolveEntitiesChange(checked === true)}
          />
          <Label
            htmlFor="graph-resolve-entities"
            className="cursor-pointer text-sm text-muted-foreground"
          >
            自动实体消歧
          </Label>
        </div>

        {documentError ? (
          <div className="rounded-xl border border-error/20 bg-error-container px-4 py-3 text-sm text-error">
            {documentError}
          </div>
        ) : null}

        {documentResult ? (
          <div className="grid gap-3 rounded-2xl border border-info/20 bg-info-container/80 p-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <div className="text-xs uppercase tracking-[0.18em] text-info">
                doc_id
              </div>
              <div className="mt-1 text-sm font-medium text-foreground">
                {documentResult.doc_id}
              </div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-[0.18em] text-info">
                实体
              </div>
              <div className="mt-1 text-sm font-medium text-foreground">
                {formatGraphNumber(documentResult.entity_count)}
              </div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-[0.18em] text-info">
                关系
              </div>
              <div className="mt-1 text-sm font-medium text-foreground">
                {formatGraphNumber(documentResult.relation_count)}
              </div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-[0.18em] text-info">
                合并实体
              </div>
              <div className="mt-1 text-sm font-medium text-foreground">
                {formatGraphNumber(documentResult.merged_entities)}
              </div>
            </div>
          </div>
        ) : null}

        <Button
          type="submit"
          className="w-full gap-2 sm:w-auto"
          disabled={isSubmittingDocument}
        >
          {isSubmittingDocument ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <FileText className="h-4 w-4" />
          )}
          提交文本构图
        </Button>
      </form>
    </div>
  );
}
