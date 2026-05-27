"""
Notebook workbench API 模型。
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

NotebookStorageScope = Literal["session", "workspace"]
NotebookCellType = Literal["code", "markdown", "raw"]
NotebookRunScope = Literal["cell", "range", "all"]
NotebookInsertPosition = Literal["start", "end", "before", "after"]


class NotebookOutputSummaryResponse(BaseModel):
    output_type: str
    name: Optional[str] = None
    text_preview: Optional[str] = None
    mime_types: list[str] = Field(default_factory=list)
    has_binary_payload: bool = False


class NotebookCellResponse(BaseModel):
    cell_id: str
    cell_type: NotebookCellType
    source: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    execution_count: Optional[int] = None
    outputs: list[dict[str, Any]] = Field(default_factory=list)
    output_summaries: list[NotebookOutputSummaryResponse] = Field(default_factory=list)


class NotebookCellInput(BaseModel):
    cell_id: Optional[str] = None
    cell_type: NotebookCellType
    source: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    outputs: list[dict[str, Any]] = Field(default_factory=list)
    execution_count: Optional[int] = None


class NotebookRuntimeSummaryResponse(BaseModel):
    runtime_kind: Optional[str] = None
    display_name: Optional[str] = None
    scope: Optional[str] = None
    start_policy: Optional[str] = None
    reuse_policy: Optional[str] = None
    control_mode: Optional[str] = None
    kernel_active: bool = False
    status: Optional[str] = None
    status_label: Optional[str] = None
    runtime_busy: bool = False
    env_id: Optional[str] = None
    sandbox_mode: Optional[str] = None


class NotebookStateResponse(BaseModel):
    notebook_path: str
    storage_scope: NotebookStorageScope
    resolved_from: NotebookStorageScope
    write_target_scope: NotebookStorageScope
    session_file_exists: bool = False
    workspace_file_exists: bool = False
    has_session_override: bool = False
    can_fork_to_session: bool = False
    will_create_session_copy: bool = False
    writable: bool = True
    edit_lock_reason: Optional[str] = None
    exists: bool = True
    modified_at: Optional[str] = None
    size: int = 0
    runtime_summary: NotebookRuntimeSummaryResponse = Field(
        default_factory=NotebookRuntimeSummaryResponse
    )
    last_runtime_state: Optional[str] = None
    last_execution_status: Optional[str] = None
    last_execution_record_id: Optional[str] = None
    execution_record_count: int = 0


class NotebookListItemResponse(BaseModel):
    path: str
    title: str
    storage_scope: NotebookStorageScope
    resolved_from: NotebookStorageScope
    session_file_exists: bool = False
    workspace_file_exists: bool = False
    has_session_override: bool = False
    modified_at: Optional[str] = None
    size: int = 0
    cell_count: int = 0
    code_cell_count: int = 0
    output_cell_count: int = 0
    parse_error: Optional[str] = None


class NotebookListResponse(BaseModel):
    user_id: str
    session_id: str
    directory: Optional[str] = None
    notebooks: list[NotebookListItemResponse] = Field(default_factory=list)
    total: int = 0


class NotebookDocumentResponse(BaseModel):
    notebook_path: str
    title: str
    state: NotebookStateResponse
    metadata: dict[str, Any] = Field(default_factory=dict)
    nbformat: int = 4
    nbformat_minor: int = 5
    cells: list[NotebookCellResponse] = Field(default_factory=list)


class CreateNotebookRequest(BaseModel):
    notebook_path: str = Field(description="要创建的 notebook 相对路径，仅允许 .ipynb")
    title: Optional[str] = Field(default=None, description="可选标题")
    initial_cells: list[NotebookCellInput] = Field(default_factory=list)
    metadata_patch: dict[str, Any] = Field(default_factory=dict)
    overwrite: bool = False


class NotebookPathRequest(BaseModel):
    notebook_path: str


class SaveNotebookRequest(BaseModel):
    notebook_path: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    cells: list[NotebookCellInput] = Field(default_factory=list)


class InsertNotebookCellRequest(BaseModel):
    notebook_path: str
    cell: NotebookCellInput
    position: NotebookInsertPosition = "end"
    reference_cell_id: Optional[str] = None


class UpdateNotebookCellRequest(BaseModel):
    notebook_path: str
    cell_id: str
    cell_type: Optional[NotebookCellType] = None
    source: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    outputs: Optional[list[dict[str, Any]]] = None
    execution_count: Optional[int] = None


class MoveNotebookCellRequest(BaseModel):
    notebook_path: str
    cell_id: str
    direction: Optional[Literal["up", "down"]] = None
    target_index: Optional[int] = Field(default=None, ge=0)


class ClearNotebookOutputsRequest(BaseModel):
    notebook_path: str
    cell_id: Optional[str] = None
    clear_all: bool = False


class RunNotebookRequest(BaseModel):
    notebook_path: str
    scope: NotebookRunScope = "all"
    cell_id: Optional[str] = None
    start_index: Optional[int] = Field(default=None, ge=0)
    end_index: Optional[int] = Field(default=None, ge=0)
    restart_runtime: bool = False
    clear_previous_outputs: bool = True
    stop_on_error: bool = True


class DeleteNotebookCellRequest(BaseModel):
    notebook_path: str
    cell_id: str


class NotebookRunCellResultResponse(BaseModel):
    index: int
    cell_id: Optional[str] = None
    cell_type: NotebookCellType
    status: Literal["completed", "failed", "skipped"]
    reason: Optional[str] = None
    execution_count: Optional[int] = None
    output_count: int = 0
    source_preview: str = ""
    output_summaries: list[NotebookOutputSummaryResponse] = Field(default_factory=list)


class NotebookRunResponse(BaseModel):
    notebook_path: str
    status: Literal["success", "partial_success"]
    executed_code_cell_count: int = 0
    stopped_on_error: bool = False
    stopped_reason: Optional[str] = None
    runtime_summary: NotebookRuntimeSummaryResponse = Field(
        default_factory=NotebookRuntimeSummaryResponse
    )
    document: NotebookDocumentResponse
    cells: list[NotebookRunCellResultResponse] = Field(default_factory=list)


class ForkNotebookResponse(BaseModel):
    notebook_path: str
    state: NotebookStateResponse
    document: NotebookDocumentResponse


class NotebookSearchRequest(BaseModel):
    notebook_path: str
    query: str = Field(min_length=1, description="要搜索的关键词")
    cell_type: Optional[NotebookCellType] = None
    case_sensitive: bool = False
    max_results: int = Field(default=50, ge=1, le=500)


class NotebookSearchMatchResponse(BaseModel):
    cell_id: str
    cell_index: int
    cell_type: NotebookCellType
    source_preview: str = ""
    snippet: str = ""
    matched_fields: list[str] = Field(default_factory=list)


class NotebookSearchResponse(BaseModel):
    notebook_path: str
    query: str
    total_matches: int = 0
    matches: list[NotebookSearchMatchResponse] = Field(default_factory=list)


class NotebookOutlineItemResponse(BaseModel):
    item_type: Literal["heading", "code_cell", "markdown_cell", "raw_cell"]
    cell_id: str
    cell_index: int
    level: Optional[int] = None
    title: str
    source_preview: str = ""
    execution_count: Optional[int] = None
    has_outputs: bool = False
    has_error_output: bool = False


class NotebookOutlineResponse(BaseModel):
    notebook_path: str
    items: list[NotebookOutlineItemResponse] = Field(default_factory=list)
    total: int = 0


class NotebookVariableSummaryResponse(BaseModel):
    name: str
    type_name: str
    module_name: Optional[str] = None
    size: Optional[int] = None
    shape: Optional[list[Any] | str] = None
    preview: Optional[str] = None


class NotebookVariablesResponse(BaseModel):
    notebook_path: str
    runtime_summary: NotebookRuntimeSummaryResponse = Field(
        default_factory=NotebookRuntimeSummaryResponse
    )
    variables: list[NotebookVariableSummaryResponse] = Field(default_factory=list)
    total: int = 0


class NotebookArtifactSummaryResponse(BaseModel):
    artifact_id: str
    artifact_kind: Literal["inline_output", "stdout_log", "stderr_log", "file_ref"]
    display_name: str
    source_cell_id: Optional[str] = None
    cell_index: Optional[int] = None
    execution_count: Optional[int] = None
    record_id: Optional[str] = None
    mime_type: Optional[str] = None
    relative_path: Optional[str] = None
    inline_available: bool = False


class NotebookArtifactsResponse(BaseModel):
    notebook_path: str
    artifacts: list[NotebookArtifactSummaryResponse] = Field(default_factory=list)
    total: int = 0


class NotebookExecutionRecordResponse(BaseModel):
    record_id: str
    sequence: int
    status: str
    started_at: str
    finished_at: str
    duration_ms: Optional[int] = None
    source_cell_id: Optional[str] = None
    cell_index: Optional[int] = None
    execution_count: Optional[int] = None
    result_preview_text: Optional[str] = None
    stdout_ref: Optional[str] = None
    stderr_ref: Optional[str] = None
    artifact_refs: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class NotebookExecutionRecordsResponse(BaseModel):
    notebook_path: str
    records: list[NotebookExecutionRecordResponse] = Field(default_factory=list)
    total: int = 0


class NotebookRuntimeStateResponse(BaseModel):
    notebook_path: str
    runtime_summary: NotebookRuntimeSummaryResponse = Field(
        default_factory=NotebookRuntimeSummaryResponse
    )
    runtime_busy: bool = False
    kernel_active: bool = False
    can_interrupt: bool = False
    can_restart: bool = False
    can_stop: bool = False
    edit_lock_reason: Optional[str] = None


class NotebookRuntimeControlResponse(BaseModel):
    notebook_path: str
    action: Literal["interrupt", "restart", "stop"]
    status: Literal["success", "noop"]
    detail: str
    runtime_summary: NotebookRuntimeSummaryResponse = Field(
        default_factory=NotebookRuntimeSummaryResponse
    )
    state: NotebookStateResponse


class NotebookKernelSummaryResponse(BaseModel):
    notebook_path: str
    kernel_active: bool = True
    is_busy: bool
    last_active_at: str
    created_at: str | None = None


class NotebookWorkbenchIssueResponse(BaseModel):
    area: Literal["document", "runtime", "variables", "artifacts", "execution"]
    detail: str


class NotebookWorkbenchSummaryResponse(BaseModel):
    total_cell_count: int = 0
    code_cell_count: int = 0
    markdown_cell_count: int = 0
    raw_cell_count: int = 0
    executed_code_cell_count: int = 0
    output_cell_count: int = 0
    error_cell_count: int = 0
    variable_count: int = 0
    artifact_count: int = 0
    execution_record_count: int = 0
    latest_execution_status: Optional[str] = None
    latest_execution_record_id: Optional[str] = None
    runtime_busy: bool = False
    kernel_active: bool = False


class NotebookWorkbenchCellStatusResponse(BaseModel):
    cell_id: str
    cell_index: int
    cell_type: NotebookCellType
    status: Literal["not_run", "completed", "failed", "skipped", "unknown"] = "not_run"
    execution_count: Optional[int] = None
    output_count: int = 0
    has_outputs: bool = False
    has_error_output: bool = False
    latest_record_id: Optional[str] = None
    duration_ms: Optional[int] = None
    source_preview: str = ""


class NotebookWorkbenchSnapshotResponse(BaseModel):
    notebook_path: str
    generated_at: str
    document: NotebookDocumentResponse
    runtime_state: NotebookRuntimeStateResponse
    outline: NotebookOutlineResponse
    variables: NotebookVariablesResponse
    artifacts: NotebookArtifactsResponse
    execution_records: NotebookExecutionRecordsResponse
    cell_statuses: list[NotebookWorkbenchCellStatusResponse] = Field(default_factory=list)
    summary: NotebookWorkbenchSummaryResponse = Field(
        default_factory=NotebookWorkbenchSummaryResponse
    )
    issues: list[NotebookWorkbenchIssueResponse] = Field(default_factory=list)


class NotebookPromoteRequest(BaseModel):
    notebook_path: str
    overwrite: bool = False


class NotebookPromoteResponse(BaseModel):
    notebook_path: str
    promoted_from_scope: NotebookStorageScope
    overwritten_workspace_copy: bool = False
    state: NotebookStateResponse
    document: NotebookDocumentResponse


class NotebookDiffCellChangeResponse(BaseModel):
    cell_id: str
    status: Literal["added", "removed", "changed"]
    cell_index_session: Optional[int] = None
    cell_index_workspace: Optional[int] = None
    changed_fields: list[str] = Field(default_factory=list)
    source_preview: str = ""
    unified_diff: str = ""


class NotebookDiffResponse(BaseModel):
    notebook_path: str
    session_exists: bool = False
    workspace_exists: bool = False
    metadata_changed: bool = False
    changed_cells: list[NotebookDiffCellChangeResponse] = Field(default_factory=list)
    total_changed_cells: int = 0
