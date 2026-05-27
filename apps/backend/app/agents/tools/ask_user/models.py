"""
AskUser 工具数据模型
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AskUserType(str, Enum):
    """询问类型"""

    CONFIRM = "confirm"  # 是/否确认
    INPUT = "input"  # 文本输入
    SELECT = "select"  # 单选
    MULTI_SELECT = "multi_select"  # 多选
    CHECKPOINT_REVIEW = "checkpoint_review"  # 检查点评审


class AskUserRequest(BaseModel):
    """向用户发起的询问请求"""

    request_id: str = Field(description="请求唯一标识")
    type: AskUserType = Field(description="询问类型")
    title: str = Field(description="标题")
    message: str = Field(description="详细消息")

    # 可选配置
    placeholder: str | None = Field(None, description="输入框占位符（INPUT类型）")
    options: list[dict[str, Any]] | None = Field(
        None, description="选项列表（SELECT/MULTI_SELECT类型）"
    )
    default_value: Any | None = Field(None, description="默认值")
    timeout: int = Field(300, description="超时时间（秒），默认300秒，最大600秒", ge=10, le=600)

    # 工具上下文
    tool_call_id: str | None = Field(None, description="关联的工具调用ID")

    # 检查点评审专用数据
    checkpoint_data: dict[str, Any] | None = Field(
        None, description="检查点评审数据（CHECKPOINT_REVIEW类型）"
    )

    # 时间戳
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(), description="请求创建时间"
    )


class AskUserResponse(BaseModel):
    """用户响应"""

    request_id: str = Field(description="对应请求的ID")
    approved: bool = Field(description="是否批准/确认")
    value: Any | None = Field(None, description="用户输入的值")


@dataclass
class AskUserPendingItem:
    """待处理 AskUser 请求条目。"""

    request: AskUserRequest
    session_id: str
    user_id: str
    future: asyncio.Future
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class AskUserStore:
    """
    AskUser 请求存储和管理

    单例模式，管理所有待处理的请求
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._requests: dict[str, AskUserPendingItem] = {}
        return cls._instance

    def create_request(
        self,
        request: AskUserRequest,
        session_id: str,
        user_id: str,
    ) -> asyncio.Future:
        """创建新的请求，返回 Future 用于等待"""
        future = asyncio.get_event_loop().create_future()
        self._requests[request.request_id] = AskUserPendingItem(
            request=request,
            session_id=session_id,
            user_id=user_id,
            future=future,
        )
        return future

    def resolve_request(self, request_id: str, response: AskUserResponse) -> bool:
        """
        解析请求，设置 Future 结果

        Returns:
            bool: 是否成功解析
        """
        item = self._requests.get(request_id)
        if item is None:
            return False

        if item.future.done():
            return False

        item.future.set_result(response)
        return True

    def remove_request(self, request_id: str) -> None:
        """移除请求"""
        self._requests.pop(request_id, None)

    def get_request(self, request_id: str) -> AskUserPendingItem | None:
        """获取指定请求的待处理条目。"""
        return self._requests.get(request_id)

    def cancel_by_session(self, session_id: str, user_id: str) -> int:
        """取消指定会话的所有待处理请求。"""
        to_remove: list[str] = []
        for request_id, item in self._requests.items():
            if item.session_id == session_id and item.user_id == user_id:
                if not item.future.done():
                    item.future.cancel()
                to_remove.append(request_id)

        for request_id in to_remove:
            self._requests.pop(request_id, None)

        return len(to_remove)

    def get_pending_requests(self) -> list[str]:
        """获取待处理的请求 ID 列表"""
        return [req_id for req_id, item in self._requests.items() if not item.future.done()]

    def list_pending(
        self,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """列出待处理请求，可按会话和用户过滤。"""
        result: list[dict[str, Any]] = []
        for request_id, item in self._requests.items():
            if item.future.done():
                continue
            if session_id and item.session_id != session_id:
                continue
            if user_id and item.user_id != user_id:
                continue
            result.append(
                {
                    "request_id": request_id,
                    "session_id": item.session_id,
                    "user_id": item.user_id,
                    "created_at": item.created_at,
                    "request": item.request.model_dump(),
                }
            )
        return result

    @property
    def pending_count(self) -> int:
        """待处理请求数量"""
        return len(self.get_pending_requests())
