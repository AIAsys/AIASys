"""
AIASys 原生子 Agent 调度工具 (TaskTool)。

基于自有 AiasysRuntimeBackend 实现子 Agent 创建与执行。
"""

from __future__ import annotations

import logging
import tomllib
import uuid
from collections.abc import AsyncGenerator
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import tomli_w

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.agent.agent_path import AgentPath, normalize_agent_max_depth
from app.services.agent.runtime_backends.aiasys.backend import AiasysRuntimeBackend
from app.services.agent.runtime_backends.aiasys.session import AiasysRuntimeSession
from app.services.agent.runtime_backends.base import (
    AgentRuntimeEvent,
    RuntimeSessionCreateSpec,
)
from app.services.agent.subagent_lifecycle import SubAgentLifecycleManager
from app.services.agent.subagent_registry import get_subagent_registry
from app.services.agent.subagent_storage import SubAgentStorage
from app.services.agent.system_presets import (
    get_role_type_default_tools,
    get_subagent_universal_excludes,
)
from app.services.history import (
    current_session_id,
    current_session_root,
    current_user_id,
    current_workspace,
)
from app.utils.path_utils import as_system_path

logger = logging.getLogger(__name__)


def _filter_mcp_configs(
    host_mcp_configs: list | None,
    mcp_policy: str,
    mcp_servers: list[str],
) -> list | None:
    """根据子 Agent 的 MCP 继承策略过滤 Host 的 MCP 配置。

    策略:
    - none: 不继承任何 MCP 配置
    - inherit: 完整继承 Host 的所有 MCP 配置
    - allowlist: 只继承 mcp_servers 中列出的 server
    - denylist: 继承全部，但排除 mcp_servers 中列出的 server
    """
    policy = (mcp_policy or "none").strip().lower()
    if policy == "none":
        return None
    if not host_mcp_configs:
        return None

    if policy == "inherit":
        return host_mcp_configs

    allowed_names = {name.strip() for name in mcp_servers if name.strip()}
    if not allowed_names:
        return None if policy == "allowlist" else host_mcp_configs

    filtered: list[dict[str, Any]] = []
    for block in host_mcp_configs:
        if not isinstance(block, dict):
            continue
        raw_servers = block.get("mcpServers") or block.get("mcp_servers") or {}
        if not isinstance(raw_servers, dict):
            continue
        new_servers: dict[str, Any] = {}
        for server_name, server_config in raw_servers.items():
            name = str(server_name).strip()
            if policy == "allowlist":
                if name in allowed_names:
                    new_servers[name] = server_config
            elif policy == "denylist":
                if name not in allowed_names:
                    new_servers[name] = server_config
        if new_servers:
            # 保持原始 key 风格
            key = "mcpServers" if "mcpServers" in block else "mcp_servers"
            filtered.append({key: new_servers})

    return filtered if filtered else None


def _resolve_skills_dir(
    workspace: Path,
    skill_policy: str,
    skills: list[str],
) -> Path | None:
    """根据子 Agent 的 Skill 继承策略决定 skills_dir。

    策略:
    - none: 不继承任何 Skill
    - inherit: 继承 Host workspace 的全部 Skill
    - allowlist/denylist: 返回原始 workspace skills 目录路径，
      由 runtime 在加载 system prompt 时做过滤注入
    """
    policy = (skill_policy or "inherit").strip().lower()
    if policy == "none":
        return None
    workspace_skills = workspace / ".aiasys" / "skills"
    if not workspace_skills.exists():
        return None
    return workspace_skills


_TASK_PARAMETERS = {
    "type": "object",
    "properties": {
        "subagent_name": {
            "type": "string",
            "description": "要调用的子 Agent 名称。可用预设角色: coder, data_analyst, researcher, reviewer。也可使用自定义子 Agent 名称。省略时默认使用 coder。当用户说'让数据分析专家处理'或'委派给某个专家'时，必须把对应 role_id 填到这里。",
        },
        "description": {
            "type": "string",
            "description": "任务简述，用于 UI 展示和日志",
        },
        "prompt": {
            "type": "string",
            "description": "给子 Agent 的完整任务指令。当用户要求委派任务给专家时，把用户原任务改写为清晰指令填到这里。",
        },
    },
    "required": ["prompt"],
}


def _streaming_event(event: AgentRuntimeEvent) -> ToolResult:
    """将一个 AgentRuntimeEvent 包装为流式 ToolResult。"""
    return ToolResult(
        content="",
        is_error=False,
        artifacts=[{"_streaming_event": asdict(event)}],
    )


def _annotate_subagent_runtime_event(
    event: AgentRuntimeEvent,
    *,
    agent_id: str,
    subagent_name: str,
) -> AgentRuntimeEvent:
    payload = asdict(event)
    payload["agent_id"] = str(payload.get("agent_id") or agent_id)
    payload["subagent_type"] = str(payload.get("subagent_type") or subagent_name)
    payload["subagent_name"] = str(payload.get("subagent_name") or subagent_name)
    return AgentRuntimeEvent(**payload)


def _find_subagent_manifest(
    host_agent_config: dict[str, Any],
    subagent_name: str,
) -> dict[str, Any] | None:
    """从 Host agent config 中查找指定子 Agent 的 manifest。"""
    subagents = host_agent_config.get("subagents") or {}
    if not isinstance(subagents, dict):
        return None
    binding = subagents.get(subagent_name)
    if not isinstance(binding, dict):
        return None
    manifest = binding.get("agent_manifest")
    if isinstance(manifest, dict):
        return manifest
    raw_path = binding.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    try:
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = path.resolve()
        with path.open("rb") as file:
            payload = tomllib.load(file) or {}
    except Exception:
        logger.warning(
            "读取子 Agent manifest 失败: subagent=%s path=%s",
            subagent_name,
            raw_path,
            exc_info=True,
        )
        return None
    agent = payload.get("agent")
    if isinstance(agent, dict):
        return agent
    return None


def _resolve_collaboration_policy(ctx: dict[str, Any]) -> dict[str, Any]:
    raw_policy = ctx.get("collaboration_policy")
    if hasattr(raw_policy, "model_dump"):
        raw_policy = raw_policy.model_dump()
    if not isinstance(raw_policy, dict):
        raw_policy = {}

    max_depth = normalize_agent_max_depth(raw_policy.get("max_depth"), default=1)
    if max_depth < 1:
        max_depth = 1

    return {
        "max_depth": max_depth,
        "allow_nested_spawn": bool(raw_policy.get("allow_nested_spawn", False)),
        "max_threads": raw_policy.get("max_threads"),
    }


def _materialize_subagent_toml(
    manifest: dict[str, Any],
    subagent_name: str,
    tmpdir: str | None = None,
) -> Path:
    """将子 Agent manifest 物化为临时 TOML 文件。

    如果提供 tmpdir 则使用该目录，否则自行创建临时目录。
    调用方负责在 finally 块中清理临时目录。
    """
    import tempfile

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"native_subagent_{subagent_name}_{timestamp}_{uuid.uuid4().hex[:8]}.toml"
    if tmpdir is None:
        tmpdir = tempfile.mkdtemp(prefix="aiasys_subagent_")
    path = Path(tmpdir) / filename

    # manifest 已经是 agent 段内容，需要包装为完整 TOML
    clean_manifest = {k: v for k, v in deepcopy(manifest).items() if v is not None}
    payload = {"version": 1, "agent": clean_manifest}
    with open(as_system_path(str(path)), "wb") as f:
        tomli_w.dump(payload, f)
    return path


class TaskTool(AiasysTool):
    """AIASys 原生子 Agent 调度工具。

    当 Host Agent 调用 Task 时，此工具：
    1. 查找子 Agent 配置
    2. 创建独立的工作区和存储
    3. 启动新的 AiasysRuntimeSession 运行子 Agent
    4. 流式返回子 Agent 的执行事件
    """

    name = "Task"
    description = (
        "将任务委派给专门的子 Agent 执行。"
        "参数: subagent_name(子Agent名称, 可选, 默认coder), description(任务简述), prompt(完整指令)"
    )
    parameters = _TASK_PARAMETERS

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """同步调用（非流式）。

        为了兼容非流式场景，提供同步版本。
        实际会运行完整子 Agent，但只返回最终结果。
        """
        # 收集所有流式结果，只返回最后一个 result
        final_result: ToolResult | None = None
        async for item in self.invoke_stream(ctx, **kwargs):
            if item.artifacts and any(
                isinstance(a, dict) and a.get("_streaming_event") is not None
                for a in item.artifacts
            ):
                continue
            final_result = item
        return final_result or ToolResult(content="子 Agent 执行完成（无输出）")

    async def invoke_stream(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[ToolResult, None]:
        """流式调用子 Agent。

        yield 中间事件（通过 _streaming_event artifact 标记）和最终结果。
        """
        ctx = ctx or {}
        subagent_name = str(kwargs.get("subagent_name") or "").strip() or "coder"
        description = str(kwargs.get("description") or "").strip()
        prompt = str(kwargs.get("prompt") or "").strip()

        if not prompt:
            yield ToolResult(content="缺少 prompt 参数", is_error=True)
            return

        user_id = str(ctx.get("user_id") or current_user_id.get() or "")
        session_id = str(ctx.get("session_id") or current_session_id.get() or "")
        host_session_id = str(ctx.get("host_session_id") or session_id)
        workspace = Path(str(ctx.get("workspace") or current_workspace.get() or ""))
        session_root = Path(str(ctx.get("session_root") or current_session_root.get() or workspace))
        host_agent_config = ctx.get("agent_config") or {}
        host_llm_config = ctx.get("llm_config")

        if not user_id or not session_id:
            yield ToolResult(content="无法确定当前会话上下文", is_error=True)
            return

        # 1. 查找子 Agent manifest
        subagent_manifest = _find_subagent_manifest(host_agent_config, subagent_name)
        if subagent_manifest is None:
            # fallback 到协作专家运行时查找（workspace > global）
            from app.services.agent.subagent_catalog import (
                get_normalized_enabled_expert_role_ids,
                is_subagent_dispatch_enabled,
                load_subagent_for_runtime,
            )

            normalized_enabled_expert_role_ids = get_normalized_enabled_expert_role_ids(
                user_id=user_id,
                session_id=session_id,
            )

            workspace_id = user_id
            try:
                from app.services.workspace_registry import get_workspace_registry_service

                registry = get_workspace_registry_service()
                resolved = registry.find_workspace_id_by_session_id(user_id, session_id)
                if resolved:
                    workspace_id = resolved
            except Exception:
                pass
            if not is_subagent_dispatch_enabled(
                user_id=user_id,
                role_id=subagent_name,
                workspace_id=workspace_id,
                explicit_enabled_role_ids=normalized_enabled_expert_role_ids,
            ):
                available = list((host_agent_config.get("subagents") or {}).keys())
                yield ToolResult(
                    content=(
                        f"协作专家 '{subagent_name}' 未启用到我的默认或当前工作区，"
                        f"不能派发。当前可派发: {available}"
                    ),
                    is_error=True,
                )
                return
            subagent_manifest = load_subagent_for_runtime(
                user_id=user_id,
                name=subagent_name,
                session_id=session_id,
                workspace_id=workspace_id,
            )
        if subagent_manifest is None:
            available = list((host_agent_config.get("subagents") or {}).keys())
            yield ToolResult(
                content=f"未找到子 Agent '{subagent_name}'。可用: {available}",
                is_error=True,
            )
            return

        # 2. 生成唯一 agent_id
        agent_id = f"{subagent_name}_{uuid.uuid4().hex[:12]}"
        current_path = AgentPath.parse(str(ctx.get("agent_path") or "/root"))
        collaboration_policy = _resolve_collaboration_policy(ctx)
        effective_max_depth = int(collaboration_policy["max_depth"])
        allow_nested_spawn = bool(collaboration_policy["allow_nested_spawn"])
        registry = get_subagent_registry()
        raw_max_threads = collaboration_policy.get("max_threads")
        max_threads = (
            raw_max_threads if isinstance(raw_max_threads, int) and raw_max_threads > 0 else None
        )
        try:
            child_path = current_path.ensure_child_allowed(
                max_depth=effective_max_depth,
                child_agent_id=agent_id,
            )
        except ValueError as exc:
            yield ToolResult(content=str(exc), is_error=True)
            return
        parent_agent_id = (
            str(current_path.current_agent_id or ctx.get("parent_agent_id") or "") or None
        )
        child_allow_spawn = allow_nested_spawn and child_path.depth < effective_max_depth

        # 2a. 预检查并发限制（快速失败，避免创建不必要的 storage/session）
        if max_threads is not None:
            active_count = registry.count_active_for_host(host_session_id)
            if active_count >= max_threads:
                yield ToolResult(
                    content=(
                        f"当前会话协作节点并发数已达到上限 {max_threads}，"
                        "请等待已有节点完成后再派发。"
                    ),
                    is_error=True,
                )
                return

        parent_tool_call_id = str(
            ctx.get("_tool_call_id") or kwargs.get("_tool_call_id") or uuid.uuid4().hex[:12]
        )
        effective_model = subagent_manifest.get("model")
        # 如果 manifest 没指定模型，fallback 到 task_models.subagent
        if not effective_model:
            llm_config = ctx.get("llm_config")
            if llm_config and hasattr(llm_config, "task_models"):
                task_models = llm_config.task_models
                subagent_model = task_models.get("subagent")
                if subagent_model:
                    available = set(getattr(llm_config, "models", {}).keys())
                    if subagent_model not in available:
                        logger.warning(
                            "task_models.subagent 配置的模型 '%s' 不存在，可用模型: %s",
                            subagent_model,
                            available,
                        )
                    else:
                        effective_model = subagent_model
        nickname = None
        nickname_pool = subagent_manifest.get("agent_nickname_pool")
        if isinstance(nickname_pool, list) and nickname_pool:
            nickname = str(nickname_pool[0] or "").strip() or None

        # 3. 创建子 Agent storage 工作区
        storage = SubAgentStorage(user_id, host_session_id, agent_id)
        storage.create_workspace(
            parent_tool_call_id=parent_tool_call_id,
            subagent_type=subagent_name,
            description=description or f"子 Agent: {subagent_name}",
            effective_model=effective_model,
            model_override=effective_model,
            host_session_id=host_session_id,
            parent_agent_id=parent_agent_id,
            agent_path=str(child_path),
            depth=child_path.depth,
            nickname=nickname,
        )

        # 4. 决定工具、MCP、Skill 继承策略，并先完成 manifest 修正
        tool_policy = subagent_manifest.get("tool_policy") or "inherit"
        fork_turns = subagent_manifest.get("fork_turns")  # None=all, 0=none, int=N

        # 4a. 运行时动态注入工具集（如果 manifest 未显式声明 tools）
        # 必须在物化 TOML 之前完成，否则 backend 读取的是空工具表
        if not subagent_manifest.get("tools"):
            if tool_policy == "allowlist":
                default_tools = get_role_type_default_tools(subagent_name)
                if default_tools:
                    subagent_manifest["tools"] = list(default_tools)
                    subagent_manifest["allowed_tools"] = list(default_tools)
            elif tool_policy in ("inherit", "denylist") and not ctx.get("parent_registry"):
                # 没有可继承的父 registry 时，fallback 到角色默认工具集
                default_tools = get_role_type_default_tools(subagent_name)
                if default_tools:
                    subagent_manifest["tools"] = list(default_tools)

        # 4b. 统一附加一级禁用排除
        universal_excludes = get_subagent_universal_excludes()
        if universal_excludes:
            existing_excludes = set(subagent_manifest.get("exclude_tools") or [])
            merged_excludes = existing_excludes | set(universal_excludes)
            subagent_manifest["exclude_tools"] = list(merged_excludes)

        # 4c. 物化子 Agent TOML 到 storage 目录
        subagent_toml_path = _materialize_subagent_toml(
            subagent_manifest, subagent_name, str(storage.subagent_dir)
        )

        mcp_policy = subagent_manifest.get("mcp_policy") or "none"
        mcp_servers = subagent_manifest.get("mcp_servers") or []
        host_mcp_configs = ctx.get("mcp_configs")
        child_mcp_configs = _filter_mcp_configs(host_mcp_configs, mcp_policy, mcp_servers)
        if child_mcp_configs:
            logger.info(
                "子 Agent %s 继承 MCP: policy=%s, 原始 %d blocks -> 子 Agent %d blocks",
                subagent_name,
                mcp_policy,
                len(host_mcp_configs) if host_mcp_configs else 0,
                len(child_mcp_configs),
            )

        skill_policy = subagent_manifest.get("skill_policy") or "inherit"
        skills = subagent_manifest.get("skills") or []
        child_skills_dir = _resolve_skills_dir(workspace, skill_policy, skills)
        if child_skills_dir:
            logger.debug(
                "子 Agent %s 继承 Skill: policy=%s, dir=%s",
                subagent_name,
                skill_policy,
                child_skills_dir,
            )

        # 获取 Host messages 用于 fork_turns 继承
        host_messages = ctx.get("messages") or []

        # 读取 Host budget，子会话共享同一对象引用，消耗自动汇总到 Host
        host_budget = ctx.get("budget")

        # 6. 创建 RuntimeSessionCreateSpec（共享 Host 会话目录）
        from app.core.workspace_path import WorkspacePath

        # 子 Agent 共享主控的 session_root，不创建独立工作区。
        shared_work_dir = WorkspacePath(str(session_root))
        spec = RuntimeSessionCreateSpec(
            work_dir=shared_work_dir,
            session_id=agent_id,
            user_id=user_id,
            config=host_llm_config,
            agent_file=subagent_toml_path,
            skills_dir=WorkspacePath(str(child_skills_dir)) if child_skills_dir else None,
            authorization_mode=str(ctx.get("authorization_mode") or "smart"),
            yolo=bool(ctx.get("yolo", False)),
            mcp_configs=child_mcp_configs,
            is_subagent=True,
            parent_registry=ctx.get("parent_registry"),
            tool_policy=tool_policy,
            fork_turns=fork_turns,
            fork_messages=host_messages,
            host_session_id=host_session_id,
            parent_agent_id=parent_agent_id,
            agent_path=str(child_path),
            agent_max_depth=effective_max_depth,
            allow_subagent_spawn=child_allow_spawn,
            collaboration_policy=collaboration_policy,
            budget=host_budget,
            memory_enabled=False,  # 子 Agent 不需要 memory
        )

        # 6. 创建子 Agent session
        backend = AiasysRuntimeBackend()
        subagent_session: AiasysRuntimeSession | None = None
        try:
            subagent_session = await backend.create_session(spec)
        except Exception as exc:
            logger.exception(
                "创建子 Agent session 失败: subagent=%s agent_id=%s", subagent_name, agent_id
            )
            yield ToolResult(
                content=f"创建子 Agent session 失败: {exc}",
                is_error=True,
            )
            return

        # 8. 注册到运行时注册表（原子检查并发限制，防止竞态超发）
        registered = await registry.try_register(
            agent_id,
            subagent_session,
            host_session_id=host_session_id,
            max_threads=max_threads,
        )
        if not registered:
            yield ToolResult(
                content=(
                    f"当前会话协作节点并发数已达到上限 {max_threads}，请等待已有节点完成后再派发。"
                ),
                is_error=True,
            )
            return

        # 8. 记录完整 launch_spec，供后续继续对话 / resume 重建
        full_launch_spec = {
            "agent_id": agent_id,
            "subagent_name": subagent_name,
            "host_session_id": host_session_id,
            "user_id": user_id,
            "storage_path": str(storage.subagent_dir),
            "subagent_toml_path": subagent_toml_path,
            "effective_model": effective_model,
            "parent_tool_call_id": parent_tool_call_id,
            "parent_agent_id": parent_agent_id,
            "child_path": str(child_path),
            "nickname": nickname,
            "description": description,
            "max_threads": max_threads,
            "timeout_seconds": collaboration_policy.get("timeout_policy", {}).get(
                "default_seconds", 300
            ),
            "llm_config": subagent_session._spec.config.model_dump(mode="json"),
            "agent_file": subagent_toml_path,
            "session_root": str(session_root),
            "child_skills_dir": str(child_skills_dir) if child_skills_dir else None,
            "collaboration_policy": collaboration_policy,
            "authorization_mode": str(ctx.get("authorization_mode") or "smart"),
            "yolo": bool(ctx.get("yolo", False)),
            "mcp_configs": child_mcp_configs,
            "tool_policy": tool_policy,
            "agent_path": str(child_path),
        }
        storage.update_launch_spec(full_launch_spec)
        registry.set_launch_spec(agent_id, full_launch_spec)

        # 9. 持久化初始用户指令
        await storage.append_context_message(
            {
                "role": "user",
                "content": prompt,
                "parent_tool_call_id": parent_tool_call_id,
            }
        )

        # 10. 运行子 Agent（生命周期管理器负责事件流、持久化、状态转换和 contextvar）
        lifecycle_manager = SubAgentLifecycleManager(registry=registry)
        try:
            async for result in lifecycle_manager.run_subagent_session(
                subagent_session=subagent_session,
                agent_id=agent_id,
                subagent_name=subagent_name,
                prompt=prompt,
                storage=storage,
                keep_alive=True,
                timeout_seconds=(registry.get_launch_spec(agent_id) or {}).get(
                    "timeout_seconds", 300
                ),
                workspace=workspace,
                session_root=session_root,
                user_id=user_id,
                host_session_id=host_session_id,
            ):
                yield result
        finally:
            try:
                await storage.flush()
            except Exception:
                logger.warning("子 Agent 缓冲刷盘失败", exc_info=True)


class AgentTool(TaskTool):
    """AIASys 原生子 Agent 调度工具（Agent 名称变体）。

    为了保持 LLM 兼容性，同时注册 Task 和 Agent 两个名称，
    底层实现与 TaskTool 完全一致。
    """

    name = "Agent"
    description = (
        "创建并运行一个专门的子 Agent 来执行任务。"
        "参数: subagent_name(子Agent名称, 可选, 默认coder), description(任务简述), prompt(完整指令)"
    )
    parameters = _TASK_PARAMETERS
