"""文件管理 API

支持多用户隔离和认证。

此模块重新导出所有工具函数、模型和端点，保持统一命名空间。
核心实现已拆分到 files_utils、files_core 子模块。
"""

from __future__ import annotations

from fastapi import APIRouter

# Re-export endpoints from sub-modules
from app.api.routes.files_core import (
    copy_file,
    create_file,
    delete_file,
    download_file,
    export_markdown_document,
    export_workspace,
    get_csv_preview,
    get_file_content,
    list_all_files,
    move_file,
    update_csv_preview,
    update_file_content,
    upload_file,
)

# Re-export utilities so tests and other consumers can still access them
# from app.api.routes.files directly.
from app.api.routes.files_utils import (
    EDITABLE_EXTENSIONS,
    INTERNAL_SESSION_DIRS,
    INTERNAL_SESSION_FILES,
    RESOURCE_DB_EXTENSIONS,
    RESOURCE_METADATA_TABLE,
    WORKSPACE_DIR,
    WORKSPACE_MEMORY_MIRROR_PATH,
    CsvPageUpdateRequest,
    CsvPreviewResponse,
    FileContentRequest,
    FileContentResponse,
    FileCopyRequest,
    FileCopyResponse,
    FileCreateRequest,
    FileCreateResponse,
    FileInfo,
    FileListResponse,
    _build_memory_mirror_candidate_paths,
    _build_notebook_candidate_paths,
    _build_scoped_candidate_paths,
    _build_visible_file_info,
    _check_user_access,
    _clear_workspace_memory_from_mirror,
    _ensure_path_within_root,
    _get_logical_workspace_root,
    _get_notebook_edit_lock_reason,
    _get_session_owner_user_id,
    _get_user_workspace,
    _get_work_dir,
    _is_editable_file,
    _is_markdown_file,
    _is_notebook_file_name,
    _is_notebook_relative_path,
    _is_runtime_busy_for_session,
    _is_session_private_workspace_path,
    _is_workspace_memory_mirror_path,
    _iter_directory_files,
    _iter_session_files,
    _iter_visible_workspace_files,
    _normalize_relative_path,
    _resolve_memory_mirror_path,
    _resolve_notebook_path,
    _resolve_workspace_path,
    _resolve_workspace_path_for_write,
    _should_skip_session_file,
    _sync_workspace_memory_from_mirror,
    get_workspace_registry_service,
)

router = APIRouter(prefix="/files", tags=["files"])

# Include sub-routers (prefix is handled by this parent router)
import app.api.routes.files_core as _files_core

router.include_router(_files_core.router)
