"""
AIASys Memory 写入工具 (MemoryTool)。

允许 Agent 将持久化信息写入用户默认层 MEMORY.md，
跨会话保留。支持 add（追加）、replace（替换）、remove（删除）操作。
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.history import current_user_id
from app.services.memory.constants import MEMORY_FILE_NAME
from app.services.memory.resolver import invalidate_user_resolver_cache
from app.services.memory.store import MemoryCapacityError, MemorySecurityError, MemoryStore

logger = logging.getLogger(__name__)


class MemoryTool(AiasysTool):
    """将信息持久化到 MEMORY.md。"""

    name = "Memory"
    description = (
        "Save durable information to persistent memory that survives across sessions. "
        "Memory is injected into future turns, so keep it compact and focused on facts "
        "that will still matter later.\n\n"
        "WHEN TO SAVE:\n"
        "- User corrects you or says 'remember this'\n"
        "- User shares a durable preference, habit, or personal detail\n"
        "- User corrects a long-term project or workspace convention\n"
        "- A stable rule should persist across future sessions\n\n"
        "ACTIONS:\n"
        "- add: append a new entry\n"
        "- replace: update an existing entry by matching a unique substring (old_text)\n"
        "- remove: delete an existing entry by matching a unique substring (old_text)\n\n"
        "SKIP: trivial info, things easily re-discovered, temporary task state, "
        "single-run tool output, or ordinary environment observations."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "replace", "remove"],
                "description": "The action to perform.",
            },
            "content": {
                "type": "string",
                "description": "The entry content. Required for 'add' and 'replace'.",
            },
            "old_text": {
                "type": "string",
                "description": "Short unique substring identifying the entry to replace or remove. Required for 'replace' and 'remove'.",
            },
        },
        "required": ["action"],
    }

    def _get_store(
        self, ctx: dict[str, Any]
    ) -> tuple[str | None, MemoryStore | None, ToolResult | None]:
        """获取 MemoryStore 实例。出错时返回 (None, error_result)。"""
        user_id = str(ctx.get("user_id") or current_user_id.get() or "").strip()
        if not user_id:
            return (
                None,
                None,
                ToolResult(
                    content="Unable to determine user_id from context.",
                    is_error=True,
                ),
            )

        from app.core.config import get_user_global_memory_dir

        memory_dir = get_user_global_memory_dir(user_id)
        memory_path = memory_dir / MEMORY_FILE_NAME

        store = MemoryStore(memory_path)
        store.initialize()
        return user_id, store, None

    def _write_with_checks(
        self,
        store: MemoryStore,
        mutator,
    ) -> ToolResult:
        """通过 MemoryStore 写入，处理安全扫描和容量限制异常。"""
        from app.services.memory.constants import MAX_MEMORY_SIZE

        try:
            new_text = store.update_text(mutator, max_size=MAX_MEMORY_SIZE)
            return ToolResult(content=f"Memory updated. Current size: {len(new_text)} chars.")
        except MemorySecurityError as exc:
            return ToolResult(
                content=f"Security check failed: {exc}",
                is_error=True,
            )
        except MemoryCapacityError as exc:
            return ToolResult(
                content=f"Capacity limit reached: {exc}",
                is_error=True,
            )

    async def _do_add(
        self,
        store: MemoryStore,
        content: str,
    ) -> ToolResult:
        """追加新条目到 MEMORY.md。"""

        def mutate(existing: str) -> str:
            existing = existing.strip()
            if existing:
                return existing + "\n\n" + content
            return content

        return self._write_with_checks(store, mutate)

    async def _do_replace(
        self,
        store: MemoryStore,
        old_text: str,
        content: str,
    ) -> ToolResult:
        """按子串匹配替换已有条目。"""

        def mutate(existing: str) -> str:
            idx = existing.find(old_text)
            if idx == -1:
                raise ValueError(f"No entry containing '{old_text}' found in memory.")
            return existing[:idx] + content + existing[idx + len(old_text) :]

        try:
            return self._write_with_checks(store, mutate)
        except ValueError as exc:
            return ToolResult(content=str(exc), is_error=True)

    async def _do_remove(
        self,
        store: MemoryStore,
        old_text: str,
    ) -> ToolResult:
        """按子串匹配删除已有条目。删除包含该子串的整行/整段。"""

        def mutate(existing: str) -> str:
            idx = existing.find(old_text)
            if idx == -1:
                raise ValueError(f"No entry containing '{old_text}' found in memory.")

            para_start = existing.rfind("\n\n", 0, idx)
            if para_start == -1:
                para_start = 0
            else:
                para_start += 2

            para_end = existing.find("\n\n", idx)
            if para_end == -1:
                para_end = len(existing)

            before = existing[:para_start]
            after = existing[para_end:]
            return (
                before.rstrip() + "\n\n" + after.lstrip()
                if before and after
                else (before + after).strip()
            )

        try:
            return self._write_with_checks(store, mutate)
        except ValueError as exc:
            return ToolResult(content=str(exc), is_error=True)

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        ctx = ctx or {}
        action = str(kwargs.get("action", "")).strip().lower()
        content = str(kwargs.get("content", "")).strip()
        old_text = str(kwargs.get("old_text", "")).strip()

        user_id, store, error = self._get_store(ctx)
        if error:
            return error
        assert user_id is not None
        assert store is not None

        if action == "add":
            if not content:
                return ToolResult(
                    content="Content is required for 'add' action.",
                    is_error=True,
                )
            result = await self._do_add(store, content)
            if not result.is_error:
                invalidate_user_resolver_cache(user_id)
            return result

        elif action == "replace":
            if not old_text:
                return ToolResult(
                    content="old_text is required for 'replace' action.",
                    is_error=True,
                )
            if not content:
                return ToolResult(
                    content="content is required for 'replace' action.",
                    is_error=True,
                )
            result = await self._do_replace(store, old_text, content)
            if not result.is_error:
                invalidate_user_resolver_cache(user_id)
            return result

        elif action == "remove":
            if not old_text:
                return ToolResult(
                    content="old_text is required for 'remove' action.",
                    is_error=True,
                )
            result = await self._do_remove(store, old_text)
            if not result.is_error:
                invalidate_user_resolver_cache(user_id)
            return result

        return ToolResult(
            content=f"Unknown action '{action}'. Use: add, replace, remove",
            is_error=True,
        )
