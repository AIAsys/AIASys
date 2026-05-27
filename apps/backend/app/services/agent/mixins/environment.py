"""
环境解析 Mixin

负责解析会话环境 ID、代码超时、运行时环境变量等配置
"""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from app.services.workspace_registry import get_workspace_registry_service

if TYPE_CHECKING:
    from app.services.agent import AgentService

logger = logging.getLogger(__name__)


def resolve_workspace_env_vars(user_id: str, workspace_root: Path) -> dict[str, str] | None:
    """从 workspace registry 读取 runtime_binding.env_vars。"""
    try:
        workspace_registry = get_workspace_registry_service()
        workspace_id = workspace_root.name
        workspace = workspace_registry.get_workspace(
            user_id,
            workspace_id,
            include_conversations=False,
        )
        env_vars = workspace.runtime_binding.env_vars or {}
        return {str(key): str(value) for key, value in env_vars.items()}
    except Exception:
        return None


def resolve_merged_env_vars_for_session(
    user_id: str,
    workspace_root: Path,
) -> dict[str, str] | None:
    """合并全局 + 工作区环境变量，工作区优先。"""
    workspace_vars = resolve_workspace_env_vars(user_id, workspace_root)
    from app.services.global_env_vars import get_global_env_vars

    global_vars = get_global_env_vars(user_id)
    if not global_vars and not workspace_vars:
        return None
    merged = dict(global_vars)
    if workspace_vars:
        merged.update(workspace_vars)
    return merged


class EnvironmentMixin:
    """环境解析功能"""

    def _resolve_env_id_for_session(
        self: "AgentService",
        user_id: str,
        session_id: str,
        preferred_env_id: Optional[str] = None,
    ) -> str | None:
        """
        解析会话环境 ID。

        优先级：
        1. preferred_env_id（请求显式指定）
        2. session metadata.env_id
        3. workspace runtime_binding.env_id
        4. None，表示当前任务不带 Python 环境
        """
        if preferred_env_id:
            return preferred_env_id

        metadata = self._session_manager.get_session(session_id, user_id)
        if metadata and metadata.env_id:
            return metadata.env_id

        try:
            workspace_registry = get_workspace_registry_service()
            workspace_id = workspace_registry.find_workspace_id_by_session_id(
                user_id,
                session_id,
            )
            if workspace_id:
                workspace = workspace_registry.get_workspace(
                    user_id,
                    workspace_id,
                    include_conversations=False,
                )
                if workspace.runtime_binding.env_id:
                    return workspace.runtime_binding.env_id
        except Exception as exc:
            logger.debug("读取工作区 runtime_binding 失败: %s", exc)

        return None

    def _resolve_sandbox_mode_for_session(
        self: "AgentService",
        user_id: str,
        session_id: str,
        preferred_sandbox_mode: Optional[str] = None,
    ) -> str | None:
        """解析当前会话应使用的 sandbox_mode，会话覆盖优先于工作区默认。"""
        if preferred_sandbox_mode:
            return preferred_sandbox_mode

        metadata = self._session_manager.get_session(session_id, user_id)
        if metadata and metadata.sandbox_mode:
            return metadata.sandbox_mode

        try:
            workspace_registry = get_workspace_registry_service()
            workspace_id = workspace_registry.find_workspace_id_by_session_id(
                user_id,
                session_id,
            )
            if workspace_id:
                workspace = workspace_registry.get_workspace(
                    user_id,
                    workspace_id,
                    include_conversations=False,
                )
                if workspace.runtime_binding.sandbox_mode:
                    return workspace.runtime_binding.sandbox_mode
        except Exception as exc:
            logger.debug("读取工作区 sandbox_mode 失败: %s", exc)

        return None

    def resolve_session_env(
        self: "AgentService",
        user_id: str,
        session_id: str,
        preferred_env_id: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        解析会话环境，返回 (env_id, env_name)
        """
        env_id = self._resolve_env_id_for_session(user_id, session_id, preferred_env_id)
        return env_id or "", "未绑定 Python"

    def _resolve_code_timeout_for_session(
        self: "AgentService", user_id: str, session_id: str
    ) -> int | None:
        """解析当前会话代码执行超时（秒）。"""
        metadata = self._session_manager.get_session(session_id, user_id)
        return metadata.code_timeout if metadata else None
