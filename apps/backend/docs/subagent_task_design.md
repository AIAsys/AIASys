# SubAgent & Task 架构设计

> 历史材料说明
>
> 本文保留早期 Task / SubAgent 设计推演，示例工具名与配置片段已经过期。
> 当前实现请优先回看 `apps/backend/app/` 对应源码与 `apps/backend/docs/README.md` 的当前入口。

## 概述

AIASys 支持 **Host-Worker** 双 Agent 架构，通过 `Task` 工具实现任务的委派和协作。Host Agent 负责整体规划，SubAgent 专注于特定领域的任务执行。

```
┌─────────────────┐     Task 委派      ┌─────────────────┐
│   Host Agent    │ ──────────────────> │   SubAgent      │
│  (全局规划)      │                     │ (领域专精)       │
└─────────────────┘                     └─────────────────┘
         │                                       │
         │         .execution/                   │
         │         ├── host_events.jsonl         │
         │         └── subagents/                │
         │             └── {task_id}.jsonl       │
         └───────────────────────────────────────┘
```

---

## 核心概念

### 1. SubAgent（子代理）

SubAgent 是独立的 Agent 配置，具有：
- **独立的系统提示词**：专注特定领域（如数据分析、代码审查）
- **独立的工具集**：可选择性启用部分工具
- **隔离的执行环境**：在 Docker 沙盒中运行

### 2. Task 工具

`Task` 是特殊的工具调用，用于将任务委派给 SubAgent：

```python
# Task 工具参数
{
    "subagent_name": "coder",           # 目标子代理
    "description": "编写排序算法",       # 任务描述
    "prompt": "详细任务说明..."          # 完整提示词
}
```

### 3. 执行流程

```
User Request
     │
     ▼
┌─────────────┐    Step 1    ┌─────────────┐
│ Host Agent  │ ───────────> │  Task 工具   │
│             │              │  调用       │
└─────────────┘              └──────┬──────┘
                                    │
                     SubagentEvent  │ 流式输出
                     (task_tool_call_id)
                                    │
                                    ▼
                           ┌─────────────┐
                           │  SubAgent   │
                           │  (coder)    │
                           │  Step 1-N   │
                           └─────────────┘
                                    │
                     Step End       │
                     ToolResult     │
                                    ▼
                           ┌─────────────┐
                           │ Host Agent  │
                           │  汇总结果    │
                           └─────────────┘
```

---

## 存储架构

### Agent Runtime 原生存储（.session/）

Agent Runtime 自动管理以下文件：

```
.session/{session_id}/
├── context.jsonl              # Host Agent 对话历史
├── context_sub_1.jsonl        # 第1个 SubAgent/CreateSubagent
├── context_sub_2.jsonl        # 第2个 SubAgent/CreateSubagent
└── context_sub_N.jsonl        # 第N个...
```

**文件名生成规则**（来自 runtime 源码）：
```python
subagent_base_name = f"{main_context_file.stem}_sub"  # "context_sub"
# 通过 next_available_rotation 找下一个序号: _1, _2, _3...
```

**SDK 存储的特点**：

| 特点 | 说明 |
|-----|------|
| **自动管理** | SDK 自动创建和维护 |
| **无关联 ID** | `context_sub_*.jsonl` **不包含** `task_tool_call_id` |
| **仅 Message** | 只保存 `user/assistant/tool` message，无实时事件 |
| **用于恢复** | 仅供 SDK 恢复 Session 使用 |

**关键问题**：SDK 的 SubAgent context **不保存与 Host Task 的关联**！

```
Host context.jsonl:
  ├─ ToolCall: Task (id=tool_abc123)
  └─ ToolResult: task_tool_call_id=tool_abc123

SubAgent context_sub_1.jsonl:
  ├─ user: "任务详情..."
  ├─ assistant: tool_calls=[RunNotebook]
  └─ tool: RunNotebook 结果
  
   文件中**没有** tool_abc123 的引用！
```

### 自定义执行日志（.execution/）

由于 SDK 的存储不包含关联信息，我们需要自己维护执行日志：

```
.execution/
├── host_events.jsonl              # Host Agent 完整事件流
└── subagents/
    └── {task_tool_call_id}.jsonl  # 按 Task ID 组织的 SubAgent 事件
```

**为什么需要双重存储？**

| 维度 | SDK (.session/) | 自定义 (.execution/) |
|-----|----------------|---------------------|
| **管理者** | SDK 自动 | 我们的代码 |
| **关联性** |  无 Task ID 关联 |  明确 `task_tool_call_id` |
| **实时事件** |  无 (Think/Step等) |  完整保存 |
| **用途** | LLM 恢复对话 | 前端展示/执行回放 |
| **稳定性** | SDK 内部格式 | 我们控制的格式 |

### 存储对比示例

**场景**：Host 调用 Task → coder 创建文件

**SDK 存储**：
```jsonl
// context.jsonl (Host)
{"role":"assistant","tool_calls":[{"id":"tool_abc123","name":"Task"...}]}
{"role":"tool","tool_call_id":"tool_abc123","content":"任务完成"}

// context_sub_1.jsonl (SubAgent)
{"role":"user","content":"创建文件..."}
{"role":"assistant","tool_calls":[{"name":"RunNotebook"...}]}
{"role":"tool","content":"文件已创建"}
//  没有 tool_abc123 的引用，无法关联到 Host 的 Task
```

**我们的存储**（.execution/）：
```jsonl
// host_events.jsonl
{"event_type":"tool_call","tool_call_id":"tool_abc123","tool_name":"Task"}

// subagents/tool_abc123.jsonl
{"task_tool_call_id":"tool_abc123","event_type":"step_begin","step_n":1}
{"task_tool_call_id":"tool_abc123","event_type":"think","content":"我需要..."}
{"task_tool_call_id":"tool_abc123","event_type":"tool_call","tool_name":"RunNotebook"}
//  明确关联到 tool_abc123
```

### 存储示例

**Host 事件** (`.execution/host_events.jsonl`):
```jsonl
{"event_id": "...", "event_type": "step_begin", "step_n": 1, ...}
{"event_id": "...", "event_type": "tool_call", "tool_name": "Task", "tool_call_id": "tool_abc123", ...}
{"event_id": "...", "event_type": "tool_result", "tool_call_id": "tool_abc123", ...}
```

**SubAgent 事件** (`.execution/subagents/tool_abc123.jsonl`):
```jsonl
{"event_id": "...", "task_tool_call_id": "tool_abc123", "event_type": "step_begin", "step_n": 1, ...}
{"event_id": "...", "task_tool_call_id": "tool_abc123", "event_type": "think", "content": "我需要..."}
{"event_id": "...", "task_tool_call_id": "tool_abc123", "event_type": "tool_call", "tool_name": "RunNotebook", ...}
{"event_id": "...", "task_tool_call_id": "tool_abc123", "event_type": "tool_result", ...}
```

对比 SDK 的存储 (`.session/context_sub_1.jsonl`)：
```jsonl
{"role":"user","content":"创建文件..."}
{"role":"assistant","tool_calls":[{"name":"RunNotebook"...}]}
{"role":"tool","content":"文件已创建"}
//  没有 task_tool_call_id，无法关联到 Host
```

---

## SDK 源码分析

### 关键发现

通过分析 runtime 源码，我们发现：

```python
# task.py 第 101-127 行
async def _run_subagent(self, agent: Agent, prompt: str) -> ToolReturnValue:
    # 1. 获取当前 Task 的 tool_call_id
    current_tool_call = get_current_tool_call_or_none()
    current_tool_call_id = current_tool_call.id  # ← 有关联 ID！
    
    # 2. 通过 Wire 发送实时事件（包含 task_tool_call_id）
    def _super_wire_send(msg: WireMessage) -> None:
        event = SubagentEvent(
            task_tool_call_id=current_tool_call_id,  # ← 包含关联！
            event=msg,
        )
        super_wire.soul_side.send(event)  # ← 只发实时流，不存文件！
    
    # 3. 创建 SubAgent context 文件（不包含 task_tool_call_id）
    subagent_context_file = await self._get_subagent_context_file()
    # 文件名: context_sub_1.jsonl, context_sub_2.jsonl...
    context = Context(file_backend=subagent_context_file)
    # ← 只存 message history，不存关联信息！
```

### SubAgent Context 文件生成

```python
# task.py 第 71-80 行
async def _get_subagent_context_file(self) -> Path:
    main_context_file = self._session.context_file
    subagent_base_name = f"{main_context_file.stem}_sub"  # "context_sub"
    # 通过 next_available_rotation 找下一个序号
    sub_context_file = await next_available_rotation(
        main_context_file.parent / f"{subagent_base_name}{main_context_file.suffix}"
    )
    return sub_context_file
```

结果文件名：
- `context_sub_1.jsonl` - 第 1 个 SubAgent
- `context_sub_2.jsonl` - 第 2 个 SubAgent
- ...

**问题**：序号只表示创建顺序，不对应具体的 Task ID。

---

## 事件关联机制

### 关联字段：`task_tool_call_id`

```
Host ToolCall
├─ id: "tool_abc123"                    # Host 的工具调用 ID
├─ function.name: "Task"
└─ function.arguments.subagent_name: "coder"

    SubagentEvent (流式输出)
    ├─ task_tool_call_id: "tool_abc123"  # 关联到 Host 的调用
    ├─ event_type: "text" | "tool_call" | ...
    └─ ...

Host ToolResult
├─ tool_call_id: "tool_abc123"          # 与 ToolCall 对应
└─ return_value: "任务完成..."
```

### 前端展示层级

```
[Host] Step 1
├─ [Host] Think: 我应该委派给 coder
├─ [Host] ToolCall: Task → coder (tool_abc123)
│  │
│  ├─ [coder] Step 1
│  ├─ [coder] Think: 我需要创建 CSV
│  ├─ [coder] ToolCall: RunNotebook
│  ├─ [coder] ToolResult: 成功
│  └─ [coder] Text: 任务完成！
│
├─ [Host] ToolResult: 任务完成！（来自 coder）
└─ [Host] Text: coder 已完成数据分析
```

---

## SSE 事件流

### 前端接收的事件类型

```typescript
// Host 文本输出
{ type: "text", content: "我来帮你..." }

// Host 工具调用（包括 Task）
{ 
  type: "tool_call", 
  tool: "Task", 
  arguments: { subagent_name: "coder", ... }
}

// Host 工具结果
{ 
  type: "tool_result", 
  tool_call_id: "tool_abc123",
  output: "任务完成！",
  success: true 
}

// 新增：SubAgent 事件（核心）
{
  type: "subagent_event",
  task_tool_call_id: "tool_abc123",
  subagent_name: "coder",
  event_type: "text" | "tool_call" | "tool_result" | "think" | "step_begin",
  // 根据 event_type 变化：
  content?: string,           // text, think
  tool_name?: string,         // tool_call
  tool_call_id?: string,      // tool_call, tool_result
  arguments?: object,         // tool_call
  output?: string,            // tool_result
  success?: boolean,          // tool_result
  step_n?: number             // step_begin
}

// 文件变更（原有）
{ type: "file_changes", changes: [...] }
```

---

## API 接口

### 执行日志查询

```bash
# 获取 Host Agent 事件
GET /api/agent/execution/{user_id}/{session_id}/host

# 获取特定 Task 的 SubAgent 事件
GET /api/agent/execution/{user_id}/{session_id}/subagent/{task_tool_call_id}

# 获取合并的执行流程（按时间排序）
GET /api/agent/execution/{user_id}/{session_id}/flow

# 获取 Task 摘要列表
GET /api/agent/execution/{user_id}/{session_id}/tasks
```

### 响应示例

**`/tasks` 端点**:
```json
{
  "user_id": "test_user",
  "session_id": "test_session",
  "tasks": [
    {
      "task_tool_call_id": "tool_abc123",
      "subagent_name": "coder",
      "event_count": 31
    }
  ],
  "count": 1
}
```

**`/flow` 端点**:
```json
{
  "user_id": "test_user",
  "session_id": "test_session",
  "events": [
    { "agent": "host", "event_type": "tool_call", "tool_name": "Task", ... },
    { "agent": "subagent", "task_tool_call_id": "tool_abc123", "event_type": "step_begin", ... },
    { "agent": "subagent", "task_tool_call_id": "tool_abc123", "event_type": "tool_call", ... }
  ],
  "task_count": 1,
  "task_tool_call_ids": ["tool_abc123"]
}
```

---

## 配置指南

### 1. 启用 Task 工具

```yaml
# agent.yaml
agent:
  tools:
    # 必须启用这两个工具
    - "app.services.agent.runtime_backends.aiasys.tools.task_tool:TaskTool"
    - "app.services.agent.runtime_backends.aiasys.tools.create_subagent_tool:CreateSubagentTool"
    # 其他工具...
    - "app.agents.tools.read_media_tool:ReadMediaFile"
```

### 2. 配置 SubAgent

```yaml
# agent.yaml
agent:
  subagents:
    coder:
      path: ./coder.yaml          # 子代理配置文件路径
      description: |
        专业的代码编写和调试助手，擅长 Python 编程。
    
    data_analyst:
      path: ./data_analyst.yaml
      description: |
        数据分析专家，精通 pandas、numpy、matplotlib。
```

### 3. SubAgent 配置

```yaml
# coder.yaml
version: 1
agent:
  extend: default
  name: "coder"
  description: "代码编写助手"
  
  tools:
    - "app.agents.tools.read_media_tool:ReadMediaFile"
    - "app.agents.tools.notebook_session_tool:ListSessionNotebooksTool"
    - "app.agents.tools.notebook_session_tool:ReadNotebookOutputsTool"
  
  system_prompt_path: ./coder_prompt.md
```

---

## 前端集成

### 实时展示

```typescript
// SSE 连接
const eventSource = new EventSource('/api/agent/execute/stream');

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  switch (data.type) {
    case 'tool_call':
      if (data.tool === 'Task') {
        // 显示 Task 开始
        showTaskStart(data.arguments.subagent_name);
      }
      break;
      
    case 'subagent_event':
      // 显示 SubAgent 执行详情
      showSubAgentEvent(data);
      break;
  }
};
```

### 历史回放

```typescript
// 获取完整执行流程
const response = await fetch(`/api/agent/execution/${userId}/${sessionId}/flow`);
const { events } = await response.json();

// 按层级组织事件
const tree = buildExecutionTree(events);
renderExecutionSteps(tree);
```

---

## 调试技巧

### 查看执行日志

```bash
# Host 事件
cat workspaces/{user_id}/{session_id}/.execution/host_events.jsonl | jq .

# SubAgent 事件
cat workspaces/{user_id}/{session_id}/.execution/subagents/tool_xxx.jsonl | jq .
```

### API 测试

```bash
curl "http://localhost:13001/api/agent/execution/test_user/test_session/tasks"
```

---

## 相关文件

### 后端代码

| 文件 | 说明 |
|-----|------|
| `app/services/agent_service.py` | Agent 执行服务，处理 SubagentEvent 并记录执行日志 |
| `app/services/execution_logger.py` | 执行日志记录和查询，维护 Host/SubAgent 事件关联 |
| `app/api/routes/agent.py` | API 路由定义，提供执行日志查询接口 |
| `app/agents/docker_sandbox_agent_config/data_analysis.yaml` | Docker 模式 Host Agent 配置 |
| `app/agents/docker_sandbox_agent_config/data_analysis_sub.yaml` | Docker 模式 Worker Agent 配置 |
| `app/services/agent/system_presets.py` | Local 主线 system preset 事实源（Host/Subagent 基线） |
| `app/agents/local_sandbox_agent_config/*.md` | Local 主线 prompt 模板 |

### SDK 源码参考

| 文件 | 说明 |
|-----|------|
| `app/services/agent/runtime_backends/aiasys/tools/task_tool.py` | Task 工具实现，创建 SubAgent context |
| `app/services/agent/subagent_storage.py` | SubAgent 存储管理 |
| `app/services/agent/runtime_backends/aiasys/session.py` | Session 与 Wire 消息类型 |

### 存储路径

```
workspaces/{user_id}/{session_id}/
├── .session/{session_id}/
│   ├── context.jsonl              # SDK: Host Agent
│   ├── context_sub_1.jsonl        # SDK: SubAgent #1 (无 Task ID)
│   └── context_sub_2.jsonl        # SDK: SubAgent #2 (无 Task ID)
├── .execution/
│   ├── host_events.jsonl          # 自定义: Host 事件
│   └── subagents/
│       └── {task_tool_call_id}.jsonl  # 自定义: 按 Task ID 组织的 SubAgent 事件
└── workspace/                     # 工作文件
    └── ...
```

---

## 架构优势

1. **职责分离**: Host 规划、SubAgent 执行，各司其职
2. **领域专精**: 不同 SubAgent 专注不同领域，效果更优
3. **完整可观测**: 通过 `.execution/` 存储，实现完整执行回放
4. **实时流式**: SubAgent 执行过程实时推送到前端
5. **调试友好**: 详细的执行日志便于问题定位
