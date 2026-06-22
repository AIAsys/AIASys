"""
Agent 配置管理模块

负责动态 agent 配置生成、验证和清理。
"""

import logging
import platform
import shutil
import tomllib
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import tomli_w
from jinja2 import Environment as JinjaEnvironment
from jinja2 import StrictUndefined


def _strip_none_values(obj: Any) -> Any:
    """递归移除字典中的 None 值，避免 TOML 序列化失败。"""
    if isinstance(obj, dict):
        return {k: _strip_none_values(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_strip_none_values(v) for v in obj]
    return obj


from app.core.config import SANDBOX_DEFAULT_MODE, WORKSPACE_DIR, is_sandbox_mode_enabled
from app.core.workspace_path import WorkspacePath
from app.models.runtime_environment import WorkspaceRuntimeEnv
from app.services.agent.system_presets import (
    DATA_ANALYSIS_BASELINE,
    ResolvedSystemPreset,
    get_local_system_preset_virtual_path,
    resolve_system_agent_preset_from_path,
)
from app.services.agent.utils import get_work_dir
from app.services.runtime_tooling import (
    canonicalize_runtime_tool_name,
    probe_runtime_tool,
)
from app.services.session.core import SessionManager
from app.utils.path_utils import as_system_path

logger = logging.getLogger(__name__)

RUNTIME_AGENT_CONFIG_DIR_NAME = "runtime-agent-config"
DEFAULT_ANALYSIS_PROFILE_BASENAME = "data_analysis"


def _normalize_enabled_expert_role_ids(enabled_expert_role_ids: Any) -> list[str] | None:
    if enabled_expert_role_ids is None:
        return None
    if not isinstance(enabled_expert_role_ids, list):
        return []
    normalized: list[str] = []
    for item in enabled_expert_role_ids:
        text = str(item or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _normalize_expert_role_tool_ids(
    expert_role_tool_ids: Any,
) -> dict[str, list[str]] | None:
    if expert_role_tool_ids is None:
        return None
    if not isinstance(expert_role_tool_ids, dict):
        return None

    normalized: dict[str, list[str]] = {}
    for raw_role_id, raw_tool_ids in expert_role_tool_ids.items():
        role_id = str(raw_role_id or "").strip()
        if not role_id or not isinstance(raw_tool_ids, list):
            continue

        tool_ids: list[str] = []
        seen_tool_ids: set[str] = set()
        for raw_tool_id in raw_tool_ids:
            tool_id = canonicalize_runtime_tool_name(str(raw_tool_id or "").strip())
            if not tool_id or tool_id in seen_tool_ids:
                continue
            tool_ids.append(tool_id)
            seen_tool_ids.add(tool_id)

        if tool_ids or isinstance(raw_tool_ids, list):
            normalized[role_id] = tool_ids

    return normalized or None


def _is_subagent_enabled_for_runtime(
    role_id: str,
    *,
    user_id: str,
    workspace_id: str | None,
    enabled_subagent_ids: list[str] | None,
) -> bool:
    role_id = str(role_id or "").strip()
    if not role_id:
        return False
    try:
        from app.services.agent.subagent_catalog import (
            is_subagent_dispatch_enabled,
        )

        return is_subagent_dispatch_enabled(
            user_id=user_id,
            role_id=role_id,
            workspace_id=workspace_id,
            explicit_enabled_role_ids=enabled_subagent_ids,
        )
    except Exception:
        logger.warning(
            "读取子 Agent 可见性策略失败，按未启用处理: user=%s workspace=%s role=%s",
            user_id,
            workspace_id,
            role_id,
            exc_info=True,
        )
        return False


def _normalize_supported_sandbox_mode(sandbox_mode: str | None) -> str:
    normalized_mode = str(sandbox_mode or "").strip().lower()
    if not normalized_mode:
        return SANDBOX_DEFAULT_MODE or "local"
    if is_sandbox_mode_enabled(normalized_mode):
        return normalized_mode
    logger.warning(
        "收到未启用的 sandbox_mode=%s，自动回退到 %s",
        normalized_mode,
        SANDBOX_DEFAULT_MODE or "local",
    )
    return SANDBOX_DEFAULT_MODE or "local"


def resolve_agent_system_default_paths(
    *,
    sandbox_mode: str | None,
    execution_policy: Any = None,
) -> tuple[Path, Path]:
    effective_sandbox_mode = _normalize_supported_sandbox_mode(sandbox_mode)
    profile_basename = DEFAULT_ANALYSIS_PROFILE_BASENAME
    prompt_path = DATA_ANALYSIS_BASELINE.prompt_template_path
    if effective_sandbox_mode != "local":
        logger.warning(
            "当前主线不再使用 sandbox 专属 Agent YAML，sandbox_mode=%s 使用本地主线 preset",
            effective_sandbox_mode,
        )
    return get_local_system_preset_virtual_path(profile_basename), prompt_path


def _is_supported_tool(tool_name: str) -> bool:
    """检查工具在当前 backend 运行时中是否存在。"""
    return probe_runtime_tool(tool_name).available


def _sanitize_tool_list(tool_names: list[str]) -> list[str]:
    """清理已过时或不可加载的工具，避免动态配置生成出坏列表。"""
    sanitized: list[str] = []
    seen: set[str] = set()
    for tool_name in tool_names:
        canonical_tool_name = canonicalize_runtime_tool_name(tool_name)
        availability = probe_runtime_tool(canonical_tool_name)
        if availability.available:
            if canonical_tool_name not in seen:
                sanitized.append(canonical_tool_name)
                seen.add(canonical_tool_name)
        else:
            logger.warning(
                "动态配置中忽略不可用工具: %s (%s)",
                tool_name,
                availability.reason,
            )
    return sanitized


def _patched_sessions_dir(self) -> Path:
    """
    自定义 sessions_dir 方法，让 session 存储在 workspace 下的 .aiasys/session 目录
    """
    return WorkspacePath(self.work_dir) / ".aiasys" / "session"


def _select_preferred_agent_model_id(
    config_ids: list[str],
    provider_configs: dict[str, Any],
    fallback_order: list[str] = None,
) -> Optional[str]:
    """
    根据优先级选择最佳模型配置

    优先级：
    1. kimi-deepresearch
    2. kimi-research（包含 kimi-research-think）
    3. kimi-longcontext（或 kimi-128k）
    4. kimi（包含 kimi-think）
    5. 系统默认

    Args:
        config_ids: 可用的配置 ID 列表
        provider_configs: 提供商配置字典
        fallback_order: 自定义回退顺序

    Returns:
        选中的配置 ID，如果没有匹配则返回 None
    """
    if not config_ids:
        return None

    if fallback_order is None:
        # 默认优先级顺序
        fallback_order = [
            "kimi-deepresearch",
            "kimi-research",
            "kimi-research-think",
            "kimi-longcontext",
            "kimi-128k",
            "kimi",
            "kimi-think",
            "kimi-k2",
        ]

    # 首先尝试精确匹配
    for preferred in fallback_order:
        if preferred in config_ids:
            # 如果是 "kimi-research"，还需要检查是否有同名配置
            if preferred in provider_configs:
                return preferred
            # 否则继续查找
            for cid in config_ids:
                if cid == preferred:
                    return cid

    # 然后尝试前缀匹配（如 kimi-research 匹配 kimi-research-think）
    for preferred in fallback_order:
        matching = [cid for cid in config_ids if cid.startswith(preferred)]
        if matching:
            # 选择最短的那个（即基础版本）
            return min(matching, key=len)

    # 最后尝试包含匹配
    for preferred in fallback_order:
        matching = [cid for cid in config_ids if preferred in cid]
        if matching:
            return matching[0]

    return None


def _format_package_list(env: WorkspaceRuntimeEnv | None) -> tuple[str, str]:
    packages = list(env.packages) if env is not None else []
    if not packages:
        return "未登记依赖清单", "当前 Python 环境没有可用的依赖清单。"

    package_names = [package.name for package in packages]
    package_list = (
        ", ".join(package_names)
        if len(package_names) <= 10
        else ", ".join(package_names[:10]) + f" 等共 {len(package_names)} 个包"
    )
    detail_lines = ["| 包名 | 版本 |", "|------|------|"]
    for package in packages[:20]:
        detail_lines.append(f"| {package.name} | {package.version or 'unknown'} |")
    if len(packages) > 20:
        detail_lines.append(f"| ... 等共 {len(packages)} 个包 | |")
    return package_list, "\n".join(detail_lines)


def _resolve_bound_python_env(
    session_id: str | None,
    user_id: str | None,
) -> tuple[WorkspaceRuntimeEnv | None, str | None, str | None]:
    if not session_id or not user_id:
        return None, None, None
    try:
        session_manager = SessionManager(WORKSPACE_DIR)
        metadata = session_manager.get_session(session_id, user_id)
        workspace_id = getattr(metadata, "workspace_id", None) if metadata else None
        if not workspace_id:
            from app.services.workspace_registry import get_workspace_registry_service

            workspace_id = get_workspace_registry_service().find_workspace_id_by_session_id(
                user_id,
                session_id,
            )
        if not workspace_id:
            return None, None, None

        from app.services.runtime_environment import get_runtime_environment_service
        from app.services.workspace_registry import get_workspace_registry_service

        workspace = get_workspace_registry_service().get_workspace(
            user_id,
            workspace_id,
            include_conversations=False,
        )
        binding = workspace.runtime_binding
        if binding.sandbox_mode == "docker" or not binding.env_id:
            return None, workspace_id, None
        env = get_runtime_environment_service().inspect_env(
            user_id,
            workspace_id,
            binding.env_id,
        )
        return env, workspace_id, binding.env_id
    except Exception as exc:
        logger.debug("解析提示词 Python 环境失败: %s", exc)
        return None, None, None


def _get_available_shells() -> List[str]:
    """检测当前系统可用的 shell 列表。"""
    shells = []
    # cmd.exe 已禁用，不再列入候选
    candidates = ["bash", "sh", "powershell", "pwsh", "zsh", "fish"]
    for shell in candidates:
        if shutil.which(shell):
            shells.append(shell)
    return shells


def _get_execution_env_info(
    session_id: str | None = None,
    user_id: str | None = None,
) -> Dict[str, str]:
    """按当前工作区真实绑定生成提示词环境变量。"""
    env, workspace_id, env_id = _resolve_bound_python_env(session_id, user_id)
    available_shells = _get_available_shells()
    platform_info = {
        "PLATFORM": platform.system(),
        "PLATFORM_VERSION": platform.release(),
        "AVAILABLE_SHELLS": ", ".join(available_shells) if available_shells else "未检测到",
    }
    if env is None:
        return {
            "PYTHON_ENV_SECTION": (
                "当前任务未绑定 Python/UV 环境。\n\n"
                "- Shell 命令会在工作区目录直接执行，不会自动进入 UV 环境或创建虚拟环境。\n"
                "- 不要假设 pandas、numpy、Playwright、Chromium 或其他 Python/浏览器依赖已经安装。\n"
                "- 需要 Python、notebook、依赖安装、浏览器预览或截图时，先请求用户确认并启用对应环境。"
            ),
            "PYTHON_VERSION": "未绑定",
            "BASE_IMAGE": "none",
            "PACKAGE_LIST": "未绑定 Python 环境",
            "PACKAGE_DETAILS": "当前任务未绑定 Python 环境。",
            **platform_info,
        }

    package_list, package_details = _format_package_list(env)
    env_lines = [
        f"当前任务已绑定 Python 环境: {env.display_name or env.env_id}",
        f"- 环境 ID: {env_id or env.env_id}",
        f"- 工作区 ID: {workspace_id or 'unknown'}",
        f"- 状态: {env.status}",
    ]
    if env.kind == "uv":
        env_lines.append("- 类型: UV 工作区环境")
    elif env.kind == "registered_python":
        env_lines.append("- 类型: 已登记 Python 解释器")
    if env.python_version:
        env_lines.append(f"- Python 版本: {env.python_version}")
    if env.python_executable:
        env_lines.append(f"- Python 路径: {env.python_executable}")
    if env.material_path:
        env_lines.append(f"- 环境目录: {env.material_path}")
    env_lines.append(f"- 依赖摘要: {package_list}")

    return {
        "PYTHON_ENV_SECTION": "\n".join(env_lines),
        "PYTHON_VERSION": env.python_version or "未探测",
        "BASE_IMAGE": env.kind,
        "PACKAGE_LIST": package_list,
        "PACKAGE_DETAILS": package_details,
        **platform_info,
    }


def _render_system_prompt_template(
    template_path: Path,
    env_info: Dict[str, str],
) -> str:
    """
    渲染系统提示词模板

    使用 Jinja2 渲染提示词模板，注入环境变量。
    模板使用 ${VAR} 语法。

    Args:
        template_path: 模板文件路径
        env_info: 环境信息字典

    Returns:
        渲染后的提示词内容
    """
    if not template_path.exists():
        logger.warning(f"提示词模板不存在: {template_path}")
        return ""

    try:
        template_content = template_path.read_text(encoding="utf-8")

        # 使用 ${VAR} 模板语法
        jinja_env = JinjaEnvironment(
            variable_start_string="${",
            variable_end_string="}",
            undefined=StrictUndefined,
        )
        template = jinja_env.from_string(template_content)

        return template.render(**env_info)
    except Exception as e:
        logger.error(f"渲染提示词模板失败: {template_path}, error={e}")
        # 返回原始内容，避免完全失败
        try:
            return template_path.read_text(encoding="utf-8")
        except Exception:
            return ""


def _build_manifest_from_system_baseline(
    baseline: Any,
    *,
    env_info: Dict[str, str],
    tool_subset: list[str] | None = None,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "name": baseline.agent_name,
        "tools": list(baseline.tools),
        "system_prompt": _render_system_prompt_template(
            baseline.prompt_template_path,
            env_info,
        ),
    }
    if baseline.model:
        manifest["model"] = baseline.model
    if baseline.when_to_use:
        manifest["when_to_use"] = baseline.when_to_use
    if baseline.tool_policy:
        manifest["tool_policy"] = baseline.tool_policy
    if baseline.allowed_tools:
        manifest["allowed_tools"] = list(baseline.allowed_tools)
    if baseline.exclude_tools:
        manifest["exclude_tools"] = list(baseline.exclude_tools)
    if baseline.expert_profile:
        manifest["expert_profile"] = deepcopy(baseline.expert_profile)
    if tool_subset is not None:
        _apply_tool_subset_to_manifest(manifest, tool_subset)
    return manifest


def _apply_tool_subset_to_manifest(
    agent_manifest: dict[str, Any],
    requested_tool_ids: list[str],
) -> None:
    system_limit_tool_ids = _sanitize_tool_list(
        list(agent_manifest.get("allowed_tools") or agent_manifest.get("tools") or [])
    )
    requested_tool_ids = _sanitize_tool_list(
        [
            canonicalize_runtime_tool_name(str(tool_id or "").strip())
            for tool_id in requested_tool_ids
            if str(tool_id or "").strip()
        ]
    )
    requested_tool_id_set = set(requested_tool_ids)
    if system_limit_tool_ids:
        effective_tool_ids = [
            tool_id for tool_id in system_limit_tool_ids if tool_id in requested_tool_id_set
        ]
    else:
        effective_tool_ids = list(requested_tool_ids)
    effective_tool_id_set = set(effective_tool_ids)

    original_tool_ids = _sanitize_tool_list(list(agent_manifest.get("tools") or []))
    if original_tool_ids:
        agent_manifest["tools"] = [
            tool_id for tool_id in original_tool_ids if tool_id in effective_tool_id_set
        ]
    else:
        agent_manifest["tools"] = list(effective_tool_ids)

    if "allowed_tools" in agent_manifest or agent_manifest.get("tool_policy") == "allowlist":
        agent_manifest["allowed_tools"] = list(effective_tool_ids)


def _build_embedded_subagent_manifests_from_preset(
    preset: ResolvedSystemPreset,
    *,
    env_info: Dict[str, str],
    enabled_subagent_ids: list[str] | None = None,
    role_tool_ids_by_subagent: dict[str, list[str]] | None = None,
    subagent_enabled_for_runtime: Any = None,
) -> dict[str, Any]:
    embedded_subagents: dict[str, Any] = {}
    for subagent_name, subagent_binding in preset.baseline.subagents.items():
        if enabled_subagent_ids is not None and subagent_name not in enabled_subagent_ids:
            continue
        if subagent_enabled_for_runtime is not None and not subagent_enabled_for_runtime(
            str(subagent_name)
        ):
            continue
        baseline = preset.subagent_baselines.get(subagent_binding.baseline_id)
        if baseline is None:
            logger.warning(
                "结构化 system preset 缺少子角色 baseline: host=%s role=%s baseline=%s",
                preset.baseline.baseline_id,
                subagent_name,
                subagent_binding.baseline_id,
            )
            continue
        embedded_subagents[subagent_name] = {
            "baseline_id": baseline.baseline_id,
            "description": subagent_binding.description,
            "agent_manifest": _build_manifest_from_system_baseline(
                baseline,
                env_info=env_info,
                tool_subset=(
                    role_tool_ids_by_subagent.get(subagent_name)
                    if role_tool_ids_by_subagent is not None
                    else None
                ),
            ),
        }
    return embedded_subagents


def _build_manifest_from_toml_config(
    source_config_path: Path,
    *,
    env_info: Dict[str, str],
    enabled_subagent_ids: list[str] | None = None,
    role_tool_ids_by_subagent: dict[str, list[str]] | None = None,
    subagent_enabled_for_runtime: Any = None,
) -> dict[str, Any]:
    with open(as_system_path(str(source_config_path)), "rb") as f:
        payload = tomllib.load(f) or {}
    agent_manifest = payload.get("agent")
    if not isinstance(agent_manifest, dict):
        raise ValueError(f"Agent 配置缺少 agent 段: {source_config_path}")

    manifest = deepcopy(agent_manifest)
    raw_prompt_path = manifest.pop("system_prompt_path", None)
    if isinstance(raw_prompt_path, str) and raw_prompt_path.strip():
        prompt_path = Path(raw_prompt_path)
        if not prompt_path.is_absolute():
            prompt_path = (source_config_path.parent / prompt_path).resolve()
        manifest["system_prompt"] = _render_system_prompt_template(prompt_path, env_info)

    subagents = manifest.get("subagents")
    if isinstance(subagents, dict):
        rewritten_subagents: dict[str, Any] = {}
        for subagent_name, subagent in subagents.items():
            if enabled_subagent_ids is not None and subagent_name not in enabled_subagent_ids:
                continue
            if subagent_enabled_for_runtime is not None and not subagent_enabled_for_runtime(
                str(subagent_name)
            ):
                continue
            if not isinstance(subagent, dict):
                continue
            raw_sub_path = subagent.get("path")
            if not isinstance(raw_sub_path, str) or not raw_sub_path.strip():
                continue
            subagent_path = Path(raw_sub_path)
            if not subagent_path.is_absolute():
                subagent_path = (source_config_path.parent / subagent_path).resolve()
            if not subagent_path.exists():
                continue
            embedded_manifest = _build_manifest_from_toml_config(
                subagent_path,
                env_info=env_info,
                enabled_subagent_ids=None,
                role_tool_ids_by_subagent=None,
                subagent_enabled_for_runtime=None,
            )
            if role_tool_ids_by_subagent is not None and subagent_name in role_tool_ids_by_subagent:
                _apply_tool_subset_to_manifest(
                    embedded_manifest,
                    role_tool_ids_by_subagent[subagent_name],
                )
            next_subagent = {key: value for key, value in subagent.items() if key != "path"}
            next_subagent["agent_manifest"] = embedded_manifest
            rewritten_subagents[subagent_name] = next_subagent
        manifest["subagents"] = rewritten_subagents

    return manifest


async def build_dynamic_agent_manifest(
    session_id: str,
    user_id: str,
    sandbox_mode: Optional[str] = None,
    agent_type: str = "data_analysis",
) -> dict[str, Any]:
    """
    生成结构化的动态 agent manifest。

    当前系统默认基线已经从 checked-in YAML 中剥离；本函数输出内存中的 manifest，
    供 runtime 或后续 materialize 逻辑消费。
    """
    del agent_type
    from app.services.agent_config import AgentMode, get_agent_config_service

    session_manager = SessionManager(WORKSPACE_DIR)
    session_metadata = session_manager.get_session(session_id, user_id)
    if sandbox_mode is None and session_metadata is not None:
        sandbox_mode = getattr(session_metadata, "sandbox_mode", None)

    agent_mode = AgentMode.ANALYSIS
    execution_policy = (
        getattr(session_metadata, "execution_policy", None)
        if session_metadata is not None
        else None
    )
    enabled_expert_role_ids = (
        getattr(session_metadata, "enabled_expert_role_ids", None)
        if session_metadata is not None
        else None
    )
    normalized_enabled_expert_role_ids = _normalize_enabled_expert_role_ids(enabled_expert_role_ids)
    expert_role_tool_ids = (
        getattr(session_metadata, "expert_role_tool_ids", None)
        if session_metadata is not None
        else None
    )
    normalized_expert_role_tool_ids = _normalize_expert_role_tool_ids(expert_role_tool_ids)
    workspace_registry = None
    workspace_id: str | None = (
        getattr(session_metadata, "workspace_id", None) if session_metadata is not None else None
    )
    try:
        from app.services.workspace_registry import get_workspace_registry_service

        workspace_registry = get_workspace_registry_service()
        if not workspace_id:
            workspace_id = workspace_registry.find_workspace_id_by_session_id(
                user_id,
                session_id,
            )
    except Exception:
        workspace_id = workspace_id or None

    def _runtime_role_enabled(role_id: str) -> bool:
        return _is_subagent_enabled_for_runtime(
            role_id,
            user_id=user_id,
            workspace_id=workspace_id,
            enabled_subagent_ids=normalized_enabled_expert_role_ids,
        )

    system_config_path, _ = resolve_agent_system_default_paths(
        sandbox_mode=sandbox_mode,
        execution_policy=execution_policy,
    )
    preset = resolve_system_agent_preset_from_path(system_config_path)

    env_info = _get_execution_env_info(session_id=session_id, user_id=user_id)
    if preset is not None:
        agent_manifest = _build_manifest_from_system_baseline(
            preset.baseline,
            env_info=env_info,
        )
        embedded_subagents = _build_embedded_subagent_manifests_from_preset(
            preset,
            env_info=env_info,
            enabled_subagent_ids=normalized_enabled_expert_role_ids,
            role_tool_ids_by_subagent=normalized_expert_role_tool_ids,
            subagent_enabled_for_runtime=_runtime_role_enabled,
        )
        if embedded_subagents:
            agent_manifest["subagents"] = embedded_subagents
    else:
        agent_manifest = _build_manifest_from_toml_config(
            system_config_path,
            env_info=env_info,
            enabled_subagent_ids=normalized_enabled_expert_role_ids,
            role_tool_ids_by_subagent=normalized_expert_role_tool_ids,
            subagent_enabled_for_runtime=_runtime_role_enabled,
        )

    # 合并自定义子 Agent（global + 工作区），按工作区启用策略过滤。
    try:
        from app.services.agent.subagent_catalog import (
            load_custom_subagents_for_manifest,
        )

        custom_subagents = load_custom_subagents_for_manifest(
            user_id,
            workspace_id=workspace_id,
        )
        existing_subagents = agent_manifest.get("subagents") or {}
        if not isinstance(existing_subagents, dict):
            existing_subagents = {}

        # workspace 级专家覆盖 global 级同名专家
        # 按 enabled_expert_role_ids 过滤自定义子 Agent
        for name, manifest in custom_subagents.items():
            if not _runtime_role_enabled(str(name)):
                continue
            if (
                name in existing_subagents
                and str(manifest.get("_source") or manifest.get("source") or "") == "builtin"
            ):
                continue
            existing_subagents[name] = {
                "description": manifest.get("description", ""),
                "agent_manifest": manifest,
            }
        if existing_subagents:
            agent_manifest["subagents"] = existing_subagents
    except Exception:
        logger.warning(
            "合并自定义子 Agent 失败（忽略）: user=%s session=%s workspace=%s",
            user_id,
            session_id,
            workspace_id if "workspace_id" in dir() else None,
            exc_info=True,
        )

    rendered_prompt = str(agent_manifest.get("system_prompt") or "")

    try:
        config_service = get_agent_config_service()
        merged_config = await config_service.get_merged_config(
            mode=agent_mode,
            user_id=user_id,
            sandbox_mode=sandbox_mode,
            session_id=session_id,
            workspace_id=workspace_id,
            base_config_path=system_config_path,
            rendered_system_prompt=rendered_prompt,
        )

        rendered_prompt = merged_config.system_prompt
        if merged_config.is_customized:
            logger.info(
                "应用用户自定义配置: user=%s, mode=%s, prompt_source=%s, tools_customized=%s",
                user_id,
                agent_mode.value,
                merged_config.prompt_source,
                len(merged_config.enabled_tools) > 0,
            )
    except Exception as e:
        logger.warning("读取用户配置失败，使用系统默认: user=%s, error=%s", user_id, e)
        merged_config = None

    # 获取 workspace 根目录用于加载工作区级 agent.md
    _workspace_dir: Path | None = None
    try:
        if workspace_registry is not None and workspace_id is not None:
            _workspace_dir = workspace_registry.get_workspace_root(user_id, workspace_id)
    except Exception:
        logger.debug("获取 workspace 根目录失败，跳过工作区规范: user=%s", user_id)

    agent_manifest["system_prompt"] = rendered_prompt

    if merged_config:
        agent_manifest["tool_strategy"] = merged_config.tool_strategy
        original_tools = agent_manifest.get("tools", [])
        agent_manifest["tools"] = _sanitize_tool_list(list(merged_config.enabled_tools))
        disabled = set(original_tools) - set(agent_manifest["tools"])
        added = set(agent_manifest["tools"]) - set(original_tools)
        if disabled:
            logger.info("用户配置禁用工具: %s", list(disabled))
        if added:
            logger.info("用户配置启用工具: %s", list(added))
    else:
        agent_manifest["tools"] = _sanitize_tool_list(list(agent_manifest.get("tools", [])))

    logger.info(
        "生成结构化 agent manifest: session=%s, tools=%s, subagents=%s",
        session_id,
        len(agent_manifest.get("tools", []) or []),
        len(agent_manifest.get("subagents", {}) or {}),
    )
    return agent_manifest


async def generate_dynamic_agent_config(
    session_id: str,
    user_id: str,
    sandbox_mode: Optional[str] = None,
    agent_type: str = "data_analysis",
) -> Path:
    """
    生成动态 agent 配置文件

    当前 runtime create 协议仍要求 `agent_file: Path`，因此这里把结构化 manifest
    materialize 成临时 YAML；但系统默认基线已改由结构化 preset store 驱动。

    Args:
        session_id: 会话 ID
        user_id: 用户 ID
        sandbox_mode: 沙盒模式，None 则使用系统默认配置
        agent_type: Agent 类型，"data_analysis"（统一主控）

    Returns:
        临时 agent 配置文件路径
    """
    session_manager = SessionManager(WORKSPACE_DIR)
    session_metadata = session_manager.get_session(session_id, user_id)
    if sandbox_mode is None and session_metadata is not None:
        sandbox_mode = getattr(session_metadata, "sandbox_mode", None)

    execution_policy = (
        getattr(session_metadata, "execution_policy", None)
        if session_metadata is not None
        else None
    )
    _system_config_path, _ = resolve_agent_system_default_paths(
        sandbox_mode=sandbox_mode,
        execution_policy=execution_policy,
    )
    temp_agent_config_dir = (
        get_work_dir(user_id, session_id).to_local_path()
        / ".aiasys"
        / "session"
        / RUNTIME_AGENT_CONFIG_DIR_NAME
    )

    temp_agent_config_dir.mkdir(parents=True, exist_ok=True)
    agent_manifest = await build_dynamic_agent_manifest(
        session_id=session_id,
        user_id=user_id,
        sandbox_mode=sandbox_mode,
        agent_type=agent_type,
    )
    agent_config = {"version": 1, "agent": deepcopy(agent_manifest)}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rendered_prompt = str(agent_config["agent"].pop("system_prompt", "") or "")
    temp_prompt_filename = f"prompt_{user_id}_{session_id}_{timestamp}.md"
    temp_prompt_path = temp_agent_config_dir / temp_prompt_filename
    Path(as_system_path(temp_prompt_path)).write_text(rendered_prompt, encoding="utf-8")
    agent_config["agent"]["system_prompt_path"] = str(temp_prompt_path.resolve())
    agent_config["agent"]["system_prompt_args"] = {}

    subagents = agent_config["agent"].get("subagents", {})
    if isinstance(subagents, dict):
        rewritten_subagents: dict[str, Any] = {}
        for subagent_name, subagent in subagents.items():
            if not isinstance(subagent, dict):
                continue
            embedded_manifest = deepcopy(subagent.get("agent_manifest") or {})
            if not isinstance(embedded_manifest, dict):
                continue

            rendered_subagent_prompt = str(embedded_manifest.pop("system_prompt", "") or "")
            temp_subagent_prompt_filename = (
                f"subprompt_{subagent_name}_{user_id}_{session_id}_{timestamp}.md"
            )
            temp_subagent_prompt_path = temp_agent_config_dir / temp_subagent_prompt_filename
            Path(as_system_path(temp_subagent_prompt_path)).write_text(
                rendered_subagent_prompt,
                encoding="utf-8",
            )
            embedded_manifest["system_prompt_path"] = str(temp_subagent_prompt_path.resolve())
            embedded_manifest["system_prompt_args"] = {}

            temp_subagent_filename = (
                f"subagent_{subagent_name}_{user_id}_{session_id}_{timestamp}.toml"
            )
            temp_subagent_path = temp_agent_config_dir / temp_subagent_filename

            with open(as_system_path(temp_subagent_path), "w", encoding="utf-8") as f:
                f.write(
                    tomli_w.dumps({"version": 1, "agent": _strip_none_values(embedded_manifest)})
                )

            rewritten_subagent = {
                key: value
                for key, value in subagent.items()
                if key not in {"agent_manifest", "baseline_id"}
            }
            rewritten_subagent["path"] = str(temp_subagent_path.resolve())
            rewritten_subagents[subagent_name] = rewritten_subagent
        agent_config["agent"]["subagents"] = rewritten_subagents

    temp_agent_filename = f"agent_{user_id}_{session_id}_{timestamp}.toml"
    temp_agent_path = temp_agent_config_dir / temp_agent_filename

    with open(as_system_path(temp_agent_path), "w", encoding="utf-8") as f:
        f.write(tomli_w.dumps(_strip_none_values(agent_config)))

    logger.info(
        "生成动态 agent 配置: session=%s, prompt_chars=%s, subagents=%s",
        session_id,
        len(rendered_prompt),
        len(agent_config["agent"].get("subagents", {}) or {}),
    )

    return temp_agent_path


def cleanup_temp_agent_configs(max_age_hours: int = 24) -> int:
    """
    清理过期的临时 agent 配置文件

    Args:
        max_age_hours: 文件最大保留时间（小时）

    Returns:
        清理的文件数量
    """
    import time

    cleaned_count = 0
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    temp_dirs: set[Path] = set()
    try:
        runtime_config_dirs = (Path(WORKSPACE_DIR)).glob(
            f"*/*/.aiasys/session/{RUNTIME_AGENT_CONFIG_DIR_NAME}"
        )
        temp_dirs.update(path for path in runtime_config_dirs if path.is_dir())
    except Exception:
        logger.debug("扫描会话级 agent 临时目录失败", exc_info=True)

    try:
        for temp_dir in temp_dirs:
            if not temp_dir.exists():
                continue
            for file_path in temp_dir.iterdir():
                if not file_path.is_file():
                    continue

                # 检查文件年龄
                file_age = current_time - file_path.stat().st_mtime
                if file_age > max_age_seconds:
                    try:
                        file_path.unlink()
                        cleaned_count += 1
                        logger.debug(f"清理过期配置: {file_path}")
                    except Exception as e:
                        logger.warning(f"删除过期配置失败: {file_path}, error={e}")
    except Exception as e:
        logger.warning(f"清理临时配置失败: {e}")

    if cleaned_count > 0:
        logger.info(f"清理 {cleaned_count} 个过期临时配置")

    return cleaned_count


# 导出
generate_dynamic_agent_config.__doc__ = generate_dynamic_agent_config.__doc__
