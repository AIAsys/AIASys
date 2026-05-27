"""
Agent 配置服务

提供用户级 Agent 配置的读取、合并、保存功能。
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from app.core.config import WORKSPACE_DIR
from app.services.agent.models.llm_config import LoopControl
from app.services.agent.system_presets import (
    build_system_config_from_preset,
    resolve_system_agent_preset_from_path,
)
from app.services.agent_config.models import (
    AgentMode,
    LoopControlOverrides,
    MergedAgentConfig,
    ModeOverrides,
    PromptConfig,
    ResolvedLoopControlConfig,
    ToolOverride,
    ToolsConfig,
    UserAgentConfig,
    get_system_default_config_path,
)
from app.services.agent_context_documents import (
    ensure_user_soul_file,
    read_user_soul_text,
    read_workspace_project_profile_text,
)
from app.services.runtime_tooling import (
    canonicalize_runtime_tool_name,
    probe_runtime_tool,
)

logger = logging.getLogger(__name__)


def _is_supported_tool(tool_name: str) -> bool:
    """检查工具标识在当前运行时中是否可导入。"""
    return probe_runtime_tool(canonicalize_runtime_tool_name(tool_name)).available


def _filter_supported_tools(tool_names: List[str]) -> List[str]:
    """过滤当前运行时无法加载的工具，避免旧配置打断会话启动。"""
    filtered: List[str] = []
    seen: set[str] = set()
    for tool_name in tool_names:
        canonical_tool_name = canonicalize_runtime_tool_name(tool_name)
        availability = probe_runtime_tool(canonical_tool_name)
        if availability.available:
            if canonical_tool_name not in seen:
                filtered.append(canonical_tool_name)
                seen.add(canonical_tool_name)
        else:
            logger.warning(
                "忽略不可用工具: %s (%s)",
                tool_name,
                availability.reason,
            )
    return filtered


ToolStrategyName = Literal["auto", "search", "deferred", "passthrough"]
VALID_TOOL_STRATEGIES: set[str] = {"auto", "search", "deferred", "passthrough"}


def _canonicalize_tool_name_list(tool_names: List[str]) -> List[str]:
    """把工具列表投影为当前 runtime 视图，同时保持顺序并去重。"""
    return list(
        dict.fromkeys(
            canonicalize_runtime_tool_name(str(tool_name or "").strip())
            for tool_name in tool_names
            if str(tool_name or "").strip()
        )
    )


def _normalize_tool_strategy(value: str | None) -> ToolStrategyName:
    strategy = str(value or "auto").strip().lower()
    if strategy in VALID_TOOL_STRATEGIES:
        return strategy  # type: ignore[return-value]
    return "auto"


def _project_tools_config_for_runtime(tools_config: ToolsConfig | None) -> ToolsConfig | None:
    """把持久化里的工具配置映射到当前 runtime 的 canonical 工具名。"""
    if tools_config is None:
        return None

    tool_overrides = {
        canonicalize_runtime_tool_name(tool_name): ToolOverride(
            **{
                **override.model_dump(),
                "name": canonicalize_runtime_tool_name(tool_name),
            }
        )
        for tool_name, override in tools_config.tool_overrides.items()
    }

    return ToolsConfig(
        selection_mode=tools_config.selection_mode,
        enabled_tools=_canonicalize_tool_name_list(tools_config.enabled_tools),
        disabled_tools=_canonicalize_tool_name_list(tools_config.disabled_tools),
        extra_tools=_canonicalize_tool_name_list(tools_config.extra_tools),
        tool_overrides=tool_overrides,
        tool_strategy=_normalize_tool_strategy(tools_config.tool_strategy),
    )


class AgentConfigService:
    """
    Agent 配置服务

    管理用户级 Agent 配置的读取、合并和持久化。
    """

    # 目录和文件常量
    AGENT_CONFIG_DIR = ".aiasys/agent_config"
    USER_CONFIG_FILE = "user_config.json"
    PROMPT_OVERRIDE_FILE = "prompt_override.md"
    TOOLS_CONFIG_FILE = "tools.json"
    RUNTIME_CONFIG_FILE = "runtime.json"

    def __init__(self, workspace_root: Optional[Path] = None):
        """
        初始化配置服务

        Args:
            workspace_root: 工作区根目录，默认使用配置中的 WORKSPACE_DIR
        """
        self.workspace_root = Path(workspace_root) if workspace_root else Path(WORKSPACE_DIR)

    def _get_user_config_dir(self, user_id: str) -> Path:
        """获取用户配置目录路径"""
        return self.workspace_root / user_id / "global_workspace" / self.AGENT_CONFIG_DIR

    def _get_session_root_dir(self, user_id: str, session_id: str) -> Path:
        """获取会话根目录路径"""
        return self.workspace_root / user_id / session_id

    def _get_session_config_dir(self, user_id: str, session_id: str) -> Path:
        """获取会话级配置目录路径"""
        return self._get_session_root_dir(user_id, session_id) / self.AGENT_CONFIG_DIR

    def _get_workspace_config_dir(self, user_id: str, workspace_id: str) -> Path:
        """获取工作区级配置目录路径"""
        return self.workspace_root / user_id / workspace_id / self.AGENT_CONFIG_DIR

    def _get_workspace_mode_config_dir(
        self,
        user_id: str,
        workspace_id: str,
        mode: str,
    ) -> Path:
        """获取工作区级指定模式的配置目录"""
        return self._get_workspace_config_dir(user_id, workspace_id) / mode

    def _get_mode_config_dir(self, user_id: str, mode: str) -> Path:
        """获取指定模式的配置目录"""
        return self._get_user_config_dir(user_id) / mode

    def _get_session_mode_config_dir(
        self,
        user_id: str,
        session_id: str,
        mode: str,
    ) -> Path:
        """获取会话级指定模式的配置目录"""
        return self._get_session_config_dir(user_id, session_id) / mode

    def _get_user_config_index_path(self, user_id: str) -> Path:
        """获取用户配置索引文件路径"""
        return self._get_user_config_dir(user_id) / self.USER_CONFIG_FILE

    def _load_mapping_file(self, path: Path) -> dict:
        """读取 JSON/YAML 映射文件，统一返回 dict。"""
        if not path.exists():
            return {}

        raw_text = path.read_text(encoding="utf-8")
        if not raw_text.strip():
            return {}

        if path.suffix == ".json":
            data = json.loads(raw_text)
        else:
            data = tomllib.loads(raw_text)
        return data if isinstance(data, dict) else {}

    def _write_json_file(self, path: Path, payload: dict) -> None:
        """统一把结构化配置写为 JSON。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _get_prompt_override_path(self, user_id: str, mode: str) -> Path:
        """获取提示词覆盖文件路径"""
        return self._get_mode_config_dir(user_id, mode) / self.PROMPT_OVERRIDE_FILE

    def _get_tools_config_path(self, user_id: str, mode: str) -> Path:
        """获取工具配置文件路径"""
        return self._get_mode_config_dir(user_id, mode) / self.TOOLS_CONFIG_FILE

    def _get_runtime_config_path(self, user_id: str, mode: str) -> Path:
        """获取运行时配置文件路径。"""
        return self._get_mode_config_dir(user_id, mode) / self.RUNTIME_CONFIG_FILE

    def _get_session_prompt_override_path(
        self,
        user_id: str,
        session_id: str,
        mode: str,
    ) -> Path:
        """获取会话级提示词覆盖文件路径"""
        return (
            self._get_session_mode_config_dir(user_id, session_id, mode) / self.PROMPT_OVERRIDE_FILE
        )

    def _get_session_tools_config_path(
        self,
        user_id: str,
        session_id: str,
        mode: str,
    ) -> Path:
        """获取会话级工具配置文件路径"""
        return self._get_session_mode_config_dir(user_id, session_id, mode) / self.TOOLS_CONFIG_FILE

    def _get_session_runtime_config_path(
        self,
        user_id: str,
        session_id: str,
        mode: str,
    ) -> Path:
        """获取会话级运行时配置文件路径。"""
        return (
            self._get_session_mode_config_dir(user_id, session_id, mode) / self.RUNTIME_CONFIG_FILE
        )

    def _get_workspace_prompt_override_path(
        self,
        user_id: str,
        workspace_id: str,
        mode: str,
    ) -> Path:
        """获取工作区级提示词覆盖文件路径"""
        return (
            self._get_workspace_mode_config_dir(user_id, workspace_id, mode)
            / self.PROMPT_OVERRIDE_FILE
        )

    def _get_workspace_tools_config_path(
        self,
        user_id: str,
        workspace_id: str,
        mode: str,
    ) -> Path:
        """获取工作区级工具配置文件路径"""
        return (
            self._get_workspace_mode_config_dir(user_id, workspace_id, mode)
            / self.TOOLS_CONFIG_FILE
        )

    def _get_workspace_runtime_config_path(
        self,
        user_id: str,
        workspace_id: str,
        mode: str,
    ) -> Path:
        """获取工作区级运行时配置文件路径。"""
        return (
            self._get_workspace_mode_config_dir(user_id, workspace_id, mode)
            / self.RUNTIME_CONFIG_FILE
        )

    def _ensure_config_dir_exists(self, user_id: str) -> Path:
        """
        确保用户配置目录存在，不存在则创建

        Returns:
            用户配置目录路径
        """
        config_dir = self._get_user_config_dir(user_id)
        if not config_dir.exists():
            config_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"创建用户 Agent 配置目录: {config_dir}")
        ensure_user_soul_file(self.workspace_root, user_id)
        return config_dir

    def _ensure_session_config_dir_exists(self, user_id: str, session_id: str) -> Path:
        """确保会话级配置目录存在"""
        config_dir = self._get_session_config_dir(user_id, session_id)
        if not config_dir.exists():
            config_dir.mkdir(parents=True, exist_ok=True)
            logger.info("创建会话 Agent 配置目录: %s", config_dir)
        return config_dir

    def _ensure_workspace_config_dir_exists(
        self,
        user_id: str,
        workspace_id: str,
    ) -> Path:
        """确保工作区级配置目录存在"""
        config_dir = self._get_workspace_config_dir(user_id, workspace_id)
        if not config_dir.exists():
            config_dir.mkdir(parents=True, exist_ok=True)
            logger.info("创建工作区 Agent 配置目录: %s", config_dir)
        return config_dir

    def _load_runtime_override_from_path(
        self,
        runtime_path: Path,
    ) -> LoopControlOverrides | None:
        """读取运行时覆盖配置。"""
        if not runtime_path.exists():
            return None

        try:
            runtime_data = self._load_mapping_file(runtime_path)
            if not runtime_data:
                return None
            runtime_override = LoopControlOverrides(**runtime_data)
            return runtime_override if runtime_override.has_values() else None
        except Exception as exc:
            logger.warning("读取运行时配置失败: path=%s, error=%s", runtime_path, exc)
            return None

    def _has_mode_local_config(self, mode_dir: Path) -> bool:
        """判断当前层是否存在任意本地覆盖。"""
        prompt_path = mode_dir / self.PROMPT_OVERRIDE_FILE
        if prompt_path.exists():
            try:
                if prompt_path.read_text(encoding="utf-8").strip():
                    return True
            except Exception:
                return True

        tools_path = mode_dir / self.TOOLS_CONFIG_FILE
        if tools_path.exists():
            try:
                tools_data = self._load_mapping_file(tools_path)
                if tools_data:
                    return True
            except Exception:
                return True

        runtime_path = mode_dir / self.RUNTIME_CONFIG_FILE
        if self._load_runtime_override_from_path(runtime_path) is not None:
            return True

        return False

    async def get_user_config(self, user_id: str) -> Optional[UserAgentConfig]:
        """
        获取完整用户配置

        读取用户的所有配置，包括提示词和工具配置。

        Args:
            user_id: 用户 ID

        Returns:
            用户配置，如果不存在返回 None
        """
        config_dir = self._ensure_config_dir_exists(user_id)
        if not config_dir.exists():
            return None

        try:
            config = UserAgentConfig()

            # 读取 analysis 模式配置
            analysis_config = self._load_mode_config_sync(user_id, AgentMode.ANALYSIS)
            if analysis_config:
                config.analysis = analysis_config

            # 读取索引文件获取更新时间
            index_path = self._get_user_config_index_path(user_id)
            if index_path.exists():
                index_data = self._load_mapping_file(index_path)
                if index_data:
                    config.updated_at = index_data.get("updated_at")

            return config

        except Exception as e:
            logger.error(f"读取用户配置失败: user={user_id}, error={e}")
            return None

    def _load_mode_config_sync(
        self,
        user_id: str,
        mode: AgentMode,
    ) -> Optional[ModeOverrides]:
        """
        加载指定模式的配置

        Args:
            user_id: 用户 ID
            mode: Agent 模式

        Returns:
            模式配置，如果不存在返回 None
        """
        mode_dir = self._get_mode_config_dir(user_id, mode.value)
        index_path = self._get_user_config_index_path(user_id)
        return self._load_mode_config_from_dir_sync(mode_dir, index_path=index_path)

    def _load_mode_config_from_dir_sync(
        self,
        mode_dir: Path,
        *,
        index_path: Optional[Path] = None,
    ) -> Optional[ModeOverrides]:
        """从指定目录加载模式配置。"""
        if not mode_dir.exists():
            return None

        overrides = ModeOverrides()
        has_config = False

        # 读取提示词覆盖
        prompt_path = mode_dir / self.PROMPT_OVERRIDE_FILE
        if prompt_path.exists():
            content = prompt_path.read_text(encoding="utf-8")
            if content.strip():
                overrides.prompt = PromptConfig(content=content)
                has_config = True

        # 读取工具配置
        tools_path = mode_dir / self.TOOLS_CONFIG_FILE
        if tools_path.exists():
            try:
                tools_data = self._load_mapping_file(tools_path)
                if tools_data:
                    overrides.tools = _project_tools_config_for_runtime(ToolsConfig(**tools_data))
                    has_config = True
            except Exception as e:
                logger.warning("读取工具配置失败: dir=%s, error=%s", mode_dir, e)

        runtime_override = self._load_runtime_override_from_path(
            mode_dir / self.RUNTIME_CONFIG_FILE
        )
        if runtime_override is not None:
            overrides.runtime = runtime_override
            has_config = True

        # 读取索引文件检查是否启用
        if index_path and index_path.exists():
            try:
                index_data = self._load_mapping_file(index_path)
                if index_data and "modes" in index_data:
                    mode_key = mode_dir.name
                    mode_index = index_data["modes"].get(mode_key, {})
                    overrides.enabled = mode_index.get("enabled", has_config)
            except Exception:
                overrides.enabled = has_config
        else:
            overrides.enabled = has_config

        return overrides if has_config else None

    async def _load_mode_config(
        self,
        user_id: str,
        mode: AgentMode,
    ) -> Optional[ModeOverrides]:
        return self._load_mode_config_sync(user_id, mode)

    async def _load_mode_config_from_dir(
        self,
        mode_dir: Path,
        *,
        index_path: Optional[Path] = None,
    ) -> Optional[ModeOverrides]:
        return self._load_mode_config_from_dir_sync(mode_dir, index_path=index_path)

    async def get_session_override(
        self,
        mode: AgentMode,
        user_id: str,
        session_id: str,
    ) -> Optional[ModeOverrides]:
        """读取会话级覆盖配置。"""
        mode_dir = self._get_session_mode_config_dir(user_id, session_id, mode.value)
        return self._load_mode_config_from_dir_sync(mode_dir)

    async def get_workspace_override(
        self,
        mode: AgentMode,
        user_id: str,
        workspace_id: str,
    ) -> Optional[ModeOverrides]:
        """读取工作区级覆盖配置。"""
        mode_dir = self._get_workspace_mode_config_dir(user_id, workspace_id, mode.value)
        return self._load_mode_config_from_dir_sync(mode_dir)

    async def get_workspace_editor_config(
        self,
        mode: AgentMode,
        user_id: str,
        workspace_id: str,
        sandbox_mode: Optional[str] = None,
    ) -> dict[str, object]:
        """获取工作区设置编辑器所需的有效配置。"""
        workspace_override = await self.get_workspace_override(mode, user_id, workspace_id)
        merged = await self.get_merged_config(
            mode=mode,
            user_id=user_id,
            sandbox_mode=sandbox_mode,
            workspace_id=workspace_id,
        )

        source = merged.prompt_source
        prompt_content = (
            workspace_override.prompt.content
            if workspace_override is not None
            and workspace_override.prompt is not None
            and workspace_override.prompt.content
            else merged.system_prompt
        )
        if source == "system_default" and not prompt_content:
            system_config = self._load_system_config(
                get_system_default_config_path(mode, sandbox_mode)
            )
            prompt_content, source = self._merge_prompt(
                system_config=system_config,
                user_mode_overrides=None,
                workspace_mode_overrides=None,
                session_mode_overrides=None,
                mode=mode,
                user_id=user_id,
            )

        return {
            "mode": mode.value,
            "enabled": True,
            "prompt_content": prompt_content,
            "enabled_tools": list(merged.enabled_tools),
            "disabled_tools": list(merged.disabled_tools),
            "tool_strategy": merged.tool_strategy,
            "reserved_context_size": merged.runtime_config.reserved_context_size,
            "compaction_trigger_ratio": merged.runtime_config.compaction_trigger_ratio,
            "source": source,
            "runtime_source": merged.runtime_source,
            "has_local_override": workspace_override is not None,
            "has_local_runtime_override": bool(
                workspace_override
                and workspace_override.runtime
                and workspace_override.runtime.has_values()
            ),
        }

    async def get_merged_config(
        self,
        mode: AgentMode,
        user_id: str,
        sandbox_mode: Optional[str] = None,
        session_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        base_config_path: Optional[Path] = None,
        rendered_system_prompt: Optional[str] = None,
    ) -> MergedAgentConfig:
        """
        获取合并后的配置

        将系统默认配置和用户自定义配置合并，生成最终配置。

        Args:
            mode: Agent 模式
            user_id: 用户 ID
            sandbox_mode: 沙盒模式（仅对 analysis 有效）

        Returns:
            合并后的配置
        """
        # 读取系统默认配置
        system_config_path = base_config_path or get_system_default_config_path(
            mode,
            sandbox_mode,
        )
        system_config = self._load_system_config(system_config_path)
        system_preset = resolve_system_agent_preset_from_path(system_config_path)

        # 读取用户配置
        user_config = await self.get_user_config(user_id)
        user_mode_overrides = None
        session_mode_overrides = None

        if user_config:
            if mode == AgentMode.ANALYSIS and user_config.analysis:
                user_mode_overrides = user_config.analysis

        workspace_mode_overrides = None
        if workspace_id:
            workspace_mode_overrides = await self.get_workspace_override(
                mode=mode,
                user_id=user_id,
                workspace_id=workspace_id,
            )

        if session_id:
            session_mode_overrides = await self.get_session_override(
                mode=mode,
                user_id=user_id,
                session_id=session_id,
            )

        workspace_profile_text = self._load_workspace_project_profile_text(
            user_id=user_id,
            workspace_id=workspace_id,
            session_id=session_id,
        )

        # 合并提示词
        system_prompt, prompt_source = self._merge_prompt(
            system_config=system_config,
            user_mode_overrides=user_mode_overrides,
            workspace_mode_overrides=workspace_mode_overrides,
            session_mode_overrides=session_mode_overrides,
            mode=mode,
            user_id=user_id,
            workspace_profile_text=workspace_profile_text,
            base_config_path=system_config_path,
            rendered_system_prompt=rendered_system_prompt,
        )

        # 合并工具配置
        enabled_tools, disabled_tools, tool_overrides, tool_strategy = self._merge_tools(
            system_config=system_config,
            mode_overrides_chain=[
                override
                for override in [
                    user_mode_overrides,
                    workspace_mode_overrides,
                    session_mode_overrides,
                ]
                if override is not None
            ],
        )
        runtime_config, runtime_source = self._merge_runtime_config(
            system_config=system_config,
            user_mode_overrides=user_mode_overrides,
            workspace_mode_overrides=workspace_mode_overrides,
            session_mode_overrides=session_mode_overrides,
        )
        model_name, model_params, model_source = self._merge_model_config(
            system_config=system_config,
            user_mode_overrides=user_mode_overrides,
            workspace_mode_overrides=workspace_mode_overrides,
            session_mode_overrides=session_mode_overrides,
        )

        # 构建合并结果
        is_customized = any(
            bool(override and override.enabled)
            for override in [
                user_mode_overrides,
                workspace_mode_overrides,
                session_mode_overrides,
            ]
        )

        return MergedAgentConfig(
            mode=mode,
            system_prompt=system_prompt,
            prompt_source=prompt_source,
            enabled_tools=enabled_tools,
            disabled_tools=disabled_tools,
            tool_overrides=tool_overrides,
            tool_strategy=tool_strategy,
            model=model_name,
            model_params=model_params,
            runtime_config=runtime_config,
            runtime_source=runtime_source,
            is_customized=is_customized,
            base_config_path=(
                system_preset.config_ref if system_preset is not None else str(system_config_path)
            ),
        )

    def _load_system_config(self, config_path: Path) -> dict:
        """
        加载系统默认配置

        Args:
            config_path: 配置文件路径

        Returns:
            配置字典
        """
        try:
            preset = resolve_system_agent_preset_from_path(config_path)
            if preset is not None:
                return build_system_config_from_preset(preset)
            if config_path.exists():
                return tomllib.loads(config_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            logger.error(f"加载系统配置失败: {config_path}, error={e}")

        return {}

    def _resolve_system_loop_control(self, system_config: dict) -> LoopControl:
        """从系统配置中提取 loop_control 基线；没有则退回运行时默认值。"""
        raw_loop_control = system_config.get("loop_control")
        if not isinstance(raw_loop_control, dict):
            return LoopControl()

        try:
            return LoopControl(**raw_loop_control)
        except Exception as exc:
            logger.warning("系统 loop_control 配置无效，回退到默认值: error=%s", exc)
            return LoopControl()

    def _merge_runtime_config(
        self,
        *,
        system_config: dict,
        user_mode_overrides: ModeOverrides | None,
        workspace_mode_overrides: ModeOverrides | None = None,
        session_mode_overrides: ModeOverrides | None,
    ) -> tuple[ResolvedLoopControlConfig, str]:
        """合并 loop_control 运行时配置。"""
        resolved = self._resolve_system_loop_control(system_config)
        source = "system_default"

        if (
            user_mode_overrides is not None
            and user_mode_overrides.runtime is not None
            and user_mode_overrides.runtime.has_values()
        ):
            resolved = user_mode_overrides.runtime.apply_to(resolved)
            source = "user_default"

        if (
            workspace_mode_overrides is not None
            and workspace_mode_overrides.runtime is not None
            and workspace_mode_overrides.runtime.has_values()
        ):
            resolved = workspace_mode_overrides.runtime.apply_to(resolved)
            source = "workspace_override"

        if (
            session_mode_overrides is not None
            and session_mode_overrides.runtime is not None
            and session_mode_overrides.runtime.has_values()
        ):
            resolved = session_mode_overrides.runtime.apply_to(resolved)
            source = "session_override"

        return ResolvedLoopControlConfig.from_loop_control(resolved), source

    def _merge_model_config(
        self,
        *,
        system_config: dict,
        user_mode_overrides: ModeOverrides | None,
        workspace_mode_overrides: ModeOverrides | None = None,
        session_mode_overrides: ModeOverrides | None,
    ) -> tuple[str | None, dict | None, str]:
        """合并模型配置。session_override > workspace_override > user_override > system_default。"""
        agent_cfg = system_config.get("agent", {}) or {}
        model_name: str | None = agent_cfg.get("model")
        model_params: dict | None = dict(agent_cfg.get("generation_kwargs") or {})
        source = "system_default"

        for overrides, override_source in (
            (user_mode_overrides, "user_default"),
            (workspace_mode_overrides, "workspace_override"),
            (session_mode_overrides, "session_override"),
        ):
            if overrides is None or overrides.model is None:
                continue
            if overrides.model.model is not None:
                model_name = overrides.model.model
                source = override_source
            for field in ("temperature", "max_tokens", "top_p", "thinking_effort"):
                value = getattr(overrides.model, field, None)
                if value is not None:
                    model_params[field] = value
                    source = override_source

        if not model_params:
            model_params = None
        return model_name, model_params, source

    def get_effective_runtime_config(
        self,
        *,
        mode: AgentMode,
        user_id: str,
        sandbox_mode: str | None = None,
        session_id: str | None = None,
        workspace_id: str | None = None,
        base_config_path: Path | None = None,
    ) -> ResolvedLoopControlConfig:
        """同步获取当前生效的 loop_control，用于 runtime Config 构建。"""
        system_config_path = base_config_path or get_system_default_config_path(
            mode,
            sandbox_mode,
        )
        system_config = self._load_system_config(system_config_path)
        user_mode_overrides = self._load_mode_config_from_dir_sync(
            self._get_mode_config_dir(user_id, mode.value),
            index_path=self._get_user_config_index_path(user_id),
        )
        workspace_mode_overrides = None
        if workspace_id:
            workspace_mode_overrides = self._load_mode_config_from_dir_sync(
                self._get_workspace_mode_config_dir(user_id, workspace_id, mode.value),
            )
        session_mode_overrides = None
        if session_id:
            session_mode_overrides = self._load_mode_config_from_dir_sync(
                self._get_session_mode_config_dir(user_id, session_id, mode.value),
            )

        runtime_config, _ = self._merge_runtime_config(
            system_config=system_config,
            user_mode_overrides=user_mode_overrides,
            workspace_mode_overrides=workspace_mode_overrides,
            session_mode_overrides=session_mode_overrides,
        )
        return runtime_config

    def _merge_prompt(
        self,
        system_config: dict,
        user_mode_overrides: Optional[ModeOverrides],
        workspace_mode_overrides: Optional[ModeOverrides] = None,
        session_mode_overrides: Optional[ModeOverrides] = None,
        *,
        mode: AgentMode,
        user_id: str,
        workspace_profile_text: str | None = None,
        base_config_path: Optional[Path] = None,
        rendered_system_prompt: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        合并提示词

        Args:
            system_config: 系统默认配置
            mode_overrides: 用户覆盖配置
            mode: Agent 模式

        Returns:
            (合并后的提示词, 来源标记)
        """
        # 获取系统默认提示词。动态运行态会先完成模板渲染，再传入这里。
        system_prompt = rendered_system_prompt or ""
        system_prompt_path_str = system_config.get("agent", {}).get("system_prompt_path")

        if not system_prompt and system_prompt_path_str:
            system_prompt_path = Path(system_prompt_path_str)
            if not system_prompt_path.is_absolute():
                # 相对路径，基于配置文件目录
                config_path = base_config_path or get_system_default_config_path(mode)
                system_prompt_path = config_path.parent / system_prompt_path

            if system_prompt_path.exists():
                system_prompt = system_prompt_path.read_text(encoding="utf-8")

        sections: list[str] = []
        if system_prompt.strip():
            sections.append(system_prompt.strip())

        soul_text = read_user_soul_text(self.workspace_root, user_id)
        if soul_text:
            sections.append("## Agent Soul\n\n" + soul_text)

        prompt_source = "system_default"

        if (
            user_mode_overrides
            and user_mode_overrides.prompt
            and user_mode_overrides.prompt.content
        ):
            sections.append("## 用户默认工作说明\n\n" + user_mode_overrides.prompt.content.strip())
            prompt_source = "user_default"

        if workspace_profile_text:
            sections.append("## Project Profile\n\n" + workspace_profile_text)

        if (
            workspace_mode_overrides
            and workspace_mode_overrides.prompt
            and workspace_mode_overrides.prompt.content
        ):
            sections.append(
                "## 工作区工作说明\n\n" + workspace_mode_overrides.prompt.content.strip()
            )
            prompt_source = "workspace_override"

        if (
            session_mode_overrides
            and session_mode_overrides.prompt
            and session_mode_overrides.prompt.content
        ):
            sections.append(
                "## 当前会话工作说明\n\n" + session_mode_overrides.prompt.content.strip()
            )
            prompt_source = "session_override"

        return "\n\n".join(section for section in sections if section), prompt_source

    def _load_workspace_project_profile_text(
        self,
        *,
        user_id: str,
        workspace_id: str | None = None,
        session_id: str | None = None,
    ) -> str | None:
        """读取当前工作区项目画像。"""
        resolved_workspace_id = workspace_id
        if not resolved_workspace_id and session_id:
            try:
                from app.services.workspace_registry import WorkspaceRegistryService

                registry = WorkspaceRegistryService(self.workspace_root)
                resolved_workspace_id = registry.find_workspace_id_by_session_id(
                    user_id,
                    session_id,
                )
            except Exception:
                resolved_workspace_id = None
        if not resolved_workspace_id:
            return None
        try:
            from app.services.workspace_registry import WorkspaceRegistryService

            registry = WorkspaceRegistryService(self.workspace_root)
            workspace = registry.get_workspace(
                user_id,
                resolved_workspace_id,
                include_conversations=False,
            )
            workspace_dir = registry.get_workspace_root(user_id, resolved_workspace_id)
            return read_workspace_project_profile_text(
                workspace_dir,
                title=workspace.title,
                description=workspace.description,
            )
        except Exception:
            logger.debug(
                "读取工作区项目画像失败，已跳过: user=%s workspace=%s session=%s",
                user_id,
                resolved_workspace_id,
                session_id,
                exc_info=True,
            )
            return None

    def _smart_merge_prompts(self, base_prompt: str, user_prompt: str) -> str:
        """
        智能合并提示词

        支持通过标记控制合并位置：
        - [AFTER:section_name] - 在指定 section 后插入
        - [BEFORE:section_name] - 在指定 section 前插入
        - [REPLACE:section_name] - 替换指定 section

        Args:
            base_prompt: 基础提示词
            user_prompt: 用户提示词

        Returns:
            合并后的提示词
        """
        # 解析用户提示词中的标记
        marker_pattern = r"^\[(AFTER|BEFORE|REPLACE):([^\]]+)\]\s*\n?"
        match = re.match(marker_pattern, user_prompt, re.MULTILINE)

        if not match:
            # 没有标记，默认追加到末尾
            return base_prompt + "\n\n" + user_prompt

        action = match.group(1)
        section_name = match.group(2).strip()
        content = user_prompt[match.end() :]

        # 查找目标 section
        section_pattern = rf"(^|\n)(#{1, 6}\s*{re.escape(section_name)}.*?)(\n|$)"
        section_match = re.search(section_pattern, base_prompt, re.IGNORECASE)

        if not section_match:
            # 找不到目标 section，追加到末尾
            logger.warning(f"Smart merge: section '{section_name}' not found, appending")
            return base_prompt + "\n\n" + content

        if action == "REPLACE":
            # 替换整个 section
            start = section_match.start()
            end = section_match.end()
            return base_prompt[:start] + "\n" + content + base_prompt[end:]

        elif action == "AFTER":
            # 在 section 后插入
            insert_pos = section_match.end()
            return base_prompt[:insert_pos] + "\n" + content + base_prompt[insert_pos:]

        elif action == "BEFORE":
            # 在 section 前插入
            insert_pos = section_match.start()
            return base_prompt[:insert_pos] + content + "\n" + base_prompt[insert_pos:]

        return base_prompt + "\n\n" + content

    def _merge_tools(
        self,
        system_config: dict,
        mode_overrides_chain: List[ModeOverrides],
    ) -> Tuple[List[str], List[str], Dict[str, ToolOverride], ToolStrategyName]:
        """
        合并工具配置

        Args:
            system_config: 系统默认配置
            mode_overrides: 用户覆盖配置

        Returns:
            (启用的工具列表, 禁用的工具列表, 工具参数覆盖)
        """
        # 获取系统默认工具列表
        system_tools = system_config.get("agent", {}).get("tools", [])
        enabled_tools = _filter_supported_tools(list(system_tools))
        disabled_tools = []
        tool_overrides = {}
        tool_strategy: ToolStrategyName = "auto"

        # 如果没有覆盖，返回系统默认
        if not mode_overrides_chain:
            return enabled_tools, disabled_tools, tool_overrides, tool_strategy

        for mode_overrides in mode_overrides_chain:
            if not mode_overrides.tools:
                continue

            tools_config = mode_overrides.tools
            tool_strategy = _normalize_tool_strategy(tools_config.tool_strategy)

            if tools_config.selection_mode == "explicit":
                requested_tools = _canonicalize_tool_name_list(list(tools_config.enabled_tools))
                enabled_tools = _filter_supported_tools(requested_tools)
                disabled_tools = [
                    tool_name
                    for tool_name in _canonicalize_tool_name_list(list(system_tools))
                    if tool_name not in enabled_tools
                ]
                for tool_name in tools_config.disabled_tools:
                    canonical_tool_name = canonicalize_runtime_tool_name(tool_name)
                    if canonical_tool_name in enabled_tools:
                        enabled_tools.remove(canonical_tool_name)
                    if canonical_tool_name not in disabled_tools:
                        disabled_tools.append(canonical_tool_name)

            # 应用禁用列表
            for tool_name in tools_config.disabled_tools:
                canonical_tool_name = canonicalize_runtime_tool_name(tool_name)
                if canonical_tool_name in enabled_tools:
                    enabled_tools.remove(canonical_tool_name)
                if canonical_tool_name not in disabled_tools:
                    disabled_tools.append(canonical_tool_name)

            # 应用额外工具 / 重启用工具
            for tool_name in tools_config.extra_tools:
                canonical_tool_name = canonicalize_runtime_tool_name(tool_name)
                if canonical_tool_name not in enabled_tools and _is_supported_tool(
                    canonical_tool_name
                ):
                    enabled_tools.append(canonical_tool_name)
                    if canonical_tool_name in disabled_tools:
                        disabled_tools.remove(canonical_tool_name)
                elif canonical_tool_name not in enabled_tools:
                    logger.warning("忽略额外启用的不可用工具: %s", tool_name)

            # 应用工具参数覆盖
            for tool_name, override in tools_config.tool_overrides.items():
                canonical_tool_name = canonicalize_runtime_tool_name(tool_name)
                tool_overrides[canonical_tool_name] = ToolOverride(
                    **{
                        **override.model_dump(),
                        "name": canonical_tool_name,
                    }
                )

        return enabled_tools, disabled_tools, tool_overrides, tool_strategy

    async def get_session_editor_config(
        self,
        mode: AgentMode,
        user_id: str,
        session_id: str,
        sandbox_mode: Optional[str] = None,
    ) -> dict[str, object]:
        """获取当前会话设置编辑器所需的有效配置。"""
        session_override = await self.get_session_override(mode, user_id, session_id)
        merged = await self.get_merged_config(
            mode=mode,
            user_id=user_id,
            sandbox_mode=sandbox_mode,
            session_id=session_id,
        )

        source = merged.prompt_source
        prompt_content = (
            session_override.prompt.content
            if session_override is not None
            and session_override.prompt is not None
            and session_override.prompt.content
            else merged.system_prompt
        )
        if source == "system_default" and not prompt_content:
            system_config = self._load_system_config(
                get_system_default_config_path(mode, sandbox_mode)
            )
            prompt_content, source = self._merge_prompt(
                system_config=system_config,
                user_mode_overrides=None,
                session_mode_overrides=None,
                mode=mode,
                user_id=user_id,
            )

        return {
            "mode": mode.value,
            "enabled": True,
            "prompt_content": prompt_content,
            "enabled_tools": list(merged.enabled_tools),
            "disabled_tools": list(merged.disabled_tools),
            "tool_strategy": merged.tool_strategy,
            "reserved_context_size": merged.runtime_config.reserved_context_size,
            "compaction_trigger_ratio": merged.runtime_config.compaction_trigger_ratio,
            "source": source,
            "runtime_source": merged.runtime_source,
            "has_local_override": session_override is not None,
            "has_local_runtime_override": bool(
                session_override
                and session_override.runtime
                and session_override.runtime.has_values()
            ),
        }

    async def save_prompt_override(
        self,
        mode: AgentMode,
        user_id: str,
        content: str,
        session_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> bool:
        """
        保存提示词覆盖

        Args:
            mode: Agent 模式
            user_id: 用户 ID
            content: 提示词内容
            session_id: 会话 ID（session 级保存）
            workspace_id: 工作区 ID（workspace 级保存）

        Returns:
            是否保存成功
        """
        try:
            if session_id:
                self._ensure_session_config_dir_exists(user_id, session_id)
                mode_dir = self._get_session_mode_config_dir(
                    user_id,
                    session_id,
                    mode.value,
                )
            elif workspace_id:
                self._ensure_workspace_config_dir_exists(user_id, workspace_id)
                mode_dir = self._get_workspace_mode_config_dir(
                    user_id,
                    workspace_id,
                    mode.value,
                )
            else:
                self._ensure_config_dir_exists(user_id)
                mode_dir = self._get_mode_config_dir(user_id, mode.value)
            mode_dir.mkdir(parents=True, exist_ok=True)

            # 保存提示词文件
            prompt_path = mode_dir / self.PROMPT_OVERRIDE_FILE
            prompt_path.write_text(content, encoding="utf-8")

            if not session_id and not workspace_id:
                # 更新用户默认索引文件
                await self._update_config_index(
                    user_id,
                    mode,
                    enabled=self._has_mode_local_config(mode_dir),
                )

            scope = session_id or workspace_id or "-"
            logger.info(
                "保存提示词覆盖成功: user=%s, mode=%s, scope=%s",
                user_id,
                mode.value,
                scope,
            )
            return True

        except Exception as e:
            scope = session_id or workspace_id or "-"
            logger.error(
                "保存提示词覆盖失败: user=%s, mode=%s, scope=%s, error=%s",
                user_id,
                mode.value,
                scope,
                e,
            )
            return False

    async def save_tools_config(
        self,
        mode: AgentMode,
        user_id: str,
        disabled_tools: Optional[List[str]] = None,
        extra_tools: Optional[List[str]] = None,
        enabled_tools: Optional[List[str]] = None,
        tool_strategy: str | None = None,
        tool_overrides: Optional[Dict[str, ToolOverride]] = None,
        session_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        sandbox_mode: Optional[str] = None,
    ) -> bool:
        """
        保存工具配置

        Args:
            mode: Agent 模式
            user_id: 用户 ID
            disabled_tools: 禁用的工具列表
            extra_tools: 额外启用的工具列表
            tool_overrides: 工具参数覆盖

        Returns:
            是否保存成功
        """
        try:
            if session_id:
                self._ensure_session_config_dir_exists(user_id, session_id)
                mode_dir = self._get_session_mode_config_dir(
                    user_id,
                    session_id,
                    mode.value,
                )
            elif workspace_id:
                self._ensure_workspace_config_dir_exists(user_id, workspace_id)
                mode_dir = self._get_workspace_mode_config_dir(
                    user_id,
                    workspace_id,
                    mode.value,
                )
            else:
                self._ensure_config_dir_exists(user_id)
                mode_dir = self._get_mode_config_dir(user_id, mode.value)
            mode_dir.mkdir(parents=True, exist_ok=True)

            # 构建工具配置
            explicit_selection = enabled_tools is not None
            tools_config = ToolsConfig(
                selection_mode="explicit" if explicit_selection else "inherit",
                tool_strategy=_normalize_tool_strategy(tool_strategy),
            )
            if explicit_selection:
                resolved_enabled_tools = _filter_supported_tools(
                    _canonicalize_tool_name_list(list(enabled_tools or []))
                )
                if resolved_enabled_tools:
                    tools_config.enabled_tools = resolved_enabled_tools
            resolved_disabled_tools = [
                canonicalize_runtime_tool_name(tool_name)
                for tool_name in list(disabled_tools or [])
            ]
            resolved_extra_tools = [
                canonicalize_runtime_tool_name(tool_name) for tool_name in list(extra_tools or [])
            ]
            resolved_disabled_tools = list(dict.fromkeys(resolved_disabled_tools))
            resolved_extra_tools = list(dict.fromkeys(resolved_extra_tools))

            if session_id and not explicit_selection:
                system_config_path = get_system_default_config_path(mode, sandbox_mode)
                system_config = self._load_system_config(system_config_path)
                user_config = await self.get_user_config(user_id)
                user_mode_overrides = None
                if user_config:
                    if mode == AgentMode.ANALYSIS and user_config.analysis:
                        user_mode_overrides = user_config.analysis

                base_enabled_tools, _, _, _ = self._merge_tools(
                    system_config=system_config,
                    mode_overrides_chain=[
                        override for override in [user_mode_overrides] if override is not None
                    ],
                )
                system_tools = _filter_supported_tools(
                    list(system_config.get("agent", {}).get("tools", []))
                )
                desired_enabled_tools = [
                    tool_name
                    for tool_name in system_tools
                    if tool_name not in resolved_disabled_tools
                ]
                resolved_extra_tools = [
                    tool_name
                    for tool_name in desired_enabled_tools
                    if tool_name not in base_enabled_tools
                ]
                resolved_disabled_tools = [
                    tool_name
                    for tool_name in base_enabled_tools
                    if tool_name not in desired_enabled_tools
                ]

            if resolved_disabled_tools:
                tools_config.disabled_tools = resolved_disabled_tools
            if resolved_extra_tools:
                tools_config.extra_tools = resolved_extra_tools
            if tool_overrides:
                tools_config.tool_overrides = {
                    canonicalize_runtime_tool_name(tool_name): ToolOverride(
                        **{
                            **override.model_dump(),
                            "name": canonicalize_runtime_tool_name(tool_name),
                        }
                    )
                    for tool_name, override in tool_overrides.items()
                }

            # 保存工具配置文件
            tools_path = mode_dir / self.TOOLS_CONFIG_FILE
            tools_data = tools_config.model_dump(exclude_defaults=True)

            if tools_data:  # 只在有内容时保存
                self._write_json_file(tools_path, tools_data)
            else:
                # 如果配置为空则删除文件
                if tools_path.exists():
                    tools_path.unlink()

            # 更新索引文件（仅用户默认层）
            if not session_id and not workspace_id:
                await self._update_config_index(
                    user_id,
                    mode,
                    enabled=self._has_mode_local_config(mode_dir),
                )

            scope = session_id or workspace_id or "-"
            logger.info(
                "保存工具配置成功: user=%s, mode=%s, scope=%s",
                user_id,
                mode.value,
                scope,
            )
            return True

        except Exception as e:
            scope = session_id or workspace_id or "-"
            logger.error(
                "保存工具配置失败: user=%s, mode=%s, scope=%s, error=%s",
                user_id,
                mode.value,
                scope,
                e,
            )
            return False

    async def save_runtime_config(
        self,
        mode: AgentMode,
        user_id: str,
        *,
        reserved_context_size: int | None = None,
        compaction_trigger_ratio: float | None = None,
        session_id: str | None = None,
        workspace_id: str | None = None,
    ) -> bool:
        """保存 loop_control 运行时配置覆盖。"""
        try:
            if session_id:
                self._ensure_session_config_dir_exists(user_id, session_id)
                mode_dir = self._get_session_mode_config_dir(
                    user_id,
                    session_id,
                    mode.value,
                )
            elif workspace_id:
                self._ensure_workspace_config_dir_exists(user_id, workspace_id)
                mode_dir = self._get_workspace_mode_config_dir(
                    user_id,
                    workspace_id,
                    mode.value,
                )
            else:
                self._ensure_config_dir_exists(user_id)
                mode_dir = self._get_mode_config_dir(user_id, mode.value)
            mode_dir.mkdir(parents=True, exist_ok=True)

            runtime_override = LoopControlOverrides(
                reserved_context_size=reserved_context_size,
                compaction_trigger_ratio=compaction_trigger_ratio,
            )
            runtime_path = mode_dir / self.RUNTIME_CONFIG_FILE
            runtime_data = runtime_override.model_dump(exclude_none=True)

            if runtime_data:
                self._write_json_file(runtime_path, runtime_data)
            else:
                if runtime_path.exists():
                    runtime_path.unlink()

            if not session_id and not workspace_id:
                await self._update_config_index(
                    user_id,
                    mode,
                    enabled=self._has_mode_local_config(mode_dir),
                )

            scope = session_id or workspace_id or "-"
            logger.info(
                "保存运行时配置成功: user=%s, mode=%s, scope=%s",
                user_id,
                mode.value,
                scope,
            )
            return True
        except Exception as exc:
            scope = session_id or workspace_id or "-"
            logger.error(
                "保存运行时配置失败: user=%s, mode=%s, scope=%s, error=%s",
                user_id,
                mode.value,
                scope,
                exc,
            )
            return False

    async def _update_config_index(
        self,
        user_id: str,
        mode: AgentMode,
        enabled: bool,
    ) -> None:
        """
        更新配置索引文件

        Args:
            user_id: 用户 ID
            mode: Agent 模式
            enabled: 是否启用
        """
        index_path = self._get_user_config_index_path(user_id)

        # 读取现有索引
        index_data = {}
        if index_path.exists():
            try:
                index_data = self._load_mapping_file(index_path)
            except Exception:
                pass

        # 确保结构存在
        if "modes" not in index_data:
            index_data["modes"] = {}

        # 更新指定模式的索引
        mode_index = index_data["modes"].get(mode.value, {})
        mode_index["enabled"] = enabled
        mode_index["prompt_path"] = f"./{mode.value}/{self.PROMPT_OVERRIDE_FILE}"
        mode_index["tools_path"] = f"./{mode.value}/{self.TOOLS_CONFIG_FILE}"
        mode_index["runtime_path"] = f"./{mode.value}/{self.RUNTIME_CONFIG_FILE}"

        index_data["modes"][mode.value] = mode_index
        index_data["version"] = "1.0"
        index_data["updated_at"] = datetime.now().isoformat()

        # 保存索引文件
        self._write_json_file(index_path, index_data)

    async def reset_to_default(
        self,
        mode: AgentMode,
        user_id: str,
        session_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> bool:
        """
        重置为系统默认配置

        删除指定作用域的自定义配置，恢复使用系统默认。

        Args:
            mode: Agent 模式
            user_id: 用户 ID
            session_id: 会话 ID（session 级重置）
            workspace_id: 工作区 ID（workspace 级重置）

        Returns:
            是否重置成功
        """
        try:
            if session_id:
                mode_dir = self._get_session_mode_config_dir(user_id, session_id, mode.value)
            elif workspace_id:
                mode_dir = self._get_workspace_mode_config_dir(user_id, workspace_id, mode.value)
            else:
                mode_dir = self._get_mode_config_dir(user_id, mode.value)

            if mode_dir.exists():
                # 删除整个模式配置目录
                shutil.rmtree(mode_dir)
                logger.info("删除配置目录: %s", mode_dir)

            if not session_id and not workspace_id:
                # 更新用户默认索引文件
                index_path = self._get_user_config_index_path(user_id)
                if index_path.exists():
                    index_data = self._load_mapping_file(index_path)

                    if "modes" in index_data and mode.value in index_data["modes"]:
                        index_data["modes"][mode.value]["enabled"] = False
                        index_data["updated_at"] = datetime.now().isoformat()

                        self._write_json_file(index_path, index_data)

            scope = session_id or workspace_id or "-"
            logger.info(
                "重置配置成功: user=%s, mode=%s, scope=%s",
                user_id,
                mode.value,
                scope,
            )
            return True

        except Exception as e:
            scope = session_id or workspace_id or "-"
            logger.error(
                "重置配置失败: user=%s, mode=%s, scope=%s, error=%s",
                user_id,
                mode.value,
                scope,
                e,
            )
            return False

    async def validate_config(
        self,
        mode: AgentMode,
        user_id: str,
        session_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> Tuple[bool, List[str]]:
        """
        验证配置的有效性

        Args:
            mode: Agent 模式
            user_id: 用户 ID
            session_id: 会话 ID（session 级验证）
            workspace_id: 工作区 ID（workspace 级验证）

        Returns:
            (是否有效, 错误信息列表)
        """
        errors = []

        try:
            if session_id:
                mode_dir = self._get_session_mode_config_dir(user_id, session_id, mode.value)
            elif workspace_id:
                mode_dir = self._get_workspace_mode_config_dir(user_id, workspace_id, mode.value)
            else:
                mode_dir = self._get_mode_config_dir(user_id, mode.value)

            if not mode_dir.exists():
                return True, []  # 没有配置视为有效

            # 验证提示词文件
            prompt_path = mode_dir / self.PROMPT_OVERRIDE_FILE
            if prompt_path.exists():
                try:
                    content = prompt_path.read_text(encoding="utf-8")
                    if len(content) > 100000:  # 100KB 限制
                        errors.append("提示词文件过大（超过 100KB）")
                except Exception as e:
                    errors.append(f"提示词文件读取失败: {e}")

            # 验证工具配置文件
            tools_path = mode_dir / self.TOOLS_CONFIG_FILE
            if tools_path.exists():
                try:
                    tools_data = self._load_mapping_file(tools_path)
                    if tools_data:
                        ToolsConfig(**tools_data)
                except Exception as e:
                    errors.append(f"工具配置文件格式错误: {e}")

            runtime_path = mode_dir / self.RUNTIME_CONFIG_FILE
            if runtime_path.exists():
                try:
                    runtime_data = self._load_mapping_file(runtime_path)
                    if runtime_data:
                        LoopControlOverrides(**runtime_data)
                except Exception as e:
                    errors.append(f"运行时配置文件格式错误: {e}")

            return len(errors) == 0, errors

        except Exception as e:
            errors.append(f"验证过程出错: {e}")
            return False, errors


# 全局服务实例
_agent_config_service: Optional[AgentConfigService] = None


def get_agent_config_service() -> AgentConfigService:
    """
    获取 AgentConfigService 单例实例

    Returns:
        AgentConfigService 实例
    """
    global _agent_config_service
    if _agent_config_service is None:
        _agent_config_service = AgentConfigService()
    return _agent_config_service
