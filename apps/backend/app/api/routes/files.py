"""文件管理 API

支持多用户隔离和认证。

此模块重新导出所有工具函数、模型和端点，保持统一命名空间。
核心实现已拆分到 files_utils、files_core 子模块。
"""

from __future__ import annotations

from fastapi import APIRouter

# Re-export endpoints from sub-modules
from app.api.routes.files_core import (  # noqa: E402, F401
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
from app.api.routes.files_utils import (  # noqa: E402, F401
    CsvPageUpdateRequest,
    CsvPreviewResponse,
    FileContentRequest,
    FileCopyRequest,
    FileCopyResponse,
    FileCreateRequest,
    FileCreateResponse,
    FileInfo,
    FileListResponse,
    FileMoveRequest,
    FileMoveResponse,
)

router = APIRouter(prefix="/files", tags=["files"])

# Include sub-routers (prefix is handled by this parent router)
import app.api.routes.files_core as _files_core

router.include_router(_files_core.router)
