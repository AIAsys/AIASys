"""
上下文管理 Mixin

负责会话上下文的设置、重置和资源清理
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.agents.tools.ask_user import AskUserStore, AskUser
from app.core.config import WORKSPACE_DIR, get_user_global_workspace_dir
from app.services.agent.agent_instructions import load_agent_instructions
from app.services.history import (
    current_code_timeout,
    current_env_id,
    current_global_workspace,
    current_runtime_env_vars,
    current_runtime_execution_plan,
    current_session_id,
    current_session_root,
    current_user_id,
    current_workspace,
)
from app.services.history.session_execution_journal import SessionExecutionJournal

if TYPE_CHECKING:
    from app.services.agent import AgentService

logger = logging.getLogger(__name__)
MEMORY_CONTEXT_TEXT_MAX_CHARS = 24000


def _truncate_memory_context_text(text: str) -> str:
    """限制首轮 memory 注入体积，避免摘要异常膨胀挤占上下文。"""
    if len(text) <= MEMORY_CONTEXT_TEXT_MAX_CHARS:
        return text
    truncated = text[:MEMORY_CONTEXT_TEXT_MAX_CHARS]
    last_break = truncated.rfind("\n")
    if last_break > MEMORY_CONTEXT_TEXT_MAX_CHARS * 0.5:
        truncated = truncated[:last_break]
    return truncated.rstrip() + "\n\n...（memory 内容已截断，请按需读取原始文件）"


def build_memory_tool_developer_instructions(
    work_dir: Path,
    max_chars: int = 15000,
) -> str | None:
    """构建 Codex 风格的 memory tool developer instructions，用于注入 system prompt。

    读取策略：
    1. 用户默认层 memory 根目录固定为 global_workspace/.aiasys/.memory/
    2. 尝试读取轻量 memory_summary.md
    3. 如果 summary 不存在或为空，返回 None（不注入）

    对齐 Codex 的实现方式：
    - 将 memory_summary 内容包装成开发者指令块
    - 限制字符数（默认 15000，约 3750 tokens）
    - 返回 None 表示无 memory 可注入

    Args:
        work_dir: 工作区目录（用于定位 user_id）
        max_chars: 最大字符数限制

    Returns:
        格式化的 developer instructions 字符串，或 None
    """
    try:
        session_dir = Path(work_dir)
        user_id = session_dir.parent.name

        from app.services.memory.resolver import (
            _get_memory_summary_path_if_exists,
        )

        # 传入 user 目录（session_dir.parent），让 _to_global_memory_path 正确映射
        summary_path = _get_memory_summary_path_if_exists(session_dir.parent)

        if summary_path is None or not summary_path.exists():
            return None

        summary_text = summary_path.read_text(encoding="utf-8").strip()
        if not summary_text:
            return None

        # 截断处理
        if len(summary_text) > max_chars:
            truncated = summary_text[:max_chars]
            last_break = truncated.rfind("\n")
            if last_break > max_chars * 0.5:
                truncated = truncated[:last_break]
            summary_text = truncated.rstrip() + "\n\n...（memory summary 已截断）"

        # 格式化为 developer instructions
        return f"""You have access to a cross-session memory system. Use it to maintain continuity across conversations.

## Memory Layout

- /global/.aiasys/.memory/memory_summary.md: condensed memory index (provided below)
- /global/.aiasys/.memory/MEMORY.md: full memory registry
- /global/.aiasys/.memory/raw_memories.md: raw extracted memories
- /global/.aiasys/.memory/rollout_summaries/: per-run evidence
- /workspace/.aiasys/memory/workspace_memory.md: workspace-specific memory (if bound)

## Memory Usage Guidelines

1. **Start with the summary below** — extract task-relevant keywords and context
2. **Search MEMORY.md** for detailed information using those keywords
3. **Only open raw_memories.md or rollout_summaries/** if MEMORY.md references them
4. **Stop lookup when you have enough context** — don't read everything

## Memory Update Policy

- Do NOT modify memory files during normal task execution
- Only update memory when explicitly asked by the user
- Memory updates are handled by a separate process after task completion

## Current Memory Summary

{summary_text}
"""
    except Exception as e:
        logger.warning("构建 memory developer instructions 失败: %s", e, exc_info=True)
        return None


def load_agent_instructions_for_user_message(
    workspace_dir: Path | None = None,
) -> str | None:
    """加载 AGENTS.md 规范文件内容，用于注入 user instructions 层。"""
    try:
        return load_agent_instructions(workspace_dir=workspace_dir)
    except Exception:
        logger.warning("加载 Agent Instructions 失败，已跳过", exc_info=True)
        return None


def build_memory_context_text(work_dir: Path) -> str | None:
    """加载 Codex 风格 memory summary 文本，用于注入 contextual user message。

    读取策略：
    1. 用户默认层 memory 根目录固定为 global_workspace/.aiasys/.memory/
    2. 先尝试读取轻量 memory_summary.md
    3. 如果 summary 不存在，fallback 到完整 resolve 预览
    """
    sections: list[str] = []
    try:
        session_dir = Path(str(work_dir))
        user_id = session_dir.parent.name
        session_id = session_dir.name

        from app.services.memory.resolver import (
            _get_memory_summary_path_if_exists,
            resolve_workspace_memory_context,
        )

        workspace_id, workspace_store = resolve_workspace_memory_context(
            session_dir=session_dir,
            user_id=user_id,
            session_id=session_id,
        )
        summary_path = _get_memory_summary_path_if_exists(session_dir.parent)
        if summary_path is not None and summary_path.exists():
            summary_text = summary_path.read_text(encoding="utf-8")
            clean_text = _truncate_memory_context_text(summary_text.strip())
            if clean_text:
                sections.append("## Memory")
                sections.append(
                    "You have access to a memory folder with guidance from prior runs. "
                    "Use it when the task depends on workspace history, conventions, or prior decisions. "
                    "Do not update memory files during this turn unless the user explicitly asks."
                )
                sections.append(
                    "Memory layout (use ReadFile or Shell to access):\n"
                    "- /global/.aiasys/.memory/memory_summary.md: already provided below; do not open it again.\n"
                    "- /global/.aiasys/.memory/MEMORY.md: searchable registry and primary memory file.\n"
                    "- /global/.aiasys/.memory/raw_memories.md: raw extracted memories, useful when the registry is not enough.\n"
                    "- /global/.aiasys/.memory/rollout_summaries/: per-run recaps and evidence snippets.\n"
                    "- /workspace/.aiasys/memory/workspace_memory.md: workspace-specific memory when a workspace is bound."
                )
                sections.append(
                    "Quick memory pass:\n"
                    "1. Skim the summary below and extract task-relevant keywords.\n"
                    "2. Search MEMORY.md using those keywords (Shell grep or ReadFile).\n"
                    "3. Only if MEMORY.md points to raw memories or rollout summaries, open the 1-2 most relevant files.\n"
                    "4. Stop lookup when there are no relevant hits."
                )
                sections.append("MEMORY_SUMMARY:")
                sections.append(clean_text)

        if not sections:
            from app.services.memory import resolve_session_memory_preview

            preview = resolve_session_memory_preview(
                session_dir=session_dir,
                user_id=user_id,
                session_id=session_id,
            )
            if preview.rendered_markdown.strip():
                sections.append("## Memory")
                sections.append(
                    "Memory summary is unavailable, so this turn includes a resolved AIASys memory snapshot. "
                    "Use it as read-only guidance for this run."
                )
                sections.append(_truncate_memory_context_text(preview.rendered_markdown.strip()))
    except Exception:
        logger.warning("memory context 构建失败，已跳过", exc_info=True)

    return "\n\n".join(sections) if sections else None


class ContextMixin:
    """上下文管理功能"""

    def _set_session_context(
        self: "AgentService",
        user_id: str,
        session_id: str,
        workspace_path: Path,
        session_root: Path,
        env_id: str | None,
        code_timeout: int | None = None,
        runtime_env_vars: dict[str, str] | None = None,
        runtime_execution_plan: object | None = None,
    ) -> dict[str, Any]:
        """设置会话上下文并返回 reset 所需 token。"""
        global_workspace_path = get_user_global_workspace_dir(user_id)
        global_workspace_path.mkdir(parents=True, exist_ok=True)
        return {
            "user_id": current_user_id.set(user_id),
            "session_id": current_session_id.set(session_id),
            "workspace": current_workspace.set(workspace_path),
            "session_root": current_session_root.set(session_root),
            "global_workspace": current_global_workspace.set(global_workspace_path),
            "env_id": current_env_id.set(env_id),
            "code_timeout": current_code_timeout.set(code_timeout),
            "runtime_env_vars": current_runtime_env_vars.set(runtime_env_vars),
            "runtime_execution_plan": current_runtime_execution_plan.set(runtime_execution_plan),
        }

    def _reset_session_context(self: "AgentService", tokens: dict[str, Any]) -> None:
        """重置会话上下文。"""
        reset_plan = [
            ("code_timeout", current_code_timeout),
            ("env_id", current_env_id),
            ("runtime_env_vars", current_runtime_env_vars),
            ("runtime_execution_plan", current_runtime_execution_plan),
            ("global_workspace", current_global_workspace),
            ("session_root", current_session_root),
            ("workspace", current_workspace),
            ("session_id", current_session_id),
            ("user_id", current_user_id),
        ]
        for token_name, context_var in reset_plan:
            token = tokens.get(token_name)
            if token is None:
                continue
            try:
                context_var.reset(token)
            except ValueError as exc:
                logger.warning("重置会话上下文失败，已降级忽略: field=%s error=%s", token_name, exc)

    async def _cleanup_session_resources(
        self: "AgentService",
        user_id: str,
        session_id: str,
        session_key: str,
        *,
        remove_runtime_instance: bool = False,
    ) -> None:
        """
        清理会话级资源。

        顺序：
        1. active_session
        2. ask_user sender
        3. ask_user pending
        4. runtime instance（如需要）
        5. session lock
        """
        runtime_session = self._active_sessions.pop(session_key, None)
        if runtime_session is not None:
            try:
                await runtime_session.close()
            except Exception as e:
                logger.warning(
                    "关闭 runtime session 失败: user=%s, session=%s, error=%s",
                    user_id,
                    session_id,
                    e,
                )

        try:
            AskUser.clear_event_sender(session_id)
            AskUserStore().cancel_by_session(session_id=session_id, user_id=user_id)
        except Exception as e:
            logger.warning(
                "清理 AskUser 资源失败: user=%s, session=%s, error=%s",
                user_id,
                session_id,
                e,
            )

        # 清理 monitor 进程（后台 shell 监听器）
        try:
            from app.services.agent.runtime_backends.aiasys.tools.monitor_tool import (
                get_monitor_service,
            )

            await get_monitor_service().cleanup_session(session_key)
        except Exception:
            logger.warning(
                "清理 monitor 资源失败: user=%s, session=%s",
                user_id,
                session_id,
                exc_info=True,
            )

        # 清理连接器凭据配置文件
        try:
            from app.services.database.database_access_broker import (
                get_connector_credentials_path,
            )

            creds_path = get_connector_credentials_path(session_id)
            if creds_path.exists():
                creds_path.unlink()
        except Exception:
            logger.warning(
                "清理连接器凭据文件失败: user=%s, session=%s",
                user_id,
                session_id,
                exc_info=True,
            )

        if remove_runtime_instance:
            try:
                from app.agents.tools.local_ipython_box import LocalIPythonBox

                had_kernel = LocalIPythonBox.has_kernel(session_id=session_id, user_id=user_id)
                LocalIPythonBox.shutdown_kernel(session_id=session_id, user_id=user_id)
                if had_kernel:
                    session_dir = WORKSPACE_DIR / user_id / session_id
                    if session_dir.exists():
                        SessionExecutionJournal(session_dir, session_id).update_recovery_config(
                            last_runtime_state="discarded"
                        )
            except Exception as e:
                logger.warning(
                    "清理本地运行态失败: user=%s, session=%s, error=%s",
                    user_id,
                    session_id,
                    e,
                )

        # 清理 memory resolver 缓存，避免会话结束后仍持有过期快照
        try:
            from app.services.memory import invalidate_resolver_cache

            invalidate_resolver_cache(user_id, session_id)
        except Exception:
            logger.warning(
                "清理 memory resolver 缓存失败: user=%s, session=%s",
                user_id,
                session_id,
                exc_info=True,
            )

        # 清理子 Agent registry 中该会话的子 Agent
        try:
            from app.services.agent.subagent_registry import get_subagent_registry

            registry = get_subagent_registry()
            for agent_id in list(registry._host_session_ids.keys()):
                if registry._host_session_ids.get(agent_id) == session_key:
                    registry.cancel(agent_id)
                    registry.unregister(agent_id)
        except Exception:
            logger.warning("清理子 Agent registry 失败", exc_info=True)

        async with self._locks_lock:
            self._session_locks.pop(session_key, None)
