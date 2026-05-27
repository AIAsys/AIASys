"""Memory 核心模型。

长期 memory 内容使用纯文本 Markdown，运行态只保留 snapshot 元数据。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.services.memory.constants import USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE


class MemoryScope(str, Enum):
    """Memory 作用域。"""

    USER = USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE
    WORKSPACE = "workspace"


class MemorySnapshotRecord(BaseModel):
    """冻结后的 memory snapshot 记录。"""

    id: str
    user_id: str = Field(default="")
    workspace_id: str | None = None
    session_id: str | None = None
    version: str
    snapshot_hash: str
    system_markdown: str
    user_markdown: str
    workspace_markdown: str = ""
    generated_at: str = Field(default="")


class ResolvedMemoryPreview(BaseModel):
    """当前上下文 resolve 后的 memory 预览。"""

    version: str
    snapshot_hash: str
    rendered_markdown: str = ""
