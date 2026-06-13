"""
会话管理 Mixin

负责 runtime session 的创建、复用和配置漂移检查
"""

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from app.core.aiasys_config import load_aiasys_config
from app.core.workspace_path import WorkspacePath
from app.services.agent.models.llm_config import AiasysLlmConfig, LoopControl
from app.services.agent.runtime_backends import (
    AgentRuntimeBackend,
    AgentRuntimeSession,
    RuntimeSessionCreateSpec,
    get_backend,
)
from app.services.agent.utils import _select_preferred_agent_model_id, get_work_dir
from app.services.agent_config import AgentMode, get_agent_config_service
from app.services.history import current_env_id
from app.services.llm.llm_config_service import get_llm_config_service
from app.services.memory import (
    persist_memory_preview_snapshot,
    resolve_session_memory_preview,
)

if TYPE_CHECKING:
    from app.services.agent import AgentService

logger = logging.getLogger(__name__)


async def generate_dynamic_agent_config(*args, **kwargs):
    from app.services.agent.config import (
        generate_dynamic_agent_config as _generate_dynamic_agent_config,
    )

    return await _generate_dynamic_agent_config(*args, **kwargs)


def _extract_runtime_session_id(session: Any) -> str | None:
    """提取 runtime session ID。"""
    session_id = getattr(session, "session_id", None)
    if isinstance(session_id, str) and session_id:
        return session_id
    return None


def _extract_runtime_mcp_configs(session: Any) -> list | None:
    """读取 runtime session 的 mcp_configs。"""
    if hasattr(session, "mcp_configs"):
        return getattr(session, "mcp_configs")
    if hasattr(session, "_mcp_configs"):
        return getattr(session, "_mcp_configs")
    return None


def _compute_llm_config_signature(config: AiasysLlmConfig) -> str:
    payload = {
        "default_model": getattr(config, "default_model", None),
        "providers": getattr(config, "providers", None),
        "models": getattr(config, "models", None),
        "loop_control": getattr(config, "loop_control", None),
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


class SessionMixin:
    """会话管理功能"""

    def __init__(self):
        self._session_locks: dict[str, asyncio.Lock] = {}

    async def _get_session_lock(self: "AgentService", session_key: str) -> asyncio.Lock:
        """获取会话级别的锁，用于串行化同一会话的请求"""
        if session_key not in self._session_locks:
            self._session_locks[session_key] = asyncio.Lock()
        return self._session_locks[session_key]

    def _get_runtime_backend(self: "AgentService") -> AgentRuntimeBackend:
        """获取当前 AIASys 绑定的 runtime backend。"""
        runtime_backend = getattr(self, "_runtime_backend", None)
        if runtime_backend is None:
            runtime_backend = get_backend()
            self._runtime_backend = runtime_backend
        return runtime_backend

    async def _get_or_create_session(
        self: "AgentService",
        user_id: str,
        session_id: str,
        config: AiasysLlmConfig,
        title: Optional[str] = None,
        sandbox_mode: Optional[str] = None,
        llm_config_signature: Optional[str] = None,
    ) -> AgentRuntimeSession:
        """获取已有会话或创建新会话"""
        return await self._do_get_or_create_session(
            user_id,
            session_id,
            config,
            title,
            sandbox_mode,
            llm_config_signature,
        )

    async def _do_get_or_create_session(
        self: "AgentService",
        user_id: str,
        session_id: str,
        config: AiasysLlmConfig,
        title: Optional[str] = None,
        sandbox_mode: Optional[str] = None,
        llm_config_signature: Optional[str] = None,
    ) -> AgentRuntimeSession:
        """实际获取或创建会话的逻辑"""
        # 延迟导入，避免 `config_projection -> app.services.agent.* ->
        # SessionMixin -> config_projection` 的循环导入。
        from app.services.session.config_projection import (
            compute_agent_config_version,
            compute_capability_snapshot_version,
            ensure_workspace_layout,
            read_runtime_config_state,
            write_runtime_config_state,
        )

        work_dir = get_work_dir(user_id, session_id)
        workspace_path = Path(str(work_dir))
        ensure_workspace_layout(workspace_path)
        session_key = f"{user_id}/{session_id}"

        # 当前工作目录自己的 Skill 包目录：.../skills/
        workspace_skill_dir = workspace_path / ".aiasys" / "skills"
        skills_dir = (
            WorkspacePath(str(workspace_skill_dir)) if workspace_skill_dir.exists() else None
        )

        resolved_env_id = current_env_id.get()

        # 获取会话的 sandbox_mode（如果会话已创建）
        session_metadata = self._session_manager.get_session(session_id, user_id)
        # 优先使用传入的参数（用于新会话），否则使用会话元数据中的值
        if sandbox_mode is None:
            sandbox_mode = session_metadata.sandbox_mode if session_metadata else None
        collaboration_policy = (
            getattr(session_metadata, "collaboration_policy", None)
            if session_metadata is not None
            else None
        )
        collaboration_policy_payload = (
            collaboration_policy.model_dump()
            if hasattr(collaboration_policy, "model_dump")
            else collaboration_policy
            if isinstance(collaboration_policy, dict)
            else None
        )
        try:
            workspace_id_for_policy = (
                getattr(session_metadata, "workspace_id", None)
                if session_metadata is not None
                else None
            )
            if not workspace_id_for_policy:
                from app.services.workspace_registry import get_workspace_registry_service

                workspace_id_for_policy = (
                    get_workspace_registry_service().find_workspace_id_by_session_id(
                        user_id,
                        session_id,
                    )
                )
            if workspace_id_for_policy:
                from app.services.agent.subagent_catalog import (
                    resolve_workspace_collaboration_runtime_policy,
                )

                collaboration_policy_payload = resolve_workspace_collaboration_runtime_policy(
                    user_id=user_id,
                    workspace_id=workspace_id_for_policy,
                )
        except Exception:
            logger.debug(
                "读取工作区协作默认策略失败，继续使用会话兼容策略: session=%s",
                session_id,
                exc_info=True,
            )

        agent_type = "analysis"

        # 生成动态 agent 配置（根据当前执行环境渲染提示词模板）
        # resume/create 必须使用同一份配置来源，避免恢复与新建行为不一致。
        # 支持用户自定义配置覆盖系统默认配置。
        dynamic_agent_path = await generate_dynamic_agent_config(
            session_id=session_id,
            user_id=user_id,
            sandbox_mode=sandbox_mode,
            agent_type=agent_type,
        )
        current_agent_config_version = await compute_agent_config_version(
            user_id=user_id,
            session_id=session_id,
            sandbox_mode=sandbox_mode,
            execution_policy=(
                getattr(session_metadata, "execution_policy", None)
                if session_metadata is not None
                else None
            ),
        )
        current_capability_snapshot_version = compute_capability_snapshot_version(workspace_path)
        logger.info(
            f"使用动态 agent 配置: {dynamic_agent_path.name}, sandbox_mode={sandbox_mode}, agent_type={agent_type}"
        )

        # ===== 加载 MCP 配置 =====
        try:
            from app.services.llm.mcp_session_service import get_mcp_session_service

            mcp_service = get_mcp_session_service()
            mcp_configs = mcp_service.get_sdk_config(user_id, session_id)
            if mcp_configs:
                logger.info(f"加载 MCP 配置: {len(mcp_configs)} 个 server")
            else:
                logger.debug("没有可用的 MCP 配置")
                mcp_configs = None
        except Exception as e:
            logger.warning(f"加载 MCP 配置失败（继续执行）: {e}")
            mcp_configs = None
        # ========================

        # 检查是否需要重建 Session（MCP 配置变化时）
        # 当前 runtime backend 不支持动态 MCP / Skill / Agent 配置热更新，必须重建 Session
        force_recreate = False
        existing_session = self._active_sessions.get(session_key)
        runtime_config_state = read_runtime_config_state(workspace_path)
        applied_agent_config_version = runtime_config_state.get("applied_agent_config_version")
        applied_capability_snapshot_version = runtime_config_state.get(
            "applied_capability_snapshot_version"
        )
        applied_memory_snapshot_version = runtime_config_state.get(
            "applied_memory_snapshot_version"
        )
        current_llm_config_signature = llm_config_signature or _compute_llm_config_signature(config)
        current_memory_preview = resolve_session_memory_preview(
            session_dir=workspace_path,
            user_id=user_id,
            session_id=session_id,
        )
        has_current_memory = bool(current_memory_preview.rendered_markdown.strip())
        current_memory_snapshot_version = (
            current_memory_preview.version if has_current_memory else None
        )
        applied_llm_config_signature = runtime_config_state.get("applied_llm_config_signature")

        if existing_session:
            # 比较 MCP 配置
            old_configs = _extract_runtime_mcp_configs(existing_session)
            if old_configs != mcp_configs:
                logger.info("MCP 配置变化，需要重建 Session")
                force_recreate = True
        if (
            existing_session
            and applied_agent_config_version
            and applied_agent_config_version != current_agent_config_version
        ):
            logger.info("Agent 配置版本变化，需要重建 Session")
            force_recreate = True
        if (
            existing_session
            and applied_capability_snapshot_version
            and applied_capability_snapshot_version != current_capability_snapshot_version
        ):
            logger.info("能力快照版本变化，需要重建 Session")
            force_recreate = True
        if (
            existing_session
            and applied_memory_snapshot_version != current_memory_snapshot_version
            and (
                applied_memory_snapshot_version is not None
                or current_memory_snapshot_version is not None
            )
        ):
            logger.info("Memory 快照版本变化，需要重建 Session")
            force_recreate = True
        if (
            existing_session
            and applied_llm_config_signature
            and applied_llm_config_signature != current_llm_config_signature
        ):
            logger.info("LLM 配置签名变化，需要重建 Session")
            force_recreate = True

        if existing_session and force_recreate:
            logger.info("运行时配置已变化，关闭旧 Session: %s", session_id)
            try:
                await existing_session.close()
            except Exception as exc:
                logger.warning("关闭旧 Session 失败（继续重建）: %s", exc)
            self._active_sessions.pop(session_key, None)
            existing_session = None

        if existing_session and not force_recreate:
            # 检查 Session 是否仍然有效
            try:
                # 尝试访问 runtime session ID 来验证有效性
                runtime_session_id = _extract_runtime_session_id(existing_session)
                if not runtime_session_id:
                    raise ValueError("runtime session 缺少 session_id")
                # 复用时刷新上下文 token 计数，避免显示过期的启发式估算
                refresh_fn = getattr(
                    existing_session, "refresh_context_tokens_from_metadata", None
                )
                if callable(refresh_fn):
                    refresh_fn()
                logger.debug(f"复用已有 Session: {session_id}")
                return existing_session
            except Exception:
                logger.info(f"Session 无效，重新创建: {session_id}")
                self._active_sessions.pop(session_key, None)

        # 创建新 Session
        logger.info(f"创建新 Session: {session_id}")

        # 保存会话元数据（用于后续恢复）
        try:
            agent_type = "analysis"
            self._session_manager.create_session(
                session_id=session_id,
                user_id=user_id,
                title=title,
                env_id=resolved_env_id,
                sandbox_mode=sandbox_mode,
                agent_type=agent_type,
            )
        except Exception as e:
            logger.warning(f"创建会话元数据失败（不影响执行）: {e}")

        runtime_backend = self._get_runtime_backend()

        # 读取 memory 开关
        memory_enabled = True
        try:
            from app.core.aiasys_config import load_aiasys_config

            toml_cfg = load_aiasys_config(user_id=user_id)
            memory_enabled = toml_cfg.memory.enabled
        except Exception:
            logger.debug("读取 memory 开关失败，默认启用", exc_info=True)

        # 读取会话级授权模式配置（默认 full_auto 保持现有行为，可通过 session_metadata 覆盖）
        authorization_mode = (
            session_metadata.authorization_mode
            if session_metadata is not None and session_metadata.authorization_mode
            else "full_auto"
        )

        session = await runtime_backend.create_session(
            RuntimeSessionCreateSpec(
                work_dir=work_dir,
                session_id=session_id,
                user_id=user_id,
                config=config,
                agent_file=dynamic_agent_path,
                skills_dir=skills_dir,
                yolo=(authorization_mode == "full_auto"),
                authorization_mode=authorization_mode,
                mcp_configs=mcp_configs,
                collaboration_policy=collaboration_policy_payload,
                memory_enabled=memory_enabled,
            )
        )
        persisted_memory_snapshot = persist_memory_preview_snapshot(
            session_dir=workspace_path,
            user_id=user_id,
            session_id=session_id,
            preview=current_memory_preview,
        )
        write_runtime_config_state(
            workspace_path,
            applied_agent_config_version=current_agent_config_version,
            applied_capability_snapshot_version=current_capability_snapshot_version,
            applied_llm_config_signature=current_llm_config_signature,
            applied_memory_snapshot_version=(
                persisted_memory_snapshot.version if persisted_memory_snapshot is not None else None
            ),
            applied_memory_snapshot_hash=(
                persisted_memory_snapshot.snapshot_hash
                if persisted_memory_snapshot is not None
                else None
            ),
        )
        return session

    def _get_config(
        self: "AgentService",
        model: Optional[str],
        user_id: str,
        model_id: Optional[str] = None,
        session_id: Optional[str] = None,
        thinking_enabled: Optional[bool] = None,
        thinking_effort: Optional[str] = None,
    ) -> AiasysLlmConfig:
        """
        获取 LLM 配置

        优先使用动态配置（用户配置 > 系统配置），如果没有则返回空配置，
        让执行层给出明确错误。
        """
        try:
            llm_service = get_llm_config_service()
            full_config = llm_service.get_full_config(user_id)
            runtime_config = get_agent_config_service().get_effective_runtime_config(
                mode=AgentMode.ANALYSIS,
                user_id=user_id,
                session_id=session_id,
            )
            loop_control = LoopControl(**runtime_config.model_dump())

            # 合并用户级 config.toml 增量配置
            toml_cfg = load_aiasys_config(user_id=user_id)
            if toml_cfg.compaction.tool_snip_max_chars > 0:
                loop_control.tool_snip_max_chars = toml_cfg.compaction.tool_snip_max_chars

            if full_config.get("providers") and full_config.get("models"):
                providers = full_config["providers"]
                models = {
                    model_id: model_cfg
                    for model_id, model_cfg in full_config["models"].items()
                    if str(model_cfg.get("model_type") or "chat") == "chat"
                }

                selected_model_id = None

                if model_id and model_id in models:
                    selected_model_id = model_id
                    logger.info("使用指定模型 ID: %s", selected_model_id)
                elif model:
                    for mid, mcfg in models.items():
                        if mcfg.get("model") == model:
                            selected_model_id = mid
                            logger.info("通过模型名称匹配到模型 ID: %s", selected_model_id)
                            break

                if not selected_model_id and session_id:
                    from app.services.llm.model_selection_service import (
                        get_model_selection_service,
                    )

                    resolved_model_id = get_model_selection_service().resolve_effective_model_id(
                        user_id=user_id,
                        session_id=session_id,
                    )
                    if resolved_model_id and resolved_model_id in models:
                        selected_model_id = resolved_model_id
                        logger.info(
                            "按会话 > 工作区 > 全局链路解析模型 ID: %s",
                            selected_model_id,
                        )

                if not selected_model_id:
                    selected_model_id = _select_preferred_agent_model_id(
                        models=models,
                        providers=providers,
                        configured_default_model=full_config.get("default_model"),
                    )
                    logger.info("Agent 自动选择模型 ID: %s", selected_model_id)

                if selected_model_id not in models and models:
                    logger.warning(
                        "选中的模型 %s 不存在，回退到第一个可用模型",
                        selected_model_id,
                    )
                    selected_model_id = next(iter(models))

                used_providers = {
                    mcfg.get("provider") for mcfg in models.values() if mcfg.get("provider")
                }
                filtered_providers = {
                    pid: pcfg for pid, pcfg in providers.items() if pid in used_providers
                }

                for mcfg in models.values():
                    provider_id = mcfg.get("provider")
                    provider_cfg = filtered_providers.get(provider_id, {})
                    if provider_cfg.get("type") == "openai_responses":
                        caps = mcfg.get("capabilities", [])
                        if isinstance(caps, list) and "always_thinking" not in caps:
                            mcfg["capabilities"] = [*caps, "always_thinking"]

                # 根据前端传入的 thinking 配置动态覆盖选中模型的 reasoning 设置
                if thinking_enabled is not None and selected_model_id:
                    mcfg = models.get(selected_model_id)
                    if mcfg is not None:
                        caps = mcfg.get("capabilities", [])
                        if not isinstance(caps, list):
                            caps = list(caps) if isinstance(caps, (set, tuple)) else [str(caps)]
                        if thinking_enabled:
                            if "thinking" not in caps:
                                caps = [*caps, "thinking"]
                            mcfg["capabilities"] = caps
                            if thinking_effort is not None:
                                mcfg["thinking_effort"] = thinking_effort
                        else:
                            mcfg["capabilities"] = [
                                c for c in caps if c not in ("thinking", "always_thinking")
                            ]
                            mcfg.pop("thinking_effort", None)

                return AiasysLlmConfig(
                    default_model=selected_model_id or "",
                    default_thinking=False,
                    providers=filtered_providers,
                    models=models,
                    loop_control=loop_control,
                    task_models=toml_cfg.llm.task_models,
                )

        except Exception as e:
            logger.error(f"加载 LLM 动态配置失败: {e}")

        # 动态配置为空（启动同步可能失败），返回空 Config 让 runtime 报明确错误。
        logger.error("LLM 动态配置为空，请检查 config.toml 和启动日志")
        return AiasysLlmConfig(
            default_model="",
            default_thinking=False,
            providers={},
            models={},
            loop_control=LoopControl(),
        )
