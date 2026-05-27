"""
MCP 配置模型

定义 MCP Server 配置的数据结构
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class MCPServerConfig(BaseModel):
    """MCP Server 配置

    支持三种传输类型:
    - streamable-http: HTTP 传输，远程访问
    - stdio: 标准输入输出，本地进程
    - sse: Server-Sent Events 传输
    """

    name: str = Field(
        ..., description="Server 显示名称，如 'my-sqlite'", min_length=1, max_length=64
    )

    type: Literal["streamable-http", "stdio", "sse"] = Field(..., description="传输类型")

    # HTTP/SSE 类型配置
    url: Optional[str] = Field(
        None,
        description="MCP Server URL (HTTP/SSE 类型必填)",
        examples=["http://localhost:13003/mcp"],
    )

    headers: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="HTTP 请求头，可包含 Authorization",
        examples=[{"Authorization": "Bearer token-xxx"}],
    )

    # STDIO 类型配置
    command: Optional[str] = Field(
        None, description="命令 (STDIO 类型必填)", examples=["npx", "python"]
    )

    args: Optional[List[str]] = Field(
        default_factory=list,
        description="命令参数",
        examples=[["-y", "@modelcontextprotocol/server-postgres"]],
    )

    env: Optional[Dict[str, str]] = Field(
        default_factory=dict, description="环境变量", examples=[{"GITHUB_TOKEN": "${GITHUB_TOKEN}"}]
    )

    # 通用配置
    enabled: bool = Field(default=True, description="是否启用")

    is_system_default: bool = Field(default=False, description="是否为系统内置默认 MCP")

    auto_attach_modes: List[str] = Field(
        default_factory=list, description="哪些 mode 下默认自动附着"
    )

    auto_attached_by_mode: bool = Field(default=False, description="当前是否因为 mode 默认附着")

    description: Optional[str] = Field(None, description="Server 描述")

    timeout_ms: int = Field(default=30000, ge=1000, le=120000, description="超时时间（毫秒）")

    enabled_tools: List[str] = Field(
        default_factory=list, description="启用的工具列表（为空表示全部启用）"
    )

    @field_validator("headers", mode="before")
    @classmethod
    def set_headers_default(cls, v: Optional[Dict[str, str]]) -> Dict[str, str]:
        """将 None 转换为空字典"""
        return v if v is not None else {}

    @field_validator("args", mode="before")
    @classmethod
    def set_args_default(cls, v: Optional[List[str]]) -> List[str]:
        """将 None 转换为空列表"""
        return v if v is not None else []

    @field_validator("env", mode="before")
    @classmethod
    def set_env_default(cls, v: Optional[Dict[str, str]]) -> Dict[str, str]:
        """将 None 转换为空字典"""
        return v if v is not None else {}

    @field_validator("url")
    @classmethod
    def validate_url_for_http(cls, v: Optional[str], info) -> Optional[str]:
        """验证 HTTP 类型必须有 URL"""
        data = info.data
        if data.get("type") in ["streamable-http", "sse"] and not v:
            raise ValueError(f"type={data.get('type')} 时必须提供 url")
        return v

    @field_validator("command")
    @classmethod
    def validate_command_for_stdio(cls, v: Optional[str], info) -> Optional[str]:
        """验证 STDIO 类型必须有 command"""
        data = info.data
        if data.get("type") == "stdio" and not v:
            raise ValueError("type=stdio 时必须提供 command")
        return v

    def to_sdk_config(self) -> Dict[str, Any]:
        """转换为 SDK 配置格式"""
        if self.type == "streamable-http":
            return {
                "type": "streamable-http",
                "url": self.url,
                "headers": self.headers,
            }
        elif self.type == "sse":
            return {
                "type": "sse",
                "url": self.url,
                "headers": self.headers,
            }
        elif self.type == "stdio":
            return {
                "type": "stdio",
                "command": self.command,
                "args": self.args,
                "env": self.env,
            }
        else:
            raise ValueError(f"未知的 type: {self.type}")

    def should_auto_attach_for_mode(self, mode: Optional[str]) -> bool:
        """判断当前 mode 下是否应自动附着。"""
        normalized_mode = str(mode or "analysis").strip().lower() or "analysis"
        return normalized_mode in {
            str(item).strip().lower()
            for item in (self.auto_attach_modes or [])
            if str(item).strip()
        }


class UserMCPConfig(BaseModel):
    """用户 MCP 配置

    存储用户的所有 MCP Server 配置
    """

    user_id: str = Field(..., description="用户 ID")

    servers: List[MCPServerConfig] = Field(default_factory=list, description="MCP Server 列表")

    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(), description="创建时间"
    )

    updated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(), description="更新时间"
    )

    def get_enabled_servers(self) -> List[MCPServerConfig]:
        """获取启用的 Server 列表"""
        return [s for s in self.servers if s.enabled]

    def get_server_by_name(self, name: str) -> Optional[MCPServerConfig]:
        """根据名称获取 Server 配置"""
        for server in self.servers:
            if server.name == name:
                return server
        return None

    def add_or_update_server(self, server_config: MCPServerConfig) -> None:
        """添加或更新 Server 配置"""
        # 查找现有配置
        for i, existing in enumerate(self.servers):
            if existing.name == server_config.name:
                # 更新现有配置
                self.servers[i] = server_config
                self.updated_at = datetime.now().isoformat()
                return

        # 添加新配置
        self.servers.append(server_config)
        self.updated_at = datetime.now().isoformat()

    def remove_server(self, name: str) -> bool:
        """删除 Server 配置"""
        for i, server in enumerate(self.servers):
            if server.name == name:
                self.servers.pop(i)
                self.updated_at = datetime.now().isoformat()
                return True
        return False


class MCPConnectionStatus(BaseModel):
    """MCP Server 连接状态"""

    name: str = Field(..., description="Server 名称")
    status: Literal["connected", "disconnected", "error", "unknown", "configured"] = Field(
        ..., description="连接状态"
    )
    tools_count: int = Field(default=0, description="可用工具数量")
    error_message: Optional[str] = Field(None, description="错误信息")
    latency_ms: Optional[int] = Field(None, description="连接延迟（毫秒）")
    is_system_default: bool = Field(default=False, description="是否为系统默认配置")
    last_checked: str = Field(
        default_factory=lambda: datetime.now().isoformat(), description="最后检查时间"
    )
