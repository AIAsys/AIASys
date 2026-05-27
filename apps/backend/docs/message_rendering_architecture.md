# 消息渲染架构设计文档

本文档说明 AIASys 中历史会话加载与流式输出的消息渲染架构。

## 概述

前端使用统一的 `ChatItem` 数据结构来表示聊天消息，支持两种数据来源：
1. **流式输出** - 实时从后端接收的事件流
2. **历史加载** - 从 `/api/sessions/{id}/history` 接口加载的持久化消息

两种来源最终都渲染为相同的 UI 组件，但数据流转路径不同。

## 核心数据结构

### ChatItem (前端类型定义)

```typescript
type ChatItem = {
  type: "message";
  id: string;
  sender: "user" | "ai";
  role?: "user" | "assistant" | "system";
  content?: string;           // 纯文本内容（向后兼容）
  segments?: ChatSegment[];   // 分段内容（新格式，优先使用）
  timestamp: Date;
  isStreaming?: boolean;
  isStopped?: boolean;
  taskId?: string;
  steps?: ExecutionStep[];    // 执行步骤（用于恢复执行空间）
  workerRecords?: WorkerRecord[];
  attachments?: string[];
};

type ChatSegment = {
  type: "text" | "thought" | "final_answer" | "tool_call" | "tool_output" | "think";
  content: string;
  toolName?: string;
  toolParams?: string;
  isComplete?: boolean;       // 用于 think 类型的流式状态
};
```

### 后端消息格式

后端存储的消息 `content` 字段支持两种格式：

**格式 1: 字符串（旧格式，向后兼容）**
```json
{
  "role": "assistant",
  "content": "这是纯文本回复"
}
```

**格式 2: 数组（新格式，推荐）**
```json
{
  "role": "assistant",
  "content": [
    {"type": "think", "think": "我在思考..."},
    {"type": "text", "text": "这是最终回复"}
  ]
}
```

## 流式输出路径

### 数据流

```
用户提交 → useAgentStream → SSE 事件 → 构建 segments → setChatItems → 渲染
```

### 关键代码位置

**事件处理**: `apps/web/src/pages/DataAnalysisPage/hooks/useCodeExecutor/index.ts:289-370`

流式输出时，前端通过 SSE 接收事件，直接构建 `ChatSegment` 数组：

```typescript
// text 类型 segment
if (eventType === "text" && event.content) {
  const segments = streamingSegmentsRef.current;
  const lastSeg = segments[segments.length - 1];
  if (lastSeg && lastSeg.type === "text" && !lastSeg.isComplete) {
    lastSeg.content += event.content;  // 追加到现有 segment
  } else {
    segments.push({ type: "text", content: event.content });
  }
}

// think 类型 segment
if (eventType === "think" && event.content) {
  const segments = streamingSegmentsRef.current;
  const lastSeg = segments[segments.length - 1];
  if (lastSeg && lastSeg.type === "think" && !lastSeg.isComplete && isStreaming) {
    lastSeg.content += event.content;
  } else {
    segments.push({ type: "think", content: event.content, isComplete: false });
  }
}
```

### 渲染逻辑

**组件**: `apps/web/src/components/chat/AiMessageContent/index.tsx:321-381`

当 `segments` 存在时，按顺序渲染每个 segment：
- `think` → `StreamingThoughtBlock` 组件
- `text` → `ReactMarkdown` 渲染
- `tool_call` / `tool_output` → 工具调用/结果展示

## 历史加载路径

### 数据流

```
点击历史会话 → useSessionManagement → API 请求 → 解析 content → 构建 segments → setChatItems → 渲染
```

### 关键代码位置

**数据处理**: `apps/web/src/pages/DataAnalysisPage/hooks/useSessionManagement.ts:87-124`

历史加载时，需要将后端返回的数组格式 `content` 转换为前端 `ChatSegment`：

```typescript
function buildSegmentsFromContent(
  content: string | Array<{ type: string; text?: string; think?: string }>,
): ChatSegment[] | undefined {
  if (!content || typeof content === "string") return undefined;
  if (!Array.isArray(content)) return undefined;

  const segments: ChatSegment[] = [];
  for (const segment of content) {
    if (segment.type === "text" && segment.text) {
      segments.push({ type: "text", content: segment.text });
    } else if (segment.type === "think" && segment.think) {
      segments.push({ type: "think", content: segment.think, isComplete: true });
    }
  }
  return segments.length > 0 ? segments : undefined;
}
```

创建 `ChatItem` 时同时设置 `content` 和 `segments`：

```typescript
const normalizedContent = normalizeContent(msg.content);
const segments = buildSegmentsFromContent(msg.content);

restoredItems.push({
  type: "message",
  id: msg.id || `msg-${sid}-${timeValue}-${index}`,
  sender: "ai",
  role: "assistant",
  content: normalizedContent,      // 字符串格式，用于兼容
  segments: segments,              // segment 数组，用于正确渲染
  timestamp: isNaN(ts.getTime()) ? new Date() : ts,
  isStreaming: false,
  steps: msg.steps,                // 恢复执行步骤
});
```

### 为什么需要 segments

如果不提供 `segments`，`AiMessageContent` 会尝试从 `steps` 中提取内容（`useDerivedFromSteps`），但：
1. `useDerivedFromSteps` 只处理 `agent_role === "host"` 的 steps
2. 实际执行可能是 worker 完成的，导致内容提取失败
3. 直接使用后端存储的 `content` 数组是最可靠的方式

## 渲染统一性

两种路径最终都通过相同的渲染逻辑：

**入口组件**: `apps/web/src/components/chat/AiMessageContent/index.tsx`

```typescript
const renderSegments = () => {
  if (!segments || segments.length === 0) {
    // 没有 segments 时，尝试从 steps 派生（历史兼容）
    return (
      <>
        <ThoughtSection derivedThoughts={derivedFromSteps?.thoughts} />
        <ToolsSection tools={tools} derivedTools={derivedFromSteps?.tools} />
        <AnswerSection
          finalAnswer={mergedFinalAnswer}
          derivedFinalAnswer={derivedFromSteps?.finalAnswer}
        />
      </>
    );
  }

  // 按顺序渲染每个 segment
  return segments.map((seg, idx) => {
    if (seg.type === "think") {
      return <StreamingThoughtBlock ... />;
    }
    if (seg.type === "text") {
      return <ReactMarkdown ...>{seg.content}</ReactMarkdown>;
    }
    // ... 其他类型
  });
};
```

## 向后兼容性

### 旧格式消息
- `content` 是字符串
- `segments` 为 `undefined`
- 渲染时走 `derivedFromSteps` 分支或直接使用 `content`

### 新格式消息
- `content` 是数组（后端返回）
- 前端转换为字符串 `content` + `segments` 数组
- 渲染时走 `segments` 分支，显示效果与流式输出一致

## 相关文件

| 文件 | 说明 |
|------|------|
| `apps/web/src/pages/DataAnalysisPage/hooks/useSessionManagement.ts` | 历史会话加载逻辑 |
| `apps/web/src/pages/DataAnalysisPage/hooks/useCodeExecutor/index.ts` | 流式输出处理 |
| `apps/web/src/components/chat/AiMessageContent/index.tsx` | AI 消息渲染组件 |
| `apps/web/src/pages/DataAnalysisPage/types.ts` | ChatItem / ChatSegment 类型定义 |

## 注意事项

1. **后端存储格式**: 后端消息 `content` 可以是字符串或数组，前端需要处理两种情况
2. **Segment 优先级**: 渲染时优先使用 `segments`，不存在时才从 `steps` 派生
3. **Think 完成状态**: 历史加载的 `think` segment 标记为 `isComplete: true`，流式输出时根据事件标记
4. **内容归一化**: `normalizeContent()` 确保 `content` 始终是字符串，用于兼容旧代码
