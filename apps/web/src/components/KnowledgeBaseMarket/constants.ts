import type {
  KnowledgeBaseExtractionMode,
  KnowledgeBaseSearchMode,
} from "@/types/knowledge";

export const SEARCH_MODE_OPTIONS: Array<{
  value: KnowledgeBaseSearchMode;
  label: string;
}> = [
  { value: "fulltext", label: "全文" },
  { value: "vector", label: "向量" },
  { value: "hybrid", label: "混合" },
];

export const EXTRACTION_MODE_OPTIONS: Array<{
  value: KnowledgeBaseExtractionMode;
  label: string;
}> = [
  { value: "enhanced", label: "增强" },
  { value: "basic", label: "基础" },
  { value: "docling", label: "Docling" },
];

export function normalizeSearchMode(
  value?: string | null,
): KnowledgeBaseSearchMode {
  if (value === "vector" || value === "hybrid" || value === "fulltext") {
    return value;
  }
  return "fulltext";
}
