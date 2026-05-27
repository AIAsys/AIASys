# AIASys Backend

AIASys 后端服务，负责 Agent 执行编排、会话持久化、运行环境管理与 MCP/Skills 接口。

## 技术栈

- Python `>=3.12`（见 `pyproject.toml`）
- FastAPI + Uvicorn
- 自研 Agent Runtime
- 本地 sandbox + 可选 Docker sandbox

## 核心能力

- SSE 流式执行：`POST /api/agent/execute/stream`
- 会话管理：`/api/sessions/*`
- 文件管理：`/api/files/*`
- 运行环境与容器管理：`/api/runtime-envs/*`、`/api/containers/*`
- MCP 配置：`/api/mcp/*`、`/api/mcp-session/*`
- 知识库：`/api/rag/*`（查询/上传/文档管理）
- SQLite + sqlite-vec 知识库：`/api/knowledge/*`（向量检索/多租户隔离）
- 内置 DuckDB 浏览器：`/api/database/*`（表结构查看/SQL 预览）
- 用户偏好记忆：`/api/preferences/*`（个性化设置）
- 技能市场与安装：`/api/skills/*`
- AskUser 人机确认：`/api/ask-user/*`

## 快速开始

如只想单独运行后端，也可以：

```bash
cd apps/backend
uv sync
uv run uvicorn app.main:app --reload --port 13001
```

服务地址：

- API Base: `http://localhost:13001`
- Swagger: `http://localhost:13001/docs`
- Health: `http://localhost:13001/health`

可选能力：

- `docling` 默认不随基础环境安装；如需复杂文档解析，可执行 `uv sync --extra docling`

## 运行配置（最小）

当前后端统一从 `apps/backend/config.json` 读取运行配置，可参考 `apps/backend/config.example.json`。

```json
{
  "server": {
    "port": 13001
  },
  "auth": {
    "mode": "local"
  },
  "sandbox": {
    "default_mode": "local",
    "enabled_modes": ["local"]
  }
}
```

说明：

- `auth.mode` 支持 `local / sso / none`
- `sandbox.default_mode` 当前主线支持 `local`
- `sandbox.enabled_modes` 用于声明当前允许启用的运行时模式
- LLM、Embedding、上传限制等也统一在 `config.json` 中维护
- 修改 `config.json` 后需重启后端服务

## 认证模式

- `local`: 本地 JWT（Cookie 或 Bearer Token）
- `sso`: 通过外部 SSO Session 校验
- `none`: 开发/测试用匿名身份

## SSE 事件类型（Agent）

`/api/agent/execute/stream` 的常见事件：

- `status`
- `content`（`content_type` 为 `text` 或 `think`）
- `tool_call`
- `tool_result`
- `subagent_event`
- `file_changes`
- `error`
- 结束标记：`[DONE]`

## 目录结构

```text
apps/backend/
├── app/
│   ├── api/routes/         # FastAPI 路由
│   ├── services/           # 业务编排（agent/session/runtime/mcp）
│   ├── agents/tools/       # 工具（notebook、memory、AskUser 等）
│   ├── core/               # 配置、认证、数据库、日志
│   └── models/             # Pydantic 模型
├── data/rag/               # 内置 RAG 数据目录
├── workspaces/             # 会话持久化目录
├── tests/                  # 测试
└── pyproject.toml
```

## 存储说明

会话数据目录：`apps/backend/workspaces/{user_id}/{session_id}/`

- `metadata.json`: 会话元数据
- `history.json`: 消息历史
- `file_snapshots.json`: 文件快照
- `.session/`: SDK 会话状态
- `workspace/`: 用户上传与生成文件

## 相关文档

- `apps/backend/docs/README.md`
- 根目录开发入口：`dev.sh`（聚合 `check/setup/start/start-local/restart/restart-local/stop/status/logs`）
