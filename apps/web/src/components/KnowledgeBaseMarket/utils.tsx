// 格式化工具函数

import {
  File as FileIcon,
  FileCode,
  FileImage,
  FileSpreadsheet,
  FileText,
} from "lucide-react";
import type { LLMModelConfig } from "@/lib/api/llm";
import type { KnowledgeBase } from "@/types/knowledge";

export function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

export function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function getFileIcon(filename: string) {
  const ext = filename.split(".").pop()?.toLowerCase();
  switch (ext) {
    case "pdf":
      return <FileText className="h-8 w-8 text-error" />;
    case "doc":
    case "docx":
      return <FileText className="h-8 w-8 text-tertiary" />;
    case "md":
    case "txt":
      return <FileCode className="h-8 w-8 text-muted-foreground" />;
    case "xls":
    case "xlsx":
    case "csv":
      return <FileSpreadsheet className="h-8 w-8 text-success" />;
    case "png":
    case "jpg":
    case "jpeg":
    case "gif":
      return <FileImage className="h-8 w-8 text-info" />;
    default:
      return <FileIcon className="h-8 w-8 text-muted-foreground" />;
  }
}

export function toPositiveInteger(value: string, fallback: number): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function formatEmbeddingModel(model: LLMModelConfig): string {
  const dimension = typeof model.dimension === "number" ? ` · ${model.dimension}维` : "";
  return `${model.name || model.model}${dimension}`;
}

export function getStatusBadge(kb: KnowledgeBase): { label: string; className: string } {
  switch (kb.init_status) {
    case "draft":
      return {
        label: "待配置",
        className:
          "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-400",
      };
    case "indexing":
      return {
        label: "索引中",
        className:
          "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-400",
      };
    case "needs_reindex":
      return {
        label: "需重建",
        className:
          "border-orange-200 bg-orange-50 text-orange-700 dark:border-orange-900 dark:bg-orange-950/30 dark:text-orange-400",
      };
    case "error":
      return {
        label: "异常",
        className:
          "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400",
      };
    default:
      return {
        label: "可使用",
        className:
          "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-400",
      };
  }
}
