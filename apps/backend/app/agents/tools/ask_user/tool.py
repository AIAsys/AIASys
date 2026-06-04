"""
AskUser 工具实现

允许 Agent 向用户发起确认或输入请求，暂停执行等待用户响应
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.agents.tools.ask_user.models import (
    AskUserRequest,
    AskUserResponse,
    AskUserStore,
    AskUserType,
)
from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.history import current_session_id, current_user_id

logger = logging.getLogger(__name__)


class AskUserParams(BaseModel):
    """AskUser 工具参数"""

    type: AskUserType = Field(
        default=AskUserType.CONFIRM,
        description="询问类型: confirm(确认), input(输入), select(单选), multi_select(多选)",
    )
    title: str = Field(
        description="询问标题，简洁明了",
    )
    message: str = Field(
        description="详细消息说明",
    )
    placeholder: str = Field(
        default=None,
        description="输入框提示文字（仅input类型）",
    )
    options: list = Field(
        default=None,
        description="选项列表（仅select/multi_select类型）",
    )
    default_value: str = Field(
        default=None,
        description="默认值",
    )
    timeout: int = Field(
        default=300,
        description="等待超时时间（秒），默认300秒，最大600秒",
        ge=10,
        le=600,
    )


class AskUser(AiasysTool):
    """
    AskUser 工具 - 允许 Agent 向用户发起确认或输入请求

    使用方式:
        1. Agent 调用 AskUser 工具
        2. 工具发送 SSE 事件给前端
        3. 工具阻塞等待用户响应
        4. 用户响应后返回结果给 Agent
    """

    # 类属性 - 供 SDK 使用
    name: str = "AskUser"
    description: str = """
向用户发起确认或输入请求。

当需要用户确认敏感操作、提供额外信息或做出选择时使用此工具。
工具会暂停执行并等待用户响应。

支持四种类型：
- confirm: 是/否确认框，返回 approved: true/false
- input: 文本输入框，返回用户输入的字符串
- select: 单选列表，返回选中的选项值
- multi_select: 多选列表，返回选中的选项值列表

注意：此工具会阻塞执行，直到用户响应或超时（默认300秒）。
"""
    params: type[BaseModel] = AskUserParams

    # 类变量 - 按 session_id 存储事件发送器，避免跨会话串流
    _event_senders: dict[str, Any] = {}

    def __init__(self):
        """初始化 - 无参数，避免 SDK 依赖注入问题"""
        super().__init__()
        self._store = AskUserStore()

    @classmethod
    def set_event_sender(cls, session_id: str, sender) -> None:
        """设置指定会话的事件发送函数。"""
        cls._event_senders[session_id] = sender

    @classmethod
    def clear_event_sender(cls, session_id: str) -> None:
        """清理指定会话的事件发送函数。会话关闭时由调用方触发。"""
        cls._event_senders.pop(session_id, None)

    @classmethod
    async def emit_request_for_session(
        cls,
        session_id: str,
        request: AskUserRequest,
    ) -> bool:
        """在非 AskUser 工具调用上下文中，主动向指定会话发出 AskUser 请求。"""
        sender = cls._event_senders.get(session_id)
        if sender is None:
            return False

        event = {
            "type": "ask_user_request",
            "request": request.model_dump(),
        }
        try:
            await sender(event)
            return True
        except Exception as exc:
            logger.warning("发送 AskUser 事件失败: %s", exc)
            return False

    def _build_request(self, **kwargs: Any) -> AskUserRequest:
        """根据 kwargs 构建 AskUserRequest。"""
        tool_call_id = kwargs.pop("tool_call_id", None)
        params = AskUserParams.model_validate(kwargs)
        request_id = str(uuid.uuid4())

        options_list = None
        if params.options:
            options_list = [{"label": opt, "value": opt} for opt in params.options]

        return AskUserRequest(
            request_id=request_id,
            type=params.type,
            title=params.title,
            message=params.message,
            placeholder=params.placeholder,
            options=options_list,
            default_value=params.default_value,
            timeout=params.timeout,
            tool_call_id=tool_call_id,
        )

    async def invoke_stream(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        """流式执行 AskUser 工具，先 yield ask_user_request 事件再等待响应。"""
        import json

        request = self._build_request(**kwargs)

        # 通过 runtime 事件流向前端发送 ask_user_request
        yield ToolResult(
            content="",
            is_error=False,
            artifacts=[
                {
                    "_streaming_event": {
                        "kind": "ask_user_request",
                        "content": json.dumps(request.model_dump()),
                    }
                }
            ],
        )

        session_id = current_session_id.get() or "unknown-session"
        user_id = current_user_id.get() or "unknown-user"

        future = self._store.create_request(
            request=request,
            session_id=session_id,
            user_id=user_id,
        )

        try:
            response: AskUserResponse = await asyncio.wait_for(future, timeout=request.timeout)
            if response.approved:
                yield ToolResult(content=f"用户已确认: {response.value}")
            else:
                yield ToolResult(content="用户已取消", is_error=True)
        except asyncio.TimeoutError:
            yield ToolResult(
                content=f"等待用户响应超时（{request.timeout}秒）",
                is_error=True,
            )
        finally:
            self._store.remove_request(request.request_id)

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """
        执行 AskUser 工具（委托给 invoke_stream 取最终结果）。

        Args:
            ctx: 上下文信息
            **kwargs: 工具参数

        Returns:
            ToolResult
        """
        final_result: ToolResult | None = None
        async for result in self.invoke_stream(ctx, **kwargs):
            final_result = result
        return final_result or ToolResult(content="无结果", is_error=True)

    async def _send_event(self, request: AskUserRequest) -> None:
        """发送 SSE 事件给前端"""
        session_id = current_session_id.get()
        if not session_id:
            return

        sender = AskUser._event_senders.get(session_id)
        if sender is None:
            return

        event = {
            "type": "ask_user_request",
            "request": request.model_dump(),
        }

        try:
            await sender(event)
        except Exception:
            logger.error("发送 AskUser 事件失败，前端可能无对话框", exc_info=True)

    async def resolve(self, request_id: str, approved: bool, value: Any = None) -> bool:
        """
        解析请求（由前端 API 调用）

        Returns:
            bool: 是否成功解析
        """
        response = AskUserResponse(
            request_id=request_id,
            approved=approved,
            value=value,
        )
        return self._store.resolve_request(request_id, response)


# 全局实例（单例）
_ask_user_tool = None


def get_ask_user_tool(session_id: str | None = None, event_sender=None):
    """
    获取 AskUser 单例

    Args:
        event_sender: SSE 事件发送函数

    Returns:
        AskUser: 工具实例
    """
    global _ask_user_tool
    if _ask_user_tool is None:
        _ask_user_tool = AskUser()
    if event_sender is not None:
        effective_session_id = session_id or current_session_id.get()
        if effective_session_id:
            AskUser.set_event_sender(effective_session_id, event_sender)
    return _ask_user_tool


def reset_ask_user_tool() -> None:
    """重置工具实例（用于测试）"""
    global _ask_user_tool
    _ask_user_tool = None
