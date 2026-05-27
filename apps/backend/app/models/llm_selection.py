"""
LLM 模型作用域选择响应模型
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

ModelScope = Literal["global", "workspace", "session"]
InheritedScope = Literal["global", "workspace"]


class LLMModelIdentity(BaseModel):
    model_id: Optional[str] = Field(default=None, description="模型配置 ID")
    display_name: Optional[str] = Field(default=None, description="模型显示名称")
    model_name: Optional[str] = Field(default=None, description="底层模型名称")
    provider: Optional[str] = Field(default=None, description="服务商 ID")
    provider_name: Optional[str] = Field(default=None, description="服务商显示名称")


class LLMModelScopeSelection(BaseModel):
    scope: ModelScope
    configured_model_id: Optional[str] = Field(
        default=None,
        description="当前作用域显式保存的模型 ID；为空表示继承上层",
    )
    configured_missing: bool = Field(
        default=False,
        description="显式保存的模型 ID 是否已经失效或不可用",
    )
    configured_display_name: Optional[str] = Field(
        default=None,
        description="显式保存模型的显示名称",
    )
    configured_model_name: Optional[str] = Field(
        default=None,
        description="显式保存模型的底层模型名称",
    )
    configured_provider: Optional[str] = Field(
        default=None,
        description="显式保存模型的服务商 ID",
    )
    configured_provider_name: Optional[str] = Field(
        default=None,
        description="显式保存模型的服务商显示名称",
    )
    inherited_from: Optional[InheritedScope] = Field(
        default=None,
        description="当前作用域未显式指定时，继承自哪一层",
    )
    effective: LLMModelIdentity = Field(
        default_factory=LLMModelIdentity,
        description="按优先级链路解析后的当前生效模型",
    )


class WorkspaceLLMSelectionResponse(BaseModel):
    workspace_id: str
    global_scope: LLMModelScopeSelection
    workspace_scope: LLMModelScopeSelection
    effective: LLMModelIdentity = Field(default_factory=LLMModelIdentity)


class SessionLLMSelectionResponse(BaseModel):
    session_id: str
    workspace_id: Optional[str] = None
    global_scope: LLMModelScopeSelection
    workspace_scope: LLMModelScopeSelection
    session_scope: LLMModelScopeSelection
    effective: LLMModelIdentity = Field(default_factory=LLMModelIdentity)


class UpdateScopedModelSelectionRequest(BaseModel):
    model_id: Optional[str] = Field(
        default=None,
        description="为空时清除当前作用域显式覆盖，回退继承上层",
    )
