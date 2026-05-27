import type { SessionRuntimeSummary } from "./workspace";

export type NotebookStorageScope = "session" | "workspace";
export type NotebookCellType = "code" | "markdown" | "raw";
export type NotebookRunScope = "cell" | "range" | "all";
export type NotebookInsertPosition = "start" | "end" | "before" | "after";

export interface NotebookOutputSummary {
  output_type: string;
  name?: string | null;
  text_preview?: string | null;
  mime_types: string[];
  has_binary_payload: boolean;
}

export interface NotebookCell {
  cell_id: string;
  cell_type: NotebookCellType;
  source: string;
  metadata: Record<string, unknown>;
  execution_count?: number | null;
  outputs: Array<Record<string, unknown>>;
  output_summaries: NotebookOutputSummary[];
}

export interface NotebookCellInput {
  cell_id?: string | null;
  cell_type: NotebookCellType;
  source: string;
  metadata?: Record<string, unknown>;
  outputs?: Array<Record<string, unknown>>;
  execution_count?: number | null;
}

export interface NotebookState {
  notebook_path: string;
  storage_scope: NotebookStorageScope;
  resolved_from: NotebookStorageScope;
  write_target_scope: NotebookStorageScope;
  session_file_exists: boolean;
  workspace_file_exists: boolean;
  has_session_override: boolean;
  can_fork_to_session: boolean;
  will_create_session_copy: boolean;
  writable: boolean;
  edit_lock_reason?: string | null;
  exists: boolean;
  modified_at?: string | null;
  size: number;
  runtime_summary: SessionRuntimeSummary;
  last_runtime_state?: string | null;
  last_execution_status?: string | null;
  last_execution_record_id?: string | null;
  execution_record_count: number;
}

export interface NotebookListItem {
  path: string;
  title: string;
  storage_scope: NotebookStorageScope;
  resolved_from: NotebookStorageScope;
  session_file_exists: boolean;
  workspace_file_exists: boolean;
  has_session_override: boolean;
  modified_at?: string | null;
  size: number;
  cell_count: number;
  code_cell_count: number;
  output_cell_count: number;
  parse_error?: string | null;
}

export interface NotebookDocument {
  notebook_path: string;
  title: string;
  state: NotebookState;
  metadata: Record<string, unknown>;
  nbformat: number;
  nbformat_minor: number;
  cells: NotebookCell[];
}

export interface NotebookListResponse {
  user_id: string;
  session_id: string;
  directory?: string | null;
  notebooks: NotebookListItem[];
  total: number;
}

export interface CreateNotebookRequest {
  notebook_path: string;
  title?: string | null;
  initial_cells?: NotebookCellInput[];
  metadata_patch?: Record<string, unknown>;
  overwrite?: boolean;
}

export interface SaveNotebookRequest {
  notebook_path: string;
  metadata: Record<string, unknown>;
  cells: NotebookCellInput[];
}

export interface InsertNotebookCellRequest {
  notebook_path: string;
  cell: NotebookCellInput;
  position?: NotebookInsertPosition;
  reference_cell_id?: string | null;
}

export interface UpdateNotebookCellRequest {
  notebook_path: string;
  cell_id: string;
  cell_type?: NotebookCellType;
  source?: string;
  metadata?: Record<string, unknown>;
  outputs?: Array<Record<string, unknown>>;
  execution_count?: number | null;
}

export interface MoveNotebookCellRequest {
  notebook_path: string;
  cell_id: string;
  direction?: "up" | "down";
  target_index?: number;
}

export interface DeleteNotebookCellRequest {
  notebook_path: string;
  cell_id: string;
}

export interface ClearNotebookOutputsRequest {
  notebook_path: string;
  cell_id?: string | null;
  clear_all?: boolean;
}

export interface RunNotebookRequest {
  notebook_path: string;
  scope?: NotebookRunScope;
  cell_id?: string | null;
  start_index?: number;
  end_index?: number;
  restart_runtime?: boolean;
  clear_previous_outputs?: boolean;
  stop_on_error?: boolean;
}

export interface NotebookRunCellResult {
  index: number;
  cell_id?: string | null;
  cell_type: NotebookCellType;
  status: "completed" | "failed" | "skipped";
  reason?: string | null;
  execution_count?: number | null;
  output_count: number;
  source_preview: string;
  output_summaries: NotebookOutputSummary[];
}

export interface NotebookRunResponse {
  notebook_path: string;
  status: "success" | "partial_success";
  executed_code_cell_count: number;
  stopped_on_error: boolean;
  stopped_reason?: string | null;
  runtime_summary: SessionRuntimeSummary;
  document: NotebookDocument;
  cells: NotebookRunCellResult[];
}

export interface NotebookSearchRequest {
  notebook_path: string;
  query: string;
  cell_type?: NotebookCellType | null;
  case_sensitive?: boolean;
  max_results?: number;
}

export interface NotebookSearchMatch {
  cell_id: string;
  cell_index: number;
  cell_type: NotebookCellType;
  source_preview: string;
  snippet: string;
  matched_fields: string[];
}

export interface NotebookSearchResponse {
  notebook_path: string;
  query: string;
  total_matches: number;
  matches: NotebookSearchMatch[];
}

export interface NotebookOutlineItem {
  item_type: "heading" | "code_cell" | "markdown_cell" | "raw_cell";
  cell_id: string;
  cell_index: number;
  level?: number | null;
  title: string;
  source_preview: string;
  execution_count?: number | null;
  has_outputs: boolean;
  has_error_output: boolean;
}

export interface NotebookOutlineResponse {
  notebook_path: string;
  items: NotebookOutlineItem[];
  total: number;
}

export interface NotebookVariableSummary {
  name: string;
  type_name: string;
  module_name?: string | null;
  size?: number | null;
  shape?: Array<unknown> | string | null;
  preview?: string | null;
}

export interface NotebookVariablesResponse {
  notebook_path: string;
  runtime_summary: SessionRuntimeSummary;
  variables: NotebookVariableSummary[];
  total: number;
}

export interface NotebookArtifactSummary {
  artifact_id: string;
  artifact_kind: "inline_output" | "stdout_log" | "stderr_log" | "file_ref";
  display_name: string;
  source_cell_id?: string | null;
  cell_index?: number | null;
  execution_count?: number | null;
  record_id?: string | null;
  mime_type?: string | null;
  relative_path?: string | null;
  inline_available: boolean;
}

export interface NotebookArtifactsResponse {
  notebook_path: string;
  artifacts: NotebookArtifactSummary[];
  total: number;
}

export interface NotebookExecutionRecord {
  record_id: string;
  sequence: number;
  status: string;
  started_at: string;
  finished_at: string;
  duration_ms?: number | null;
  source_cell_id?: string | null;
  cell_index?: number | null;
  execution_count?: number | null;
  result_preview_text?: string | null;
  stdout_ref?: string | null;
  stderr_ref?: string | null;
  artifact_refs: string[];
  error?: string | null;
}

export interface NotebookExecutionRecordsResponse {
  notebook_path: string;
  records: NotebookExecutionRecord[];
  total: number;
}

export interface NotebookWorkbenchIssue {
  area: "document" | "runtime" | "variables" | "artifacts" | "execution";
  detail: string;
}

export interface NotebookWorkbenchSummary {
  total_cell_count: number;
  code_cell_count: number;
  markdown_cell_count: number;
  raw_cell_count: number;
  executed_code_cell_count: number;
  output_cell_count: number;
  error_cell_count: number;
  variable_count: number;
  artifact_count: number;
  execution_record_count: number;
  latest_execution_status?: string | null;
  latest_execution_record_id?: string | null;
  runtime_busy: boolean;
  kernel_active: boolean;
}

export interface NotebookWorkbenchCellStatus {
  cell_id: string;
  cell_index: number;
  cell_type: NotebookCellType;
  status: "not_run" | "completed" | "failed" | "skipped" | "unknown";
  execution_count?: number | null;
  output_count: number;
  has_outputs: boolean;
  has_error_output: boolean;
  latest_record_id?: string | null;
  duration_ms?: number | null;
  source_preview: string;
}

export interface NotebookWorkbenchSnapshot {
  notebook_path: string;
  generated_at: string;
  document: NotebookDocument;
  runtime_state: NotebookRuntimeStateResponse;
  outline: NotebookOutlineResponse;
  variables: NotebookVariablesResponse;
  artifacts: NotebookArtifactsResponse;
  execution_records: NotebookExecutionRecordsResponse;
  cell_statuses: NotebookWorkbenchCellStatus[];
  summary: NotebookWorkbenchSummary;
  issues: NotebookWorkbenchIssue[];
}

export interface NotebookRuntimeStateResponse {
  notebook_path: string;
  runtime_summary: SessionRuntimeSummary;
  runtime_busy: boolean;
  kernel_active: boolean;
  can_interrupt: boolean;
  can_restart: boolean;
  can_stop: boolean;
  edit_lock_reason?: string | null;
}

export interface NotebookKernelSummary {
  notebook_path: string;
  kernel_active: boolean;
  is_busy: boolean;
  last_active_at: string;
  created_at?: string | null;
}

export interface NotebookRuntimeControlResponse {
  notebook_path: string;
  action: "interrupt" | "restart" | "stop";
  status: "success" | "noop";
  detail: string;
  runtime_summary: SessionRuntimeSummary;
  state: NotebookState;
}

export interface NotebookPromoteRequest {
  notebook_path: string;
  overwrite?: boolean;
}

export interface NotebookPromoteResponse {
  notebook_path: string;
  promoted_from_scope: NotebookStorageScope;
  overwritten_workspace_copy: boolean;
  state: NotebookState;
  document: NotebookDocument;
}

export interface NotebookDiffCellChange {
  cell_id: string;
  status: "added" | "removed" | "changed";
  cell_index_session?: number | null;
  cell_index_workspace?: number | null;
  changed_fields: string[];
  source_preview: string;
  unified_diff?: string | null;
}

export interface NotebookDiffResponse {
  notebook_path: string;
  session_exists: boolean;
  workspace_exists: boolean;
  metadata_changed: boolean;
  changed_cells: NotebookDiffCellChange[];
  total_changed_cells: number;
}
