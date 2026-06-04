# 核心类型定义

> 基于实际代码的类型说明

## 目录

- [ChatSegment](#chatsegment) - 消息分段类型
- [ChatItem](#chatitem) - 聊天消息
- [TaskEvent](#taskevent) - 任务事件
- [ExecutionStep](#executionstep) - 执行步骤
- [WorkerRecord](#workerrecord) - Worker 状态

---

## ChatSegment

AI 消息的内容分段，位于 `pages/DataAnalysisPage/types.ts`。

```typescript
type ChatSegment = {
  type: "text" | "thought" | "final_answer" | "tool_call" | "tool_output" | "think";
  content: string;
  toolName?: string;
  toolParams?: string;
  isComplete?: boolean;
};
```

### 类型说明

| 类型 | 用途 | 示例场景 |
|------|------|----------|
| `text` | 最终回答文本 | AI 的正式回复 |
| `thought` | 思考内容（旧格式） | 模型思考过程 |
| `final_answer` | 最终答案（旧格式） | 思考后的结论 |
| `tool_call` | 工具调用 | 调用 read_file 等工具 |
| `tool_output` | 工具输出 | 工具执行结果 |
| `think` | 思考内容（新格式，带流式） | DeepSeek 等模型的思考 |

### 各类型字段

#### text

```typescript
{
  type: "text";
  content: "这是AI的回复内容...";
}
```

#### tool_call

```typescript
{
  type: "tool_call";
  content: "",  // 通常为空
  toolName: "read_file";
  toolParams: '{"path":"data.csv"}';
}
```

#### tool_output

```typescript
{
  type: "tool_output";
  content: "文件内容...";  // 可能很大
  toolName: "read_file";
}
```

#### think

```typescript
{
  type: "think";
  content: "让我分析一下...";
  isComplete: false;  // 流式中
}
```

---

## ChatItem

聊天消息项，位于 `pages/DataAnalysisPage/types.ts`。

```typescript
type ChatItem = {
  type: "message";
  id: string;
  sender: "user" | "ai";
  role?: "user" | "assistant" | "system";
  content?: string;
  segments?: ChatSegment[];
  timestamp: Date;
  isStreaming?: boolean;
  isStopped?: boolean;
  taskId?: string;
  steps?: ExecutionStep[];
  workerRecords?: WorkerRecord[];
  attachments?: string[];
};
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | `"message"` | 固定为 message |
| `id` | `string` | 唯一标识 |
| `sender` | `"user" \| "ai"` | 发送者 |
| `role` | `"user" \| "assistant" \| "system"` | OpenAI 格式角色 |
| `content` | `string?` | 文本内容（旧格式） |
| `segments` | `ChatSegment[]?` | 分段内容（新格式） |
| `timestamp` | `Date` | 创建时间 |
| `isStreaming` | `boolean?` | 是否流式中 |
| `isStopped` | `boolean?` | 是否被用户终止 |
| `taskId` | `string?` | 关联的任务ID |
| `steps` | `ExecutionStep[]?` | 执行步骤（历史恢复） |
| `workerRecords` | `WorkerRecord[]?` | Worker 状态记录 |
| `attachments` | `string[]?` | 附件列表 |

### 新旧格式对比

**旧格式**:
```typescript
{
  type: "message",
  sender: "ai",
  content: "思考内容...最终答案...",
  // 需要解析 content 区分思考和答案
}
```

**新格式**:
```typescript
{
  type: "message",
  sender: "ai",
  segments: [
    { type: "think", content: "思考内容..." },
    { type: "tool_call", toolName: "read_file", toolParams: "..." },
    { type: "text", content: "最终答案..." }
  ]
}
```

---

## TaskEvent

任务执行事件，位于 `types/task.ts`。

```typescript
type TaskEvent = {
  event?: string;
  type?: string;
  agent_name?: string;
  agent_role?: string;
  content?: string;
  tool_name?: string;
  tool_params?: Record<string, unknown>;
  timestamp?: string;
  // ... 其他字段
};
```

### 常见事件类型

| 事件类型 | 说明 |
|----------|------|
| `agent_output` | Agent 输出（思考内容） |
| `worker_output` | Worker 输出 |
| `tool_start` | 工具调用开始 |
| `tool_output` | 工具输出结果 |
| `tool_end` | 工具调用结束 |
| `text` | 文本输出（新格式） |
| `error` | 错误事件 |

### 示例

```typescript
// 工具调用开始
{
  event: "tool_start",
  tool_name: "read_file",
  tool_params: { path: "data.csv" }
}

// 工具输出
{
  event: "tool_output",
  tool_name: "read_file",
  content: "文件内容..."
}

// Agent 输出
{
  event: "agent_output",
  agent_name: "host",
  content: "让我分析一下数据..."
}
```

---

## ExecutionStep

执行步骤，用于历史恢复，位于 `types/execution.ts`。

```typescript
interface ExecutionStep {
  type: string;
  agent_name?: string;
  agent_role?: string;
  content?: string;
  model_output?: string;
  tool_name?: string;
  input_args?: Record<string, unknown>;
  output?: string;
  status?: "running" | "completed" | "failed";
  duration_ms?: number;
  timestamp?: string;
}
```

### 用途

从历史记录恢复聊天状态时，使用 `steps` 重建消息内容。

```typescript
// 恢复时从 steps 提取
steps.forEach((step) => {
  if (step.type === "tool_use") {
    tools.push({
      type: "tool_call",
      toolName: step.tool_name,
      toolParams: JSON.stringify(step.input_args),
    });
  }
});
```

---

## WorkerRecord

Worker Agent 状态记录，位于 `pages/DataAnalysisPage/types.ts`。

```typescript
type WorkerRecord = {
  name: string;
  status: "running" | "completed" | "failed";
  durationMs?: number;
};
```

### 用途

在 AI 消息底部显示 Worker 执行状态指示器。

```tsx
// WorkerIndicators.tsx
{workerActivities.map((worker) => (
  <div key={worker.name}>
    <span>{worker.name}</span>
    <StatusIcon status={worker.status} />
    {worker.durationMs && <span>{formatDuration(worker.durationMs)}</span>}
  </div>
))}
```

---

## 类型关系图

```
ChatItem (消息)
├── id, sender, timestamp (基础信息)
├── content (旧格式文本)
├── segments[] (新格式分段)
│   ├── text
│   ├── think
│   ├── tool_call
│   └── tool_output
├── taskId (关联任务)
├── steps[] (历史步骤)
│   └── ExecutionStep
└── workerRecords[] (Worker状态)
    └── WorkerRecord

TaskEvent (流式事件)
├── event/type (事件类型)
├── agent_name/role (Agent信息)
├── content (内容)
└── tool_name/params (工具信息)
```

---

## 类型使用场景

| 场景 | 主要类型 | 文件位置 |
|------|----------|----------|
| 消息渲染 | `ChatItem`, `ChatSegment` | `DataAnalysisPage/types.ts` |
| 流式处理 | `TaskEvent` | `types/task.ts` |
| 历史恢复 | `ExecutionStep` | `types/execution.ts` |
| Worker展示 | `WorkerRecord` | `DataAnalysisPage/types.ts` |

---

## 扩展类型

### 添加新的 ChatSegment 类型

```typescript
// 1. 修改 types.ts
type ChatSegment = {
  type: "text" | "..." | "new_type";  // 添加新类型
  content: string;
  newField?: string;  // 新字段
};

// 2. 在 AiMessageContent 添加渲染逻辑
if (seg.type === "new_type") {
  return <NewComponent data={seg} />;
}
```

### 添加新的 TaskEvent 类型

```typescript
// 1. 扩展 TaskEvent 类型
type TaskEvent = {
  // ...
  new_event_type?: string;
};

// 2. 在 eventProcessor 添加处理
if (event.event === "new_event") {
  // 处理逻辑
}
```
