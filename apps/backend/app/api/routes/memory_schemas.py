"""Memory route request and response schemas（纯文本简化版）。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.memory.constants import USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE


class ResolveMemoryRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    workspace_id: str | None = None
    include_user_default_memory: bool = True
    include_workspace_memory: bool = True


class ResolveMemoryResponse(BaseModel):
    version: str
    snapshot_hash: str
    rendered_markdown: str = ""
    current_memory_snapshot_version: str | None = None
    current_memory_snapshot_hash: str | None = None
    applied_memory_snapshot_version: str | None = None
    applied_memory_snapshot_hash: str | None = None
    pending_memory_snapshot_version: str | None = None
    pending_memory_snapshot_hash: str | None = None


class RegenerateMemorySummaryRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    scope: str = Field(..., min_length=1)
    session_id: str | None = None
    workspace_id: str | None = None


class MemorySummaryResponse(BaseModel):
    content: str


class MemoryPipelineJobStatus(BaseModel):
    kind: str
    job_key: str
    status: str
    worker_id: str | None = None
    lease_until: int | None = None
    attempt_count: int = 0
    last_error: str | None = None
    created_at: int
    updated_at: int
    completed_at: int | None = None
    workspace_id: str | None = None
    session_id: str | None = None


class MemoryConsolidationStatus(BaseModel):
    scope_key: str
    input_watermark: int = 0
    output_memory_hash: str | None = None
    output_summary_hash: str | None = None
    updated_at: int


class MemoryStage1Status(BaseModel):
    total_outputs: int = 0
    pending_outputs: int = 0
    latest_output_at: int | None = None
    latest_job: MemoryPipelineJobStatus | None = None


class MemoryStage2Status(BaseModel):
    latest_consolidated_at: int | None = None
    latest_job: MemoryPipelineJobStatus | None = None
    consolidation: MemoryConsolidationStatus | None = None


class MemoryPipelineStatusResponse(BaseModel):
    user_id: str
    scope_key: str = USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE
    stage1: MemoryStage1Status
    stage2: MemoryStage2Status
    state_db_path: str
    memory_root_path: str


class MemoryRetentionRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    keep_latest: int | None = Field(default=None, ge=1)
    max_age_days: int | None = Field(default=None, ge=0)


class MemoryRetentionResponse(BaseModel):
    success: bool = True
    pruned_count: int = 0
    pruned_rollout_slugs: list[str] = Field(default_factory=list)
    retained_count: int = 0
    keep_latest: int
    max_age_days: int | None = None


class MemoryVersionItem(BaseModel):
    id: str
    version_type: str
    source: str | None = None
    created_at: int
    summary: str = ""  # 内容前 200 字摘要


class MemoryVersionListResponse(BaseModel):
    versions: list[MemoryVersionItem] = Field(default_factory=list)


class MemoryVersionDetailResponse(BaseModel):
    id: str
    user_id: str
    scope_key: str
    version_type: str
    source: str | None = None
    memory_content: str
    summary_content: str | None = None
    created_at: int


class RestoreMemoryVersionResponse(BaseModel):
    success: bool = True
    version_id: str
    restored_scope_key: str
