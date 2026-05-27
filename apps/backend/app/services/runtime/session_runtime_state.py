from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


LOCAL_RUNTIME_KIND = "local_ipython"


def _normalize_runtime_binding(
    *,
    sandbox_mode: Optional[str],
    env_id: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    normalized_mode = (sandbox_mode or "").strip().lower()
    normalized_env_id = str(env_id or "").strip() or None
    if normalized_mode in {"", "local"}:
        return ("local" if normalized_env_id else None), normalized_env_id
    return sandbox_mode, env_id


def _resolve_workspace_runtime_env(
    *,
    user_id: str,
    env_id: Optional[str],
    workspace_id: Optional[str] = None,
) -> tuple[str | None, dict[str, Any] | None]:
    if not env_id:
        return None, None
    try:
        from app.services.runtime_environment import get_runtime_environment_service
        from app.services.workspace_registry import get_workspace_registry_service

        registry = get_workspace_registry_service()
        if workspace_id:
            env = get_runtime_environment_service().inspect_env(
                user_id,
                workspace_id,
                env_id,
            )
            return workspace_id, env.model_dump(mode="json")

        for workspace in registry.list_workspaces(
            user_id,
            include_conversations=False,
        ):
            try:
                env = get_runtime_environment_service().inspect_env(
                    user_id,
                    workspace.workspace_id,
                    env_id,
                )
            except FileNotFoundError:
                continue
            return workspace.workspace_id, env.model_dump(mode="json")
    except Exception as exc:
        logger.debug("解析工作区运行环境摘要失败: %s", exc)
    return None, None


def _resolve_workspace_container_resource(
    *,
    user_id: str,
    container_id: Optional[str],
    workspace_id: Optional[str] = None,
) -> tuple[str | None, dict[str, Any] | None]:
    if not container_id:
        return None, None
    try:
        from app.services.container_resource import get_container_resource_service
        from app.services.workspace_registry import get_workspace_registry_service

        service = get_container_resource_service()
        registry = get_workspace_registry_service()
        if workspace_id:
            container = service.inspect_container(
                user_id,
                workspace_id,
                container_id,
            )
            return workspace_id, container.model_dump(mode="json")

        for workspace in registry.list_workspaces(
            user_id,
            include_conversations=False,
        ):
            try:
                container = service.inspect_container(
                    user_id,
                    workspace.workspace_id,
                    container_id,
                )
            except FileNotFoundError:
                continue
            return workspace.workspace_id, container.model_dump(mode="json")
    except Exception as exc:
        logger.debug("解析工作区 Docker 沙盒摘要失败: %s", exc)
    return None, None


def _resolve_local_kernel_active(session_id: str, user_id: str) -> bool:
    try:
        from app.agents.tools.local_ipython_box import LocalIPythonBox

        return LocalIPythonBox.has_kernel(session_id=session_id, user_id=user_id)
    except Exception as exc:
        logger.warning("解析本地 kernel 状态失败: %s", exc)
        return False


def _map_local_runtime_status(
    *,
    kernel_active: bool,
    last_runtime_state: Optional[str],
    runtime_busy: bool,
) -> tuple[str, str]:
    if runtime_busy:
        return "busy", "执行中"

    if kernel_active:
        return "ready", "已就绪"

    normalized_state = (last_runtime_state or "").strip().lower()
    if normalized_state in {"", "fresh", "not_initialized"}:
        return "not_started", "尚未使用"
    if normalized_state in {"discarded", "missing"}:
        return "released", "已释放"
    if normalized_state == "refresh_required":
        return "refresh_required", "待更新"
    if normalized_state == "failed":
        return "failed", "上次失败"
    if normalized_state == "available":
        return "released", "已释放"

    return normalized_state or "unknown", "状态未知"


def build_session_runtime_summary(
    *,
    session_dir: Path,
    session_id: str,
    user_id: str,
    sandbox_mode: Optional[str],
    env_id: Optional[str],
    last_runtime_state: Optional[str],
    runtime_busy: bool = False,
    workspace_id: Optional[str] = None,
) -> dict[str, Any]:
    """构建统一的会话运行态摘要，供前端与 Agent 共用。"""
    effective_sandbox_mode, effective_env_id = _normalize_runtime_binding(
        sandbox_mode=sandbox_mode,
        env_id=env_id,
    )
    workspace_id, workspace_env = _resolve_workspace_runtime_env(
        user_id=user_id,
        env_id=effective_env_id,
        workspace_id=workspace_id,
    )

    if effective_sandbox_mode == "docker":
        container_workspace_id, container = _resolve_workspace_container_resource(
            user_id=user_id,
            container_id=effective_env_id,
            workspace_id=workspace_id,
        )
        if container:
            status = str(container.get("status") or "created")
            status_label = {
                "running": "运行中",
                "stopped": "已停止",
                "created": "已登记",
                "missing": "未找到",
                "error": "异常",
            }.get(status, "状态未知")
            return {
                "runtime_kind": "docker",
                "display_name": container.get("name") or effective_env_id,
                "scope": "workspace",
                "start_policy": "use_registered_container_on_shell_call",
                "reuse_policy": "reuse_registered_container",
                "control_mode": "workspace_runtime_binding",
                "kernel_active": False,
                "status": status,
                "status_label": status_label,
                "runtime_busy": runtime_busy,
                "env_id": effective_env_id,
                "sandbox_mode": "docker",
                "workspace_id": container_workspace_id,
                "container_resource": container,
            }
        return {
            "runtime_kind": "docker",
            "display_name": effective_env_id or "Docker 沙盒",
            "scope": "workspace",
            "start_policy": "use_registered_container_on_shell_call",
            "reuse_policy": "reuse_registered_container",
            "control_mode": "workspace_runtime_binding",
            "kernel_active": False,
            "status": "missing",
            "status_label": "未找到",
            "runtime_busy": runtime_busy,
            "env_id": effective_env_id,
            "sandbox_mode": "docker",
            "workspace_id": workspace_id,
        }

    if workspace_env:
        env_kind = workspace_env.get("kind")
        status = str(workspace_env.get("status") or "registered")
        status_label = {
            "registered": "已登记",
            "ready": "可用",
            "running": "运行中",
            "stopped": "已停止",
            "missing": "未找到",
            "unavailable": "不可用",
            "error": "异常",
        }.get(status, "状态未知")
        return {
            "runtime_kind": env_kind,
            "display_name": workspace_env.get("display_name") or effective_env_id,
            "scope": "workspace",
            "start_policy": (
                "use_uv_project_on_tool_call"
                if env_kind == "uv"
                else "use_registered_python_on_tool_call"
            ),
            "reuse_policy": "reuse_within_session",
            "control_mode": "workspace_runtime_binding",
            "kernel_active": _resolve_local_kernel_active(session_id, user_id),
            "status": status,
            "status_label": status_label,
            "runtime_busy": runtime_busy,
            "env_id": effective_env_id,
            "sandbox_mode": "local",
            "workspace_id": workspace_id,
            "runtime_environment": workspace_env,
        }

    if not effective_env_id:
        return {
            "runtime_kind": "plain_shell",
            "display_name": "未绑定 Python",
            "scope": "workspace",
            "start_policy": "direct_shell_in_workspace",
            "reuse_policy": None,
            "control_mode": "workspace_runtime_binding",
            "kernel_active": False,
            "status": "not_configured",
            "status_label": "未绑定 Python",
            "runtime_busy": runtime_busy,
            "env_id": None,
            "sandbox_mode": effective_sandbox_mode,
            "workspace_id": workspace_id,
        }

    return {
        "runtime_kind": effective_sandbox_mode or "unknown",
        "display_name": effective_env_id or "默认执行环境",
        "scope": "session",
        "start_policy": None,
        "reuse_policy": None,
        "control_mode": "session_managed",
        "kernel_active": False,
        "status": (last_runtime_state or "unknown"),
        "status_label": "状态未知",
        "runtime_busy": runtime_busy,
        "env_id": effective_env_id,
        "sandbox_mode": effective_sandbox_mode,
    }


def format_runtime_summary_for_prompt(
    runtime_summary: dict[str, Any] | None,
) -> str:
    """把运行态摘要转成给 Agent 使用的上下文提示。"""
    if not runtime_summary:
        return ""

    status_label = str(runtime_summary.get("status_label") or "状态未知")
    kernel_active = bool(runtime_summary.get("kernel_active"))
    runtime_busy = bool(runtime_summary.get("runtime_busy"))
    lines = [
        f"- 当前执行环境: {runtime_summary.get('display_name') or '未知执行环境'}",
        f"- 当前状态: {status_label}",
    ]
    workspace_id = str(runtime_summary.get("workspace_id") or "").strip()
    session_id = str(runtime_summary.get("session_id") or "").strip()
    if workspace_id:
        lines.append(f"- 当前工作区 ID: {workspace_id}")
    if session_id:
        lines.append(f"- 当前会话 session_id: {session_id}")

    if runtime_summary.get("runtime_kind") == LOCAL_RUNTIME_KIND:
        lines.append(
            "- notebook 执行环境不会随 Agent 打开自动创建；首次调用 notebook / 代码工具时才会准备。"
        )
        if kernel_active:
            lines.append("- 当前会话已经持有可复用的 notebook 内核，可继续复用已有变量和内存状态。")
        else:
            lines.append(
                "- 当前会话还没有活跃内核；如果需要执行代码，可以直接调用 notebook 工具，系统会按需准备内核。"
            )
        lines.append("- 若用户重置执行环境、停止会话或系统主动释放，已有内核会被销毁。")
    elif runtime_summary.get("runtime_kind") == "uv":
        lines.append(
            "- Shell 和代码工具会使用工作区 UV 环境，不会安装依赖到 AIASys 后端自己的 Python 环境。"
        )
    elif runtime_summary.get("runtime_kind") == "registered_python":
        lines.append("- Shell 和代码工具会使用当前工作区绑定的已登记 Python 解释器。")
        lines.append(
            "- 安装依赖前需要确认会修改该解释器对应环境；如需隔离依赖，改用工作区 UV 环境。"
        )
    elif runtime_summary.get("runtime_kind") == "plain_shell":
        lines.append("- 当前任务未绑定 Python/UV 环境。")
        lines.append("- Shell 命令会在工作区目录直接执行，不会自动进入 UV 环境或创建虚拟环境。")
        lines.append("- 需要 Python、notebook 或依赖管理时，先请求用户确认并启用 Python 环境。")
    elif runtime_summary.get("runtime_kind") == "docker":
        lines.append("- Shell 和 Monitor 会使用当前工作区绑定的 Docker 沙盒执行脚本。")
        lines.append(
            "- Notebook / IPython 持久内核当前只支持工作区 UV Python 环境；需要交互式 notebook 时请切回 Python 环境。"
        )
    if runtime_busy:
        lines.append("- 当前会话正在执行，避免并发触发相互冲突的代码运行。")

    return "\n".join(lines)


def resolve_effective_runtime_state(
    *,
    session_dir: Path,
    session_id: str,
    user_id: str,
    sandbox_mode: Optional[str],
    env_id: Optional[str],
    last_runtime_state: Optional[str],
) -> Optional[str]:
    """基于当前真实运行态解析对前端更准确的 runtime state。"""
    if last_runtime_state != "available":
        return last_runtime_state

    effective_sandbox_mode, effective_env_id = _normalize_runtime_binding(
        sandbox_mode=sandbox_mode,
        env_id=env_id,
    )
    if not effective_env_id:
        return "missing"

    if effective_sandbox_mode == "local":
        return "available" if _resolve_local_kernel_active(session_id, user_id) else "missing"

    return last_runtime_state
