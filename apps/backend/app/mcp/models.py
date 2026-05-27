"""
MCP 管理数据模型

三层合并模型：
- 系统默认层：app/mcp/system_defaults.json
- 用户全局层：workspaces/{user_id}/global_workspace/.aiasys/mcp_config.json
- 工作区层：workspaces/{user_id}/{ws}/.aiasys/mcp_config.json

合并规则：高层完全覆盖低层（工作区 > 用户全局 > 系统默认）
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class MCPConfig(BaseModel):
    """MCP 配置（单文件模型）。

    三层都使用同一格式。
    """

    version: int = Field(default=1, description="配置格式版本")
    servers: dict[str, "MCPServerDefinition"] = Field(
        default_factory=dict, description="server_name -> server 定义"
    )
    disabled_servers: list[str] = Field(
        default_factory=list, description="显式禁用的 server 名称列表"
    )

    model_config = ConfigDict(extra="ignore")


class EnvField(BaseModel):
    """环境变量字段定义。"""

    name: str = Field(..., description="变量名")
    required: bool = Field(default=False, description="是否必填")
    description: Optional[str] = Field(default=None, description="说明")
    default_value: Optional[str] = Field(default=None, description="默认值/占位符")

    model_config = ConfigDict(extra="ignore")


class MCPServerDefinition(BaseModel):
    """MCP server 定义。"""

    name: str = Field(..., description="Server 名称，全局唯一标识")
    display_name: str = Field(..., description="展示名称")
    type: Literal["streamable-http", "stdio", "sse"] = Field(..., description="传输类型")
    url: Optional[str] = Field(None, description="URL（HTTP/SSE 类型）")
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP 请求头")
    command: Optional[str] = Field(None, description="命令（STDIO 类型）")
    args: list[str] = Field(default_factory=list, description="命令参数")
    env: dict[str, str] = Field(
        default_factory=dict,
        description="环境变量（敏感信息）",
    )
    env_schema: dict[str, str] = Field(
        default_factory=dict,
        description="需要的环境变量说明，key=变量名，value=说明文字",
    )
    env_fields: list[EnvField] = Field(
        default_factory=list,
        description="环境变量字段定义列表（含必填、说明、默认值）",
    )
    readme_excerpt: Optional[str] = Field(default=None, description="README 说明摘录")
    description: Optional[str] = Field(None, description="描述")
    timeout_ms: int = Field(default=30000, ge=1000, le=120000, description="超时毫秒")
    is_system_default: bool = Field(default=False, description="是否系统内置")
    auto_attach_modes: list[str] = Field(default_factory=list, description="自动附着的 mode 列表")
    enabled_tools: list[str] = Field(
        default_factory=list, description="启用的工具列表（为空表示全部启用）"
    )

    model_config = ConfigDict(extra="ignore")

    def to_sdk_config(self, env: dict[str, str] | None = None) -> dict[str, Any]:
        """转换为 SDK 可用的配置格式。"""
        effective_env = {**(env or self.env or {})}
        if self.type in ("streamable-http", "sse"):
            return {
                "type": self.type,
                "url": self.url,
                "headers": self.headers,
                "env": effective_env or None,
            }
        elif self.type == "stdio":
            return {
                "type": "stdio",
                "command": self.command,
                "args": self.args,
                "env": effective_env or None,
            }
        raise ValueError(f"未知的 type: {self.type}")

    def should_auto_attach_for_mode(self, mode: str | None) -> bool:
        """判断当前 mode 下是否应自动附着。"""
        normalized_mode = str(mode or "analysis").strip().lower() or "analysis"
        return normalized_mode in {
            str(item).strip().lower() for item in self.auto_attach_modes if str(item).strip()
        }


class MCPOperationResult(BaseModel):
    """MCP 操作结果。"""

    success: bool
    server_name: str
    message: str

    model_config = ConfigDict(arbitrary_types_allowed=True)
