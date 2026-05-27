# Backend API 现状

本文档只记录当前 `apps/backend` 已落地并且容易被文档漂移误导的 API 契约。

- 路由注册入口: `app/api/routes/__init__.py`
- 应用入口: `app/main.py`
- 规则边界: 影响实现判断时，以源码为准，不以本文档为准

## 基础约定

| 项目 | 当前事实 |
| --- | --- |
| 默认端口 | `13001`，来自 `apps/backend/config.json -> server.port` |
| 根级健康检查 | `GET /health`、`GET /health/auth`、`GET /health/docker` |
| API 主前缀 | `/api` |
| OpenAPI 文档 | 仅在 `DEBUG=true` 时开放 `/docs` 和 `/redoc` |
| 主认证依赖 | `require_auth()`，默认走 `local` 模式 |

## 认证契约

当前后端不再把 `X-User-ID` 作为前端正式调用契约。现行约定如下：

1. 大多数 `/api/*` 路由都要求认证。
2. `local` 模式下，前端和浏览器应优先依赖 `access_token` Cookie。
3. 脚本或调试工具可以使用 `Authorization: Bearer <token>`。
4. `none` 模式只用于本地开发或测试，会注入一个虚拟开发身份。
5. `sso` 模式通过请求 Cookie 对接外部 SSO 服务，不要求前端自己拼装用户 Header。

与旧文档不同，下面这些说法现在已经不成立：

- “默认认证模式是 simple”
- “前端必须传 `X-User-ID`”
- “GraphRAG 路由在 `/api/graphrag`”

## 核心路由分组

### `GET /health*`

- `GET /health`: 应用健康检查，返回 `status/app/version/auth_mode`
- `GET /health/auth`: 返回当前认证模式和 CORS 配置
- `GET /health/docker`: 返回 Docker 预构建镜像状态

这些路由不挂在 `/api` 前缀下。

### `/api/auth`

当前主要用于本地认证和前端登录态同步：

- `POST /api/auth/login`
- `POST /api/auth/register`
- `POST /api/auth/logout`
- `GET /api/auth/session`
- `POST /api/auth/forgot-password`
- `GET /api/auth/me`
- `PUT /api/auth/me`

前端通常用 `/api/auth/session` 或 `/api/auth/me` 确认登录态，而不是自己保存一套用户身份 Header。

### `/api/sessions`

会话路由承担了“草稿创建 + 元数据 + 历史恢复 + 草稿清理”的生命周期职责：

- `POST /api/sessions/create`
- `GET /api/sessions/status/{session_id}`
- `GET /api/sessions/{user_id}/{session_id}`
- `POST /api/sessions/{user_id}/{session_id}/messages`
- `GET /api/sessions/{user_id}/{session_id}/messages`
- `GET /api/sessions/{user_id}/{session_id}/file-snapshots`
- `DELETE /api/sessions/{user_id}/{session_id}`
- `GET /api/sessions/history/{user_id}/{session_id}`
- `GET /api/sessions/available-draft`
- `GET /api/sessions/{user_id}`
- `POST /api/sessions/ensure-dir/{session_id}`
- `POST /api/sessions/cleanup-drafts`
- `POST /api/sessions/mark-draft-for-cleanup`

需要注意的当前事实：

1. `create` 支持 `env_id`、`sandbox_mode`。
2. `status/{session_id}` 和 `ensure-dir/{session_id}` 会在需要时自动补建空草稿。
3. `history/{user_id}/{session_id}` 返回的是基于 SDK `context.jsonl` 投影后的可见历史，不等于原始文件逐字透传。
4. 删除会话时会先中断 Agent、清理容器和运行环境绑定，再删除整个会话目录。

### `/api/agent`

Agent 主链当前对外重点如下：

- `POST /api/agent/execute`
- `POST /api/agent/execute/stream`
- `POST /api/agent/stop`
- `POST /api/agent/prewarm`
- `GET /api/agent/history/{user_id}/{session_id}`
- `GET /api/agent/execution/{user_id}/{session_id}/flow`
- `GET /api/agent/sessions/{user_id}`
- `GET /api/agent/sessions`
- `GET /api/agent/storage/info`
- `POST /api/agent/admin/cleanup`

`/api/agent/execute/stream` 是前端对话主链使用的 SSE 接口。当前事件流会混合文本、工具调用、文件变化和子代理事件，前端不应假设只有纯文本分片。

### `/api/files`

文件路由保留会话产物下载、删除、导出和内容读写兼容能力。当前工作区文件列表、上传、创建、复制和移动使用 `/api/workspaces/{workspace_id}/files/*`：

- `GET /api/files/download/{user_id}/{session_id}/{filename:path}`
- `DELETE /api/files/delete/{user_id}/{session_id}/{filename:path}`
- `GET /api/files/export/{user_id}/{session_id}`
- `GET /api/files/export-document/{user_id}/{session_id}/{filename:path}`
- `GET /api/files/content/{user_id}/{session_id}/{filename:path}`
- `PUT /api/files/content/{user_id}/{session_id}/{filename:path}`

当前工作区文件接口：

- `GET /api/workspaces/{workspace_id}/files/list`
- `POST /api/workspaces/{workspace_id}/files/upload`
- `POST /api/workspaces/{workspace_id}/files/create`
- `POST /api/workspaces/{workspace_id}/files/copy`
- `PUT /api/workspaces/{workspace_id}/files/move`
- `GET /api/workspaces/{workspace_id}/files/download/{filename:path}`
- `GET /api/workspaces/{workspace_id}/files/content/{filename:path}`
- `PUT /api/workspaces/{workspace_id}/files/content/{filename:path}`

当前导出契约：

- `export`: 导出整个会话逻辑工作区 ZIP
- `export-document?format=md`: 下载原始 Markdown
- `export-document?format=docx|pdf`: 调用 Pandoc 转换后下载

当前文件可见性策略：

1. 逻辑工作区以会话根目录为准。
2. 后端会兼容旧的 `workspace/` 子目录，并把其中的文件按逻辑根目录暴露给前端。
3. 工作区树按普通文件树展示，`.` 开头的普通文件和目录默认可见。
4. `.session`、`.sessions`、根级 `metadata.json`、`history.json`、`file_snapshots.json`、`.cleanup_marker` 这些内部文件不会在工作区面板中展示。

### `/api/runtime-envs`

运行环境主链已经不是单纯“环境列表”，还包含用户偏好、镜像状态、会话绑定和容器监控：

- 市场与详情:
  - `GET /api/runtime-envs`
  - `GET /api/runtime-envs/categories`
  - `GET /api/runtime-envs/market-stats`
  - `GET /api/runtime-envs/{env_id}`
- 自定义环境:
  - `GET /api/runtime-envs/custom`
  - `POST /api/runtime-envs/custom`
  - `PATCH /api/runtime-envs/custom/{env_id}`
  - `DELETE /api/runtime-envs/custom/{env_id}`
  - `GET /api/runtime-envs/custom/{env_id}/build-status`
  - `POST /api/runtime-envs/custom/{env_id}/rebuild`
  - `GET /api/runtime-envs/custom/{env_id}/image-status`
  - `POST /api/runtime-envs/custom/{env_id}/ensure-image`
- 用户偏好:
  - `GET /api/runtime-envs/user/preference`
  - `POST /api/runtime-envs/user/default-env`
  - `POST /api/runtime-envs/user/scenario-default`
  - `POST /api/runtime-envs/user/favorites/{env_id}`
  - `DELETE /api/runtime-envs/user/favorites/{env_id}`
  - `GET /api/runtime-envs/user/recommended`
- 会话绑定:
  - `POST /api/runtime-envs/sessions/{session_id}/switch`
  - `GET /api/runtime-envs/sessions/{session_id}/active`
- 容器监控:
  - `GET /api/runtime-envs/containers`
  - `POST /api/runtime-envs/containers/{pool_key:path}/stop`
  - `GET /api/runtime-envs/containers/{pool_key:path}/stats`

当前切换契约的几个关键点：

1. 切环境时如果会话还不存在，会自动创建会话元数据。
2. 空草稿重置时保留现有元数据字段。
3. `sandbox_mode=local` 时不会做 Docker 预热。
4. `GET /active` 在无活跃实例时会回退到用户默认环境。

### `/api/preferences`

这是用户全局偏好接口，不是任务偏好文件接口：

- `GET /api/preferences/{user_id}`
- `PUT /api/preferences/{user_id}`
- `POST /api/preferences/{user_id}/enable`
- `POST /api/preferences/{user_id}/disable`

任务偏好 `.preference.md` 的初始化由 `sessions` 和 `runtime-envs` 生命周期负责。

### `/api/rag`

内置 RAG 路由目前保持稳定的五个接口：

- `GET /api/rag/health`
- `POST /api/rag/query`
- `POST /api/rag/documents/upload`
- `GET /api/rag/documents`
- `DELETE /api/rag/documents/{doc_id}`

### `/api/graph`

GraphRAG 当前走的是单独路由树，前缀是 `/api/graph`，不是 `/api/graphrag`。已落地主链包括：

- `POST /api/graph/documents`
- `POST /api/graph/documents/upload`
- `POST /api/graph/query`
- `GET /api/graph/entities`
- `GET /api/graph/statistics`
- `GET /api/graph/communities`
- `GET /api/graph/visualization`
- `GET /api/graph/config/llm/status`
- `GET /api/graph/health`

## 当前推荐的最小验证

```bash
cd apps/backend
uv run uvicorn app.main:app --reload --port 13001
```

```bash
curl http://localhost:13001/health
curl http://localhost:13001/health/auth
curl --cookie "access_token=<token>" http://localhost:13001/api/auth/session
```

```bash
curl --cookie "access_token=<token>" \
  -X POST http://localhost:13001/api/sessions/create \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"demo","title":"Demo"}'
```

## 源码优先级

当本文档与实现冲突时，优先看这些文件：

- `app/main.py`
- `app/api/routes/__init__.py`
- `app/api/routes/auth.py`
- `app/api/routes/sessions.py`
- `app/api/routes/agent.py`
- `app/api/routes/files.py`
- `app/api/routes/runtime_env.py`
- `app/api/routes/rag.py`
- `app/graphrag/api/routes.py`
