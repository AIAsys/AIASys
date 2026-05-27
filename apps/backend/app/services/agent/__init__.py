"""
Agent 服务模块。

改为 lazy export，避免仅为了导入子模块而触发整条 agent service 初始化链。
"""

from __future__ import annotations

import logging
from importlib import import_module

logger = logging.getLogger(__name__)

RunCancelled = None

__all__ = [
    "AgentService",
    "agent_service",
    "WORKSPACE_DIR",
    "cleanup_temp_agent_configs",
    "generate_dynamic_agent_config",
    "_verify_agent_config",
    "get_work_dir",
    "get_session_key",
    "format_prompt_for_log",
    "is_system_reminder_message",
    "serialize_tool_output",
    "_select_preferred_agent_model_id",
    "_get_execution_env_info",
    "append_display_history_entry",
    "wrap_user_prompt",
    "get_ask_user_tool",
    "compare_files",
    "scan_directory",
    "RunCancelled",
    "ContextMixin",
    "SessionMixin",
    "EnvironmentMixin",
    "ExecutionMixin",
    "EventMixin",
    "ControlMixin",
    "HistoryMixin",
]

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "WORKSPACE_DIR": ("app.core.config", "WORKSPACE_DIR"),
    "cleanup_temp_agent_configs": (
        "app.services.agent.config",
        "cleanup_temp_agent_configs",
    ),
    "generate_dynamic_agent_config": (
        "app.services.agent.config",
        "generate_dynamic_agent_config",
    ),
    "_verify_agent_config": ("app.services.agent.config", "_verify_agent_config"),
    "get_work_dir": ("app.services.agent.utils", "get_work_dir"),
    "get_session_key": ("app.services.agent.utils", "get_session_key"),
    "format_prompt_for_log": ("app.services.agent.utils", "format_prompt_for_log"),
    "is_system_reminder_message": (
        "app.services.agent.utils",
        "is_system_reminder_message",
    ),
    "serialize_tool_output": ("app.services.agent.utils", "serialize_tool_output"),
    "_select_preferred_agent_model_id": (
        "app.services.agent.utils",
        "_select_preferred_agent_model_id",
    ),
    "_get_execution_env_info": (
        "app.services.agent.utils",
        "_get_execution_env_info",
    ),
    "append_display_history_entry": (
        "app.services.history",
        "append_display_history_entry",
    ),
    "wrap_user_prompt": ("app.services.history", "wrap_user_prompt"),
    "get_ask_user_tool": ("app.agents.tools.ask_user.tool", "get_ask_user_tool"),
    "compare_files": ("app.utils.file_utils", "compare_files"),
    "scan_directory": ("app.utils.file_utils", "scan_directory"),
    "ContextMixin": ("app.services.agent.mixins", "ContextMixin"),
    "SessionMixin": ("app.services.agent.mixins", "SessionMixin"),
    "EnvironmentMixin": ("app.services.agent.mixins", "EnvironmentMixin"),
    "ExecutionMixin": ("app.services.agent.mixins", "ExecutionMixin"),
    "EventMixin": ("app.services.agent.mixins", "EventMixin"),
    "ControlMixin": ("app.services.agent.mixins", "ControlMixin"),
    "HistoryMixin": ("app.services.agent.mixins", "HistoryMixin"),
}


def _load_agent_service_exports() -> None:
    if "AgentService" in globals() and "agent_service" in globals():
        return

    import asyncio

    from app.core.config import WORKSPACE_DIR
    from app.services.agent.mixins import (
        ContextMixin,
        ControlMixin,
        EnvironmentMixin,
        EventMixin,
        ExecutionMixin,
        HistoryMixin,
        SessionMixin,
    )
    from app.services.agent.runtime_backends import AgentRuntimeSession
    from app.services.session import SessionManager

    class AgentService(
        ContextMixin,
        SessionMixin,
        EnvironmentMixin,
        ExecutionMixin,
        EventMixin,
        ControlMixin,
        HistoryMixin,
    ):
        """Agent 服务主类，组合所有 Mixin 并绑定默认 runtime backend。"""

        def __init__(self):
            self._active_sessions: dict[str, AgentRuntimeSession] = {}
            self._session_locks: dict = {}
            self._locks_lock = asyncio.Lock()
            self._session_manager = SessionManager(WORKSPACE_DIR)
            self._runtime_backend = None
            self._post_execution_callbacks: list = []
            self._background_tasks: dict[str, asyncio.Task] = {}
            self._background_queues: dict[str, asyncio.Queue] = {}
            self._register_builtin_post_execution_callbacks()

        def register_post_execution_callback(self, callback):
            """注册一个在 session 执行完成后调用的回调。\n\n            回调签名: async callback(user_id: str, session_id: str, failed: bool) -> None\n"""
            if callback not in self._post_execution_callbacks:
                self._post_execution_callbacks.append(callback)

        def unregister_post_execution_callback(self, callback):
            """注销 post-execution 回调。"""
            try:
                self._post_execution_callbacks.remove(callback)
            except ValueError:
                pass

        def _register_builtin_post_execution_callbacks(self):
            self.register_post_execution_callback(self._memory_stage1_callback)

        async def _memory_stage1_callback(
            self, user_id: str, session_id: str, failed: bool
        ) -> None:
            """成功执行后调度 Memory Stage 1，失败不影响普通对话主链路。"""

            if failed:
                return

            # 检查 memory 开关
            try:
                from app.core.aiasys_config import load_aiasys_config

                config = load_aiasys_config(user_id=user_id)
                if not config.memory.enabled:
                    return
            except Exception:
                logger.warning("Agent 配置加载失败，跳过 memory stage 1", exc_info=True)
                return

            try:
                from app.services.memory import schedule_stage1_for_session
                from app.services.workspace_registry import get_workspace_registry_service

                registry = get_workspace_registry_service()
                workspace_id = registry.find_workspace_id_by_session_id(user_id, session_id)
                session_dir = registry.get_session_dir(user_id, session_id)

                # 没有执行记录（纯文本对话）时跳过 Stage 1，避免无意义调度
                records_path = session_dir / ".aiasys" / "session" / "execution" / "records.jsonl"
                if not records_path.exists() or records_path.stat().st_size == 0:
                    return

                schedule_stage1_for_session(
                    user_id=user_id,
                    session_id=session_id,
                    workspace_id=workspace_id,
                    session_dir=session_dir,
                )
            except Exception:
                import logging

                logging.getLogger(__name__).warning(
                    "Memory Stage 1 调度失败，已跳过: user=%s session=%s",
                    user_id,
                    session_id,
                    exc_info=True,
                )

    globals()["AgentService"] = AgentService
    globals()["agent_service"] = AgentService()


def __getattr__(name: str):
    if name in {"AgentService", "agent_service"}:
        _load_agent_service_exports()
        return globals()[name]

    if name == "RunCancelled":
        return RunCancelled

    module_target = _LAZY_EXPORTS.get(name)
    if module_target is None:
        raise AttributeError(name)

    module_name, attr_name = module_target
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
