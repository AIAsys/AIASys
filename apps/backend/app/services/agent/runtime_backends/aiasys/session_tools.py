"""Session tool handling mixin。

从 session.py 提取的工具上下文、工具调用构建、循环检测方法。
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from app.models.session import SessionPlanState
from app.services.history import (
    current_session_id,
    current_session_root,
    current_user_id,
    current_workspace,
)
from app.services.session import PLAN_MODE_ALLOWED_TOOL_NAMES, SessionTaskPlanStore

from .session_utils import parse_tool_arguments_json

logger = logging.getLogger(__name__)


class SessionToolsMixin:
    """工具相关方法，供 AiasysRuntimeSession 混入。"""

    # 渐进式循环检测配置
    LOOP_WARN1_THRESHOLD = 3  # 第 3 次：轻警告
    LOOP_WARN2_THRESHOLD = 5  # 第 5 次：强警告
    LOOP_BLOCK_THRESHOLD = 8  # 第 8 次：阻塞（升级自原 6）
    LOOP_SIMILARITY_RATIO = 1.0  # 仅完全相同才累计计数

    def _tool_context(self) -> dict[str, Any]:
        workspace = current_workspace.get()
        session_root = current_session_root.get()
        user_id = current_user_id.get()
        session_id = current_session_id.get() or self.session_id

        resolved_session_root = Path(str(session_root or self._spec.work_dir))
        resolved_workspace = Path(str(workspace or resolved_session_root))

        return {
            "workspace": resolved_workspace,
            "session_root": resolved_session_root,
            "session_id": session_id,
            "user_id": user_id,
            "agent_config": self._agent_config,
            "llm_config": self._spec.config,
            "mcp_configs": self.mcp_configs,
            "messages": self.messages,
            "parent_registry": self._tool_registry,
            "host_session_id": self._spec.host_session_id or session_id,
            "parent_agent_id": self._spec.parent_agent_id,
            "agent_path": self._spec.agent_path,
            "agent_max_depth": self._spec.agent_max_depth,
            "allow_subagent_spawn": self._spec.allow_subagent_spawn,
            "is_subagent": self._spec.is_subagent,
            "collaboration_policy": self._spec.collaboration_policy,
            "allowed_create_subagent_scopes": ["workspace"],
            "budget": self.budget,
            "authorization_mode": self._spec.authorization_mode,
            "yolo": self._spec.yolo,
        }

    def _get_plan_state(self) -> SessionPlanState | None:
        """读取当前会话的 plan state，失败时返回 None。"""
        session_root = Path(str(current_session_root.get() or self._spec.work_dir))
        try:
            return SessionTaskPlanStore(session_root).read_plan_state()
        except Exception:
            logger.debug("读取 Plan Mode 状态失败", exc_info=True)
            return None

    def _get_plan_file_path(self) -> str | None:
        """返回当前计划文件的绝对路径（若存在）。"""
        state = self._get_plan_state()
        if state is None or not state.current_plan_file:
            return None
        session_root = Path(str(current_session_root.get() or self._spec.work_dir))
        return str(
            (
                session_root / ".aiasys" / "session" / "_active" / "plans" / state.current_plan_file
            ).resolve()
        )

    def _is_plan_mode_active(self) -> bool:
        state = self._get_plan_state()
        return state is not None and state.mode == "active"

    def _plan_mode_allowed_tools(self) -> set[str]:
        return set(PLAN_MODE_ALLOWED_TOOL_NAMES)

    def _prepare_tools_for_model(self) -> list[dict[str, Any]]:
        if not self._is_plan_mode_active():
            return self._tool_strategy.prepare_tools(self._tool_registry)
        return self._tool_strategy.prepare_tools_filtered(
            self._tool_registry,
            self._plan_mode_allowed_tools(),
        )

    def _is_tool_allowed_in_current_mode(self, tool_name: str) -> bool:
        # Plan Mode 的硬拦截已下沉到 CapabilityAuthorizationService，
        # 此处保留仅作为快速短路，避免向模型暴露明显不可用的工具。
        if not self._is_plan_mode_active():
            return True
        resolved_tool_name = self._tool_registry._aliases.get(tool_name, tool_name)
        tool = self._tool_registry._tools.get(resolved_tool_name)
        runtime_name = (
            getattr(tool, "name", resolved_tool_name) if tool is not None else resolved_tool_name
        )
        return str(runtime_name) in self._plan_mode_allowed_tools()

    def _restore_pre_plan_permission_mode(self) -> None:
        """退出 Plan Mode 后恢复之前的权限模式，并清空 metadata 中保存的值。"""
        session_root = Path(str(current_session_root.get() or self._spec.work_dir))
        try:
            store = SessionTaskPlanStore(session_root)
            plan_state = store.read_plan_state()
            pre_mode = plan_state.pre_plan_permission_mode
            if pre_mode:
                self._spec.authorization_mode = pre_mode
                logger.debug(
                    "已恢复 Plan Mode 前的权限模式: %s",
                    pre_mode,
                )
            # 清空保存值，避免重复恢复或泄漏到后续会话
            store.write_plan_state(pre_plan_permission_mode=None)
        except Exception:
            logger.debug("恢复 Plan Mode 前权限模式失败", exc_info=True)

    @staticmethod
    def _deterministic_tool_call_id(tool_name: str, arguments: str, index: int = 0) -> str:
        """基于内容生成确定性 tool call ID，避免随机 UUID 破坏 prefix cache。"""
        seed = f"{tool_name}:{arguments}:{index}"
        digest = hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()[:12]
        return f"call_{digest}"

    @staticmethod
    def _normalize_loop_detection_arguments(arguments: Any) -> str:
        """把工具参数转成稳定文本，避免 SequenceMatcher 读取映射索引。"""
        if isinstance(arguments, str):
            return arguments
        try:
            return json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)
        except TypeError:
            return str(arguments)

    def _build_openai_tool_calls(
        self,
        aggregated_tool_calls: dict[int, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        tool_calls: list[dict[str, Any]] = []
        for index in sorted(aggregated_tool_calls):
            item = aggregated_tool_calls[index]
            tool_name = str(item.get("name") or "").strip()
            arguments_text = item.get("arguments_text") or "{}"
            tool_id = item.get("id") or self._deterministic_tool_call_id(
                tool_name, arguments_text, index
            )
            if not tool_name:
                logger.warning("忽略缺少 tool_name 的 tool_call: index=%s", index)
                continue
            parsed_arguments, parse_error = self._safe_parse_arguments(tool_name, arguments_text)
            tool_calls.append(
                {
                    "id": tool_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": arguments_text,
                    },
                    "arguments": parsed_arguments,
                    "_parse_error": parse_error,
                }
            )
        return tool_calls

    def _safe_parse_arguments(
        self, tool_name: str, arguments_text: str
    ) -> tuple[dict[str, Any], str | None]:
        parsed, parse_error = parse_tool_arguments_json(arguments_text)
        if parse_error:
            schema = self._tool_registry.get_tool(tool_name)
            schema_hint = schema.parameter_schema() if schema is not None else {"type": "object"}
            error_msg = (
                f"Invalid JSON arguments for tool '{tool_name}'. "
                f"Expected schema: {json.dumps(schema_hint, ensure_ascii=False)}"
            )
            return {}, error_msg
        return parsed, None

    def _check_loop_detection(self, tool_name: str, arguments: Any = "") -> str | None:
        """渐进式循环检测：先警告，后阻塞。

        规则：
        1. 切换到不同工具时，重置之前工具的计数
        2. 参数与上次调用相似度 >= LOOP_SIMILARITY_RATIO 才累计计数
        3. 参数明显不同时重置计数（说明是有意义的连续调用）
        4. 连续相似调用达到 WARN1/WARN2/BLOCK 阈值时分别处理
        """
        if not getattr(self, "_loop_guard_enabled", True):
            return None

        for name in list(self._consecutive_tool_counts):
            if name != tool_name:
                self._consecutive_tool_counts[name] = 0
                self._previous_tool_args.pop(name, None)

        normalized_arguments = self._normalize_loop_detection_arguments(arguments)
        prev_args = self._previous_tool_args.get(tool_name, "")
        current_count = self._consecutive_tool_counts.get(tool_name, 0)

        # 比较参数相似度
        if prev_args and normalized_arguments:
            similarity = difflib.SequenceMatcher(None, prev_args, normalized_arguments).ratio()
            if similarity < self.LOOP_SIMILARITY_RATIO:
                # 参数差异大，说明是不同的合理调用
                self._consecutive_tool_counts[tool_name] = 1
                self._previous_tool_args[tool_name] = normalized_arguments
                return None

        self._consecutive_tool_counts[tool_name] = current_count + 1
        self._previous_tool_args[tool_name] = normalized_arguments
        count = self._consecutive_tool_counts[tool_name]

        if count >= self.LOOP_BLOCK_THRESHOLD:
            return (
                "<system-reminder>\n"
                f"已连续 {count} 次调用 {tool_name} 且参数高度相似。"
                "强制中断以防止死循环。请向用户报告当前阻塞原因，"
                "并建议替代方案。\n"
                "</system-reminder>"
            )
        if count >= self.LOOP_WARN2_THRESHOLD:
            return (
                "<system-reminder>\n"
                f"第 {count} 次重复调用 {tool_name}。继续重复不会产生不同结果。"
                "请立即停止重试，分析失败原因，向用户报告。\n"
                "</system-reminder>"
            )
        if count >= self.LOOP_WARN1_THRESHOLD:
            return (
                "<system-reminder>\n"
                f"这已经是第 {count} 次用相同参数调用 {tool_name}。"
                "请检查是否需要调整策略或尝试其他方法。\n"
                "</system-reminder>"
            )
        return None

    def _reset_loop_counter(self, tool_name: str) -> None:
        """工具调用成功后重置该工具的循环计数。"""
        self._consecutive_tool_counts.pop(tool_name, None)
        self._previous_tool_args.pop(tool_name, None)
