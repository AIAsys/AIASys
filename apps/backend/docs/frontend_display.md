# 前端显示方案（基于 context.jsonl）

> 历史材料说明
>
> 本文保留早期消息展示草稿，示例消息与工具名仅作演进参考。
> 当前前端行为请以运行中页面、接口返回与对应源码实现为准。

根据实际 `context.jsonl` 内容，前端应该显示什么、不显示什么。

---

## context.jsonl 结构分析

```jsonl
{"role": "_checkpoint", "id": 0}                                     不显示
{"role": "user", "content": "..."}                                   显示
{"role": "_usage", "token_count": 2649}                              可选（底部统计）
{"role": "assistant", "content": [
  {"type": "think", "think": "用户要求我...", "encrypted": null},    折叠显示
  {"type": "text", "text": "我将使用..."}                           显示
], "tool_calls": [...]}                                               显示工具调用
{"role": "tool", "content": "图表已保存...", "tool_call_id": "..."}   显示结果
```

---

## 显示策略

### 1. 用户消息（user）

```json
{"role": "user", "content": "请使用 RunNotebook 工具创建..."}
```

**显示方式：**
- 气泡形式，靠右，蓝色背景
- 直接显示 `content` 文本

```

  请使用 RunNotebook 工具创建...         user
                           10:00     

```

---

### 2. AI 消息（assistant）

```json
{
  "role": "assistant",
  "content": [
    {"type": "think", "think": "用户要求我创建...", "encrypted": null},
    {"type": "text", "text": "我将使用 RunNotebook..."}
  ],
  "tool_calls": [{
    "type": "function",
    "id": "tool_xxx",
    "function": {"name": "RunNotebook", "arguments": "{notebook_path: \"analysis.ipynb\"}"}
  }]
}
```

**显示方式：**

#### a) Think 部分（折叠显示）

```

   思考过程                          折叠状态，点击展开

  用户要求我创建一个柱状图...             展开后显示 think 内容
  我需要使用 RunNotebook 工具...        

```

**默认折叠**，因为：
- 思考过程通常很长
- 用户主要关心结果
- 需要时可展开查看

#### b) Text 部分（直接显示）

```

  我将使用 RunNotebook 工具为您...         直接显示
                                     
  图表已成功创建...                   
   标题：月度销售数据               
   X轴标签：月份                    

```

#### c) Tool Calls（工具调用卡片）

```

   使用工具: RunNotebook             标题，点击展开
                                    

  参数:                                 展开后显示
  ```json
  {"notebook_path":"analysis.ipynb","scope":"cell","cell_index":3}
  ```                                

```

**交互：**
- 默认折叠，显示工具名称
- 点击展开查看参数（代码、参数等）
- 显示执行状态（执行中/已完成）

---

### 3. 工具结果（tool）

```json
{
  "role": "tool",
  "content": "图表已成功保存到 /workspace/chart.png",
  "tool_call_id": "tool_klKkE1fO2PqJwIF3fbaC2OXp"
}
```

**显示方式：**

选项 A：合并到工具调用卡片
```

   使用工具: RunNotebook          
                                    

  参数: ...                          

   执行结果:                          显示 tool content
  图表已成功保存到 /workspace/chart.png

```

选项 B：单独显示（推荐）
```

   工具执行成功                    
  图表已成功保存到 /workspace/chart.png

```

---

### 4. 不显示的内容

| role | 说明 | 原因 |
|------|------|------|
| `_checkpoint` | 会话检查点 | 内部使用，无展示价值 |
| `_usage` | Token 统计 | 可选显示在底部统计栏 |

---

## 完整对话显示示例

```

   销售数据分析                                          

                                                            

    请使用 RunNotebook 工具创建...                         
                                             10:00:15    
     
                                                            
     
     思考过程                                         
     
                                                            
     
    我将使用 RunNotebook 工具为您创建柱状图。              
                                                        
     使用工具: RunNotebook                           
                                                        
     工具执行成功                                      
    图表已成功保存到 /workspace/chart.png               
                                                        
    图表包含以下内容：                                   
     标题：月度销售数据                                
     X轴标签：月份                                     
                                             10:00:18    
     
                                                            
   附件:                                                  
   chart.png (15.4 KB)  [查看] [下载]                    
                                                            

  [输入框...]                                    [发送]     

```

---

## 组件设计

### AssistantMessage 组件

```typescript
interface AssistantMessageProps {
  content: Array<{
    type: 'think' | 'text';
    think?: string;
    text?: string;
  }>;
  tool_calls?: Array<{
    id: string;
    function: {
      name: string;
      arguments: string;  // JSON string
    }
  }>;
  timestamp: string;
}

// 渲染逻辑
const AssistantMessage = ({ content, tool_calls }) => {
  return (
    <div className="assistant-message">
      {/* Think 部分 - 折叠 */}
      {content.map(part => 
        part.type === 'think' ? (
          <ThinkBox key="think" content={part.think} />
        ) : (
          <TextContent key="text" content={part.text} />
        )
      )}
      
      {/* Tool Calls - 折叠 */}
      {tool_calls?.map(tool => (
        <ToolCallCard key={tool.id} tool={tool} />
      ))}
    </div>
  );
};
```

### ThinkBox 组件（可折叠）

```typescript
const ThinkBox = ({ content }: { content: string }) => {
  const [expanded, setExpanded] = useState(false);
  
  return (
    <div className="think-box">
      <div 
        className="think-header" 
        onClick={() => setExpanded(!expanded)}
      >
        <span> 思考过程</span>
        <span>{expanded ? '' : ''}</span>
      </div>
      {expanded && (
        <pre className="think-content">{content}</pre>
      )}
    </div>
  );
};
```

### ToolCallCard 组件

```typescript
const ToolCallCard = ({ tool }: { tool: ToolCall }) => {
  const [expanded, setExpanded] = useState(false);
  const args = JSON.parse(tool.function.arguments);
  
  return (
    <div className="tool-call-card">
      <div 
        className="tool-header"
        onClick={() => setExpanded(!expanded)}
      >
        <span> {tool.function.name}</span>
        <span>{expanded ? '' : ''}</span>
      </div>
      {expanded && (
        <div className="tool-content">
          {args.code && (
            <pre><code>{args.code}</code></pre>
          )}
          {/* 显示 tool 结果 */}
        </div>
      )}
    </div>
  );
};
```

---

## 数据转换

### 从 context.jsonl 到前端消息列表

```typescript
function parseContextToMessages(contextLines: string[]): Message[] {
  const messages: Message[] = [];
  
  for (const line of contextLines) {
    const msg = JSON.parse(line);
    
    switch (msg.role) {
      case 'user':
        messages.push({
          role: 'user',
          content: msg.content,
          type: 'text'
        });
        break;
        
      case 'assistant':
        messages.push({
          role: 'assistant',
          content: msg.content,  // 包含 think 和 text
          tool_calls: msg.tool_calls,
          type: 'complex'
        });
        break;
        
      case 'tool':
        // 找到对应的 assistant 消息，附加结果
        const lastAssistant = messages.findLast(m => m.role === 'assistant');
        if (lastAssistant) {
          lastAssistant.tool_result = {
            call_id: msg.tool_call_id,
            content: msg.content
          };
        }
        break;
        
      // _checkpoint, _usage 忽略
    }
  }
  
  return messages;
}
```

---

## API 汇总

### 获取历史消息

```bash
GET /api/sessions/{user_id}/{session_id}/messages
```

**响应：**
```json
{
  "messages": [
    {"role": "user", "content": "...", "timestamp": "...", "metadata": {}},
    {"role": "assistant", "content": [{"type": "text", ...}], "timestamp": "..."}
  ]
}
```

### 流式执行

```bash
POST /api/agent/execute/stream
Content-Type: application/json

{
  "message": "用户输入",
  "session_id": "会话ID"
}
```

**SSE 事件：**
| type | 说明 |
|------|------|
| status | 状态更新（"思考中..."） |
| text | 文本片段（追加显示） |
| tool_call | 工具调用（显示卡片） |
| tool_result | 工具结果（更新卡片） |
| file_changes | 文件变化（更新文件树） |
| error | 错误信息 |

### 文件操作

```bash
GET /api/workspaces/{workspace_id}/files/list  # 列出当前工作区文件
GET /api/files/download/{user_id}/{session_id}/{filename}  # 下载历史会话产物
```

---

## 错误处理

### SSE 连接断开

```typescript
eventSource.onerror = () => {
  showReconnectDialog('连接已断开，是否重试？');
};
```

### 重连逻辑

1. 重新建立 SSE 连接
2. 获取最新消息状态
3. 恢复显示

---

## 总结

### 显示规则

| 来源 | 显示方式 | 默认状态 |
|------|---------|---------|
| user.content | 气泡文本 | 展开 |
| assistant.content (text) | 气泡文本 | 展开 |
| assistant.content (think) | 折叠面板 | 折叠 |
| assistant.tool_calls | 工具卡片 | 折叠 |
| tool.content | 结果提示 | 展开 |

### 不显示

- `_checkpoint` - 内部检查点
- `_usage` - 可放底部统计

### 原则

> **context 里有的就显示，没有的不加。**
> 
> 保持简洁，不要为了美观而增加不必要的复杂度。

---

## SSE 事件流（流式执行）

### 事件类型

后端通过 SSE 实时推送执行进度：

```typescript
// 基础事件类型
type SSEEvent =
  | { type: 'status'; message: string }
  | { type: 'text'; content: string }
  | { type: 'tool_call'; tool: string; arguments: Record<string, unknown> }
  | { type: 'tool_result'; tool_call_id: string; output: string; success: boolean }
  | { type: 'file_changes'; changes: FileChange[] }
  | { type: 'subagent_event'; task_tool_call_id: string; subagent_name?: string; event_type: string; ... }
  | { type: 'error'; message: string };
```

### 各事件处理

| 事件类型 | 显示方式 | 说明 |
|---------|---------|------|
| `status` | 状态条/Toast | 显示当前执行状态 |
| `text` | 文本流 | 实时追加到聊天窗口 |
| `tool_call` | 工具卡片 | 展开显示工具名称和参数 |
| `tool_result` | 工具结果 | 合并到对应的工具卡片 |
| `file_changes` | 文件通知 | 提示文件变更，刷新文件树 |
| `subagent_event` | **SubAgent 面板** | 见下方详细说明 |
| `error` | 错误提示 | 显示错误消息 |

### SubAgent 事件显示

当收到 `subagent_event` 时，需要特殊处理以展示层级关系：

```typescript
// SubAgent 事件结构
interface SubagentEvent {
  type: 'subagent_event';
  task_tool_call_id: string;  // 关联到 Host 的 Task 调用
  subagent_name?: string;     // 如 "coder", "data_worker"
  event_type: 'step_begin' | 'think' | 'text' | 'tool_call' | 'tool_result' | 'token_usage';
  // 根据 event_type 变化的字段...
  step_n?: number;
  content?: string;
  tool_name?: string;
  tool_call_id?: string;
  arguments?: Record<string, unknown>;
  output?: string;
  success?: boolean;
}
```

**显示策略：**

```
[Host] 调用 Task  coder
 [coder] Step 1
 [coder]  思考：我需要创建文件...
 [coder]  调用 RunNotebook
   参数：
    ```json
    {"notebook_path":"scratch.ipynb","scope":"cell","cell_index":0}
    ```
    结果：文件已创建
 [coder] 输出：任务完成！
[Host] Task 完成
```

**组件设计：**

```typescript
interface SubAgentPanelProps {
  taskToolCallId: string;
  subagentName: string;
  events: SubagentEvent[];
}

const SubAgentPanel = ({ taskToolCallId, subagentName, events }: SubAgentPanelProps) => {
  return (
    <div className="subagent-panel">
      <div className="subagent-header">
        <span> {subagentName}</span>
        <span className="task-id">{taskToolCallId.slice(0, 10)}...</span>
      </div>
      <div className="subagent-events">
        {events.map((event, idx) => (
          <SubAgentEventItem key={idx} event={event} />
        ))}
      </div>
    </div>
  );
};

const SubAgentEventItem = ({ event }: { event: SubagentEvent }) => {
  switch (event.event_type) {
    case 'step_begin':
      return <div className="step-marker">Step {event.step_n}</div>;
    case 'think':
      return (
        <div className="think-box collapsed">
          <span> 思考过程</span>
          <pre>{event.content}</pre>
        </div>
      );
    case 'text':
      return <div className="text-content">{event.content}</div>;
    case 'tool_call':
      return (
        <div className="tool-call">
          <span> {event.tool_name}</span>
        </div>
      );
    case 'tool_result':
      return (
        <div className={`tool-result ${event.success ? 'success' : 'error'}`}>
          {event.success ? '' : ''} {event.output?.slice(0, 100)}
        </div>
      );
    default:
      return null;
  }
};
```

### 层级展示实现

```typescript
// 将扁平事件流转换为树形结构
function buildExecutionTree(events: SSEEvent[]): ExecutionNode[] {
  const tree: ExecutionNode[] = [];
  const subagentPanels = new Map<string, ExecutionNode>();
  
  for (const event of events) {
    if (event.type === 'tool_call' && event.tool === 'Task') {
      // 创建 SubAgent 面板节点
      const taskId = event.tool_call_id;
      const subagentNode: ExecutionNode = {
        type: 'subagent',
        taskToolCallId: taskId,
        subagentName: event.arguments.subagent_name,
        children: []
      };
      subagentPanels.set(taskId, subagentNode);
      tree.push(subagentNode);
    }
    else if (event.type === 'subagent_event') {
      // 添加到对应的 SubAgent 面板
      const panel = subagentPanels.get(event.task_tool_call_id);
      if (panel) {
        panel.children.push({
          type: 'subagent_event',
          event
        });
      }
    }
    else {
      // Host 事件直接添加到树
      tree.push({
        type: 'host_event',
        event
      });
    }
  }
  
  return tree;
}
```

---

## 执行回放（历史记录）

### 从 API 获取执行日志

```typescript
// 获取 Host 事件
const hostEvents = await fetch(`/api/agent/execution/${userId}/${sessionId}/host`);

// 获取所有 Task
const tasks = await fetch(`/api/agent/execution/${userId}/${sessionId}/tasks`);

// 获取特定 Task 的 SubAgent 事件
const subagentEvents = await fetch(
  `/api/agent/execution/${userId}/${sessionId}/subagent/${taskToolCallId}`
);

// 获取合并的执行流程
const flow = await fetch(`/api/agent/execution/${userId}/${sessionId}/flow`);
```

### 回放显示

回放时需要模拟 SSE 的事件流，按时间顺序依次显示：

```typescript
async function replayExecution(sessionId: string) {
  const { events } = await fetch(`/api/agent/execution/${userId}/${sessionId}/flow`).then(r => r.json());
  
  for (const event of events) {
    if (event.agent === 'host') {
      displayHostEvent(event);
    } else {
      displaySubagentEvent(event);
    }
    await delay(100); // 模拟实时效果
  }
}
```
