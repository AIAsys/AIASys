export type GraphExtractionMode =
  | "basic"
  | "enhanced"
  | "docling";

export interface GraphEntity {
  entity_id?: string;
  name: string;
  entity_type: string;
  description?: string | null;
  properties: Record<string, unknown>;
}

export interface UpdateGraphEntityRequest {
  name?: string;
  entity_type?: string;
  description?: string;
  properties?: Record<string, unknown>;
}

export interface CreateGraphEntityRequest {
  name: string;
  entity_type?: string;
  description?: string;
  properties?: Record<string, unknown>;
}

export interface CreateGraphRelationRequest {
  source_entity_id: string;
  target_entity_id: string;
  relation_type?: string;
  description?: string;
  strength?: number;
  properties?: Record<string, unknown>;
}

export interface GraphRelation {
  relation_id: string;
  source: string;
  source_name: string;
  target: string;
  target_name: string;
  relation_type: string;
  description?: string | null;
  strength: number;
  properties: Record<string, unknown>;
}

export interface DeleteGraphEntityResponse {
  entity_id: string;
  name: string;
  deleted_relations: number;
}

export interface GraphStatistics {
  entity_count: number;
  relation_count: number;
  entity_types: string[];
  communities?: Record<string, number> | null;
  llm_status: string;
}

export interface GraphHealth {
  status: string;
  entities: number;
  relations: number;
  llm_status: string;
  kb_id: string;
}

export interface GraphLlmStatus {
  status: string;
  initialized: boolean;
  extractor_available: boolean;
  resolver_available: boolean;
  reporter_available: boolean;
  config_source: string;
}

export interface AddGraphDocumentRequest {
  content: string;
  doc_id?: string;
  resolve_entities?: boolean;
}

export interface AddGraphDocumentResponse {
  doc_id: string;
  entity_count: number;
  relation_count: number;
  token_count: number;
  merged_entities: number;
}

export interface UploadGraphDocumentOptions {
  doc_id?: string;
  resolve_entities?: boolean;
  extraction_mode?: GraphExtractionMode;
}

export interface UploadGraphDocumentResponse extends AddGraphDocumentResponse {
  filename: string;
  file_type: string;
  extraction_mode: GraphExtractionMode;
  requested_mode: GraphExtractionMode;
  warnings: string[];
  text_length: number;
}

export interface GraphQueryRequest {
  question: string;
  top_k?: number;
  depth?: number;
  use_communities?: boolean;
}

export interface GraphQueryCommunity {
  community_id: string;
  overlap_entities: string[];
  size: number;
  nodes: string[];
}

export interface GraphVisualizationNode {
  id: string;
  name: string;
  entity_type: string;
  description?: string | null;
  degree: number;
  community_ids: string[];
  primary_community?: string | null;
  properties: Record<string, unknown>;
}

export interface GraphVisualizationEdge {
  id: string;
  source: string;
  target: string;
  relation_type: string;
  description?: string | null;
  strength: number;
  metadata: Record<string, unknown>;
}

export interface GraphVisualizationResponse {
  source: string;
  nodes: GraphVisualizationNode[];
  edges: GraphVisualizationEdge[];
  truncated: boolean;
  total_nodes: number;
  total_edges: number;
}

export interface GraphQueryResponse {
  question: string;
  entities: GraphEntity[];
  context: string;
  subgraph_stats?: {
    nodes: number;
    edges: number;
  };
  subgraph?: GraphVisualizationResponse | null;
  communities?: GraphQueryCommunity[] | null;
}

export interface GraphSearchResponse {
  results: GraphEntity[];
  count: number;
}

export interface GraphCommunitySummary {
  community_id: string;
  size: number;
  weight: number;
  entity_types: Record<string, number>;
  key_entities: string[];
}

export interface GraphCommunityReportsResponse {
  level: number;
  reports_count: number;
  reports: Record<string, string>;
}

export interface GraphTableColumnInfo {
  name: string;
  type: string;
}

export interface GraphTableInfo {
  name: string;
  columns: GraphTableColumnInfo[];
}

export interface GraphRawQueryRequest {
  sql: string;
}

export interface GraphRawQueryResponse {
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
}
