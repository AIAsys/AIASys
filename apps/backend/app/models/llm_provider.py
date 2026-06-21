"""LLM Provider 配置模型。"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Set

from pydantic import BaseModel, Field, SecretStr, computed_field, field_validator

from app.utils.llm_url_validator import validate_llm_base_url

# ==================== 基础类型定义 ====================

# 接口格式导向的 ProviderType
# 系统不关心具体服务商，只认接口格式
ProviderType = Literal[
    "openai_chat_completions",  # /v1/chat/completions — 通用对话、文本生成
    "openai_responses",  # /v1/responses — Agent 工作流、内置工具
    "anthropic_messages",  # /v1/messages — Claude、智谱 GLM 等
]

# 模型能力
ModelCapability = Literal["image_in", "video_in", "thinking", "always_thinking"]

# 模型用途类型
ModelType = Literal["chat", "embedding"]


# ==================== 服务商配置 ====================


class LLMProviderConfig(BaseModel):
    """LLM 服务商配置。

    包含服务商基础连接信息和环境变量配置
    """

    id: str = Field(..., description="服务商唯一标识", min_length=1, max_length=64)

    name: str = Field(..., description="显示名称", min_length=1, max_length=128)

    type: ProviderType = Field(..., description="接口格式类型：决定系统使用哪种协议调用该服务商")

    base_url: str = Field(
        ...,
        description="API 基础 URL",
        examples=[
            "https://api.moonshot.cn/v1",
            "https://api.kimi.com/coding/v1",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ],
    )

    api_key: SecretStr = Field(..., description="API Key (将被加密存储)", examples=["sk-xxx"])

    # 可选配置 - 新增 env 字段
    env: Optional[Dict[str, str]] = Field(default=None, description="环境变量配置")

    custom_headers: Optional[Dict[str, str]] = Field(default=None, description="自定义请求头")

    reasoning_key: Optional[str] = Field(
        default=None,
        description="OpenAI-compatible API 返回 reasoning 内容的字段名。"
        "默认不设置时按 'reasoning_content' 读取。"
        "设为空字符串则禁用 reasoning 解析。",
    )

    reasoning_format: Optional[Literal["general", "deepseek-style"]] = Field(
        default=None, description="厂商特有的 reasoning 格式控制。当前仅阶跃星辰(stepfun)支持。"
    )

    # 用于前端显示的脱敏 API Key
    @computed_field
    @property
    def api_key_masked(self) -> str:
        """返回脱敏的 API Key"""
        key = self.api_key.get_secret_value()
        if not key:
            return "未设置"
        if len(key) <= 8:
            return "***"
        return f"{key[:4]}...{key[-4:]}"

    # 状态
    enabled: bool = Field(default=True, description="是否启用")

    is_default: bool = Field(default=False, description="是否为默认服务商")

    description: Optional[str] = Field(None, description="服务商描述")

    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")

    updated_at: datetime = Field(default_factory=datetime.utcnow, description="更新时间")

    @field_validator("env", mode="before")
    @classmethod
    def set_env_default(cls, v: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        return v if v is not None else None

    @field_validator("custom_headers", mode="before")
    @classmethod
    def set_headers_default(cls, v: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        return v if v is not None else None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        validate_llm_base_url(v)
        return v

    def to_sdk_config(self) -> Dict[str, Any]:
        """转换为运行时配置格式"""
        config: Dict[str, Any] = {
            "type": self.type,
            "base_url": self.base_url,
            "api_key": self.api_key.get_secret_value(),
        }
        if self.env:
            config["env"] = self.env
        if self.custom_headers:
            config["custom_headers"] = self.custom_headers
        if self.reasoning_key is not None:
            config["reasoning_key"] = self.reasoning_key
        if self.reasoning_format is not None:
            config["reasoning_format"] = self.reasoning_format
        return config

    def mask_api_key(self) -> str:
        """返回脱敏的 API Key"""
        key = self.api_key.get_secret_value()
        if len(key) <= 8:
            return "***"
        return f"{key[:4]}...{key[-4:]}"


# ==================== 模型配置 ====================


class LLMModelConfig(BaseModel):
    """LLM 模型配置。

    包含模型关联信息、上下文限制和能力定义
    """

    id: str = Field(..., description="模型配置唯一标识", min_length=1, max_length=128)

    name: str = Field(..., description="模型显示名称", min_length=1, max_length=128)

    provider: str = Field(..., description="关联的服务商 ID", min_length=1)

    model: str = Field(..., description="模型名称", min_length=1)

    max_context_size: int = Field(..., description="最大上下文长度（tokens）", gt=0)

    model_type: ModelType = Field(
        default="chat", description="模型用途类型：chat（对话）或 embedding（向量）"
    )

    dimension: Optional[int] = Field(
        default=None, description="向量维度（仅 embedding 模型需要）", gt=0
    )

    capabilities: Optional[Set[ModelCapability]] = Field(default=None, description="模型能力集合")

    reasoning_key: Optional[str] = Field(
        default=None,
        description="模型级别的 reasoning 字段名，覆盖服务商级别的同名配置。"
        "用于兼容不同厂商对 reasoning 内容的不同字段命名。",
    )

    enabled: bool = Field(default=True, description="是否启用")

    is_default: bool = Field(default=False, description="是否为默认模型")

    description: Optional[str] = Field(None, description="模型描述")

    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")

    updated_at: datetime = Field(default_factory=datetime.utcnow, description="更新时间")

    @field_validator("capabilities", mode="before")
    @classmethod
    def set_capabilities_default(
        cls, v: Optional[Set[ModelCapability]]
    ) -> Optional[Set[ModelCapability]]:
        return v if v is not None else None

    @field_validator("dimension", mode="before")
    @classmethod
    def validate_dimension_for_embedding(cls, v: Optional[int], info) -> Optional[int]:
        data = info.data
        model_type = (
            data.get("model_type") if isinstance(data, dict) else getattr(data, "model_type", None)
        )
        if model_type == "embedding" and v is not None and v <= 0:
            raise ValueError("embedding 模型的 dimension 必须大于 0")
        return v

    def to_sdk_config(self) -> Dict[str, Any]:
        """转换为运行时模型配置格式。"""
        config: Dict[str, Any] = {
            "provider": self.provider,
            "model": self.model,
            "max_context_size": self.max_context_size,
        }
        if self.capabilities:
            config["capabilities"] = list(self.capabilities)
        if self.reasoning_key is not None:
            config["reasoning_key"] = self.reasoning_key
        return config

    def model_to_sdk_config(self) -> Dict[str, Any]:
        """转换模型配置为 SDK 格式（别名方法）"""
        return self.to_sdk_config()


# ==================== 完整配置 ====================


class LLMFullConfig(BaseModel):
    """LLM 完整配置，包含服务商、模型和默认模型选择。"""

    providers: Dict[str, LLMProviderConfig] = Field(
        default_factory=dict, description="服务商配置映射 (provider_id -> config)"
    )

    models: Dict[str, LLMModelConfig] = Field(
        default_factory=dict, description="模型配置映射 (model_id -> config)"
    )

    default_model: Optional[str] = Field(default=None, description="运行时默认模型 ID")

    default_chat_model: Optional[str] = Field(default=None, description="默认 chat 模型 ID")

    default_embedding_model: Optional[str] = Field(
        default=None, description="默认 embedding 模型 ID"
    )

    @field_validator("providers", mode="before")
    @classmethod
    def set_providers_default(cls, v: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        return v if v is not None else {}

    @field_validator("models", mode="before")
    @classmethod
    def set_models_default(cls, v: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        return v if v is not None else {}

    def get_provider(self, provider_id: str) -> Optional[LLMProviderConfig]:
        """获取指定服务商配置"""
        return self.providers.get(provider_id)

    def get_model(self, model_id: str) -> Optional[LLMModelConfig]:
        """获取指定模型配置"""
        return self.models.get(model_id)

    def get_default_model_config(self) -> Optional[LLMModelConfig]:
        """获取默认模型配置"""
        if self.default_model:
            return self.models.get(self.default_model)
        return None

    def to_sdk_config(self) -> Dict[str, Any]:
        """转换为运行时完整配置格式。"""
        return {
            "providers": {
                pid: provider.to_sdk_config() for pid, provider in self.providers.items()
            },
            "models": {mid: model.to_sdk_config() for mid, model in self.models.items()},
            "default_model": self.default_model,
            "default_chat_model": self.default_chat_model,
            "default_embedding_model": self.default_embedding_model,
        }


class LLMModelDefaults(BaseModel):
    """默认 chat / embedding 模型配置。"""

    default_chat_model: Optional[str] = Field(default=None, description="默认 chat 模型 ID")
    default_embedding_model: Optional[str] = Field(
        default=None, description="默认 embedding 模型 ID"
    )


# ==================== 列表和响应模型 ====================


class LLMProviderList(BaseModel):
    """服务商列表响应"""

    providers: List[LLMProviderConfig] = Field(default_factory=list)
    total: int = Field(default=0)


class LLMModelList(BaseModel):
    """模型列表响应"""

    models: List[LLMModelConfig] = Field(default_factory=list)
    total: int = Field(default=0)


class RemoteModelInfo(BaseModel):
    """从 Provider API 获取的远程模型信息

    厂商 /v1/models 返回格式差异较大：
    - Kimi Code: 返回 context_length, supports_reasoning, supports_image_in 等
    - 标准 OpenAI: 只返回 id, object, created, owned_by
    所有扩展字段均为 Optional，不存在的厂商返回 None。
    """

    model_name: str = Field(..., description="模型名称 (API 返回的 id)")
    owned_by: Optional[str] = Field(None, description="模型所有者")
    display_name: Optional[str] = Field(None, description="显示名称")
    context_length: Optional[int] = Field(None, description="上下文长度 (tokens)")
    supports_reasoning: Optional[bool] = Field(None, description="是否支持 reasoning")
    supports_image_in: Optional[bool] = Field(None, description="是否支持图片输入")
    supports_video_in: Optional[bool] = Field(None, description="是否支持视频输入")


class FetchModelsResult(BaseModel):
    """获取远程模型列表的结果"""

    provider_id: str = Field(..., description="服务商 ID")
    models: List[RemoteModelInfo] = Field(default_factory=list, description="模型列表")
    success: bool = Field(..., description="是否成功")
    error_message: Optional[str] = Field(None, description="错误信息")
    unsupported: bool = Field(default=False, description="该 provider 是否不支持 /models 接口")


class ProviderTestResult(BaseModel):
    """服务商连通性测试结果"""

    provider_id: str = Field(..., description="服务商 ID")

    status: Literal["success", "error", "timeout"] = Field(..., description="测试状态")

    latency_ms: Optional[int] = Field(None, description="响应延迟（毫秒）")

    error_message: Optional[str] = Field(None, description="错误信息")

    tested_at: datetime = Field(default_factory=datetime.utcnow, description="测试时间")


# ==================== 预设模板 ====================

# 预设模板（仅作为前端默认值参考，不强制使用）
# 按接口格式分类，不再区分具体厂商
PROVIDER_TEMPLATES = {
    "kimi": {
        "name": "Kimi (Moonshot Coding)",
        "type": "anthropic_messages",
        "base_url": "https://api.kimi.com/coding/v1",
        "description": "Moonshot Kimi Coding API — Anthropic Messages 兼容",
    },
    "moonshot": {
        "name": "Moonshot (标准)",
        "type": "openai_chat_completions",
        "base_url": "https://api.moonshot.cn/v1",
        "description": "Moonshot 标准 API — OpenAI Chat Completions 兼容",
    },
    "dashscope": {
        "name": "DashScope (阿里云)",
        "type": "openai_chat_completions",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "description": "阿里云 DashScope — OpenAI Chat Completions 兼容",
    },
    "openai": {
        "name": "OpenAI",
        "type": "openai_chat_completions",
        "base_url": "https://api.openai.com/v1",
        "description": "OpenAI API — Chat Completions 接口",
    },
    "openai_responses": {
        "name": "OpenAI (Responses)",
        "type": "openai_responses",
        "base_url": "https://api.openai.com/v1",
        "description": "OpenAI API — Responses 接口（Agent 工作流、内置工具）",
    },
    "anthropic": {
        "name": "Anthropic",
        "type": "anthropic_messages",
        "base_url": "https://api.anthropic.com/v1",
        "description": "Anthropic Claude — Messages 接口",
    },
    "krill": {
        "name": "Krill AI",
        "type": "openai_responses",
        "base_url": "https://api-slb.krill-ai.com:62710/codex/v1",
        "description": "Krill AI — OpenAI Responses 兼容中继",
    },
}


def get_provider_templates() -> Dict[str, Any]:
    """获取服务商模板（仅作为前端默认值参考）"""
    return PROVIDER_TEMPLATES
