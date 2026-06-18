"""
执行操作 Mixin

负责同步和流式执行 Agent 任务
"""

import asyncio
import contextlib
import json
import logging
import re
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncGenerator

from app.models.worker_lifecycle import (
    build_worker_lifecycle_event,
    project_subagent_lifecycle_from_task_result,
)
from app.services.agent.message_content import (
    build_attachment_content_parts,
    downgrade_message_content_for_history,
    dump_message_content,
    extract_message_text,
)
from app.services.agent.mixins.environment import resolve_merged_env_vars_for_session
from app.services.agent.utils import get_session_key, get_work_dir
from app.services.memory import SessionDB
from app.services.memory.constants import MEMORY_DIR_NAME
from app.services.research_listener_service import (
    ResearchListenerContext,
    get_research_listener_service,
)
from app.services.runtime.runtime_execution import resolve_runtime_execution_plan
from app.services.runtime.session_runtime_state import (
    build_session_runtime_summary,
)
from app.services.runtime_tooling import is_subagent_dispatch_tool_name
from app.services.session.constants import SESSION_DIR_NAME
from app.services.task_resource_context import (
    build_task_resource_context,
    format_task_resource_context_for_prompt,
)
from app.services.workspace_registry import get_workspace_registry_service

if TYPE_CHECKING:
    from app.services.agent import AgentService

logger = logging.getLogger(__name__)


def _log_task_exception(task: asyncio.Task) -> None:
    with contextlib.suppress(asyncio.CancelledError):
        exc = task.exception()
        if exc is not None:
            logger.error("后台任务异常: %s", exc, exc_info=True)


def _resolve_agent_module():
    import app.services.agent as agent_service_module

    return agent_service_module


def _resolve_wrap_user_prompt():
    return _resolve_agent_module().wrap_user_prompt


def _resolve_append_display_history_entry():
    return _resolve_agent_module().append_display_history_entry


def _persist_message_to_session_db(
    *,
    user_id: str,
    session_id: str,
    role: str,
    content: str,
) -> None:
    work_dir = Path(str(get_work_dir(user_id, session_id)))
    db_path = work_dir / MEMORY_DIR_NAME / "sessions.db"
    SessionDB(db_path).add_message(
        session_id=session_id,
        user_id=user_id,
        role=role,
        content=content,
    )


def _persist_message_to_session_history(
    agent_service: "AgentService",
    *,
    user_id: str,
    session_id: str,
    role: str,
    content: Any,
    display_content: Any | None = None,
    reasoning_content: str | None = None,
    turn_n: int | None = None,
    origin: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(),
    }
    if display_content is not None:
        payload["display_content"] = display_content
    if reasoning_content is not None:
        payload["reasoning_content"] = reasoning_content
    if turn_n is not None:
        payload["turn_n"] = turn_n
    if origin is not None:
        payload["origin"] = origin
    agent_service._session_manager.add_message(
        session_id=session_id,
        user_id=user_id,
        message=payload,
    )


def _sync_session_messages_to_history(
    agent_service: "AgentService",
    *,
    user_id: str,
    session_id: str,
    session: Any,
) -> None:
    """将 runtime session 的完整消息列表同步到 history.json。

    替代仅持久化最终 assistant 文本的做法，确保中间轮次的 tool_calls
    和 tool 消息不丢失，避免 session 重建后 LLM 上下文断裂。

    只同步 user/assistant/tool 消息，过滤 system prompt、auto-nudge 等。
    """
    all_messages = getattr(session, "messages", None)
    if not isinstance(all_messages, list):
        return
    snapshot = [
        msg
        for msg in all_messages
        if isinstance(msg, dict) and msg.get("role") in {"user", "assistant", "tool"}
    ]
    agent_service._session_manager.sync_messages_to_history(
        session_id=session_id,
        user_id=user_id,
        messages=snapshot,
    )


def _persist_user_turn_artifacts(
    agent_service: "AgentService",
    *,
    user_id: str,
    session_id: str,
    session_root: Path,
    prompt: str,
    display_content: Any,
    transport_content: Any,
) -> None:
    """在 runtime session 已创建后持久化当前轮用户输入。

    新建 session 时，`create_session()` 会重置 `.aiasys/session/_active/history.json`
    和旧 sidecar 目录；因此首轮用户消息必须在 session 创建之后再落盘，
    否则会被初始化过程清空。
    """
    try:
        _resolve_append_display_history_entry()(
            session_root,
            session_id,
            role="user",
            content=display_content,
            transport_content=transport_content,
        )
    except Exception as e:
        logger.warning(
            "记录用户展示历史失败（继续执行）: user=%s, session=%s, error=%s",
            user_id,
            session_id,
            e,
        )
    try:
        _persist_message_to_session_db(
            user_id=user_id,
            session_id=session_id,
            role="user",
            content=prompt,
        )
    except Exception as e:
        logger.warning(
            "写入 memory 会话库失败（继续执行）: user=%s, session=%s, role=user, error=%s",
            user_id,
            session_id,
            e,
        )
    try:
        history_content = downgrade_message_content_for_history(transport_content)
        _persist_message_to_session_history(
            agent_service,
            user_id=user_id,
            session_id=session_id,
            role="user",
            content=history_content,
            display_content=display_content,
        )
    except Exception as e:
        logger.warning(
            "写入 session history 失败（继续执行）: user=%s, session=%s, role=user, error=%s",
            user_id,
            session_id,
            e,
        )


def _is_rewritten_last_user_message(
    agent_service: "AgentService",
    *,
    session_id: str,
    user_id: str,
    prompt: str,
) -> bool:
    try:
        history = agent_service._session_manager.get_history(session_id, user_id)
    except Exception:
        return False
    if not history:
        return False
    last_message = history[-1]
    if not isinstance(last_message, dict):
        return False
    if last_message.get("role") != "user" or not last_message.get("rewritten_from"):
        return False
    displayed = last_message.get("display_content", last_message.get("content"))
    return extract_message_text(displayed).strip() == prompt.strip()


def _stamp_transport_user_input_id(
    user_input: str | list[dict[str, Any]],
    message_id: str | None,
    *,
    force_list: bool = False,
) -> str | list[dict[str, Any]]:
    if not isinstance(message_id, str) or not message_id.strip():
        return user_input
    normalized_id = message_id.strip()
    if isinstance(user_input, str):
        if force_list:
            return [{"role": "user", "content": user_input, "id": normalized_id}]
        return user_input
    return [
        (
            {**item, "id": normalized_id}
            if isinstance(item, dict) and item.get("role", "user") == "user"
            else item
        )
        for item in user_input
    ]


def _get_host_wire_path(session_root: Path, session_id: str) -> Path:
    return session_root / SESSION_DIR_NAME / session_id / "wire.jsonl"


def _persist_host_execution_event(
    *,
    session_root: Path,
    session_id: str,
    event: dict[str, Any],
) -> None:
    try:
        wire_file = _get_host_wire_path(session_root, session_id)
        wire_file.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(event)
        payload.setdefault("timestamp", time.time())
        with open(wire_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning(
            "写入 host wire 事件失败（继续执行）: session=%s event_type=%s error=%s",
            session_id,
            event.get("type"),
            exc,
        )


def _build_host_turn_end_event() -> dict[str, Any]:
    return {"type": "turn_end"}


def _read_last_host_step(session_root: Path, session_id: str) -> int:
    wire_file = _get_host_wire_path(session_root, session_id)
    if not wire_file.exists():
        return 0

    last_step = 0
    try:
        with open(wire_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") != "step_begin":
                    continue
                step_n = event.get("step_n")
                if isinstance(step_n, int) and step_n > 0:
                    last_step = max(last_step, step_n)
    except Exception as exc:
        logger.warning(
            "读取 host wire 最后步骤失败（忽略）: session=%s error=%s",
            session_id,
            exc,
        )
    return last_step


def _schedule_claw_outbound_sync(*, user_id: str, session_id: str) -> None:
    try:
        from app.services.claw_runtime import get_claw_runtime_manager

        get_claw_runtime_manager().schedule_session_outbound(user_id, session_id)
    except Exception as exc:
        logger.warning(
            "调度 Claw 自动出站失败（忽略）: user=%s session=%s error=%s",
            user_id,
            session_id,
            exc,
        )


def _is_run_cancelled_error(exc: Exception) -> bool:
    run_cancelled_exc = getattr(_resolve_agent_module(), "RunCancelled", None)
    if run_cancelled_exc and isinstance(exc, run_cancelled_exc):
        return True
    return any(cls.__name__ == "RunCancelled" for cls in type(exc).mro())


def _is_context_length_exceeded_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "context_length_exceeded" in message or "maximum context length" in message


def _extract_model_config_value(
    model_config: Any,
    field_name: str,
) -> Any:
    if isinstance(model_config, dict):
        return model_config.get(field_name)
    return getattr(model_config, field_name, None)


def _classify_runtime_error(message_lower: str) -> str | None:
    """根据错误消息文本返回友好化分类 key，无法识别返回 None。"""
    if "context_length_exceeded" in message_lower or "maximum context length" in message_lower:
        return "context_length_exceeded"
    if (
        "401" in message_lower
        or "unauthorized" in message_lower
        or "invalid api key" in message_lower
    ):
        return "auth"
    if "403" in message_lower or "forbidden" in message_lower:
        return "forbidden"
    if (
        "402" in message_lower
        or "billing" in message_lower
        or "insufficient" in message_lower
        or "quota" in message_lower
    ):
        return "billing"
    if "404" in message_lower or "model_not_found" in message_lower:
        return "model_not_found"
    if "429" in message_lower or "rate_limit" in message_lower:
        return "rate_limit"
    if (
        "500" in message_lower
        or "502" in message_lower
        or "503" in message_lower
        or "server_error" in message_lower
        or "overloaded" in message_lower
    ):
        return "server"
    if "timeout" in message_lower or "timed out" in message_lower:
        return "timeout"
    return None


def _build_user_facing_runtime_error(exc: Exception, *, config: Any) -> str:
    raw_message = str(exc).strip() or "执行失败"
    message_lower = raw_message.lower()
    error_kind = _classify_runtime_error(message_lower)

    if error_kind == "context_length_exceeded":
        return _build_context_length_error_message(exc, raw_message, config)

    friendly_map = {
        "auth": "AI 模型认证失败，请检查 API Key 配置是否正确。",
        "forbidden": "AI 模型访问被拒绝，请检查账号权限或额度。",
        "billing": "AI 模型额度已用尽，请充值或更换模型提供商。",
        "model_not_found": "请求的 AI 模型不存在，请检查模型配置。",
        "rate_limit": "AI 模型请求过于频繁，请稍后重试。",
        "server": "AI 模型服务暂时不可用，请稍后重试。",
        "timeout": "AI 模型请求超时，请检查网络或稍后重试。",
    }

    friendly = friendly_map.get(error_kind)
    if friendly is not None:
        return f"{friendly}（原始错误: {raw_message}）"

    return raw_message


def _build_context_length_error_message(
    exc: Exception,
    raw_message: str,
    config: Any,
) -> str:
    default_model = getattr(config, "default_model", None)
    model_label = str(default_model) if default_model else "当前模型"
    max_context_size = None
    models = getattr(config, "models", None)
    if default_model and isinstance(models, dict) and default_model in models:
        max_context_size = _extract_model_config_value(
            models[default_model],
            "max_context_size",
        )

    loop_control = getattr(config, "loop_control", None)
    reserved_context_size = None
    compaction_trigger_ratio = None
    if isinstance(loop_control, dict):
        reserved_context_size = loop_control.get("reserved_context_size")
        compaction_trigger_ratio = loop_control.get("compaction_trigger_ratio")
    else:
        reserved_context_size = getattr(loop_control, "reserved_context_size", None)
        compaction_trigger_ratio = getattr(loop_control, "compaction_trigger_ratio", None)

    diagnostics = [
        "当前请求超过了模型上下文窗口，自动压缩没能在这次请求前腾出足够空间。",
    ]
    if max_context_size is not None:
        diagnostics.append(f"模型 `{model_label}` 的最大上下文窗口约为 {max_context_size} tokens。")
    if compaction_trigger_ratio is not None:
        diagnostics.append(f"当前自动压缩触发比例为 {compaction_trigger_ratio:.2f}。")
    if reserved_context_size is not None:
        diagnostics.append(f"当前为回复预留的上下文空间为 {reserved_context_size} tokens。")
    diagnostics.extend(
        [
            "可尝试先手动点击“压缩上下文”，或减少本轮输入/附件体量。",
            "如果经常逼近上限，可以切换到更大上下文窗口的模型，或把自动压缩触发比例调得更早一些。",
            f"底层返回：{raw_message}",
        ]
    )
    return "\n".join(diagnostics)


def _build_runtime_summary_for_prompt(
    agent_service: "AgentService",
    *,
    user_id: str,
    session_id: str,
    session_root: Path,
    sandbox_mode: str | None,
    env_id: str | None,
) -> dict[str, Any] | None:
    try:
        metadata = agent_service._session_manager.get_session(session_id, user_id)
        execution_summary = agent_service._session_manager.get_execution_summary(
            session_id,
            user_id,
        )
        workspace_id = get_workspace_registry_service().find_workspace_id_by_session_id(
            user_id,
            session_id,
        )
        effective_sandbox_mode = sandbox_mode or getattr(metadata, "sandbox_mode", None) or "local"
        effective_env_id = env_id or getattr(metadata, "env_id", None)
        summary = build_session_runtime_summary(
            session_dir=session_root,
            session_id=session_id,
            user_id=user_id,
            sandbox_mode=effective_sandbox_mode,
            env_id=effective_env_id,
            last_runtime_state=execution_summary.get("last_runtime_state"),
            runtime_busy=False,
            workspace_id=workspace_id,
        )
        summary["session_id"] = session_id
        if workspace_id:
            summary["workspace_id"] = workspace_id
        return summary
    except Exception as exc:
        logger.warning(
            "构建运行态提示摘要失败（忽略）: user=%s, session=%s, error=%s",
            user_id,
            session_id,
            exc,
        )
        return None


def _build_resource_context_for_prompt(
    *,
    user_id: str,
    workspace_path: Path,
    attached_files: list[str] | None,
    selected_references: list[str] | None = None,
) -> str:
    try:
        resource_context = build_task_resource_context(
            user_id=user_id,
            workspace_dir=workspace_path,
            attached_files=attached_files,
        )
        formatted = format_task_resource_context_for_prompt(resource_context)
        normalized_references = [
            str(item).strip() for item in (selected_references or []) if str(item).strip()
        ]
        if not normalized_references:
            return formatted
        reference_lines = [
            "本轮用户显式引用了这些对象，请优先核对其可用性：",
            *[f"- {item}" for item in normalized_references],
        ]
        if formatted:
            return f"{formatted}\n" + "\n".join(reference_lines)
        return "\n".join(reference_lines)
    except Exception as exc:
        logger.warning("构建任务资源提示摘要失败（忽略）: user=%s, error=%s", user_id, exc)
        return ""


def _wrap_transport_prompt(
    prompt: str,
    *,
    runtime_summary: dict[str, Any] | None,
    resource_context: str,
) -> str:
    """兼容新旧 `wrap_user_prompt` 签名。"""
    wrap_user_prompt = _resolve_wrap_user_prompt()
    try:
        return wrap_user_prompt(
            prompt,
            runtime_summary=runtime_summary,
            resource_context=resource_context,
        )
    except TypeError as exc:
        error_text = str(exc)
        if "unexpected keyword argument" not in error_text:
            raise
        return wrap_user_prompt(prompt)


def _resolve_model_capabilities(config: Any) -> set[str]:
    default_model = getattr(config, "default_model", None)
    models = getattr(config, "models", None)
    if not default_model or not isinstance(models, dict):
        return set()

    model_config = models.get(default_model)
    capabilities = _extract_model_config_value(model_config, "capabilities")
    if isinstance(capabilities, str):
        return {capabilities}
    if isinstance(capabilities, (list, set, tuple)):
        return {str(item) for item in capabilities if str(item).strip()}
    return set()


# ---------------------------------------------------------------------------
# @文件引用解析
# ---------------------------------------------------------------------------

_MENTION_PATH_RE = re.compile(r"@(/(?:workspace|global)/[^\s]+)")


def _extract_mentioned_file_paths(prompt: str) -> list[str]:
    """从用户 prompt 中提取 @/workspace/... 或 @/global/... 文件引用。

    返回规范化路径列表，去重并保持原文顺序，供后续加入 attachments。
    """
    if not prompt:
        return []
    seen: set[str] = set()
    results: list[str] = []
    for match in _MENTION_PATH_RE.finditer(prompt):
        path = match.group(1)
        if path not in seen:
            seen.add(path)
            results.append(path)
    return results


def _merge_mentioned_attachments(
    prompt: str,
    attachments: list[str] | None,
) -> list[str]:
    """将 prompt 中的 @文件引用合并到 attachments，避免重复。"""
    mentioned = _extract_mentioned_file_paths(prompt)
    if not mentioned:
        return list(attachments) if attachments else []
    existing = set(attachments or [])
    merged = list(attachments) if attachments else []
    for path in mentioned:
        if path not in existing:
            existing.add(path)
            merged.append(path)
    return merged


def _build_transport_user_input(
    *,
    prompt: str,
    transport_prompt: str,
    attachments: list[str] | None,
    workspace_path: Path,
    model_capabilities: set[str],
) -> tuple[str | list[dict[str, Any]], Any, Any]:
    attachment_parts = build_attachment_content_parts(
        attachments=attachments,
        workspace_dir=workspace_path,
    )
    if attachment_parts.image_paths and "image_in" not in model_capabilities:
        raise RuntimeError("当前模型不支持图片输入，请切换到支持图片输入的模型后再发送图片。")

    if not attachment_parts.transport_parts:
        return transport_prompt, prompt, transport_prompt

    display_content = dump_message_content(
        [
            {"type": "text", "text": prompt},
            *attachment_parts.display_parts,
        ]
    )
    transport_content = dump_message_content(
        [
            {"type": "text", "text": transport_prompt},
            *attachment_parts.transport_parts,
        ]
    )
    return (
        [{"role": "user", "content": transport_content}],
        display_content,
        transport_content,
    )


def _project_task_result_lifecycle_event(
    event: dict[str, Any],
) -> dict[str, Any] | None:
    if event.get("type") != "tool_result":
        return None

    tool_call_id = event.get("tool_call_id")
    if not isinstance(tool_call_id, str):
        return None

    tool_name = event.get("tool_name")
    if not is_subagent_dispatch_tool_name(str(tool_name) if isinstance(tool_name, str) else None):
        return None

    projection = project_subagent_lifecycle_from_task_result(
        is_error=bool(event.get("is_error")),
        content=str(event.get("content") or ""),
    )
    if projection is None:
        return None

    return build_worker_lifecycle_event(
        scope="subagent",
        status=projection.status,
        reason=projection.reason,
        task_tool_call_id=tool_call_id,
        parent_tool_call_id=(
            str(event.get("parent_tool_call_id"))
            if event.get("parent_tool_call_id")
            else tool_call_id
        ),
        agent_id=(str(event.get("agent_id")) if event.get("agent_id") else None),
        subagent_type=(str(event.get("subagent_type")) if event.get("subagent_type") else None),
        subagent_name=(str(event.get("subagent_name")) if event.get("subagent_name") else None),
    )


def _is_terminal_host_lifecycle_event(event: dict[str, Any]) -> bool:
    if event.get("type") != "worker.lifecycle.changed":
        return False
    if event.get("scope") != "host":
        return False
    return event.get("status") in {"finished", "cancelled", "interrupted", "failed"}


def _build_research_listener_context(
    agent_service: "AgentService",
    *,
    workspace_registry: Any,
    user_id: str,
    session_id: str,
    automation_continuation_id: str | None = None,
    automation_continuation_target_kind: str | None = None,
) -> ResearchListenerContext | None:
    metadata = agent_service._session_manager.get_session(session_id, user_id)
    context = get_research_listener_service().build_context(
        session_metadata=metadata,
        workspace_registry=workspace_registry,
        user_id=user_id,
        session_id=session_id,
    )
    if context is None:
        return None
    if automation_continuation_id or automation_continuation_target_kind:
        return replace(
            context,
            automation_continuation_id=(
                automation_continuation_id or context.automation_continuation_id
            ),
            automation_continuation_target_kind=(
                automation_continuation_target_kind or context.automation_continuation_target_kind
            ),
        )
    return context


class ExecutionMixin:
    """执行操作功能"""

    async def execute(
        self: "AgentService",
        prompt: str,
        user_id: str,
        session_id: str,
        model: str | None = None,
        model_id: str | None = None,
        sandbox_mode: str | None = None,
        attachments: list[str] | None = None,
        references: list[str] | None = None,
        automation_continuation_id: str | None = None,
        automation_continuation_target_kind: str | None = None,
        suppress_claw_outbound_sync: bool = False,
    ) -> str:
        """
        同步执行 Agent 任务

        Args:
            prompt: 用户提示词
            user_id: 用户 ID
            session_id: 会话 ID
            model: 模型名称（如 kimi-for-coding）
            model_id: 模型配置 ID（如 my-kimi-model，优先使用）
            sandbox_mode: 沙盒模式，当前主线仅支持 local，用于首次创建会话
            suppress_claw_outbound_sync: 仅供 Claw runtime 入站路径使用，避免 execute 收尾重复触发自动出站

        Returns:
            执行结果文本
        """
        config = self._get_config(
            model,
            user_id,
            model_id,
            session_id,
        )
        session_key = get_session_key(user_id, session_id)

        workspace_registry = get_workspace_registry_service()
        session_root = workspace_registry.get_session_dir(user_id, session_id)
        logical_workspace_root = workspace_registry.get_logical_workspace_root(
            user_id,
            session_id,
        )
        resolved_env_id = self._resolve_env_id_for_session(user_id, session_id)
        resolved_sandbox_mode = self._resolve_sandbox_mode_for_session(
            user_id,
            session_id,
            sandbox_mode,
        )
        resolved_code_timeout = self._resolve_code_timeout_for_session(user_id, session_id)
        resolved_env_vars = resolve_merged_env_vars_for_session(user_id, logical_workspace_root)
        frozen_runtime_plan = resolve_runtime_execution_plan(
            workspace=logical_workspace_root,
            env_id=resolved_env_id,
        )
        frozen_runtime_plan = replace(
            frozen_runtime_plan,
            env_vars=resolved_env_vars,
            frozen=True,
        )
        tokens = self._set_session_context(
            user_id=user_id,
            session_id=session_id,
            workspace_path=logical_workspace_root,
            session_root=session_root,
            env_id=resolved_env_id,
            code_timeout=resolved_code_timeout,
            runtime_env_vars=resolved_env_vars,
            runtime_execution_plan=frozen_runtime_plan,
        )
        execution_failed = False
        prompt_preview = re.sub(r"\s+", " ", prompt).strip()[:200]
        runtime_summary = _build_runtime_summary_for_prompt(
            self,
            user_id=user_id,
            session_id=session_id,
            session_root=session_root,
            sandbox_mode=resolved_sandbox_mode,
            env_id=resolved_env_id,
        )
        merged_attachments = _merge_mentioned_attachments(prompt, attachments)
        resource_context = _build_resource_context_for_prompt(
            user_id=user_id,
            workspace_path=logical_workspace_root,
            attached_files=merged_attachments,
            selected_references=references,
        )
        transport_prompt = _wrap_transport_prompt(
            prompt,
            runtime_summary=runtime_summary,
            resource_context=resource_context,
        )
        transport_user_input, display_content, transport_content = _build_transport_user_input(
            prompt=prompt,
            transport_prompt=transport_prompt,
            attachments=merged_attachments,
            workspace_path=logical_workspace_root,
            model_capabilities=_resolve_model_capabilities(config),
        )
        try:
            # 获取会话锁，确保同一会话串行执行
            session_lock = await self._get_session_lock(session_key)

            async with session_lock:
                host_terminal_event_emitted = False
                _skip_cleanup = False
                _stream_start_time = time.time()
                listener_context: ResearchListenerContext | None = None
                try:
                    existing_metadata = self._session_manager.get_session(session_id, user_id)
                    logger.info(
                        "Agent execute start: user=%s session=%s first_turn=%s code_timeout=%s prompt=%r",
                        user_id,
                        session_id,
                        existing_metadata is None or existing_metadata.message_count == 0,
                        resolved_code_timeout,
                        prompt_preview,
                    )
                    logger.info(
                        "Agent execute wrapped prompt: user=%s session=%s prompt=%r",
                        user_id,
                        session_id,
                        re.sub(r"\s+", " ", transport_prompt).strip()[:260],
                    )
                    session = await self._get_or_create_session(
                        user_id, session_id, config, sandbox_mode=resolved_sandbox_mode
                    )
                    self._active_sessions[session_key] = session
                    # 新一轮执行开始，清除 completed 标记
                    self._session_manager.mark_session_active(session_id, user_id)
                    skip_user_turn_persist = _is_rewritten_last_user_message(
                        self,
                        session_id=session_id,
                        user_id=user_id,
                        prompt=prompt,
                    )
                    normalized_message_id: str | None = None
                    if not skip_user_turn_persist:
                        _persist_user_turn_artifacts(
                            self,
                            user_id=user_id,
                            session_id=session_id,
                            session_root=session_root,
                            prompt=prompt,
                            display_content=display_content,
                            transport_content=transport_content,
                        )
                        normalized_message_id = getattr(
                            self._session_manager,
                            "_build_history_message_id",
                        )(
                            session_id,
                            existing_metadata.message_count if existing_metadata else 0,
                            {
                                "role": "user",
                                "content": transport_content,
                            },
                        )
                    else:
                        history = self._session_manager.get_history(session_id, user_id)
                        last_history_message = history[-1] if history else {}
                        if isinstance(last_history_message, dict):
                            normalized_message_id = last_history_message.get("id")
                    transport_user_input = _stamp_transport_user_input_id(
                        transport_user_input,
                        normalized_message_id,
                        force_list=skip_user_turn_persist,
                    )
                    listener_context = _build_research_listener_context(
                        self,
                        workspace_registry=workspace_registry,
                        user_id=user_id,
                        session_id=session_id,
                        automation_continuation_id=automation_continuation_id,
                        automation_continuation_target_kind=automation_continuation_target_kind,
                    )
                    if listener_context is not None:
                        get_research_listener_service().append_session_started(
                            context=listener_context,
                            prompt_preview=prompt_preview,
                            origin="execute",
                        )

                    async with session:
                        logger.info(f"开始执行: user={user_id}, session={session_id}")

                        outputs: list[str] = []
                        reasoning_outputs: list[str] = []
                        event_state = self._new_event_projection_state()
                        event_state["turn_n"] = getattr(session, "session_turn_count", 0)
                        event_state["current_host_step"] = _read_last_host_step(
                            session_root,
                            session_id,
                        )
                        async for item in session.prompt(
                            transport_user_input, merge_wire_messages=False
                        ):
                            for event in self._project_output_item(item, event_state):
                                _persist_host_execution_event(
                                    session_root=session_root,
                                    session_id=session_id,
                                    event=event,
                                )
                                if (
                                    event.get("type") == "content"
                                    and event.get("content_type") == "text"
                                ):
                                    outputs.append(event.get("text", ""))
                                elif (
                                    event.get("type") == "content"
                                    and event.get("content_type") == "think"
                                ):
                                    reasoning_outputs.append(event.get("think", ""))
                                if (
                                    event.get("type") == "worker.lifecycle.changed"
                                    and _is_terminal_host_lifecycle_event(event)
                                ):
                                    host_terminal_event_emitted = True
                                if (
                                    listener_context is not None
                                    and event.get("type") == "worker.lifecycle.changed"
                                ):
                                    get_research_listener_service().append_worker_lifecycle_event(
                                        context=listener_context,
                                        lifecycle_event=event,
                                        origin="execute",
                                    )

                                if event.get("type") == "tool_result":
                                    lifecycle_event = _project_task_result_lifecycle_event(event)
                                    if lifecycle_event is not None:
                                        _persist_host_execution_event(
                                            session_root=session_root,
                                            session_id=session_id,
                                            event=lifecycle_event,
                                        )
                                    if listener_context is not None and lifecycle_event is not None:
                                        get_research_listener_service().append_worker_lifecycle_event(
                                            context=listener_context,
                                            lifecycle_event=lifecycle_event,
                                            origin="execute",
                                        )

                        for event in self._flush_projected_output(event_state):
                            _persist_host_execution_event(
                                session_root=session_root,
                                session_id=session_id,
                                event=event,
                            )
                            if (
                                event.get("type") == "content"
                                and event.get("content_type") == "text"
                            ):
                                outputs.append(event.get("text", ""))
                            elif (
                                event.get("type") == "content"
                                and event.get("content_type") == "think"
                            ):
                                reasoning_outputs.append(event.get("think", ""))
                            if event.get("type") == "tool_result":
                                lifecycle_event = _project_task_result_lifecycle_event(event)
                                if lifecycle_event is not None:
                                    _persist_host_execution_event(
                                        session_root=session_root,
                                        session_id=session_id,
                                        event=lifecycle_event,
                                    )
                                if listener_context is not None and lifecycle_event is not None:
                                    get_research_listener_service().append_worker_lifecycle_event(
                                        context=listener_context,
                                        lifecycle_event=lifecycle_event,
                                        origin="execute",
                                    )

                        if not host_terminal_event_emitted:
                            _persist_host_execution_event(
                                session_root=session_root,
                                session_id=session_id,
                                event=_build_host_turn_end_event(),
                            )

                        result = "".join(outputs)
                        try:
                            _persist_message_to_session_db(
                                user_id=user_id,
                                session_id=session_id,
                                role="assistant",
                                content=result,
                            )
                            # 用 runtime session 的完整消息列表覆写 history.json，
                            # 确保中间轮次的 tool_calls 和 tool 消息不丢失。
                            _sync_session_messages_to_history(
                                self,
                                user_id=user_id,
                                session_id=session_id,
                                session=session,
                            )
                            if not suppress_claw_outbound_sync:
                                _schedule_claw_outbound_sync(
                                    user_id=user_id,
                                    session_id=session_id,
                                )
                        except Exception as e:
                            logger.warning(
                                "写入 memory 会话库失败（继续执行）: user=%s, session=%s, role=assistant, error=%s",
                                user_id,
                                session_id,
                                e,
                            )
                        if listener_context is not None and not host_terminal_event_emitted:
                            get_research_listener_service().append_host_completed_fallback(
                                context=listener_context,
                                reason="run_exhausted",
                                origin="execute",
                            )
                        logger.info(f"执行完成: user={user_id}, session={session_id}")
                        return result
                except Exception as exc:
                    execution_failed = True
                    listener_service = get_research_listener_service()
                    user_facing_error = _build_user_facing_runtime_error(
                        exc,
                        config=config,
                    )
                    lifecycle_event: dict[str, Any] | None = None
                    if _is_run_cancelled_error(exc):
                        host_terminal_event_emitted = True
                        lifecycle_event = build_worker_lifecycle_event(
                            scope="host",
                            status="cancelled",
                            reason="run_cancelled",
                        )
                    elif not host_terminal_event_emitted:
                        host_terminal_event_emitted = True
                        lifecycle_event = build_worker_lifecycle_event(
                            scope="host",
                            status="failed",
                            reason="exception",
                        )

                    if lifecycle_event is not None:
                        _persist_host_execution_event(
                            session_root=session_root,
                            session_id=session_id,
                            event=lifecycle_event,
                        )
                        if listener_context is not None:
                            listener_service.append_worker_lifecycle_event(
                                context=listener_context,
                                lifecycle_event=lifecycle_event,
                                origin="execute",
                            )
                    if _is_context_length_exceeded_error(exc):
                        raise RuntimeError(user_facing_error) from exc
                    raise
        finally:
            # 更新 message_count，使会话不再被当作草稿过滤
            try:
                metadata = self._session_manager.get_session(session_id, user_id)
                if metadata and metadata.message_count == 0:
                    self._session_manager._update_message_count(session_id, user_id, 1)
            except Exception as e:
                logger.warning(f"更新消息计数失败（忽略）: {e}")

            if not execution_failed:
                try:
                    self._session_manager.mark_session_completed(session_id, user_id)
                except Exception as e:
                    logger.warning(f"标记会话完成失败（忽略）: {e}")

            # Phase 2: 调用 post-execution 回调（状态驱动托管）
            for cb in getattr(self, "_post_execution_callbacks", []):
                try:
                    await cb(user_id, session_id, execution_failed)
                except Exception as e:
                    logger.warning(f"Post-execution callback 失败（忽略）: {e}")

            # 清理 monitor 资源
            try:
                from app.services.agent.runtime_backends.aiasys.tools.monitor_tool import (
                    get_monitor_service,
                )

                await get_monitor_service().cleanup_session(session_key)
            except Exception:
                logger.warning("清理 monitor 资源失败（忽略）", exc_info=True)

            await self._cleanup_session_resources(
                user_id=user_id,
                session_id=session_id,
                session_key=session_key,
                remove_runtime_instance=execution_failed,
            )
            self._reset_session_context(tokens)

    async def stop_background_session(self: "AgentService", session_key: str) -> bool:
        """停止指定 session 的后台执行任务。"""
        task = self._background_tasks.get(session_key)
        if task is None:
            return False

        session = self._active_sessions.get(session_key)
        if session is not None and hasattr(session, "cancel"):
            try:
                session.cancel()
            except Exception:
                logger.warning("取消后台 session 失败", exc_info=True)

        try:
            await asyncio.wait_for(task, timeout=10.0)
        except asyncio.TimeoutError:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        except asyncio.CancelledError:
            pass

        self._background_tasks.pop(session_key, None)
        self._background_queues.pop(session_key, None)
        return True

    async def execute_stream(
        self: "AgentService",
        prompt: str,
        user_id: str,
        session_id: str,
        model: str | None = None,
        model_id: str | None = None,
        sandbox_mode: str | None = None,
        attachments: list[str] | None = None,
        references: list[str] | None = None,
        automation_continuation_id: str | None = None,
        automation_continuation_target_kind: str | None = None,
        suppress_claw_outbound_sync: bool = False,
        thinking_enabled: bool | None = None,
        thinking_effort: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """
        流式执行 Agent 任务

        使用 SSE 格式实时返回执行进度
        底层由 AIASys runtime backend 驱动的 session 持久化历史记录

        Args:
            prompt: 用户提示词
            user_id: 用户 ID
            session_id: 会话 ID
            model: 模型名称（如 kimi-for-coding）
            model_id: 模型配置 ID（如 my-kimi-model，优先使用）
            sandbox_mode: 沙盒模式，当前主线仅支持 local，用于首次创建会话
        """
        config = self._get_config(model, user_id, model_id, session_id)
        session_key = get_session_key(user_id, session_id)

        workspace_registry = get_workspace_registry_service()
        session_root = workspace_registry.get_session_dir(user_id, session_id)
        logical_workspace_root = workspace_registry.get_logical_workspace_root(
            user_id,
            session_id,
        )
        resolved_env_id = self._resolve_env_id_for_session(user_id, session_id)
        resolved_sandbox_mode = self._resolve_sandbox_mode_for_session(
            user_id,
            session_id,
            sandbox_mode,
        )
        resolved_code_timeout = self._resolve_code_timeout_for_session(user_id, session_id)
        resolved_env_vars = resolve_merged_env_vars_for_session(user_id, logical_workspace_root)
        frozen_runtime_plan = resolve_runtime_execution_plan(
            workspace=logical_workspace_root,
            env_id=resolved_env_id,
        )
        frozen_runtime_plan = replace(
            frozen_runtime_plan,
            env_vars=resolved_env_vars,
            frozen=True,
        )
        tokens = self._set_session_context(
            user_id=user_id,
            session_id=session_id,
            workspace_path=logical_workspace_root,
            session_root=session_root,
            env_id=resolved_env_id,
            code_timeout=resolved_code_timeout,
            runtime_env_vars=resolved_env_vars,
            runtime_execution_plan=frozen_runtime_plan,
        )
        stream_failed = False
        monitor_queue: asyncio.Queue | None = None
        session = None
        _skip_cleanup = False
        _stream_start_time = time.time()
        prompt_preview = re.sub(r"\s+", " ", prompt).strip()[:200]
        runtime_summary = _build_runtime_summary_for_prompt(
            self,
            user_id=user_id,
            session_id=session_id,
            session_root=session_root,
            sandbox_mode=resolved_sandbox_mode,
            env_id=resolved_env_id,
        )
        merged_attachments = _merge_mentioned_attachments(prompt, attachments)
        resource_context = _build_resource_context_for_prompt(
            user_id=user_id,
            workspace_path=logical_workspace_root,
            attached_files=merged_attachments,
            selected_references=references,
        )
        transport_prompt = _wrap_transport_prompt(
            prompt,
            runtime_summary=runtime_summary,
            resource_context=resource_context,
        )
        transport_user_input, display_content, transport_content = _build_transport_user_input(
            prompt=prompt,
            transport_prompt=transport_prompt,
            attachments=merged_attachments,
            workspace_path=logical_workspace_root,
            model_capabilities=_resolve_model_capabilities(config),
        )
        try:
            session_lock = await self._get_session_lock(session_key)

            async with session_lock:
                host_terminal_event_emitted = False
                listener_context: ResearchListenerContext | None = None
                try:
                    existing_metadata = self._session_manager.get_session(session_id, user_id)
                    logger.info(
                        "Agent execute_stream start: user=%s session=%s first_turn=%s code_timeout=%s prompt=%r",
                        user_id,
                        session_id,
                        existing_metadata is None or existing_metadata.message_count == 0,
                        resolved_code_timeout,
                        prompt_preview,
                    )
                    logger.info(
                        "Agent execute_stream wrapped prompt: user=%s session=%s prompt=%r",
                        user_id,
                        session_id,
                        re.sub(r"\s+", " ", transport_prompt).strip()[:260],
                    )
                    session = await self._get_or_create_session(
                        user_id, session_id, config, sandbox_mode=resolved_sandbox_mode
                    )
                    self._active_sessions[session_key] = session
                    # 新一轮执行开始，清除 completed 标记
                    self._session_manager.mark_session_active(session_id, user_id)
                    skip_user_turn_persist = _is_rewritten_last_user_message(
                        self,
                        session_id=session_id,
                        user_id=user_id,
                        prompt=prompt,
                    )
                    normalized_message_id: str | None = None
                    if not skip_user_turn_persist:
                        _persist_user_turn_artifacts(
                            self,
                            user_id=user_id,
                            session_id=session_id,
                            session_root=session_root,
                            prompt=prompt,
                            display_content=display_content,
                            transport_content=transport_content,
                        )
                        normalized_message_id = getattr(
                            self._session_manager,
                            "_build_history_message_id",
                        )(
                            session_id,
                            existing_metadata.message_count if existing_metadata else 0,
                            {
                                "role": "user",
                                "content": transport_content,
                            },
                        )
                    else:
                        history = self._session_manager.get_history(session_id, user_id)
                        last_history_message = history[-1] if history else {}
                        if isinstance(last_history_message, dict):
                            normalized_message_id = last_history_message.get("id")
                    transport_user_input = _stamp_transport_user_input_id(
                        transport_user_input,
                        normalized_message_id,
                        force_list=skip_user_turn_persist,
                    )
                    listener_context = _build_research_listener_context(
                        self,
                        workspace_registry=workspace_registry,
                        user_id=user_id,
                        session_id=session_id,
                        automation_continuation_id=automation_continuation_id,
                        automation_continuation_target_kind=automation_continuation_target_kind,
                    )
                    if listener_context is not None:
                        get_research_listener_service().append_session_started(
                            context=listener_context,
                            prompt_preview=prompt_preview,
                            origin="execute_stream",
                        )

                    async with session:
                        logger.info(f"开始流式执行: user={user_id}, session={session_id}")

                        # 注册 monitor SSE queue
                        try:
                            from app.services.agent.runtime_backends.aiasys.tools.monitor_tool import (
                                get_monitor_service,
                            )

                            monitor_queue = asyncio.Queue(maxsize=256)
                            get_monitor_service().register_queue(session_key, monitor_queue)
                        except Exception:
                            logger.warning("注册 monitor queue 失败（忽略）", exc_info=True)

                        event_state = self._new_event_projection_state()
                        event_state["turn_n"] = getattr(session, "session_turn_count", 0)
                        event_state["current_host_step"] = _read_last_host_step(
                            session_root,
                            session_id,
                        )
                        is_background_mode = False

                        if is_background_mode:
                            # 已有后台任务在运行，连接到现有 Queue
                            if session_key in self._background_tasks:
                                existing_queue = self._background_queues.get(session_key)
                                if existing_queue is not None:
                                    try:
                                        while True:
                                            _event = await existing_queue.get()
                                            if _event.get("type") == "_background_done":
                                                break
                                            yield _event
                                    except asyncio.CancelledError:
                                        raise
                                _skip_cleanup = True
                                return

                            # 启动新的后台任务
                            _bg_queue = asyncio.Queue(maxsize=256)
                            self._background_queues[session_key] = _bg_queue

                            async def _background_loop():
                                _bg_stream_failed = False
                                _bg_host_terminal = False
                                _bg_outputs: list[str] = []
                                _bg_reasoning: list[str] = []
                                _bg_start_time = time.time()
                                try:
                                    async for _bg_item in session.prompt(
                                        transport_user_input, merge_wire_messages=False
                                    ):
                                        for _bg_event in self._project_output_item(
                                            _bg_item, event_state
                                        ):
                                            _persist_host_execution_event(
                                                session_root=session_root,
                                                session_id=session_id,
                                                event=_bg_event,
                                            )
                                            if (
                                                _bg_event.get("type") == "content"
                                                and _bg_event.get("content_type") == "text"
                                            ):
                                                _bg_outputs.append(_bg_event.get("text", ""))
                                            elif (
                                                _bg_event.get("type") == "content"
                                                and _bg_event.get("content_type") == "think"
                                            ):
                                                _bg_reasoning.append(_bg_event.get("think", ""))
                                            await _bg_queue.put(_bg_event)
                                            if monitor_queue is not None:
                                                while True:
                                                    try:
                                                        await _bg_queue.put(
                                                            monitor_queue.get_nowait()
                                                        )
                                                    except asyncio.QueueEmpty:
                                                        break
                                            if (
                                                _bg_event.get("type") == "worker.lifecycle.changed"
                                                and _is_terminal_host_lifecycle_event(_bg_event)
                                            ):
                                                _bg_host_terminal = True
                                            if (
                                                listener_context is not None
                                                and _bg_event.get("type")
                                                == "worker.lifecycle.changed"
                                            ):
                                                get_research_listener_service().append_worker_lifecycle_event(
                                                    context=listener_context,
                                                    lifecycle_event=_bg_event,
                                                    origin="execute_stream",
                                                )
                                            if _bg_event["type"] == "tool_result":
                                                _bg_lc = _project_task_result_lifecycle_event(
                                                    _bg_event
                                                )
                                                if _bg_lc:
                                                    _persist_host_execution_event(
                                                        session_root=session_root,
                                                        session_id=session_id,
                                                        event=_bg_lc,
                                                    )
                                                    await _bg_queue.put(_bg_lc)
                                                    if monitor_queue is not None:
                                                        while True:
                                                            try:
                                                                await _bg_queue.put(
                                                                    monitor_queue.get_nowait()
                                                                )
                                                            except asyncio.QueueEmpty:
                                                                break
                                                    if listener_context is not None:
                                                        get_research_listener_service().append_worker_lifecycle_event(
                                                            context=listener_context,
                                                            lifecycle_event=_bg_lc,
                                                            origin="execute_stream",
                                                        )
                                    for _bg_event in self._flush_projected_output(event_state):
                                        _persist_host_execution_event(
                                            session_root=session_root,
                                            session_id=session_id,
                                            event=_bg_event,
                                        )
                                        if (
                                            _bg_event.get("type") == "content"
                                            and _bg_event.get("content_type") == "text"
                                        ):
                                            _bg_outputs.append(_bg_event.get("text", ""))
                                        elif (
                                            _bg_event.get("type") == "content"
                                            and _bg_event.get("content_type") == "think"
                                        ):
                                            _bg_reasoning.append(_bg_event.get("think", ""))
                                        await _bg_queue.put(_bg_event)
                                        if monitor_queue is not None:
                                            while True:
                                                try:
                                                    await _bg_queue.put(monitor_queue.get_nowait())
                                                except asyncio.QueueEmpty:
                                                    break
                                        if _bg_event.get("type") == "tool_result":
                                            _bg_lc = _project_task_result_lifecycle_event(_bg_event)
                                            if _bg_lc:
                                                _persist_host_execution_event(
                                                    session_root=session_root,
                                                    session_id=session_id,
                                                    event=_bg_lc,
                                                )
                                                await _bg_queue.put(_bg_lc)
                                                if monitor_queue is not None:
                                                    while True:
                                                        try:
                                                            await _bg_queue.put(
                                                                monitor_queue.get_nowait()
                                                            )
                                                        except asyncio.QueueEmpty:
                                                            break
                                                if listener_context is not None:
                                                    get_research_listener_service().append_worker_lifecycle_event(
                                                        context=listener_context,
                                                        lifecycle_event=_bg_lc,
                                                        origin="execute_stream",
                                                    )
                                    if not _bg_host_terminal:
                                        _persist_host_execution_event(
                                            session_root=session_root,
                                            session_id=session_id,
                                            event=_build_host_turn_end_event(),
                                        )
                                    try:
                                        _persist_message_to_session_db(
                                            user_id=user_id,
                                            session_id=session_id,
                                            role="assistant",
                                            content="".join(_bg_outputs),
                                        )
                                        _sync_session_messages_to_history(
                                            self,
                                            user_id=user_id,
                                            session_id=session_id,
                                            session=session,
                                        )
                                        if not suppress_claw_outbound_sync:
                                            _schedule_claw_outbound_sync(
                                                user_id=user_id,
                                                session_id=session_id,
                                            )
                                    except Exception as _e:
                                        logger.warning(
                                            "写入 memory 会话库失败（继续执行）: user=%s, session=%s, role=assistant, error=%s",
                                            user_id,
                                            session_id,
                                            _e,
                                        )
                                    if listener_context is not None and not _bg_host_terminal:
                                        get_research_listener_service().append_host_completed_fallback(
                                            context=listener_context,
                                            reason="stream_exhausted",
                                            origin="execute_stream",
                                        )
                                    logger.info(
                                        f"后台执行完成: user={user_id}, session={session_id}"
                                    )
                                except Exception as _e:
                                    _listener_service = get_research_listener_service()
                                    _user_error = _build_user_facing_runtime_error(
                                        _e, config=config
                                    )
                                    if _is_run_cancelled_error(_e):
                                        _bg_stream_failed = True
                                        _bg_lc = build_worker_lifecycle_event(
                                            scope="host", status="cancelled", reason="run_cancelled"
                                        )
                                        _persist_host_execution_event(
                                            session_root=session_root,
                                            session_id=session_id,
                                            event=_bg_lc,
                                        )
                                        await _bg_queue.put(_bg_lc)
                                        _bg_host_terminal = True
                                        if listener_context is not None:
                                            _listener_service.append_worker_lifecycle_event(
                                                context=listener_context,
                                                lifecycle_event=_bg_lc,
                                                origin="execute_stream",
                                            )
                                        logger.info(
                                            f"后台执行被取消: user={user_id}, session={session_id}"
                                        )
                                    else:
                                        _bg_stream_failed = True
                                        _bg_lc = build_worker_lifecycle_event(
                                            scope="host", status="failed", reason="exception"
                                        )
                                        _persist_host_execution_event(
                                            session_root=session_root,
                                            session_id=session_id,
                                            event=_bg_lc,
                                        )
                                        await _bg_queue.put(_bg_lc)
                                        _bg_host_terminal = True
                                        if listener_context is not None:
                                            _listener_service.append_worker_lifecycle_event(
                                                context=listener_context,
                                                lifecycle_event=_bg_lc,
                                                origin="execute_stream",
                                            )
                                        logger.error(
                                            f"后台执行失败: user={user_id}, session={session_id}, error={_e}"
                                        )
                                        import traceback

                                        logger.error(traceback.format_exc())
                                        await _bg_queue.put(
                                            {"type": "error", "message": _user_error}
                                        )
                                finally:
                                    _bg_elapsed = int(time.time() - _bg_start_time)
                                    if _bg_elapsed > 0 and session.budget is not None:
                                        session.budget.time_used_seconds += _bg_elapsed
                                    await _bg_queue.put({"type": "_background_done"})
                                    # 资源清理
                                    try:
                                        _metadata = self._session_manager.get_session(
                                            session_id, user_id
                                        )
                                        if _metadata and _metadata.message_count == 0:
                                            self._session_manager._update_message_count(
                                                session_id, user_id, 1
                                            )
                                    except Exception as _e:
                                        logger.warning(f"更新消息计数失败（忽略）: {_e}")
                                    if not _bg_stream_failed:
                                        try:
                                            self._session_manager.mark_session_completed(
                                                session_id, user_id
                                            )
                                        except Exception as _e:
                                            logger.warning(f"标记会话完成失败（忽略）: {_e}")
                                    for _cb in getattr(self, "_post_execution_callbacks", []):
                                        try:
                                            await _cb(user_id, session_id, _bg_stream_failed)
                                        except Exception as _e:
                                            logger.warning(
                                                f"Post-execution callback 失败（忽略）: {_e}"
                                            )
                                    try:
                                        from app.services.agent.runtime_backends.aiasys.tools.monitor_tool import (
                                            get_monitor_service,
                                        )

                                        if monitor_queue is not None:
                                            get_monitor_service().unregister_queue(session_key)
                                        await get_monitor_service().cleanup_session(session_key)
                                    except Exception:
                                        logger.warning(
                                            "清理 monitor 资源失败（忽略）", exc_info=True
                                        )
                                    await self._cleanup_session_resources(
                                        user_id=user_id,
                                        session_id=session_id,
                                        session_key=session_key,
                                        remove_runtime_instance=_bg_stream_failed,
                                    )
                                    self._background_tasks.pop(session_key, None)
                                    self._background_queues.pop(session_key, None)

                            _bg_task = asyncio.create_task(_background_loop())
                            _bg_task.add_done_callback(_log_task_exception)
                            self._background_tasks[session_key] = _bg_task

                            try:
                                while True:
                                    _event = await _bg_queue.get()
                                    if _event.get("type") == "_background_done":
                                        break
                                    yield _event
                            except asyncio.CancelledError:
                                # 前端断开连接，让后台任务继续运行
                                _skip_cleanup = True
                                raise

                            _skip_cleanup = True
                            return

                        stream_outputs: list[str] = []
                        stream_reasoning_outputs: list[str] = []
                        async for item in session.prompt(
                            transport_user_input, merge_wire_messages=False
                        ):
                            for event in self._project_output_item(item, event_state):
                                _persist_host_execution_event(
                                    session_root=session_root,
                                    session_id=session_id,
                                    event=event,
                                )
                                if (
                                    event.get("type") == "content"
                                    and event.get("content_type") == "text"
                                ):
                                    stream_outputs.append(event.get("text", ""))
                                elif (
                                    event.get("type") == "content"
                                    and event.get("content_type") == "think"
                                ):
                                    stream_reasoning_outputs.append(event.get("think", ""))
                                yield event
                                if monitor_queue is not None:
                                    while True:
                                        try:
                                            yield monitor_queue.get_nowait()
                                        except asyncio.QueueEmpty:
                                            break
                                if (
                                    event.get("type") == "worker.lifecycle.changed"
                                    and _is_terminal_host_lifecycle_event(event)
                                ):
                                    host_terminal_event_emitted = True
                                if (
                                    listener_context is not None
                                    and event.get("type") == "worker.lifecycle.changed"
                                ):
                                    get_research_listener_service().append_worker_lifecycle_event(
                                        context=listener_context,
                                        lifecycle_event=event,
                                        origin="execute_stream",
                                    )

                                if event["type"] == "tool_result":
                                    lifecycle_event = _project_task_result_lifecycle_event(event)
                                    if lifecycle_event:
                                        _persist_host_execution_event(
                                            session_root=session_root,
                                            session_id=session_id,
                                            event=lifecycle_event,
                                        )
                                        yield lifecycle_event
                                        if monitor_queue is not None:
                                            while True:
                                                try:
                                                    yield monitor_queue.get_nowait()
                                                except asyncio.QueueEmpty:
                                                    break
                                        if listener_context is not None:
                                            get_research_listener_service().append_worker_lifecycle_event(
                                                context=listener_context,
                                                lifecycle_event=lifecycle_event,
                                                origin="execute_stream",
                                            )
                        for event in self._flush_projected_output(event_state):
                            _persist_host_execution_event(
                                session_root=session_root,
                                session_id=session_id,
                                event=event,
                            )
                            if (
                                event.get("type") == "content"
                                and event.get("content_type") == "text"
                            ):
                                stream_outputs.append(event.get("text", ""))
                            elif (
                                event.get("type") == "content"
                                and event.get("content_type") == "think"
                            ):
                                stream_reasoning_outputs.append(event.get("think", ""))
                            yield event
                            if monitor_queue is not None:
                                while True:
                                    try:
                                        yield monitor_queue.get_nowait()
                                    except asyncio.QueueEmpty:
                                        break
                            if event.get("type") == "tool_result":
                                lifecycle_event = _project_task_result_lifecycle_event(event)
                                if lifecycle_event:
                                    _persist_host_execution_event(
                                        session_root=session_root,
                                        session_id=session_id,
                                        event=lifecycle_event,
                                    )
                                    yield lifecycle_event
                                    if monitor_queue is not None:
                                        while True:
                                            try:
                                                yield monitor_queue.get_nowait()
                                            except asyncio.QueueEmpty:
                                                break
                                    if listener_context is not None:
                                        get_research_listener_service().append_worker_lifecycle_event(
                                            context=listener_context,
                                            lifecycle_event=lifecycle_event,
                                            origin="execute_stream",
                                        )
                        if not host_terminal_event_emitted:
                            _persist_host_execution_event(
                                session_root=session_root,
                                session_id=session_id,
                                event=_build_host_turn_end_event(),
                            )
                        try:
                            _persist_message_to_session_db(
                                user_id=user_id,
                                session_id=session_id,
                                role="assistant",
                                content="".join(stream_outputs),
                            )
                            _sync_session_messages_to_history(
                                self,
                                user_id=user_id,
                                session_id=session_id,
                                session=session,
                            )
                            if not suppress_claw_outbound_sync:
                                _schedule_claw_outbound_sync(
                                    user_id=user_id,
                                    session_id=session_id,
                                )
                        except Exception as e:
                            logger.warning(
                                "写入 memory 会话库失败（继续执行）: user=%s, session=%s, role=assistant, error=%s",
                                user_id,
                                session_id,
                                e,
                            )
                        if listener_context is not None and not host_terminal_event_emitted:
                            get_research_listener_service().append_host_completed_fallback(
                                context=listener_context,
                                reason="stream_exhausted",
                                origin="execute_stream",
                            )
                        logger.info(f"流式执行完成: user={user_id}, session={session_id}")
                except Exception as e:
                    listener_service = get_research_listener_service()
                    user_facing_error = _build_user_facing_runtime_error(
                        e,
                        config=config,
                    )
                    if _is_run_cancelled_error(e):
                        stream_failed = True
                        lifecycle_event = build_worker_lifecycle_event(
                            scope="host", status="cancelled", reason="run_cancelled"
                        )
                        _persist_host_execution_event(
                            session_root=session_root,
                            session_id=session_id,
                            event=lifecycle_event,
                        )
                        yield lifecycle_event
                        host_terminal_event_emitted = True
                        if listener_context is not None:
                            listener_service.append_worker_lifecycle_event(
                                context=listener_context,
                                lifecycle_event=lifecycle_event,
                                origin="execute_stream",
                            )
                        logger.info(f"流式执行被取消: user={user_id}, session={session_id}")
                    else:
                        stream_failed = True
                        lifecycle_event = build_worker_lifecycle_event(
                            scope="host", status="failed", reason="exception"
                        )
                        _persist_host_execution_event(
                            session_root=session_root,
                            session_id=session_id,
                            event=lifecycle_event,
                        )
                        yield lifecycle_event
                        host_terminal_event_emitted = True
                        if listener_context is not None:
                            listener_service.append_worker_lifecycle_event(
                                context=listener_context,
                                lifecycle_event=lifecycle_event,
                                origin="execute_stream",
                            )
                        logger.error(f"执行失败: user={user_id}, session={session_id}, error={e}")
                        import traceback

                        logger.error(traceback.format_exc())
                        yield {"type": "error", "message": user_facing_error}

                finally:
                    if not _skip_cleanup:
                        yield {"type": "status", "message": "清理资源..."}
                        # 同步模式：累加 wall-clock 时间到 session budget
                        _sync_elapsed = int(time.time() - _stream_start_time)
                        if _sync_elapsed > 0 and session is not None and session.budget is not None:
                            session.budget.time_used_seconds += _sync_elapsed
                            try:
                                session._save_budget()
                            except Exception:
                                logger.warning("保存同步模式时间统计失败", exc_info=True)
        finally:
            if _skip_cleanup:
                return
            # 更新 message_count，使会话不再被当作草稿过滤
            try:
                metadata = self._session_manager.get_session(session_id, user_id)
                if metadata and metadata.message_count == 0:
                    self._session_manager._update_message_count(session_id, user_id, 1)
            except Exception as e:
                logger.warning(f"更新消息计数失败（忽略）: {e}")

            if not stream_failed:
                try:
                    self._session_manager.mark_session_completed(session_id, user_id)
                except Exception as e:
                    logger.warning(f"标记会话完成失败（忽略）: {e}")

            # Phase 2: 调用 post-execution 回调（状态驱动托管）
            for cb in getattr(self, "_post_execution_callbacks", []):
                try:
                    await cb(user_id, session_id, stream_failed)
                except Exception as e:
                    logger.warning(f"Post-execution callback 失败（忽略）: {e}")

            # 清理 monitor 资源
            try:
                from app.services.agent.runtime_backends.aiasys.tools.monitor_tool import (
                    get_monitor_service,
                )

                if monitor_queue is not None:
                    get_monitor_service().unregister_queue(session_key)
                await get_monitor_service().cleanup_session(session_key)
            except Exception:
                logger.warning("清理 monitor 资源失败（忽略）", exc_info=True)

            await self._cleanup_session_resources(
                user_id=user_id,
                session_id=session_id,
                session_key=session_key,
                remove_runtime_instance=stream_failed,
            )
            self._reset_session_context(tokens)
