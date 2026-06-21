from __future__ import annotations

import importlib
import inspect
import logging
import tomllib
from pathlib import Path
from typing import Any

from app.core.agent_tool import AiasysTool
from app.core.config import DEFAULT_MODEL, DEFAULT_PROVIDER, LLM_PROVIDERS
from app.services.runtime_tooling import is_subagent_orchestration_tool_name
from app.utils.path_utils import as_system_path

from ..base import RuntimeSessionCreateSpec
from .llm_clients import create_llm_client
from .provider_router import ProviderRouter
from .session import AiasysRuntimeSession
from .tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

_READ_MEDIA_ALIAS = "app.agents.tools.read_media_tool:ReadMediaFile"


def _load_agent_manifest(agent_file: Path) -> dict[str, Any]:
    with open(as_system_path(str(agent_file)), "rb") as file:
        data = tomllib.load(file) or {}
    agent = data.get("agent")
    if not isinstance(agent, dict):
        raise ValueError(f"Agent 配置缺少 agent 段: {agent_file}")
    return agent


def _iter_tool_paths(
    agent_manifest: dict[str, Any],
    spec: RuntimeSessionCreateSpec | None = None,
) -> list[str]:
    tool_policy = (spec.tool_policy if spec else "inherit") or "inherit"
    tool_paths: list[str] = []

    # 子 Agent manifest 中显式声明的 tools
    raw_tools = agent_manifest.get("tools")
    manifest_tools: list[str] = []
    if isinstance(raw_tools, list):
        for raw_tool in raw_tools:
            tool_path = str(raw_tool or "").strip()
            if tool_path:
                manifest_tools.append(tool_path)
                tool_paths.append(tool_path)

    # denylist: 继承父 Agent 工具，但排除 exclude_tools
    # inherit: 继承父 Agent 工具（默认）
    # allowlist: 只使用 manifest 中声明的 tools
    if tool_policy in ("inherit", "denylist"):
        # 从父 registry 继承工具（仅取 openai schema name 映射回 tool path）
        if spec and spec.parent_registry is not None:
            try:
                parent_schemas = spec.parent_registry.get_openai_schema()
                for schema in parent_schemas:
                    name = schema.get("function", {}).get("name") or schema.get("name")
                    if name:
                        # 简化匹配：取 path 最后一段
                        short = name.split(":")[-1].split(".")[-1]
                        # 尝试通过已知工具路径找到对应 path
                        from app.services.capability_registry import _TOOL_METADATA

                        found = False
                        for tool_path in _TOOL_METADATA:
                            path_short = tool_path.split(":")[-1].split(".")[-1]
                            if path_short == short or tool_path == name:
                                if tool_path not in tool_paths:
                                    tool_paths.append(tool_path)
                                found = True
                                break
                        if not found:
                            # MCP/动态工具：保留运行时名称，后续从 parent_registry 复制
                            if name not in tool_paths:
                                tool_paths.append(name)
            except Exception:
                logger.debug("从父 registry 继承工具失败", exc_info=True)

    # 处理排除列表
    exclude_tools = {
        str(raw_tool or "").strip()
        for raw_tool in agent_manifest.get("exclude_tools", []) or []
        if str(raw_tool or "").strip()
    }

    normalized_paths: list[str] = []
    seen: set[str] = set()
    for tool_path in tool_paths:
        if spec is not None and spec.is_subagent and is_subagent_orchestration_tool_name(tool_path):
            continue
        if tool_path in exclude_tools:
            continue
        if tool_path in seen:
            continue
        seen.add(tool_path)
        normalized_paths.append(tool_path)

    return normalized_paths


def _load_symbol(tool_path: str) -> type[Any]:
    module_name, symbol_name = tool_path.rsplit(":", 1)
    module = importlib.import_module(module_name)
    return getattr(module, symbol_name)


def _read_config_value(config: Any, field_name: str) -> Any:
    if isinstance(config, dict):
        return config.get(field_name)
    return getattr(config, field_name, None)


def _instantiate_tool(
    tool_path: str,
    *,
    session_id: str,
    model_capabilities: list[str] | None,
) -> AiasysTool | None:
    if tool_path == "app.agents.tools.ask_user.tool:AskUser":
        from app.agents.tools.ask_user.tool import get_ask_user_tool

        return get_ask_user_tool(session_id=session_id)

    tool_cls = _load_symbol(tool_path)

    if tool_path == _READ_MEDIA_ALIAS:
        tool = tool_cls(set(model_capabilities or []))
    else:
        try:
            signature = inspect.signature(tool_cls)
            required_arguments = [
                parameter
                for parameter in signature.parameters.values()
                if parameter.name != "self"
                and parameter.default is inspect.Parameter.empty
                and parameter.kind
                in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.KEYWORD_ONLY,
                )
            ]
            if required_arguments:
                logger.warning("跳过需要额外构造参数的工具: %s", tool_path)
                return None
            tool = tool_cls()
        except TypeError:
            logger.warning("跳过无法无参构造的工具: %s", tool_path)
            return None

    if isinstance(tool, AiasysTool):
        return tool
    raise TypeError(
        f"Tool {tool_path} is not an AiasysTool instance. Got {type(tool).__name__} instead."
    )


def _resolve_model_id(spec: RuntimeSessionCreateSpec, agent_manifest: dict[str, Any]) -> str:
    configured_default = str(spec.config.default_model or DEFAULT_MODEL or "").strip()
    manifest_model = agent_manifest.get("model")
    if isinstance(manifest_model, str) and manifest_model.strip():
        manifest_model_id = manifest_model.strip()
        configured_models = getattr(spec.config, "models", None)
        if not isinstance(configured_models, dict) or manifest_model_id in configured_models:
            return manifest_model_id
        if configured_default:
            logger.warning(
                "Agent manifest model `%s` 不在当前 LLM 模型配置中，改用已解析模型 `%s`。",
                manifest_model_id,
                configured_default,
            )
            return configured_default
        return manifest_model_id
    return configured_default


def _resolve_model_entry(
    spec: RuntimeSessionCreateSpec,
    model_id: str,
) -> Any | None:
    if model_id and model_id in spec.config.models:
        return spec.config.models[model_id]
    return None


def _resolve_provider_entry(
    spec: RuntimeSessionCreateSpec,
    *,
    explicit_provider_id: str | None,
) -> tuple[str | None, Any | None]:
    config_providers = spec.config.providers or {}
    if explicit_provider_id and explicit_provider_id in config_providers:
        return explicit_provider_id, config_providers[explicit_provider_id]

    provider_attr = getattr(spec.config, "provider", None)
    if isinstance(provider_attr, str) and provider_attr.strip():
        provider_attr = provider_attr.strip()
        if provider_attr in config_providers:
            return provider_attr, config_providers[provider_attr]

    if config_providers:
        first_provider_id = next(iter(config_providers))
        return first_provider_id, config_providers[first_provider_id]

    if explicit_provider_id and explicit_provider_id in LLM_PROVIDERS:
        return explicit_provider_id, LLM_PROVIDERS[explicit_provider_id]

    if DEFAULT_PROVIDER in LLM_PROVIDERS:
        return DEFAULT_PROVIDER, LLM_PROVIDERS[DEFAULT_PROVIDER]

    if LLM_PROVIDERS:
        first_provider_id = next(iter(LLM_PROVIDERS))
        return first_provider_id, LLM_PROVIDERS[first_provider_id]

    return None, None


class AiasysRuntimeBackend:
    """AIASys-native agent runtime backend."""

    async def create_session(
        self,
        spec: RuntimeSessionCreateSpec,
    ) -> AiasysRuntimeSession:
        agent_manifest = _load_agent_manifest(spec.agent_file)
        model_id = _resolve_model_id(spec, agent_manifest)
        model_entry = _resolve_model_entry(spec, model_id)

        explicit_provider_id = None
        if model_entry is not None:
            explicit_provider_id = _read_config_value(model_entry, "provider")

        provider_id, provider_entry = _resolve_provider_entry(
            spec,
            explicit_provider_id=explicit_provider_id,
        )
        if provider_entry is None:
            raise ValueError("未找到可用的 LLM provider 配置")

        _protocol = str(
            _read_config_value(provider_entry, "protocol")
            or _read_config_value(provider_entry, "type")
            or "openai_chat_completions"
        ).lower()
        api_key = _read_config_value(model_entry, "api_key") or _read_config_value(
            provider_entry, "api_key"
        )
        if not api_key:
            raise ValueError(f"LLM provider 配置缺少 api_key: provider={provider_id or 'unknown'}")

        resolved_model_name = _read_config_value(model_entry, "model") or model_id or DEFAULT_MODEL
        if not resolved_model_name:
            raise ValueError("未找到可用的模型名称")

        # 解析 fallback providers
        fallback_providers: list[Any] = []
        for fb_id in spec.config.fallback_order:
            if fb_id == provider_id:
                continue
            fb = spec.config.providers.get(fb_id)
            if fb is not None:
                fallback_providers.append(fb)

        if fallback_providers:
            client: Any = ProviderRouter(
                primary=provider_entry,
                fallbacks=fallback_providers,
                model=str(resolved_model_name),
                model_config=model_entry,
            )
        else:
            client = create_llm_client(
                provider_entry,
                model=str(resolved_model_name),
                model_config=model_entry,
            )

        registry = ToolRegistry()
        model_capabilities = (
            list(_read_config_value(model_entry, "capabilities") or [])
            if model_entry is not None
            else []
        )

        tool_policy = (spec.tool_policy if spec else "inherit") or "inherit"

        # 子 Agent inherit/denylist 模式：直接从 parent_registry 复制工具实例
        if (
            spec.is_subagent
            and tool_policy in ("inherit", "denylist")
            and spec.parent_registry is not None
        ):
            exclude_tools = {
                str(raw_tool or "").strip()
                for raw_tool in (agent_manifest.get("exclude_tools") or [])
                if str(raw_tool or "").strip()
            }
            for schema in spec.parent_registry.get_openai_schema():
                name = schema.get("function", {}).get("name") or schema.get("name")
                if not name:
                    continue
                # 检查是否在排除列表中（支持 schema name 和 short name 匹配）
                if name in exclude_tools:
                    continue
                name_short = name.split(":")[-1].split(".")[-1]
                excluded = False
                for excluded_path in exclude_tools:
                    excluded_short = excluded_path.split(":")[-1].split(".")[-1]
                    if excluded_short == name_short:
                        excluded = True
                        break
                if excluded:
                    continue
                try:
                    tool = spec.parent_registry.get_tool(name)
                    if tool:
                        # 用运行时名称和类名再做一轮排除检查
                        for excluded_path in exclude_tools:
                            if tool.name == excluded_path:
                                excluded = True
                                break
                            excluded_short = excluded_path.split(":")[-1].split(".")[-1]
                            if excluded_short == type(tool).__name__:
                                excluded = True
                                break
                        if excluded:
                            continue
                        registry.register(tool)
                except ValueError:
                    logger.debug("忽略重复工具注册: %s", name)
        else:
            if (
                spec.is_subagent
                and tool_policy in ("inherit", "denylist")
                and spec.parent_registry is None
            ):
                logger.warning(
                    "子 Agent tool_policy=%s 但 parent_registry 为 None，"
                    "无法继承父 Agent 工具，仅加载 manifest 声明的工具。"
                    "session_id=%s",
                    tool_policy,
                    spec.session_id,
                )
            for tool_path in _iter_tool_paths(agent_manifest, spec=spec):
                tool: AiasysTool | None = None
                try:
                    tool = _instantiate_tool(
                        tool_path,
                        session_id=spec.session_id,
                        model_capabilities=model_capabilities,
                    )
                except Exception:
                    logger.exception("加载工具失败: %s", tool_path)
                if tool is None and spec.parent_registry is not None:
                    # 兜底：从父 registry 获取工具实例
                    # 先尝试完整 tool_path，再尝试 short name 匹配
                    tool = spec.parent_registry.get_tool(tool_path)
                    if tool is None:
                        short_name = tool_path.split(":")[-1].split(".")[-1]
                        tool = spec.parent_registry.get_tool(short_name)
                if tool is None:
                    if spec.is_subagent and spec.parent_registry is None:
                        logger.warning(
                            "子 Agent 无法加载工具 %s：parent_registry 为 None "
                            "且 _instantiate_tool 失败，该工具将不可用",
                            tool_path,
                        )
                    continue
                try:
                    registry.register(tool)
                except ValueError:
                    logger.debug("忽略重复工具注册: %s", getattr(tool, "name", tool_path))

        can_orchestrate_subagents = not spec.is_subagent

        # 注册 AIASys 原生协作节点工具。当前只给 Host 注册调度和角色管理能力；
        # 协作节点自身的继续派发必须等会话策略、实例树和控制接口全部闭环后再开放。
        if can_orchestrate_subagents:
            try:
                from app.services.agent.runtime_backends.aiasys.tools.task_tool import (
                    AgentTool,
                    TaskTool,
                )

                registry.register(TaskTool())
                logger.debug("已注册 AIASys 原生 TaskTool")
                registry.register(AgentTool())
                logger.debug("已注册 AIASys 原生 AgentTool")
            except ValueError:
                logger.debug("TaskTool/AgentTool 已注册，跳过重复注册")
            except Exception:
                logger.warning("注册 AIASys 原生 TaskTool/AgentTool 失败", exc_info=True)

            try:
                from app.services.agent.runtime_backends.aiasys.tools.create_subagent_tool import (
                    CreateSubagentTool,
                )

                registry.register(CreateSubagentTool())
                logger.debug("已注册 AIASys 原生 CreateSubagentTool")
            except ValueError:
                logger.debug("CreateSubagentTool 已注册，跳过重复注册")
            except Exception:
                logger.warning("注册 AIASys 原生 CreateSubagentTool 失败", exc_info=True)

            try:
                from app.services.agent.runtime_backends.aiasys.tools.acp_client_tool import (
                    AcpClientTool,
                )

                registry.register(AcpClientTool())
                logger.debug("已注册 AIASys 原生 AcpClientTool")
            except ValueError:
                logger.debug("AcpClientTool 已注册，跳过重复注册")
            except Exception:
                logger.warning("注册 AIASys 原生 AcpClientTool 失败", exc_info=True)

            try:
                from app.services.agent.runtime_backends.aiasys.tools.delete_subagent_tool import (
                    DeleteSubagentTool,
                )
                from app.services.agent.runtime_backends.aiasys.tools.list_subagents_tool import (
                    ListSubagentsTool,
                )
                from app.services.agent.runtime_backends.aiasys.tools.update_subagent_tool import (
                    UpdateSubagentTool,
                )

                registry.register(ListSubagentsTool())
                logger.debug("已注册 AIASys 原生 ListSubagentsTool")
                registry.register(UpdateSubagentTool())
                logger.debug("已注册 AIASys 原生 UpdateSubagentTool")
                registry.register(DeleteSubagentTool())
                logger.debug("已注册 AIASys 原生 DeleteSubagentTool")
            except ValueError:
                logger.debug("Subagent 管理工具已注册，跳过重复注册")
            except Exception:
                logger.warning("注册 AIASys 原生 Subagent 管理工具失败", exc_info=True)

            try:
                from app.services.agent.runtime_backends.aiasys.tools.monitor_tool import (
                    ManageMonitorTool,
                    SpawnMonitorTool,
                )

                registry.register(SpawnMonitorTool())
                registry.register(ManageMonitorTool())
                logger.debug("已注册 AIASys 原生 Monitor 工具")
            except ValueError:
                logger.debug("Monitor 工具已注册，跳过重复注册")
            except Exception:
                logger.warning("注册 AIASys 原生 Monitor 工具失败", exc_info=True)

            # 注册自动任务信号工具（仅 Host）
            try:
                from app.agents.tools.auto_task_signal_tool import AutoTaskSignal

                registry.register(AutoTaskSignal())
                logger.debug("已注册自动任务信号工具")
            except ValueError:
                logger.debug("自动任务信号工具已注册，跳过重复注册")
            except Exception:
                logger.warning("注册自动任务信号工具失败", exc_info=True)

            # 注册自动任务工具
            try:
                from app.agents.tools.auto_task_tool import (
                    ControlAutoTask,
                    CreateAutoTask,
                    ListAutoTasks,
                    UpdateAutoTask,
                )

                registry.register(CreateAutoTask())
                registry.register(ListAutoTasks())
                registry.register(UpdateAutoTask())
                registry.register(ControlAutoTask())
                logger.debug("已注册自动任务工具")
            except ValueError:
                logger.debug("自动任务工具已注册，跳过重复注册")
            except Exception:
                logger.warning("注册自动任务工具失败", exc_info=True)

            # 注册 Memory 工具（受 config.toml [memory] enabled 开关控制）
            if spec.memory_enabled:
                try:
                    from app.services.agent.runtime_backends.aiasys.tools.memory_tool import (
                        MemoryTool,
                    )

                    registry.register(MemoryTool())
                    logger.debug("已注册 AIASys 原生 MemoryTool")
                except ValueError:
                    logger.debug("MemoryTool 已注册，跳过重复注册")
                except Exception:
                    logger.warning("注册 AIASys 原生 MemoryTool 失败", exc_info=True)
            else:
                logger.debug("Memory 功能已关闭，跳过 MemoryTool 注册")

            # 注册会话内任务与 Plan Mode 元工具
            try:
                from app.agents.tools.task_plan_tools import (
                    EnterPlanModeTool,
                    ExitPlanModeTool,
                    SetTodoList,
                    TaskCreateTool,
                    TaskListTool,
                    TaskUpdateTool,
                )

                registry.register(TaskCreateTool())
                registry.register(TaskUpdateTool())
                registry.register(TaskListTool())
                registry.register(SetTodoList())
                registry.register(EnterPlanModeTool())
                registry.register(ExitPlanModeTool())
                logger.debug("已注册会话 Task / Plan 工具")
            except ValueError:
                logger.debug("会话 Task / Plan 工具已注册，跳过重复注册")
            except Exception:
                logger.warning("注册会话 Task / Plan 工具失败", exc_info=True)

        # 注册 MCP 工具
        mcp_clients: list[Any] = []
        if spec.mcp_configs:
            for config_block in spec.mcp_configs:
                servers = config_block.get("mcpServers", {})
                for server_name, server_cfg in servers.items():
                    mcp_client = None
                    try:
                        from app.services.agent.runtime_backends.aiasys.mcp_client import (
                            MCPClient,
                        )
                        from app.services.agent.runtime_backends.aiasys.tools.mcp_tool import (
                            MCPTool,
                        )
                        from app.services.capability_registry import (
                            get_capability_registry_service,
                        )

                        mcp_client = MCPClient(server_name, server_cfg)
                        await mcp_client.connect()
                        tools = await mcp_client.list_tools()

                        # 根据 enabled_tools 过滤（为空表示全部启用）
                        enabled_tools = server_cfg.get("enabled_tools", [])
                        if enabled_tools:
                            filtered_tools = [t for t in tools if t.name in enabled_tools]
                            skipped = len(tools) - len(filtered_tools)
                            if skipped > 0:
                                logger.info(
                                    "MCP server '%s' 已过滤 %d 个工具，启用 %d 个",
                                    server_name,
                                    skipped,
                                    len(filtered_tools),
                                )
                            tools = filtered_tools

                        get_capability_registry_service().register_mcp_tools(
                            server_name,
                            tools,
                        )
                        for tool_info in tools:
                            mcp_tool = MCPTool(
                                server_name=server_name,
                                tool_name=tool_info.name,
                                description=tool_info.description or "",
                                input_schema=tool_info.inputSchema
                                or {"type": "object", "properties": {}},
                                mcp_client=mcp_client,
                            )
                            try:
                                registry.register(mcp_tool)
                            except ValueError:
                                logger.debug("MCP 工具已注册，跳过: %s", tool_info.name)
                        mcp_clients.append(mcp_client)
                        logger.info(
                            "MCP server '%s' 已注册 %d 个工具",
                            server_name,
                            len(tools),
                        )
                    except Exception as exc:
                        if mcp_client is not None:
                            try:
                                await mcp_client.close()
                            except Exception:
                                logger.debug(
                                    "清理失败的 MCP client 时出错: %s",
                                    server_name,
                                    exc_info=True,
                                )
                        logger.warning(
                            "MCP server '%s' 连接或注册失败，已跳过: %s",
                            server_name,
                            exc,
                        )

        return AiasysRuntimeSession(
            spec,
            client,
            registry,
            mcp_clients=mcp_clients,
        )
