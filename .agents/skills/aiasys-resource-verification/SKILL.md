---
name: aiasys-resource-verification
description: |
  统一验证 AIASys 当前任务工作区中的 MCP、知识库、知识图谱、数据库是否真的可用。
  适用于设计或实现资源验活面板、排查“配置存在但不能用”、补统一验证接口、
  或在交付前为任务资源做真实 smoke 验证并沉淀证据。
  它现在也是 AIASys 仓库里 MCP 验证请求的 canonical 入口；旧 `mcp-testing` 名称保留为兼容 alias。
---

# aiasys-resource-verification

## Canonical Scope

`aiasys-resource-verification` 是当前 AIASys 仓库里资源验活的 canonical skill。

它负责两类场景：

1. AIASys 当前任务工作区里的统一资源验活
2. AIASys 仓库语境下的 MCP 专项验证

如果用户显式说的是：

- “测一下 MCP 能不能连上”
- “排查 MCP server 工具调用”
- “验证 MCP 配置到底能不能用”

也优先从这里进入。

如果只是做纯外部、与 AIASys 工作区无关的 Layer 1 MCP server 测试，可再读取：

- `references/mcp-server-testing.md`

## 使用场景

- 用户问“怎么验证 MCP / 知识库 / 知识图谱 / 数据库到底能不能用”
- 正在实现或调整 `任务配置 -> 资源` 页
- 需要为工作区级资源补统一后端聚合验证接口
- 资源类功能改完后，需要真实 smoke，而不是只看配置或 build

## 核心规则

### 规则 1：统一口径必须是“已挂载 + 可连接 + 可执行”

不要把以下状态误报成“可用”：

- 只存在配置
- 只在目录中可见
- 只有健康检查通过
- 只有连接测试通过

AIASys 中资源可用性的最低口径是：

1. `已挂载`
2. `可连接`
3. `可执行`

如果资源当前还没有任务级显式挂载能力，必须明确标成：

- `scope=catalog`
- 或 `scope=system`

而不是伪装成 `scope=task`。

### 规则 2：以工作区为主对象，以当前对话补齐运行事实

AIASys 的资源验证默认对象是 `任务工作区`，不是抽象全局配置，也不是单个临时弹窗状态。

但以下事实仍可能需要借当前对话 `session_id` 读取：

- 当前任务启用的 MCP
- 当前任务挂载的数据库连接
- 与当前运行态绑定的资源上下文

因此验证输出必须显式包含：

- `workspace_id`
- `session_id`

不要在 UI 或日志里隐式猜测当前对话。

### 规则 3：验证顺序固定

默认按这个顺序执行：

1. 读取工作区当前资源事实
2. 读取当前对话 / 运行态上下文
3. 健康检查
4. 最小 smoke
5. 输出统一结论

对于新任务或空任务，必须先确认：

- 当前工作区是否已绑定对话
- 当前对话是否已经存在

没有当前对话时，MCP 和数据库的任务级验证默认 `skipped`，不能强行报失败。

### 规则 4：最小 smoke 必须是真实调用

每类资源的最小 smoke 默认如下：

- `MCP`
  - 真实连接当前任务启用的 server
  - 完成 initialize
  - 至少执行一次 `list_tools`

- `知识库`
  - 先 `/health`
  - 若当前用户下存在知识库，则对首个知识库执行一次最小 query

- `知识图谱`
  - 先读取工作区挂载的 `primary_knowledge_graph_id`
  - 对当前主图谱先做 `/health` 等价检查
  - 再做一次最小 `search` 或不依赖大模型的 query

- `数据库`
  - 先测试已挂载连接器
  - 再做一次最小 schema / list tables 探针

不要只停在 `ping` 级别，也不要直接上重型写入验证，除非用户明确要求。

### 规则 5：结论必须区分 skipped / failed / warning

统一状态建议：

- `passed`: 当前验证项通过
- `failed`: 当前验证项明确失败
- `warning`: 部分通过、部分失败，或系统有告警但仍能继续
- `skipped`: 当前上下文不足，按设计跳过
- `unknown`: 还未验证或返回不确定

特别注意：

- 没有知识库时，知识库 smoke 应该是 `skipped`，不是 `failed`
- 没有数据库挂载时，数据库 smoke 应该是 `skipped`
- 部分 MCP 通过、部分失败时，应返回 `warning`

### 规则 6：验证证据必须可回放

至少保留以下证据：

- 触发验证的接口或页面入口
- 用到的 `workspace_id`
- 用到的 `session_id`
- 每类资源的 health / smoke 结果
- 失败明细或跳过原因

如果是实现任务，默认把证据回写到当前 task session。

## 执行步骤

1. 确认当前任务工作区与当前对话

建议先验证：

```bash
curl -sS http://127.0.0.1:13000/api/workspaces
curl -sS http://127.0.0.1:13000/api/workspaces/<workspace_id>
```

2. 读取当前主线资源事实

优先检查：

- MCP: `/api/mcp-session/<session_id>/servers`
- 知识库: `/api/workspaces/<workspace_id>/knowledge-bases`、`/api/knowledge/health`
- 图谱: `/api/workspaces/<workspace_id>/knowledge-graphs`、`/api/graph/health?workspace_id=<workspace_id>`
- 数据库: `/api/database-connectors/sessions/<session_id>/attachments`

3. 执行最小 smoke

按资源类型分别执行最小真实探针，不要只看静态配置。

4. 输出统一结构

推荐统一返回：

```json
{
  "workspace_id": "example-paper-reading",
  "session_id": "paper-reading-main",
  "resources": [
    {
      "resource_key": "mcp",
      "scope": "task",
      "mounted": true,
      "health": { "status": "passed", "summary": "..." },
      "smoke": { "status": "warning", "summary": "..." }
    }
  ]
}
```

5. 若有长期价值，更新 skill 与 task session

- 实现层证据回写 task session
- 通用方法沉淀到本 skill

## 推荐验证命令

### 工作区统一验证接口

```bash
curl -sS http://127.0.0.1:13001/api/workspaces/<workspace_id>/resource-verification
```

### 图谱主服务工作区上下文验证

```bash
curl -sS "http://127.0.0.1:13001/api/graph/health?workspace_id=<workspace_id>"
```

预期：

- 若当前工作区已挂载图谱，返回对应图谱健康结果
- 若当前工作区未挂载图谱，应明确返回错误，而不是悄悄回退到 system

### 页面级验证

进入：

- `任务配置 -> 资源`

至少确认：

- 页面能打开
- 有 `任务资源验证`
- 有 `MCP / 知识库 / 知识图谱 / 数据库`
- 无新的 React / DOM 运行时错误

### 最低交付证据

- 后端路由测试通过
- 前端 build 通过
- 真实 API smoke 通过
- 页面级资源页验证通过

## 兼容别名

以下旧 skill 名现在都应回到本 skill：

- `mcp-testing`

---

注意: 本 Skill 自给自足，默认服务于 AIASys 当前“任务工作区”主骨架，不把资源验证退化成单纯配置检查。
