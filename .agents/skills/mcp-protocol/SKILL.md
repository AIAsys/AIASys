---
name: mcp-protocol
description: |
  AIASys 的 MCP 协议集成开发指南。覆盖三层配置合并、MCP Client 连接管理、工具注册桥接、
  Session 生命周期、能力注册等核心模块。用于新增 MCP transport、修改工具桥接逻辑、
  或调整 MCP 配置合并策略时。
---

# MCP 协议集成

MCP (Model Context Protocol) 是 AIASys 的一等能力扩展机制。外部 MCP Server 通过协议适配层注册为 AIASys Tool，供 Agent 统一调用。

---

## 配置管理

### 三层合并模型

`mcp/manager.py` 实现三层配置合并：

1. **系统默认**：系统级 MCP 配置
2. **用户全局**：`global_workspace/.aiasys/mcp_config.json`
3. **工作区**：`{workspace}/.aiasys/mcp_config.json`

合并优先级：工作区 > 用户全局 > 系统默认。

### 配置模型

`mcp/models.py` 定义：

- `MCPServerDefinition`：server 名称、transport 类型、启动参数
- `MCPConfig`：server 列表、全局设置
- `MCPOperationResult`：操作结果（安装/卸载/更新）

### API

`api/routes/mcp.py` 提供 MCP 配置和 server 的 CRUD：

- 安装/卸载 MCP server
- 更新 server 配置
- 验证 server 连通性（`api/routes/workspaces_resources_verification.py`）

---

## MCP Client

### 连接管理

`services/agent/runtime_backends/aiasys/mcp_client.py` 的 `MCPClient`：

- 使用 `AsyncExitStack` 管理 `stdio_client` / `ClientSession` 的嵌套生命周期
- 支持两种 transport：
  - **stdio**：通过 `StdioServerParameters` 启动子进程
  - **streamable HTTP**：通过 `streamablehttp_client` 连接远程服务
- 连接在 session 存活期间保持打开
- 延迟导入 `streamablehttp_client`，避免启动时硬依赖

### 工具发现

`services/llm/mcp_session_service.py`：

- 管理 MCP session 的启动和初始化
- 通过 `list_tools()` 发现 server 提供的工具列表
- `api/routes/mcp_session.py` 提供 session 的 HTTP API

---

## 工具注册桥接

### MCPTool

`services/agent/runtime_backends/aiasys/tools/mcp_tool.py` 的 `MCPTool`：

- 继承 `AiasysTool`，实现 `invoke()` 方法
- 包装 MCP server 的远程工具，使其可被 `ToolRegistry` 调度
- 实例属性覆盖 ClassVar（`name`、`description`、`parameters`），供 ToolRegistry 读取
- 调用失败时返回 `ToolResult(is_error=True)`，不抛异常

### 注册流程

1. MCP session 启动 → 发现工具列表
2. 对每个工具创建 `MCPTool` 实例（绑定 `MCPClient`）
3. 注册到当前 session 的 `ToolRegistry`
4. Agent 调用时通过 `ToolRegistry.get_tool(name)` 找到 `MCPTool`
5. `MCPTool.invoke()` 通过 `MCPClient.call_tool()` 转发到远程 server

---

## 能力注册

### MCP Provider

`capabilities/providers/mcp_provider.py`：

- 将 MCP server 作为能力源注册到系统能力目录
- 能力目录供前端展示和用户选择启用

### 外部市场

`services/mcp_external_market_service.py` 和 `models/external_mcp_market.py`：

- 支持从外部市场浏览和安装 MCP server
- 市场 server 列表、搜索、详情等

---

## 验证

### 连通性验证

`aiasys-resource-verification` skill 覆盖 MCP server 的统一验证流程：

- 三级验证口径：已挂载 → 可连接 → 可执行
- 结果分类：passed / failed / warning / skipped / unknown

---

## 新增 Transport 的步骤

1. 在 `MCPClient` 中添加新 transport 的连接逻辑（如 WebSocket transport）
2. 延迟导入相关依赖，避免硬依赖
3. 确保 `AsyncExitStack` 正确管理连接生命周期
4. 在 `MCPServerDefinition` 模型中添加 transport 类型

---

## 关键文件索引

| 文件 | 职责 |
|------|------|
| `mcp/manager.py` | 三层配置合并 + CRUD |
| `mcp/models.py` | MCP 数据模型 |
| `api/routes/mcp.py` | MCP 配置 API |
| `services/agent/runtime_backends/aiasys/mcp_client.py` | MCP Client 连接管理 |
| `services/agent/runtime_backends/aiasys/tools/mcp_tool.py` | MCP Tool 桥接 |
| `services/llm/mcp_session_service.py` | MCP Session 管理 |
| `capabilities/providers/mcp_provider.py` | MCP 能力注册 |
| `services/mcp_external_market_service.py` | 外部 MCP 市场 |