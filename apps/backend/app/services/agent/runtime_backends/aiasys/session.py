from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import tomllib
from pathlib import Path
from typing import Any

from app.services.agent.compaction import estimate_text_tokens
from app.services.agent.message_content import (
    downgrade_message_content_for_history,
)
from app.services.agent.mixins.context import (
    build_memory_context_text,
)
from app.services.agent.runtime_backends.aiasys.llm_clients import BaseLlmClient, LlmRequestOptions
from app.services.session.constants import (
    ACTIVE_SESSION_STATE_DIR_NAME,
    HISTORY_SNAPSHOT_FILE_NAME,
)
from app.services.shell_executor import get_shell_executor
from app.utils.path_utils import as_system_path, atomic_write_text

from ..base import RuntimeSessionCreateSpec
from .capability_confirmation import CapabilityConfirmationManager
from .llm_clients.message_protocol import InternalMessage
from .session_budget import SessionBudgetMixin
from .session_compaction import SessionCompactionMixin
from .session_stream import SessionStreamMixin
from .session_tools import SessionToolsMixin
from .session_utils import (
    _THINKING_BUDGET_BY_EFFORT,
    normalize_capabilities,
    normalize_thinking_effort,
    read_config_value,
)
from .tool_registry import ToolRegistry
from .tool_strategy import ToolStrategy, detect_tool_strategy

logger = logging.getLogger(__name__)


class AiasysRuntimeSession(
    SessionBudgetMixin,
    SessionCompactionMixin,
    SessionToolsMixin,
    SessionStreamMixin,
):
    """AIASys-native runtime session with a minimal ReAct loop."""

    def __init__(
        self,
        spec: RuntimeSessionCreateSpec,
        client: BaseLlmClient,
        registry: ToolRegistry,
        mcp_clients: list[Any] | None = None,
    ) -> None:
        self._spec = spec
        self._client = client
        self._tool_registry = registry
        self._cancel_event = asyncio.Event()
        self._closed = False
        self._metadata_lock = asyncio.Lock()
        self._agent_config = self._load_agent_config(spec.agent_file)
        self._model_config = self._resolve_model_config()
        self._tool_strategy: ToolStrategy = detect_tool_strategy(
            self._client,
            self._model_config,
            explicit_strategy=self._resolve_workspace_tool_strategy(),
        )
        self._tool_strategy.setup_registry(self._tool_registry)
        self.session_id = spec.session_id
        self.mcp_configs = spec.mcp_configs
        self._mcp_clients: list[Any] = list(mcp_clients or [])
        self.messages: list[InternalMessage] = []
        self._context_messages: list[InternalMessage] = []
        self._confirmation_manager = CapabilityConfirmationManager()
        self._consecutive_tool_counts: dict[str, int] = {}
        self._previous_tool_args: dict[str, str] = {}
        self._estimated_token_count: int = 0
        # 自上次 LLM 调用真实 usage 修正以来，追加的消息的 token 估算累加。
        # 与 _estimated_token_count 共同组成 effective_token_count，
        # 用于运行中触发压缩、预算检查的更准确判断。
        self._pending_token_estimate: int = 0
        self._continuation_count: int = 0
        self.budget: Any | None = spec.budget if spec.budget is not None else self._load_budget()
        self._session_turn_count: int = 0
        self._current_turn_n: int | None = None
        self._agent_instructions: str | None = self._load_agent_instructions()

        # Auto-Nudge 状态：每个 user message 只触发一次
        self._auto_nudge_sent_for_current_turn: bool = False
        self._post_list_nudge_sent_for_current_turn: bool = False
        self._tools_used_since_user_message: bool = False
        self._last_tool_name: str | None = None

        # Feature flags for runtime adaptive behaviors
        self._auto_nudge_enabled = os.getenv("AIASYS_AUTO_NUDGE_ENABLED", "true").lower() == "true"
        self._loop_guard_enabled = os.getenv("AIASYS_LOOP_GUARD_ENABLED", "true").lower() == "true"

        # 从 metadata.json 恢复上次 LLM 返回的精确 context_tokens。
        # 顶层 context_tokens 与 budget 独立，确保 budget 关闭后仍能恢复精确值。
        # 启发式估算对 system prompt 容易严重偏高，因此当估算值远高于保存的
        # 精确值时，优先使用精确值；若内容明显增长（估算未高出 50%），则使用估算。
        _saved_tokens = self._load_saved_context_tokens()
        if _saved_tokens is None and self.budget is not None:
            _ct = getattr(self.budget, "context_tokens", 0) or 0
            if isinstance(_ct, int) and _ct > 0:
                _saved_tokens = _ct

        system_prompt = self._load_or_build_system_prompt()
        if system_prompt:
            self.messages.append(
                {
                    "role": "system",
                    "origin": "system",
                    "content": system_prompt,
                }
            )
            self._estimated_token_count += estimate_text_tokens([self.messages[-1]])

        # 构建 contextual user message（memory + AGENTS.md），对齐 Codex user_instructions。
        # 这些内容发送给模型，但不进入普通对话历史，避免污染工具上下文和子 Agent 继承。
        context_parts: list[str] = []
        if self._spec.memory_enabled:
            memory_text = build_memory_context_text(Path(str(self._spec.work_dir)))
            if memory_text:
                context_parts.append(memory_text)
        if self._agent_instructions:
            context_parts.append(self._agent_instructions)
        if context_parts:
            context_message: InternalMessage = {
                "role": "user",
                "origin": "contextual_user",
                "content": "\n\n".join(context_parts),
            }
            self._context_messages.append(context_message)
            self._estimated_token_count += estimate_text_tokens([context_message])

        # 子 Agent 历史对话继承（fork_turns）
        if spec.is_subagent and spec.fork_messages:
            fork_msgs = self._build_fork_messages(spec.fork_messages, spec.fork_turns)
            self.messages.extend(fork_msgs)
            self._estimated_token_count += estimate_text_tokens(fork_msgs)
        elif not spec.is_subagent:
            persisted = self._load_persisted_messages()
            persisted = self._downgrade_historical_image_messages(persisted)
            self.messages.extend(persisted)
            self._estimated_token_count += estimate_text_tokens(persisted)

        # 用保存的精确值修正启发式估算。
        # 启发式估算对 system prompt / skill 注入 / AGENTS.md 容易严重偏高，
        # 当估算值比保存的精确值高出 50% 以上时，优先使用精确值；否则说明内容
        # 确实增长了，使用当前估算。
        if _saved_tokens is not None and _saved_tokens > 0:
            if self._estimated_token_count > int(_saved_tokens * 1.5):
                self._estimated_token_count = _saved_tokens
            elif _saved_tokens > self._estimated_token_count:
                self._estimated_token_count = _saved_tokens

    @property
    def session_turn_count(self) -> int:
        """返回当前会话已持久化的最大 turn 编号，供事件投影初始化 turn 计数。

        该值在 __init__ 时从 history snapshot 恢复，并在每次 ReAct turn 开始
        时递增。执行入口应以此作为 event_state["turn_n"] 的初始值，避免每次
        新的 execute 请求都把第一 turn 重新标为 1。
        """
        return self._session_turn_count

    def refresh_context_tokens_from_metadata(self) -> None:
        """复用旧 Session 时，从 metadata 重新加载精确值修正估算。

        不关闭旧 Session 直接复用的情况下，`_estimated_token_count` 可能仍是
        创建时的旧估算；调用本方法把它刷新到最近一次 LLM 返回的精确值，避免
        前端在 during-stream 阶段看到跳低的数字。
        """
        saved = self._load_saved_context_tokens()
        if saved is None and self.budget is not None:
            _ct = getattr(self.budget, "context_tokens", 0) or 0
            if isinstance(_ct, int) and _ct > 0:
                saved = _ct
        if saved is None or saved <= 0:
            return
        # 精确值优先：估算明显偏高（>50%）时用精确值；
        # 估算偏低或相时使用精确值，确保复用时不低于上次保存的基准。
        if self._estimated_token_count > int(saved * 1.5):
            self._estimated_token_count = saved
        elif saved >= self._estimated_token_count:
            self._estimated_token_count = saved

    @property
    def effective_token_count(self) -> int:
        """当前有效上下文 token 数。

        = 最近一次 LLM 调用修正后的精确值（或压缩后估算值）
            + 自那以后追加消息的 token 估算。
        用于运行中触发压缩、预算检查，比单纯的 _estimated_token_count 更准确。
        """
        return max(0, self._estimated_token_count + self._pending_token_estimate)

    def _reset_pending_token_estimate(self) -> None:
        """在获得新的真实 usage 或完成压缩后清零 pending 估算。"""
        self._pending_token_estimate = 0

    def _messages_for_model(self) -> list[InternalMessage]:
        """返回发送给模型的消息序列。"""
        if not self._context_messages:
            return self.messages

        leading_system: list[InternalMessage] = []
        rest_start = 0
        for index, message in enumerate(self.messages):
            if message.get("role") != "system":
                break
            leading_system.append(message)
            rest_start = index + 1

        return [
            *leading_system,
            *self._context_messages,
            *self.messages[rest_start:],
        ]

    def _load_agent_instructions(self) -> str | None:
        """加载工作区目录下的 AGENTS.md，用于注入 user instructions 层。

        只扫描当前工作区目录，不向上查找项目根。
        避免把 AIASys 自身的开发规范文件注入到用户会话。
        """
        try:
            work_dir = Path(str(self._spec.work_dir))
            user_id = work_dir.parent.name
            session_id = work_dir.name

            from app.services.workspace_registry import WorkspaceRegistryService

            registry = WorkspaceRegistryService(work_dir.parent.parent)
            workspace_id = registry.find_workspace_id_by_session_id(user_id, session_id)
            workspace_dir = (
                registry.get_workspace_root(user_id, workspace_id)
                if workspace_id is not None
                else None
            )
            if workspace_dir is None:
                return None

            # 只加载工作区目录下的 AGENTS.md，不向上扫描项目根
            from app.services.agent.agent_instructions import (
                _AGENT_MD_VARIANTS,
                _LOCAL_OVERRIDE,
                _load_file,
            )

            override = workspace_dir / _LOCAL_OVERRIDE
            if override.is_file():
                content = _load_file(override)
                if content:
                    return content

            for variant in _AGENT_MD_VARIANTS:
                candidate = workspace_dir / variant
                if candidate.is_file():
                    content = _load_file(candidate)
                    if content:
                        return content

            return None
        except Exception:
            logger.debug("加载 AGENTS.md 失败，已跳过", exc_info=True)
            return None

    def _resolve_workspace_tool_strategy(self) -> str | None:
        """解析当前 session 使用的工具加载策略。

        当前主路径从动态 agent manifest 的 ``tool_strategy`` 字段读取。
        """
        manifest_strategy = str(self._agent_config.get("tool_strategy") or "").strip()
        if manifest_strategy:
            return manifest_strategy
        return None

    def _load_agent_config(self, agent_file: Path) -> dict[str, Any]:
        with open(as_system_path(str(agent_file)), "rb") as file:
            data = tomllib.load(file) or {}
        agent = data.get("agent")
        if not isinstance(agent, dict):
            raise ValueError(f"Agent 配置缺少 agent 段: {agent_file}")
        return agent

    def _load_skill_injections(self) -> str:
        """扫描 workspace 和 builtin skill，只注入 name + description（渐进式披露）。

        Tier 1: name + description 常驻 system prompt（当前方法）
        Tier 2: SKILL.md 完整内容通过 LoadSkill 工具按需加载
        Tier 3: references/ 下文档在 Skill 执行过程中按需读取
        """
        from app.skills.manager import get_skill_manager

        policy = str(self._agent_config.get("skill_policy") or "inherit").strip().lower()
        allowed_skills = {
            name.strip() for name in (self._agent_config.get("skills") or []) if name.strip()
        }

        workspace_path = Path(str(self._spec.work_dir))
        mgr = get_skill_manager()
        all_skills = mgr.list_all_skills(workspace_path)

        visible_skills: list[Any] = []
        for skill in all_skills:
            if policy == "none":
                continue
            if policy == "allowlist" and skill.name not in allowed_skills:
                continue
            if policy == "denylist" and skill.name in allowed_skills:
                continue
            visible_skills.append(skill)

        if not visible_skills:
            return ""

        lines = [
            "\n\n---\n\n## 可用 Skill",
            "",
            "以下 Skill 已加载到当前上下文。需要详细指导时，调用 LoadSkill 工具加载：",
            "",
        ]
        for skill in visible_skills:
            name = skill.display_name or skill.name
            desc = skill.description or ""
            source_tag = " [builtin]" if skill.source == "builtin" else ""
            lines.append(f"- **{name}**{source_tag}: {desc}")

        lines.append("")
        lines.append("使用方式：")
        lines.append("1. 调用 `ListSkills` 查看完整列表和来源")
        lines.append("2. 调用 `LoadSkill(name='skill-name')` 加载 SKILL.md 详细指导")
        lines.append("3. Skill 中的脚本通过 `Shell` 工具执行")
        lines.append(
            "4. 参考文档通过 `LoadSkill(name='skill-name', file='references/xxx.md')` 读取"
        )

        return "\n".join(lines)

    def _load_or_build_system_prompt(self) -> str:
        prompt = self._build_system_prompt()
        if not prompt:
            return ""

        snapshot_path = (
            Path(str(self._spec.work_dir))
            / ".aiasys"
            / "session"
            / ACTIVE_SESSION_STATE_DIR_NAME
            / "system_prompt_snapshot.md"
        )
        hash_path = snapshot_path.with_suffix(".hash")
        current_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

        sys_snapshot_path = Path(as_system_path(snapshot_path))
        sys_hash_path = Path(as_system_path(hash_path))
        if sys_hash_path.exists() and sys_snapshot_path.exists():
            stored_hash = sys_hash_path.read_text(encoding="utf-8").strip()
            if stored_hash == current_hash:
                return sys_snapshot_path.read_text(encoding="utf-8")

        sys_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        sys_snapshot_path.write_text(prompt, encoding="utf-8")
        sys_hash_path.write_text(current_hash, encoding="utf-8")
        return prompt

    def _invalidate_system_prompt_snapshot(self) -> None:
        snapshot_path = (
            Path(str(self._spec.work_dir))
            / ".aiasys"
            / "session"
            / ACTIVE_SESSION_STATE_DIR_NAME
            / "system_prompt_snapshot.md"
        )
        hash_path = snapshot_path.with_suffix(".hash")
        for p in (snapshot_path, hash_path):
            sys_p = Path(as_system_path(p))
            if sys_p.exists():
                sys_p.unlink()

    def _build_shell_environment_guidance(self) -> str:
        """根据当前实际 shell 环境给 Agent 追加分段提示。"""
        try:
            from app.services.shell_environment import _find_busybox

            executor = get_shell_executor()
            _, _, family = executor.detect_interpreter("auto")
        except Exception:
            return ""

        if os.name != "nt":
            if family in ("posix", "wsl"):
                return (
                    "Shell 环境为 POSIX。你编写的命令将直接由 bash/sh 执行，"
                    "可使用标准 Unix 工具（ls、grep、sed、awk、find 等）。"
                )
            return ""

        # Windows 各 shell  family 的精确提示
        guidance: dict[str, str] = {
            "posix": (
                "当前 Windows 使用 Git Bash。你可以编写标准 POSIX 命令 "
                "（ls、cat、grep、sed、awk、find、python 等），路径使用 /c/foo/bar 风格。"
                "若需要显式切换解释器，可在 Shell 工具的 interpreter 参数中指定 bash/wsl/busybox/powershell。"
            ),
            "wsl": (
                "当前 Windows 未安装 Git Bash，但检测到 WSL。shell 命令将通过 `wsl.exe bash -c` 执行。"
                "你可以使用常见 POSIX 命令；访问 Windows 路径时请注意 /mnt/c/ 挂载转换。"
                "若需要显式切换解释器，可在 Shell 工具的 interpreter 参数中指定 bash/wsl/busybox/powershell。"
            ),
            "busybox": (
                "当前 Windows 使用 busybox-w32（ash）作为轻量 POSIX fallback。"
                "仅支持基础 POSIX 命令，避免使用 GNU bash 数组、[[ ]]、进程替换等扩展特性；"
                "复杂任务建议用户安装 Git for Windows：https://git-scm.com/download/win。"
                "若需要显式切换解释器，可在 Shell 工具的 interpreter 参数中指定 bash/wsl/busybox/powershell。"
            ),
            "powershell": (
                "当前 Windows 未检测到 POSIX shell，shell 命令将使用 PowerShell 执行。"
                "请优先使用跨平台命令或 PowerShell cmdlet（Get-Content、Select-String、Where-Object 等）；"
                "如需完整 POSIX 环境，建议用户安装 Git for Windows：https://git-scm.com/download/win。"
                "若需要显式切换解释器，可在 Shell 工具的 interpreter 参数中指定 bash/wsl/busybox/powershell。"
            ),
            "cmd": (
                "cmd 解释器已移除，AIASys 不再支持 cmd.exe。"
                "请改用 powershell，或安装 POSIX shell（Git Bash / WSL / busybox-w32）。"
            ),
        }

        base = guidance.get(family, "")
        if family == "busybox":
            # busybox 下追加 busybox 路径，方便 Agent 知道可以用它执行 ash
            busybox_path = _find_busybox()
            if busybox_path:
                base += f"\n已安装的 busybox-w32 路径：{busybox_path}"
        return base

    def _build_system_prompt(self) -> str:
        base_prompt = ""
        raw_prompt_path = self._agent_config.get("system_prompt_path")
        if isinstance(raw_prompt_path, str) and raw_prompt_path.strip():
            prompt_path = Path(raw_prompt_path)
            if not prompt_path.is_absolute():
                prompt_path = (self._spec.agent_file.parent / prompt_path).resolve()
            if prompt_path.exists():
                base_prompt = prompt_path.read_text(encoding="utf-8")
        if not base_prompt:
            base_prompt = str(self._agent_config.get("system_prompt", "") or "")

        skill_injection = self._load_skill_injections()
        if skill_injection:
            if base_prompt:
                base_prompt = base_prompt.rstrip() + skill_injection
            else:
                base_prompt = skill_injection.lstrip()

        # 注入工具策略的使用说明（deferred / search）
        strategy_additions = self._tool_strategy.get_system_prompt_additions()
        if strategy_additions and base_prompt:
            base_prompt = base_prompt.rstrip() + "\n\n" + strategy_additions.strip()
        elif strategy_additions:
            base_prompt = strategy_additions.strip()

        try:
            from app.services.session import PLAN_WORKFLOW_GUIDANCE, TASK_MANAGEMENT_PROTOCOL

            task_plan_prompt = "\n\n".join(
                [
                    TASK_MANAGEMENT_PROTOCOL.strip(),
                    PLAN_WORKFLOW_GUIDANCE.strip(),
                    (
                        "Plan Mode 下运行时会在代码层过滤工具。"
                        "进入 Plan Mode 后只能做只读探索、列出任务、询问用户和提交计划，"
                        "不能修改源码、执行 shell、运行 notebook 或派发子 Agent。"
                    ),
                ]
            )
            if base_prompt:
                base_prompt = base_prompt.rstrip() + "\n\n" + task_plan_prompt
            else:
                base_prompt = task_plan_prompt
        except Exception:
            logger.debug("注入 Task / Plan 系统提示失败，已跳过", exc_info=True)

        # 注入跨会话 memory summary（对齐 Codex）
        if self._spec.memory_enabled:
            try:
                from app.services.agent.mixins.context import (
                    build_memory_tool_developer_instructions,
                )

                work_dir = Path(str(self._spec.work_dir))
                logger.info(f"[MEMORY DEBUG] work_dir={work_dir}, parent={work_dir.parent.name}")
                memory_instructions = build_memory_tool_developer_instructions(
                    work_dir=work_dir,
                    max_chars=15000,
                )
                logger.info(
                    f"[MEMORY DEBUG] memory_instructions={memory_instructions is not None}, length={len(memory_instructions) if memory_instructions else 0}"
                )
                if memory_instructions:
                    if base_prompt:
                        base_prompt = base_prompt.rstrip() + "\n\n" + memory_instructions
                    else:
                        base_prompt = memory_instructions
                    logger.info(
                        f"[MEMORY DEBUG] Injected memory, total prompt length={len(base_prompt)}"
                    )
                else:
                    logger.warning(
                        "[MEMORY DEBUG] memory_instructions is None - injection skipped!"
                    )
            except Exception as e:
                logger.warning(f"注入 Memory 系统提示失败，已跳过: {e}", exc_info=True)

        shell_guidance = self._build_shell_environment_guidance()
        if shell_guidance:
            if base_prompt:
                base_prompt = base_prompt.rstrip() + "\n\n" + shell_guidance
            else:
                base_prompt = shell_guidance

        return base_prompt

    def _append_message(self, message: dict[str, Any]) -> None:
        """追加消息到内存列表并持久化到 context.jsonl。

        确保工具调用和工具返回结果在会话切换后仍然可见。
        compaction 只替换内存中的 self.messages，不影响已落盘的数据。

        当处于 ReAct turn 中时，为 assistant/tool 消息附加 turn_n，
        供历史恢复时还原 turn 边界。
        """
        message = dict(message)

        # 为没有 origin 的消息设置默认值，用于区分用户真实输入、系统注入、压缩摘要等。
        if "origin" not in message:
            role = message.get("role")
            if role == "system":
                message["origin"] = "system"
            elif role == "user":
                message["origin"] = "user"
            elif role == "assistant":
                message["origin"] = "assistant"
            elif role == "tool":
                message["origin"] = "tool"

        if self._current_turn_n is not None and message.get("role") in ("assistant", "tool"):
            message["turn_n"] = self._current_turn_n

        self.messages.append(message)
        # 把新增消息计入 pending，等待下次 LLM 真实 usage 修正。
        # 避免运行中 _estimated_token_count 停留在旧精确值，导致上下文占用被低估。
        self._pending_token_estimate += estimate_text_tokens([message])

    def _load_persisted_messages(self) -> list[InternalMessage]:
        # 使用 session_dir 而非 work_dir，确保与 SessionManager 写入路径一致。
        # 当 workspace 绑定时 work_dir 指向 workspace 目录，而 history.json
        # 由 SessionManager 写入 session 目录。
        session_dir = self._spec.session_dir or Path(str(self._spec.work_dir))
        history_path = (
            session_dir
            / ".aiasys"
            / "session"
            / ACTIVE_SESSION_STATE_DIR_NAME
            / HISTORY_SNAPSHOT_FILE_NAME
        )
        sys_history_path = Path(as_system_path(history_path))
        if not sys_history_path.exists():
            return []
        try:
            payload = json.loads(sys_history_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("读取持久化 history snapshot 失败: %s", exc)
            return []
        if isinstance(payload, dict):
            raw_messages = payload.get("messages") or []
        else:
            raw_messages = []
        if not isinstance(raw_messages, list):
            return []
        return self._normalize_restored_messages(raw_messages)

    def _normalize_restored_messages(self, raw_messages: list[Any]) -> list[InternalMessage]:
        """将历史快照中的原始消息规范化并恢复 turn_n / origin 等元数据。"""
        restored: list[InternalMessage] = []
        max_turn_n = 0
        for item in raw_messages:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            # assistant 消息可能只有 tool_calls 没有 content（纯工具调用轮），
            # 不能因为 content 为 None 就跳过，否则 tool_calls 丢失导致上下文断裂。
            if role not in {"user", "assistant", "tool"}:
                continue
            if content is None and not (role == "assistant" and item.get("tool_calls")):
                continue
            message: dict[str, Any] = {"role": role, "content": content}
            message_id = item.get("id")
            if isinstance(message_id, str) and message_id.strip():
                message["id"] = message_id.strip()
            if role == "tool" and item.get("tool_call_id"):
                message["tool_call_id"] = item.get("tool_call_id")
            if role == "assistant" and item.get("tool_calls"):
                message["tool_calls"] = item.get("tool_calls")
            if item.get("reasoning_content") is not None:
                message["reasoning_content"] = item.get("reasoning_content")
            turn_n = item.get("turn_n")
            if isinstance(turn_n, int):
                message["turn_n"] = turn_n
                if turn_n > max_turn_n:
                    max_turn_n = turn_n
            origin = item.get("origin")
            if origin in (
                "user",
                "assistant",
                "tool",
                "system",
                "compaction_summary",
                "system_notice",
                "contextual_user",
                "forked",
            ):
                message["origin"] = origin
            restored.append(message)
        self._session_turn_count = max_turn_n
        return restored

    def _write_history_snapshot(self, messages: list[dict[str, Any]]) -> None:
        """将当前消息列表写回 history.json 快照。

        压缩完成后调用，确保会话重建时能看到压缩后的状态。
        只保存 user/assistant/tool 消息，system prompt 由 __init__ 重新注入。
        """
        # 使用 session_dir 而非 work_dir，与 SessionManager 写入路径对齐
        session_dir = self._spec.session_dir or Path(str(self._spec.work_dir))
        history_path = (
            session_dir
            / ".aiasys"
            / "session"
            / ACTIVE_SESSION_STATE_DIR_NAME
            / HISTORY_SNAPSHOT_FILE_NAME
        )
        try:
            snapshot_messages = [
                msg
                for msg in messages
                if isinstance(msg, dict) and msg.get("role") in {"user", "assistant", "tool"}
            ]
            atomic_write_text(
                history_path,
                json.dumps(
                    {
                        "_schema_version": 1,
                        "_compaction_snapshot": True,
                        "messages": snapshot_messages,
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
            )
        except Exception:
            logger.warning("写入 history snapshot 失败: session=%s", self.session_id, exc_info=True)

    def _downgrade_historical_image_messages(
        self,
        messages: list[InternalMessage],
    ) -> list[InternalMessage]:
        downgraded_messages: list[InternalMessage] = []
        for message in messages:
            downgraded_content = downgrade_message_content_for_history(message.get("content"))
            if downgraded_content == message.get("content"):
                downgraded_messages.append(message)
                continue

            updated_message = dict(message)
            updated_message["content"] = downgraded_content
            downgraded_messages.append(updated_message)

        return downgraded_messages

    def _resolve_model_id(self) -> str:
        configured_default = str(self._spec.config.default_model or "").strip()
        manifest_model = self._agent_config.get("model")
        if isinstance(manifest_model, str) and manifest_model.strip():
            manifest_model_id = manifest_model.strip()
            configured_models = getattr(self._spec.config, "models", None)
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

    def _resolve_model_config(self) -> Any | None:
        model_id = self._resolve_model_id()
        if not model_id:
            return None
        return self._spec.config.models.get(model_id)

    def _resolve_temperature(self) -> float | None:
        model_config = self._model_config
        if model_config is None:
            return None
        return read_config_value(model_config, "temperature")

    def _resolve_max_tokens(self) -> int | None:
        """Resolve max_tokens from model config, with a reasonable default.

        When the model config does not specify max_tokens, return 16000.
        This prevents unexpected output truncation from providers that use
        a small default (e.g. stepfun's 4096).

        The actual client (OpenAI/Anthropic) may apply its own floor/ceiling.
        """
        model_config = self._model_config
        if model_config is None:
            return None
        configured = read_config_value(model_config, "max_tokens")
        if configured is not None:
            return configured
        return 16000

    def _resolve_request_options(self) -> LlmRequestOptions:
        model_config = self._model_config
        if model_config is None:
            return LlmRequestOptions()

        if bool(read_config_value(model_config, "thinking_disabled")):
            return LlmRequestOptions(thinking_disabled=True)

        capabilities = normalize_capabilities(read_config_value(model_config, "capabilities"))
        effort = normalize_thinking_effort(read_config_value(model_config, "thinking_effort"))
        thinking_enabled = (
            "always_thinking" in capabilities
            or "thinking" in capabilities
            or bool(getattr(self._spec.config, "default_thinking", False))
            or effort is not None
        )

        if not thinking_enabled:
            return LlmRequestOptions()

        effective_effort = effort or "high"
        return LlmRequestOptions(
            thinking_enabled=True,
            thinking_effort=effective_effort,
            thinking_budget_tokens=_THINKING_BUDGET_BY_EFFORT[effective_effort],
        )

    def _build_fork_messages(
        self,
        host_messages: list[dict[str, Any]],
        fork_turns: int | None,
    ) -> list[InternalMessage]:
        """根据 fork_turns 从 Host messages 构建子 Agent 的初始对话历史。

        fork_turns 语义:
        - None: 继承全部 Host 消息（除去 system prompt）
        - 0: 不继承任何消息
        - N > 0: 继承最后 N 轮 user/assistant 对话
        """
        if fork_turns == 0:
            return []

        # 过滤掉 system prompt，只保留 user/assistant/tool 消息
        filtered = [
            msg for msg in host_messages if isinstance(msg, dict) and msg.get("role") != "system"
        ]
        filtered = self._trim_incomplete_tool_call_history(filtered)

        result = filtered
        if fork_turns is not None:
            user_indices = [i for i, msg in enumerate(filtered) if msg.get("role") == "user"]
            if user_indices:
                start_idx = user_indices[-fork_turns] if fork_turns <= len(user_indices) else 0
                result = filtered[start_idx:]

        # 标记继承自 Host 的消息，便于后续区分来源。
        return [dict(msg, origin="forked") for msg in result]

    def _trim_incomplete_tool_call_history(
        self,
        messages: list[InternalMessage],
    ) -> list[InternalMessage]:
        """裁掉末尾未闭合的 assistant tool_calls，避免子 Agent 继承非法消息序列。"""
        pending_tool_call_ids: set[str] = set()
        pending_start_index: int | None = None

        for index, message in enumerate(messages):
            role = message.get("role")
            if role == "assistant":
                tool_calls = message.get("tool_calls")
                if isinstance(tool_calls, list):
                    tool_call_ids = {
                        str(item.get("id") or "").strip()
                        for item in tool_calls
                        if isinstance(item, dict) and str(item.get("id") or "").strip()
                    }
                    if tool_call_ids:
                        pending_tool_call_ids = tool_call_ids
                        pending_start_index = index
                        continue

            if role == "tool" and pending_tool_call_ids:
                tool_call_id = str(message.get("tool_call_id") or "").strip()
                if tool_call_id in pending_tool_call_ids:
                    pending_tool_call_ids.remove(tool_call_id)
                    if not pending_tool_call_ids:
                        pending_start_index = None

        if pending_tool_call_ids and pending_start_index is not None:
            return messages[:pending_start_index]
        return messages

    def _normalize_user_input(
        self, user_input: str | list[dict[str, Any]]
    ) -> list[InternalMessage]:
        if isinstance(user_input, str):
            return [{"role": "user", "content": user_input}]

        normalized_messages: list[InternalMessage] = []
        for item in user_input:
            if not isinstance(item, dict):
                normalized_messages.append({"role": "user", "content": str(item)})
                continue
            message = dict(item)
            message.setdefault("role", "user")
            normalized_messages.append(message)
        return normalized_messages

    def cancel(self) -> None:
        self._cancel_event.set()

    def is_active(self) -> bool:
        """Session 是否仍可用于对话（未关闭、未取消）。"""
        return not self._closed and not self._cancel_event.is_set()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        # 取消所有 pending 的能力确认请求
        await self._confirmation_manager.cancel_all("会话已关闭")
        # 关闭 MCP 连接
        for mcp_client in self._mcp_clients:
            try:
                await mcp_client.close()
            except Exception as exc:
                logger.warning("关闭 MCP client 失败: %s", exc)
        self._mcp_clients.clear()
        await self._client.aclose()

    async def __aenter__(self) -> "AiasysRuntimeSession":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
