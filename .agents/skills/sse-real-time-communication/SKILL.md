---
name: sse-real-time-communication
description: |
  AIASys 的 SSE 实时通信开发指南。覆盖后端 StreamingResponse 事件流生成、前端 fetch ReadableStream 手动解析、
  事件类型体系、多 session 并行流管理、竞态防护等核心模式。用于修改 Agent 事件流、新增 SSE 事件类型、
  或调整前端流消费逻辑时。
---

# SSE 实时通信

AIASys 使用 SSE (Server-Sent Events) 作为 Agent 与前端之间的唯一实时通信通道。后端通过 FastAPI `StreamingResponse` + async generator 推送事件，前端使用 `fetch` + `ReadableStream` reader 手动解析（非 EventSource API）。

---

## 后端：事件流生成

### 核心端点

`api/routes/agent.py` 的 `/agent/execute/stream`：

- 使用 `StreamingResponse(content=async_generator, media_type="text/event-stream")`
- 通过 `async for` 消费 `agent_service.execute_stream()` 生成的 `AgentRuntimeEvent`
- 每个事件转为 `data: {json}\n\n` 格式

### 事件模型

`services/agent/runtime_backends/base.py` 定义 `AgentRuntimeEvent`：

| 字段 | 类型 | 说明 |
|------|------|------|
| `kind` | `RuntimeEventKind` | 事件类型 |
| `content_type` | `text` / `think` | 内容类型 |
| `text` | `str` | 文本内容 |
| `think` | `str` | 思考内容 |
| `tool_call_id` | `str` | 工具调用 ID |
| `tool_name` | `str` | 工具名称 |
| `arguments` | `dict` | 工具参数 |
| `content` | `str` | 工具结果内容 |
| `is_error` | `bool` | 是否错误 |
| `scope` | `host` / `subagent` | 生命周期作用域 |
| `status` | `finished` / `cancelled` / `interrupted` / `failed` | 生命周期状态 |
| `input_tokens` | `int` | 输入 token 数 |
| `output_tokens` | `int` | 输出 token 数 |

**事件类型枚举**：

- `content` — 文本/思考内容
- `data` — 通用数据事件
- `ask_user_request` — 用户询问请求事件
- `tool_call` / `tool_result` — 工具调用与结果
- `subagent_content` / `subagent_tool_call` / `subagent_tool_result` — 子 Agent 事件
- `token_usage` — Token 消耗统计
- `task_call_begin` / `task_call_end` — 任务生命周期
- `budget_limited` / `budget_updated` — 预算事件
- `worker_lifecycle` — Worker 生命周期

### 事件投影层

`services/agent/mixins/events.py` 将底层 runtime wire 事件转换为前端 SSE 事件：

- 管理 `tool_call_map` 和 `task_call_map` 跟踪进行中的调用
- 处理 host/subagent 生命周期投影
- 处理 worker lifecycle、tool call 映射、subagent 事件嵌套

### 新增 SSE 事件类型

1. 在 `base.py` 的 `RuntimeEventKind` Literal 中添加新类型
2. 在 `events.py` 中处理底层事件到新类型的投影逻辑
3. 在前端 `types/api.ts` 中添加对应的 TypeScript 类型
4. 在 `useAgentStream.ts` 的事件分发逻辑中添加处理分支

---

## 前端：流消费

### useAgentStream Hook

`hooks/useAgentStream.ts` 核心设计：

- 使用 `fetch` + `response.body.getReader()` + `TextDecoder` 手动解析 SSE 流
- 不用 `EventSource` API（因为需要 POST 请求体 + 自定义 headers）
- 支持多 session 并行流：`Map<string, SessionStreamEntry>` 管理每个 session 的独立状态
- 只有 active session 同步到 React `useState`，其他 session 保持在 `useRef` Map 中

### 竞态防护

- 每个流请求带 `requestId`，收到响应时检查 `requestId` 是否仍为当前请求
- 如果 `requestId` 已过期（新请求已发起），丢弃旧响应
- 使用 `AbortController` 在 session 切换或组件卸载时取消旧请求

### SSE 解析逻辑

- 行缓冲：逐行读取 `ReadableStream`，遇到空行（`\n\n`）表示一个事件结束
- 解析 `data:` 前缀，提取 JSON payload
- 按 `event.type` 分发到对应处理函数

### 事件类型定义

`types/api.ts` 定义前端 SSE 事件类型：

- `ContentEvent` — 文本内容
- `ToolCallEvent` / `ToolResultEvent` — 工具调用
- `SubagentEvent` — 子 Agent 事件
- `TokenUsageEvent` — Token 消耗
- `FileChangesEvent` — 文件变更通知
- `StatusEvent` — 状态变更
- `ErrorEvent` — 错误

---

## 多 Session 并行管理

### useMultiTaskEventStream

`hooks/useMultiTaskEventStream.ts`：

- `Map<string, PerSessionData>` 管理每个 session 的 SubAgent Task 事件状态
- Session 切换时通过 `useRef` 保持非活跃 session 的状态
- 任务列表排序、选中、完成跟踪
- Notebook 历史同步、工作区文件跟踪

### 状态隔离原则

- 活跃 session → React state（驱动 UI 重渲染）
- 非活跃 session → `useRef` Map（保持数据但不触发渲染）
- 切换 session 时从 `useRef` 恢复到 `useState`

---

## 关键文件索引

| 文件 | 职责 |
|------|------|
| `api/routes/agent.py` | SSE 端点 `/agent/execute/stream` |
| `services/agent/runtime_backends/base.py` | `AgentRuntimeEvent` 模型定义 |
| `services/agent/mixins/events.py` | 事件投影层（wire event → SSE event） |
| `services/agent/runtime_backends/aiasys/session_stream.py` | ReAct 循环中的事件生成 |
| `hooks/useAgentStream.ts` | 前端 SSE 消费 Hook |
| `hooks/useMultiTaskEventStream.ts` | 多 session 并行任务管理 |
| `types/api.ts` | 前端 SSE 事件类型定义 |
| `services/terminal/pty_manager.py` | Terminal SSE 传输（独立通道） |