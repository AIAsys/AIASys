# AIASys 后端 API 概览

> 本文档覆盖后端关键 API 端点，用于日常开发调试和运维排障。完整 Swagger 文档在服务启动后访问 `http://localhost:13001/docs`。

## 健康检查

### `GET /health`

应用健康检查，用于确认后端进程正常运行。

**响应示例：**

```json
{
  "status": "ok",
  "app": "AIASys",
  "version": "0.3.9",
  "auth_mode": "local"
}
```

**调用：**

```bash
curl http://localhost:13001/health
```

### `GET /health/auth`

认证健康检查。

**响应示例：**

```json
{
  "auth_mode": "local",
  "cors_origins": ["http://localhost:13000"]
}
```

---

## Agent 执行

### `POST /api/agent/execute/stream`

Agent 流式执行（SSE）。发送用户 Prompt 后返回 Server-Sent Events 流。

**请求体：**

```json
{
  "prompt": "帮我分析这个 CSV 文件",
  "session_id": "session-id",
  "user_id": "default",
  "workspace_id": "default_workspace"
}
```

必填字段：`prompt`、`session_id`。可选字段：`user_id`、`workspace_id`、`model`、`model_id`、`attachments`、`references`。

### `POST /api/agent/stop`

停止当前正在执行的 Agent 任务。需要认证，必填 `session_id`。

```bash
curl -X POST http://localhost:13001/api/agent/stop \
  -H "Content-Type: application/json" \
  -d '{"session_id": "session-id"}'
```

---

## GraphRAG 知识图谱

### `GET /api/graph/health`

知识图谱服务健康检查。

```bash
curl http://localhost:13001/api/graph/health
```

---

## 会话数据库 Broker

运行时（Docker 容器或本地进程）通过 broker 访问数据库，不直接持有数据库凭据。认证方式为 Bearer token。

### `GET /api/session-database/handles`

列出当前会话可用的数据库句柄。

```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:13001/api/session-database/handles
```

**响应：**

```json
{
  "session_id": "...",
  "handles": [
    {
      "handle": "builtin_db",
      "connector_id": null,
      "name": "Built-in Database",
      "db_type": "duckdb"
    }
  ]
}
```

### `POST /api/session-database/query`

执行查询 SQL（SELECT）。

**请求体：**

```json
{
  "handle": "builtin_db",
  "sql": "SELECT * FROM users LIMIT 10",
  "params": [],
  "limit": 100
}
```

**响应：**

```json
{
  "handle": "builtin_db",
  "columns": ["id", "name", "email"],
  "rows": [["1", "Alice", "alice@example.com"]],
  "row_count": 1,
  "truncated": false
}
```

### `POST /api/session-database/execute`

执行写入/DDL SQL。

**请求体：**

```json
{
  "handle": "builtin_db",
  "sql": "CREATE TABLE test (id INTEGER)",
  "params": []
}
```

### `GET /api/session-database/tables`

列出指定数据库句柄的表。

```bash
curl -H "Authorization: Bearer <token>" \
  "http://localhost:13001/api/session-database/tables?handle=builtin_db"
```

### `GET /api/session-database/tables/{table_name}`

描述表结构。

```bash
curl -H "Authorization: Bearer <token>" \
  "http://localhost:13001/api/session-database/tables/users?handle=builtin_db"
```

---

## 系统能力

### `GET /api/system/capability-registry`

系统能力注册表，列出所有可用的工具分类、集成和能力预设。

```bash
curl http://localhost:13001/api/system/capability-registry
```

### `GET /api/system/integrations-market`

系统集成市场目录，列出可导入的外部集成。

```bash
curl http://localhost:13001/api/system/integrations-market
```

---

## 会话管理

### `GET /api/sessions/{user_id}`

获取用户的所有会话列表。

### `POST /api/sessions/create`

创建新会话。

### `GET /api/sessions/{user_id}/{session_id}/messages`

获取会话消息历史。

### `GET /api/sessions/{user_id}/{session_id}/execution-tree`

获取会话的执行树结构。

### `GET /api/sessions/{user_id}/{session_id}/budget`

获取会话 token 预算。

### `PUT /api/sessions/{user_id}/{session_id}/budget`

设置会话 token 预算。

```bash
curl -X PUT http://localhost:13001/api/sessions/default/session-id/budget \
  -H "Content-Type: application/json" \
  -d '{"budget": 100000}'
```

---

## LLM 配置

### `GET /api/llm/providers`

列出所有 LLM 服务商。

### `POST /api/llm/providers/{provider_id}/test`

测试服务商连接。

### `GET /api/llm/models`

列出所有已配置的模型。

### `POST /api/llm/models/{model_id}/default`

设为默认模型。

---

## 工作区

### `GET /api/workspaces`

列出所有工作区。

### `POST /api/workspaces`

创建工作区。

### `GET /api/workspaces/{workspace_id}/files`

获取工作区文件列表。

---

## WebSocket

### `/ws/terminal/{user_id}/{session_id}`

终端 PTY WebSocket 连接。前端终端面板通过此端点连接到工作区文件系统的交互式 shell。

---

## 完整 API 文档

启动后端后，在 DEBUG 模式下可访问 Swagger UI：

1. 设置 `apps/backend/config.toml` 中 `server.debug` 为 `true`
2. 重启后端
3. 访问 `http://localhost:13001/docs`

Swagger 提供所有端点的交互式文档，包括请求/响应 schema 和在线调试功能。非 DEBUG 模式下 Swagger UI 和 ReDoc 默认禁用。