from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from copy import deepcopy
from typing import Any, ClassVar

from pydantic import BaseModel

from app.core.tool_result import ToolResult


class AiasysTool(ABC):
    """AIASys 内部统一 tool 协议。"""

    name: ClassVar[str]
    description: ClassVar[str]
    parameters: ClassVar[dict[str, Any]] = {}
    params: ClassVar[type[BaseModel] | None] = None

    # 风险元数据（用于 CapabilityAuthorizationService 决策）
    risk_level: ClassVar[str] = "medium"  # readonly | low | medium | high | critical
    effect_scope: ClassVar[str] = "workspace"  # workspace | global | session | external
    side_effect: ClassVar[bool] = True
    # 兼容旧 dangerous 标记
    dangerous: ClassVar[bool] = False

    @classmethod
    def parameter_schema(cls) -> dict[str, Any]:
        if cls.parameters:
            return deepcopy(cls.parameters)

        params_model = getattr(cls, "params", None)
        if (
            isinstance(params_model, type)
            and issubclass(params_model, BaseModel)
            and params_model is not BaseModel
        ):
            return params_model.model_json_schema()

        return {
            "type": "object",
            "properties": {},
        }

    @classmethod
    def validate_arguments(cls, arguments: dict[str, Any]) -> BaseModel | dict[str, Any]:
        params_model = getattr(cls, "params", None)
        if (
            isinstance(params_model, type)
            and issubclass(params_model, BaseModel)
            and params_model is not BaseModel
        ):
            return params_model.model_validate(arguments)
        return dict(arguments)

    @abstractmethod
    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """执行 tool 并返回 AIASys-native 结果。"""

    async def invoke_stream(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[ToolResult, None]:
        """流式执行 tool。

        默认实现直接委托给 invoke() 并 yield 单次结果。
        支持流式子 Agent 调度的工具应覆盖此方法，
        yield 中间事件 (通过特殊约定) 和最终结果。

        约定：为了与现有 ToolResult 类型兼容而不引入额外依赖，
        流式工具在 yield 中间事件时，使用一个特殊的 "streaming" ToolResult：
        - content="" 且 is_error=False 且 artifacts=[{"_streaming_event": <AgentRuntimeEvent dict>}]
        - Host ReAct loop 检测到 artifacts 中有 _streaming_event 时，将其解包为 AgentRuntimeEvent
        - 最终 yield 正常的 ToolResult 作为结果
        """
        result = await self.invoke(ctx, **kwargs)
        yield result
