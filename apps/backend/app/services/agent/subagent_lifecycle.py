"""
子 Agent 生命周期管理器。

把子 Agent 从 TaskTool 的一次性调用产物升级为可独立寻址、可继续对话的运行时对象：
- spawn_and_run：首次派发并运行，运行结束后保持 session 活跃
- send_input：向活跃子 Agent 追加输入并继续对话
- close_agent：显式关闭子 Agent
- resume_agent：从持久化存储恢复子 Agent 运行态
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.core.tool_result import ToolResult
from app.services.agent.runtime_backends.base import AgentRuntimeEvent
from app.services.agent.subagent_registry import (
    SubAgentRegistry,
    get_subagent_registry,
)
from app.services.agent.subagent_storage import SubAgentStorage

logger = logging.getLogger(__name__)


class SubAgentLifecycleManager:
    """管理子 Agent 的运行时生命周期。"""

    def __init__(self, registry: SubAgentRegistry | None = None) -> None:
        self._registry = registry or get_subagent_registry()

    async def run_subagent_session(
        self,
        *,
        subagent_session: Any,
        agent_id: str,
        subagent_name: str,
        prompt: str,
        storage: SubAgentStorage,
        keep_alive: bool = True,
        timeout_seconds: int = 300,
        workspace: Path | None = None,
        session_root: Path | None = None,
        user_id: str | None = None,
        host_session_id: str | None = None,
    ) -> AsyncGenerator[ToolResult, None]:
        """运行子 Agent 的首次 prompt() 循环，并管理其生命周期。

        与 TaskTool 解耦：TaskTool 负责创建 session/spec/storage，
        此方法负责执行 prompt() 循环、事件持久化、状态转换。

        Args:
            subagent_session: 已创建的 AiasysRuntimeSession
            agent_id: 子 Agent ID
            subagent_name: 子 Agent 名称/类型
            prompt: 初始任务指令
            storage: SubAgentStorage 实例
            keep_alive: 运行结束后是否保持 session 活跃
            timeout_seconds: 单步超时
            workspace, session_root, user_id, host_session_id: 用于恢复 contextvar

        Yields:
            ToolResult：中间流式事件（_streaming_event artifact）和最终结果
        """
        from app.services.history import (
            current_session_id,
            current_session_root,
            current_user_id,
            current_workspace,
        )

        # 同步主控 contextvar 到子 Agent
        _workspace_token = None
        _session_root_token = None
        _user_id_token = None
        _session_id_token = None
        try:
            if workspace:
                _workspace_token = current_workspace.set(workspace)
            if session_root:
                _session_root_token = current_session_root.set(session_root)
            if user_id:
                _user_id_token = current_user_id.set(user_id)
            _session_id_token = current_session_id.set(agent_id)
        except Exception:
            logger.warning("设置子 Agent contextvar 失败", exc_info=True)

        final_content = ""
        final_is_error = False
        meta = storage.read_meta()
        parent_tool_call_id = ""
        if isinstance(meta, dict):
            parent_tool_call_id = str(meta.get("last_task_id") or "")
        if not parent_tool_call_id:
            launch_spec = self._registry.get_launch_spec(agent_id)
            if isinstance(launch_spec, dict):
                parent_tool_call_id = str(launch_spec.get("parent_tool_call_id") or "")

        try:
            self._registry.set_status(agent_id, SubAgentRegistry.STATUS_RUNNING)
            prompt_iter = subagent_session.prompt(prompt).__aiter__()
            while True:
                try:
                    event = await asyncio.wait_for(prompt_iter.__anext__(), timeout=timeout_seconds)
                except StopAsyncIteration:
                    break

                enriched_event = self._annotate_event(
                    event,
                    agent_id=agent_id,
                    subagent_name=subagent_name,
                    parent_tool_call_id=parent_tool_call_id,
                )
                yield self._streaming_event(enriched_event)
                await self._persist_event(storage, enriched_event)
                final_content = self._extract_final_content(enriched_event, final_content)

        except asyncio.CancelledError:
            logger.warning("子 Agent 被取消: subagent=%s agent_id=%s", subagent_name, agent_id)
            final_is_error = True
            final_content = "子 Agent 执行被取消（可能是主会话断开或用户中止）"
            storage.update_status("cancelled")
            self._registry.set_status(agent_id, SubAgentRegistry.STATUS_CANCELLED)
            await self._registry.close(agent_id)
            raise
        except Exception as exc:
            logger.exception("子 Agent 执行异常: subagent=%s agent_id=%s", subagent_name, agent_id)
            final_is_error = True
            final_content = f"子 Agent 执行异常: {exc}"
            storage.update_status("failed")
            self._registry.set_status(agent_id, SubAgentRegistry.STATUS_FAILED)
        finally:
            try:
                await storage.flush()
            except Exception:
                logger.warning("子 Agent 缓冲刷盘失败", exc_info=True)
            # 重置子 Agent 的 contextvar
            try:
                if _workspace_token is not None:
                    current_workspace.reset(_workspace_token)
            except Exception:
                pass
            try:
                if _session_root_token is not None:
                    current_session_root.reset(_session_root_token)
            except Exception:
                pass
            try:
                if _user_id_token is not None:
                    current_user_id.reset(_user_id_token)
            except Exception:
                pass
            try:
                if _session_id_token is not None:
                    current_session_id.reset(_session_id_token)
            except Exception:
                pass

            if not keep_alive:
                await self.close_agent(agent_id)
            else:
                status = self._registry.get_status(agent_id)
                if status not in (
                    SubAgentRegistry.STATUS_CANCELLED,
                    SubAgentRegistry.STATUS_FAILED,
                    SubAgentRegistry.STATUS_CLOSED,
                ):
                    self._registry.set_status(agent_id, SubAgentRegistry.STATUS_IDLE)
                    if not final_is_error:
                        storage.update_status("idle")

        if not final_is_error:
            storage.update_status("idle" if keep_alive else "completed")
        if final_content:
            await storage.append_context_message(
                {
                    "role": "assistant",
                    "content": final_content,
                    "parent_tool_call_id": parent_tool_call_id,
                }
            )
        try:
            await storage.flush()
        except Exception:
            logger.warning("子 Agent 收尾刷盘失败", exc_info=True)

        yield ToolResult(
            content=final_content or "子 Agent 执行完成",
            is_error=final_is_error,
        )

    async def send_input(
        self,
        agent_id: str,
        message: str,
        *,
        timeout_seconds: int = 300,
    ) -> AsyncGenerator[AgentRuntimeEvent, None]:
        """向活跃子 Agent 追加输入并继续对话。

        Args:
            agent_id: 子 Agent ID
            message: 用户输入文本
            timeout_seconds: 单步超时

        Yields:
            AgentRuntimeEvent：子 Agent 产生的事件
        """
        session = self._registry.get(agent_id)
        if session is None or not session.is_active():
            logger.warning("尝试向未注册或已关闭的子 Agent 发送消息: agent_id=%s", agent_id)
            yield AgentRuntimeEvent(
                kind="system_warning",
                text=f"子 Agent {agent_id} 未运行或已关闭",
            )
            return

        if not self._registry.is_idle(agent_id):
            yield AgentRuntimeEvent(
                kind="system_warning",
                text=f"子 Agent {agent_id} 当前不在可输入状态",
            )
            return

        # 恢复 storage 并记录用户消息
        meta = self._registry.get_launch_spec(agent_id)
        if meta is None:
            yield AgentRuntimeEvent(
                kind="system_warning",
                text=f"子 Agent {agent_id} 缺少 launch_spec，无法继续对话",
            )
            return

        from app.services.history import (
            current_session_id,
            current_session_root,
            current_user_id,
            current_workspace,
        )

        user_id = str(meta.get("user_id") or "")
        host_session_id = str(meta.get("host_session_id") or "")
        workspace = Path(str(meta.get("workspace") or "")) if meta.get("workspace") else None
        session_root = (
            Path(str(meta.get("session_root") or "")) if meta.get("session_root") else None
        )
        storage = SubAgentStorage(user_id, host_session_id, agent_id)
        parent_tool_call_id = meta.get("parent_tool_call_id", "")
        await storage.append_context_message(
            {
                "role": "user",
                "content": message,
                "parent_tool_call_id": parent_tool_call_id,
            }
        )

        # 设置 contextvar，确保文件工具等能正确解析路径
        _workspace_token = None
        _session_root_token = None
        _user_id_token = None
        _session_id_token = None
        try:
            if workspace:
                _workspace_token = current_workspace.set(workspace)
            if session_root:
                _session_root_token = current_session_root.set(session_root)
            if user_id:
                _user_id_token = current_user_id.set(user_id)
            _session_id_token = current_session_id.set(agent_id)
        except Exception:
            logger.warning("设置子 Agent contextvar 失败", exc_info=True)

        subagent_name = str(meta.get("subagent_type") or meta.get("subagent_name") or "subagent")
        self._registry.set_status(agent_id, SubAgentRegistry.STATUS_RUNNING)
        final_content = ""
        try:
            async for event in self._run_prompt_loop(
                session,
                agent_id,
                subagent_name,
                message,
                storage,
                timeout_seconds,
            ):
                yield event
                final_content = self._extract_final_content(event, final_content)

            if final_content:
                await storage.append_context_message(
                    {
                        "role": "assistant",
                        "content": final_content,
                        "parent_tool_call_id": parent_tool_call_id,
                    }
                )
        except Exception as exc:
            logger.exception("子 Agent 继续对话异常: agent_id=%s", agent_id)
            storage.update_status("failed")
            self._registry.set_status(agent_id, SubAgentRegistry.STATUS_FAILED)
            yield AgentRuntimeEvent(
                kind="system_warning",
                text=f"子 Agent 继续对话异常: {exc}",
            )
        finally:
            try:
                await storage.flush()
            except Exception:
                logger.warning("子 Agent 缓冲刷盘失败", exc_info=True)

            # 重置 contextvar
            for var, token in (
                (current_workspace, _workspace_token),
                (current_session_root, _session_root_token),
                (current_user_id, _user_id_token),
                (current_session_id, _session_id_token),
            ):
                if token is not None:
                    try:
                        var.reset(token)
                    except Exception:
                        pass

            status = self._registry.get_status(agent_id)
            if status == SubAgentRegistry.STATUS_RUNNING:
                self._registry.set_status(agent_id, SubAgentRegistry.STATUS_IDLE)
                storage.update_status("idle")

    async def close_agent(self, agent_id: str) -> bool:
        """显式关闭子 Agent。"""
        launch_spec = self._registry.get_launch_spec(agent_id)
        closed = await self._registry.close(agent_id)
        if closed and launch_spec:
            try:
                user_id = str(launch_spec.get("user_id") or "")
                host_session_id = str(launch_spec.get("host_session_id") or "")
                storage = SubAgentStorage(user_id, host_session_id, agent_id)
                storage.update_status("closed")
            except Exception:
                logger.warning("更新子 Agent 关闭状态失败: agent_id=%s", agent_id, exc_info=True)
        return closed

    async def resume_agent(
        self,
        user_id: str,
        host_session_id: str,
        agent_id: str,
    ) -> bool:
        """从持久化存储恢复子 Agent 运行态。

        读取 meta.json / context.jsonl，重建 AiasysRuntimeSession 并注册到运行时表。
        """
        storage = SubAgentStorage(user_id, host_session_id, agent_id)
        meta = storage.read_meta()
        if meta is None:
            logger.warning("恢复子 Agent 失败，meta.json 不存在: %s", agent_id)
            return False

        launch_spec = meta.get("launch_spec") or {}
        if not launch_spec:
            logger.warning("恢复子 Agent 失败，launch_spec 不存在: %s", agent_id)
            return False

        if self._registry.is_active(agent_id):
            logger.warning("恢复子 Agent 失败，该 agent 已在内存中活跃: %s", agent_id)
            return False

        llm_config_data = launch_spec.get("llm_config")
        if not llm_config_data:
            logger.warning("恢复子 Agent 失败，缺少 llm_config: %s", agent_id)
            return False

        from app.core.workspace_path import WorkspacePath
        from app.services.agent.models.llm_config import AiasysLlmConfig
        from app.services.agent.runtime_backends.aiasys.backend import AiasysRuntimeBackend
        from app.services.agent.runtime_backends.base import RuntimeSessionCreateSpec

        try:
            llm_config = AiasysLlmConfig(**llm_config_data)
        except Exception as exc:
            logger.warning("恢复子 Agent 失败，LLM 配置解析错误: %s %s", agent_id, exc)
            return False

        agent_file = Path(str(launch_spec.get("agent_file") or ""))
        if not agent_file.exists():
            logger.warning("恢复子 Agent 失败，agent TOML 不存在: %s", agent_file)
            return False

        session_root = Path(str(launch_spec.get("session_root") or ""))
        child_skills_dir = launch_spec.get("child_skills_dir")
        collaboration_policy = launch_spec.get("collaboration_policy") or {}

        # 尝试从活跃的 Host session 获取 parent_registry
        # resume 时 parent_registry 是运行时对象，无法从持久化恢复，
        # 但如果 Host session 仍然活跃，可以直接引用其 tool_registry
        parent_registry = None
        try:
            import app.services.agent as agent_service_module

            agent_service = getattr(agent_service_module, "agent_service", None)
            if agent_service is not None:
                host_session_key = f"{user_id}/{host_session_id}"
                host_session = agent_service._active_sessions.get(host_session_key)
                if host_session is not None and hasattr(host_session, "_tool_registry"):
                    parent_registry = host_session._tool_registry
                    logger.debug(
                        "恢复子 Agent 时从 Host session 获取到 parent_registry: %s",
                        agent_id,
                    )
        except Exception:
            logger.debug("获取 Host session 的 parent_registry 失败", exc_info=True)

        spec = RuntimeSessionCreateSpec(
            work_dir=WorkspacePath(str(session_root)),
            session_id=agent_id,
            user_id=user_id,
            config=llm_config,
            agent_file=agent_file,
            skills_dir=WorkspacePath(str(child_skills_dir)) if child_skills_dir else None,
            authorization_mode=str(launch_spec.get("authorization_mode") or "smart"),
            yolo=bool(launch_spec.get("yolo", False)),
            mcp_configs=launch_spec.get("mcp_configs"),
            is_subagent=True,
            parent_registry=parent_registry,
            tool_policy=str(launch_spec.get("tool_policy") or "inherit"),
            fork_turns=0,
            fork_messages=None,
            host_session_id=host_session_id,
            parent_agent_id=launch_spec.get("parent_agent_id"),
            agent_path=str(launch_spec.get("agent_path") or "/root"),
            agent_max_depth=int(collaboration_policy.get("max_depth", 1)),
            allow_subagent_spawn=False,
            collaboration_policy=collaboration_policy,
            budget=None,
            memory_enabled=False,
        )

        backend = AiasysRuntimeBackend()
        try:
            subagent_session = await backend.create_session(spec)
        except Exception as exc:
            logger.warning("恢复子 Agent 失败，创建 session 错误: %s %s", agent_id, exc)
            return False

        # 从 context.jsonl 加载历史消息
        context_messages: list[dict[str, Any]] = []
        if storage.context_file.exists():
            text = storage.context_file.read_text(encoding="utf-8")
            for line in text.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line)
                    if isinstance(msg, dict):
                        context_messages.append(msg)
                except json.JSONDecodeError:
                    continue

        # 保留系统提示词，替换为 context.jsonl 中的对话历史
        system_messages = [m for m in subagent_session.messages if m.get("role") == "system"]
        subagent_session.messages = system_messages + context_messages

        await self._registry.register(
            agent_id,
            subagent_session,
            host_session_id=host_session_id,
            launch_spec=launch_spec,
        )
        self._registry.set_status(agent_id, SubAgentRegistry.STATUS_IDLE)
        storage.update_status("idle")
        logger.info("子 Agent 已恢复为可对话状态: agent_id=%s", agent_id)
        return True

    async def _run_prompt_loop(
        self,
        session: Any,
        agent_id: str,
        subagent_name: str,
        prompt: str,
        storage: SubAgentStorage,
        timeout_seconds: int,
    ) -> AsyncGenerator[AgentRuntimeEvent, None]:
        """执行一次 prompt() 循环，持久化并产出事件。"""
        meta = storage.read_meta()
        parent_tool_call_id = ""
        if isinstance(meta, dict):
            parent_tool_call_id = str(meta.get("last_task_id") or "")
        prompt_iter = session.prompt(prompt).__aiter__()
        while True:
            try:
                event = await asyncio.wait_for(prompt_iter.__anext__(), timeout=timeout_seconds)
            except StopAsyncIteration:
                break

            enriched_event = self._annotate_event(
                event,
                agent_id=agent_id,
                subagent_name=subagent_name,
                parent_tool_call_id=parent_tool_call_id,
            )
            await self._persist_event(storage, enriched_event)
            yield enriched_event

    def _annotate_event(
        self,
        event: AgentRuntimeEvent,
        *,
        agent_id: str,
        subagent_name: str,
        parent_tool_call_id: str = "",
    ) -> AgentRuntimeEvent:
        """给事件打上子 Agent 归属标记。

        兼容 _TurnBegin 等非 dataclass 标记对象：只保留 AgentRuntimeEvent
        支持的字段，避免注入多余关键字参数。
        """
        if isinstance(event, AgentRuntimeEvent):
            payload = asdict(event)
        else:
            payload = {"kind": getattr(event, "kind", None) or "data"}
        payload["agent_id"] = str(payload.get("agent_id") or agent_id)
        payload["subagent_type"] = str(payload.get("subagent_type") or subagent_name)
        payload["subagent_name"] = str(payload.get("subagent_name") or subagent_name)
        if parent_tool_call_id:
            payload["parent_tool_call_id"] = str(
                payload.get("parent_tool_call_id") or parent_tool_call_id
            )
        # 过滤 AgentRuntimeEvent 不支持的字段（如 _TurnBegin 的 type）
        allowed = {f.name for f in AgentRuntimeEvent.__dataclass_fields__.values()}
        payload = {k: v for k, v in payload.items() if k in allowed}
        return AgentRuntimeEvent(**payload)

    def _streaming_event(self, event: AgentRuntimeEvent) -> ToolResult:
        """将 AgentRuntimeEvent 包装为流式 ToolResult。"""
        return ToolResult(
            content="",
            is_error=False,
            artifacts=[{"_streaming_event": asdict(event)}],
        )

    async def _persist_event(
        self,
        storage: SubAgentStorage,
        event: AgentRuntimeEvent,
    ) -> None:
        """将事件持久化到 wire.jsonl 和 context.jsonl。

        每次事件都 flush，确保独立 SSE 端点能实时 tail 到最新内容。
        """
        await storage.append_wire_agent_runtime_event(asdict(event))
        await storage.flush()

        if event.kind == "tool_call":
            msg = {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": event.tool_call_id,
                        "type": "function",
                        "function": {
                            "name": event.tool_name,
                            "arguments": json.dumps(event.arguments or {}),
                        },
                    }
                ],
            }
            await storage.append_context_message(msg)
        elif event.kind == "tool_result":
            msg = {
                "role": "tool",
                "tool_call_id": event.tool_call_id,
                "content": event.content or "",
            }
            await storage.append_context_message(msg)

    def _extract_final_content(
        self,
        event: AgentRuntimeEvent,
        current: str,
    ) -> str:
        """从事件中累加最新文本结果。

        流式 content 事件是文本 delta，需要累加才能得到完整回复；
        非 text 类型（如 think）不参与最终消息内容。
        """
        if event.kind == "content" and event.content_type == "text" and event.text:
            return current + event.text
        return current


# 全局单例
_subagent_lifecycle_manager: SubAgentLifecycleManager | None = None


def get_subagent_lifecycle_manager() -> SubAgentLifecycleManager:
    """获取全局子 Agent 生命周期管理器实例。"""
    global _subagent_lifecycle_manager
    if _subagent_lifecycle_manager is None:
        _subagent_lifecycle_manager = SubAgentLifecycleManager()
    return _subagent_lifecycle_manager
