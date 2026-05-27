"""文件管理 API

支持多用户隔离和认证。

此模块重新导出所有工具函数、模型和端点，保持统一命名空间。
核心实现已拆分到 files_utils、files_core 子模块。
"""

from __future__ import annotations

from fastapi import APIRouter

# Re-export endpoints from sub-modules

# Re-export utilities so tests and other consumers can still access them
# from app.api.routes.files directly.

router = APIRouter(prefix="/files", tags=["files"])

# Include sub-routers (prefix is handled by this parent router)
import app.api.routes.files_core as _files_core

router.include_router(_files_core.router)
