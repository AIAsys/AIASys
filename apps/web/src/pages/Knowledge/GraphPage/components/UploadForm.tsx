import { Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Loader2 } from "lucide-react";
import type { GraphExtractionMode, UploadGraphDocumentResponse } from "@/types/graphrag";
import { formatGraphNumber } from "../shared";

const EXTRACTION_MODE_OPTIONS: Array<{
  value: GraphExtractionMode;
  label: string;
  description: string;
}> = [
  {
    value: "basic",
    label: "basic",
    description: "轻量解析，速度快，适合简单文本和结构简单文档。",
  },
  {
    value: "enhanced",
    label: "enhanced",
    description: "增强解析，对 Word 顺序和表格更友好。",
  },
  {
    value: "docling",
    label: "docling",
    description: "高质量转换，适合复杂版式，但资源消耗更高。",
  },
];

const GRAPH_UPLOAD_ACCEPT =
  ".txt,.md,.markdown,.pdf,.doc,.docx,.xlsx,.xlsm,.csv,.json,.yaml,.yml,.toml,.ini,.log";

interface UploadFormProps {
  uploadFile: File | null;
  uploadDocumentId: string;
  uploadExtractionMode: GraphExtractionMode;
  uploadResolveEntities: boolean;
  isUploadingDocument: boolean;
  uploadError: string | null;
  uploadResult: UploadGraphDocumentResponse | null;
  onFileChange: (file: File | null) => void;
  onDocumentIdChange: (id: string) => void;
  onExtractionModeChange: (mode: GraphExtractionMode) => void;
  onResolveEntitiesChange: (value: boolean) => void;
  onSubmit: (e: React.FormEvent) => void;
}

export function UploadForm({
  uploadFile,
  uploadDocumentId,
  uploadExtractionMode,
  uploadResolveEntities,
  isUploadingDocument,
  uploadError,
  uploadResult,
  onFileChange,
  onDocumentIdChange,
  onExtractionModeChange,
  onResolveEntitiesChange,
  onSubmit,
}: UploadFormProps) {
  return (
    <div
      id="graph-upload-workbench"
      className="scroll-mt-24 rounded-3xl border border-border bg-muted/70 p-5"
    >
      <div className="mb-4">
        <div className="flex items-center gap-2 text-base font-semibold text-foreground">
          <Upload className="h-4 w-4" />
          文件构图
        </div>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          上传后会复用共享文档提取模块，支持 basic、enhanced、docling 解析模式。
        </p>
      </div>

      <form className="space-y-4" onSubmit={onSubmit}>
        <div className="space-y-2">
          <Label htmlFor="graph-upload-file">选择文件</Label>
          <Input
            id="graph-upload-file"
            type="file"
            accept={GRAPH_UPLOAD_ACCEPT}
            onChange={(e) => onFileChange(e.target.files?.[0] || null)}
          />
          <p className="text-xs leading-5 text-muted-foreground">
            支持 TXT / Markdown / PDF / DOC / DOCX / XLSX / XLSM。默认使用 enhanced。
          </p>
        </div>

        {uploadFile ? (
          <div className="rounded-2xl border border-border bg-white px-4 py-3 text-sm text-muted-foreground">
            当前文件:{" "}
            <span className="font-medium text-foreground">
              {uploadFile.name}
            </span>
          </div>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="graph-upload-document-id">文档 ID</Label>
            <Input
              id="graph-upload-document-id"
              value={uploadDocumentId}
              onChange={(e) => onDocumentIdChange(e.target.value)}
              placeholder="可选，例如 graphrag_doc_001"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="graph-upload-extraction-mode">解析模式</Label>
            <Select
              value={uploadExtractionMode}
              onValueChange={(value) => onExtractionModeChange(value as GraphExtractionMode)}
            >
              <SelectTrigger id="graph-upload-extraction-mode">
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
            <p className="text-xs leading-5 text-muted-foreground">
              {
                EXTRACTION_MODE_OPTIONS.find(
                  (option) => option.value === uploadExtractionMode,
                )?.description
              }
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-white p-3">
          <Checkbox
            id="graph-upload-resolve-entities"
            checked={uploadResolveEntities}
            onCheckedChange={(checked) => onResolveEntitiesChange(checked === true)}
          />
          <Label
            htmlFor="graph-upload-resolve-entities"
            className="cursor-pointer text-sm text-muted-foreground"
          >
            自动实体消歧
          </Label>
        </div>

        {uploadError ? (
          <div className="rounded-xl border border-error/20 bg-error-container px-4 py-3 text-sm text-error">
            {uploadError}
          </div>
        ) : null}

        {uploadResult ? (
          <div className="space-y-3 rounded-2xl border border-success/20 bg-success-container/80 p-4">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <div className="text-xs uppercase tracking-[0.18em] text-success">
                  doc_id
                </div>
                <div className="mt-1 text-sm font-medium text-foreground">
                  {uploadResult.doc_id}
                </div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-[0.18em] text-success">
                  解析模式
                </div>
                <div className="mt-1 text-sm font-medium text-foreground">
                  {uploadResult.extraction_mode}
                </div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-[0.18em] text-success">
                  文件类型
                </div>
                <div className="mt-1 text-sm font-medium text-foreground">
                  {uploadResult.file_type}
                </div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-[0.18em] text-success">
                  实体
                </div>
                <div className="mt-1 text-sm font-medium text-foreground">
                  {formatGraphNumber(uploadResult.entity_count)}
                </div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-[0.18em] text-success">
                  关系
                </div>
                <div className="mt-1 text-sm font-medium text-foreground">
                  {formatGraphNumber(uploadResult.relation_count)}
                </div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-[0.18em] text-success">
                  提取字符
                </div>
                <div className="mt-1 text-sm font-medium text-foreground">
                  {formatGraphNumber(uploadResult.text_length)}
                </div>
              </div>
            </div>

            {uploadResult.warnings.length > 0 ? (
              <div className="rounded-xl border border-warning/20 bg-warning-container px-4 py-3 text-sm text-warning">
                {uploadResult.warnings.join("；")}
              </div>
            ) : null}
          </div>
        ) : null}

        <Button
          type="submit"
          className="w-full gap-2 sm:w-auto"
          disabled={isUploadingDocument}
        >
          {isUploadingDocument ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Upload className="h-4 w-4" />
          )}
          上传并构图
        </Button>
      </form>
    </div>
  );
}
