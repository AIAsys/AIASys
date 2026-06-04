/**
 * 知识库类型定义
 */

export interface KnowledgeBase {
  id: string;
  name: string;
  description?: string | null;
  user_id: string;
  kind: string;
  embedding_model?: string | null;
  chunk_size: number;
  chunk_overlap: number;
  default_search_mode: KnowledgeBaseSearchMode;
  default_extraction_mode?: string | null;
  extraction_mode_mapping?: Record<string, string> | null;
  document_count: number;
  init_status: KnowledgeBaseInitStatus;
  config_complete: boolean;
  config_issue?: string | null;
  config_version: number;
  last_indexed_config_version: number;
  can_edit_index_config: boolean;
  requires_reindex: boolean;
  scope: string;
  workspace_id?: string | null;
  created_at: string;
  updated_at: string;
}

export type KnowledgeBaseInitStatus =
  | "draft"
  | "ready"
  | "indexing"
  | "needs_reindex"
  | "error";
export type KnowledgeBaseSearchMode = "vector" | "fulltext" | "hybrid";
export type KnowledgeBaseExtractionMode = "enhanced" | "basic" | "docling";

export interface CreateKnowledgeBaseRequest {
  name: string;
  description?: string;
  embedding_model?: string;
  chunk_size?: number;
  chunk_overlap?: number;
  default_search_mode?: KnowledgeBaseSearchMode;
  default_extraction_mode?: string;
  extraction_mode_mapping?: Record<string, string>;
}

export interface UpdateKnowledgeBaseRequest {
  name?: string;
  description?: string;
  embedding_model?: string;
  chunk_size?: number;
  chunk_overlap?: number;
  default_search_mode?: KnowledgeBaseSearchMode;
  default_extraction_mode?: string;
  extraction_mode_mapping?: Record<string, string>;
}

export interface Document {
  id: string;
  knowledge_base_id: string;
  filename: string;
  file_type: string;
  file_size: number;
  status: "pending" | "processing" | "completed" | "failed";
  chunk_count: number;
  error_message?: string;
  created_at: string;
  updated_at: string;
}

export interface UploadDocumentResponse {
  success: boolean;
  document_id?: string;
  filename: string;
  message: string;
  chunk_count?: number;
  extraction_mode?: string;
  requested_extraction_mode?: string;
  search_mode?: KnowledgeBaseSearchMode;
  embedding_model?: string | null;
  chunk_size?: number;
  chunk_overlap?: number;
}

export interface UploadDocumentOptions {
  extraction_mode?: KnowledgeBaseExtractionMode;
  embedding_model?: string | null;
  chunk_size?: number;
  chunk_overlap?: number;
  search_mode?: KnowledgeBaseSearchMode;
}

export interface BatchUploadDocumentResponse {
  success: boolean;
  batch_id: string;
  knowledge_base_id: string;
  total: number;
  successful_count: number;
  failed_count: number;
  results: UploadDocumentResponse[];
  message: string;
  extraction_mode?: string;
  search_mode?: KnowledgeBaseSearchMode;
  embedding_model?: string | null;
  chunk_size?: number;
  chunk_overlap?: number;
}

export interface QueryRequest {
  query: string;
  top_k?: number;
  filter?: Record<string, unknown>;
  search_mode?: KnowledgeBaseSearchMode;
}

export interface QueryResult {
  content: string;
  score: number;
  document_id: string;
  document_name: string;
  chunk_index: number;
  metadata: Record<string, unknown>;
}

export interface QueryResponse {
  query: string;
  knowledge_base_id: string;
  results: QueryResult[];
  total: number;
}

export interface KnowledgeBaseHealth {
  status: "healthy" | "unhealthy";
  db_path: string;
  message?: string;
}

export interface KnowledgeBaseTableColumnInfo {
  name: string;
  type: string;
}

export interface KnowledgeBaseTableInfo {
  name: string;
  columns: KnowledgeBaseTableColumnInfo[];
}

export interface KnowledgeBaseRawQueryRequest {
  sql: string;
}

export interface KnowledgeBaseRawQueryResponse {
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
}
