---
name: agent-dev
description: Develop AIASys Agent tools and capabilities following current AIASys runtime best practices. Use when creating new tools for agents, implementing agent sessions, or working with sandbox execution. This skill covers tool development, sandbox security, agent state management, and streaming output. Always use this skill when the user asks you to create an agent tool, implement agent functionality, or work with the AIASys Agent runtime.
---

# Agent 开发规范

构建安全、可靠、可扩展的 AI Agent 能力。

---

## 开发范围

**本 Skill 覆盖：**
- Tool 开发（工具函数）
- Agent 会话管理
- AIASys Agent runtime 集成
- 沙盒执行安全
- 流式输出实现

**适用场景：**
- 新增 Agent 工具
- 修改现有 Tool 逻辑
- 实现 Agent 会话恢复
- 集成 AIASys Agent runtime 功能

**不覆盖：**
- "开发 AIASys 的 AI"的行为规范（参考 `aiasys-ai-integration`——本 skill 只覆盖 AIASys 内置 Agent 的工具开发）
- MCP 协议的 Client 连接和工具注册桥接（参考 `mcp-protocol`）
- SSE 事件流的具体实现（参考 `sse-real-time-communication`）
- IPython Kernel 和 UV 环境管理（参考 `python-runtime-sandbox`）

**关联文档：**
- `aiasys-ai-integration`：区分"开发 AIASys 的 AI"和"AIASys 内置 Agent"的边界
- `mcp-protocol`：MCP Client 连接管理、工具注册桥接
- `sse-real-time-communication`：SSE 事件流生成和解析
- `python-runtime-sandbox`：IPython Kernel 执行、沙盒环境
- `testing-strategy`：Agent Tool 的测试模板和规范

---

## Tool 开发

### 基础模板

```python
"""工具描述：说明工具功能。

工具参数：
    param1: 参数1说明
    param2: 参数2说明

返回值：
    返回值说明

异常：
    ToolError: 工具执行错误
    TimeoutError: 执行超时
"""

from typing import Dict, Any
from app.agents.tools.local_ipython_box import LocalIPythonBox, LocalIPythonBoxParams

async def tool_name(
    param1: str,
    param2: int
) -> Dict[str, Any]:
    # 参数验证
    if not param1:
        raise ValueError("param1 不能为空")
    
    # 在 LocalIPythonBox 中执行
    try:
        box = LocalIPythonBox()
        result = await box.invoke(
            **LocalIPythonBoxParams(code=f"print({param1})").model_dump()
        )
        return {"status": "success", "data": result.content}
    except TimeoutError:
        return {"status": "error", "error": "执行超时"}
    except Exception as e:
        return {"status": "error", "error": f"工具执行失败: {e}"}
```

### Tool 开发五要素

1. **完整 Docstring**
   - 工具功能描述
   - 参数说明
   - 返回值说明
   - 异常说明

2. **参数验证**
   ```python
   # 必填检查
   if not param1:
       raise ValueError("param1 不能为空")
   
   # 类型检查
   if not isinstance(param2, int):
       raise TypeError("param2 必须是整数")
   
   # 范围检查
   if param2 < 0 or param2 > 100:
       raise ValueError("param2 必须在 0-100 之间")
   ```

3. **沙盒执行**
   - 所有外部代码必须通过当前运行时工具执行，例如 `LocalIPythonBox`
   - 禁止直接执行用户输入的代码
   - 敏感操作需要额外权限检查

4. **超时控制**
   ```python
   # 默认超时
   DEFAULT_TIMEOUT = 30  # 秒
   
   # 长任务超时
   LONG_TIMEOUT = 300    # 5分钟
   
   # 执行时指定
   box = LocalIPythonBox()
   result = await box.invoke(**LocalIPythonBoxParams(code=code).model_dump())
   ```

5. **异常处理**
   ```python
   try:
       result = await execute_something()
       return {"status": "success", "data": result}
   except TimeoutError:
       return {"status": "error", "error": "执行超时", "error_code": "TIMEOUT"}
   except ValueError as e:
       return {"status": "error", "error": f"参数错误: {e}", "error_code": "INVALID_PARAM"}
   except Exception as e:
       # 未知错误记录日志
       logger.exception("Tool execution failed")
       return {"status": "error", "error": "工具执行失败", "error_code": "INTERNAL_ERROR"}
   ```

---

## 沙盒安全

### 安全原则

| 原则 | 说明 |
|------|------|
| 隔离执行 | 所有外部代码在沙盒中运行 |
| 资源限制 | CPU、内存、时间限制 |
| 网络控制 | 沙盒无网络访问（除非必要） |
| 文件隔离 | 沙盒文件系统与主机隔离 |

### 超时设置参考

```python
# 计算类任务
COMPUTE_TIMEOUT = 30

# IO 类任务
IO_TIMEOUT = 60

# 网络请求
NETWORK_TIMEOUT = 30

# 复杂分析
ANALYSIS_TIMEOUT = 300

# 代码执行（用户代码）
USER_CODE_TIMEOUT = 60
```

### 资源限制

```python
# LocalIPythonBox 资源限制配置
RESOURCE_LIMITS = {
    "cpu_quota": 100000,      # CPU 限制
    "memory_limit": "512m",   # 内存限制
    "timeout": 60,            # 超时时间
    "max_output_size": 1024 * 1024,  # 最大输出 1MB
}
```

---

## Agent 状态管理

### 状态持久化要求

- Agent 状态必须持久化
- 支持断点续传
- 支持取消任务
- 支持会话恢复

### 状态流转

```python
class AgentState(Enum):
    IDLE = "idle"           # 空闲
    RUNNING = "running"     # 运行中
    PAUSED = "paused"       # 暂停
    COMPLETED = "completed" # 完成
    FAILED = "failed"       # 失败
    CANCELLED = "cancelled" # 已取消

# 状态转换
TRANSITIONS = {
    AgentState.IDLE: [AgentState.RUNNING],
    AgentState.RUNNING: [AgentState.PAUSED, AgentState.COMPLETED, AgentState.FAILED, AgentState.CANCELLED],
    AgentState.PAUSED: [AgentState.RUNNING, AgentState.CANCELLED],
}
```

### 会话恢复实现

```python
async def resume_session(session_id: str) -> Session:
    """恢复 Agent 会话"""
    # 1. 从存储加载会话状态
    state = await load_session_state(session_id)
    
    # 2. 重建会话上下文
    session = Session.restore(state)
    
    # 3. 恢复 Tool 状态
    await session.restore_tools()
    
    return session
```

---

## 流式输出

### SSE 流式实现

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from app.agents.session import Session

app = FastAPI()

@app.get("/api/agent/stream/{task_id}")
async def stream_task(task_id: str):
    """SSE 流式输出 Agent 执行结果"""
    
    async def event_generator():
        session = await Session.get(task_id)
        
        async for chunk in session.execute_stream():
            yield f"data: {json.dumps(chunk)}\n\n"
        
        # 发送结束标记
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

### 流式事件格式

```json
{
  "type": "text|tool_call|tool_result|error|done",
  "content": "...",
  "timestamp": "2026-03-30T10:30:00Z",
  "metadata": {}
}
```

---

## 测试要求

### 必须测试的场景

- [ ] **沙盒执行测试**：验证代码在沙盒中正确执行
- [ ] **超时场景测试**：验证超时处理正确
- [ ] **异常场景测试**：验证各种错误情况的处理
- [ ] **资源限制测试**：验证资源限制生效

### 测试模板

```python
import pytest
from app.agents.tools import sample_tool

@pytest.mark.asyncio
async def test_tool_success():
    """测试正常执行"""
    result = await sample_tool(param1="test", param2=42)
    assert result["status"] == "success"

@pytest.mark.asyncio
async def test_tool_timeout():
    """测试超时处理"""
    result = await sample_tool(param1="test", timeout=1)
    assert result["status"] == "error"
    assert result["error_code"] == "TIMEOUT"

@pytest.mark.asyncio
async def test_tool_invalid_param():
    """测试参数验证"""
    with pytest.raises(ValueError):
        await sample_tool(param1="", param2=42)
```

---

## 快速检查清单

**创建新 Tool 时：**
- [ ] 完整 docstring
- [ ] 参数验证
- [ ] 沙盒执行
- [ ] 超时控制
- [ ] 异常处理

**修改现有 Tool 时：**
- [ ] 检查影响范围
- [ ] 更新单元测试
- [ ] 验证向后兼容
- [ ] 更新文档

---

## Kimi SDK 集成防错清单

涉及 Kimi SDK（`Session.create`、`Session.resume`、Agent 配置加载）时，必须逐条检查以下 5 条规则。

### 1. `resume/create` 配置同源（强制）

- `Session.resume` 和 `Session.create` 必须使用同一来源的 `agent_file`
- 禁止 `resume` 用静态 yaml、`create` 用动态 yaml 的混搭
- 否则会出现"恢复与新建行为不一致"，并导致模板变量缺失类报错

### 2. AgentSpec 路径基准（强制）

- `system_prompt_path`、`subagents.path` 的相对路径基准是"当前 agent yaml 所在目录"
- 动态生成 yaml 时，凡非绝对路径都按 `base_config_dir / sub_path` 解析
- 禁止依赖进程 `cwd` 做 `Path(...).resolve()` 推断

### 3. 模板变量来源（强制）

- system prompt 模板变量只来自两类：
  - `builtin_args`（如 `KIMI_NOW` / `KIMI_WORK_DIR`）
  - `agent.system_prompt_args`
- 对业务自定义变量（如 `PYTHON_VERSION`）必须二选一：
  - 在 `system_prompt_args` 中显式提供
  - 或在业务层预渲染 prompt 后再交给 SDK

### 4. 恢复失败回退策略（强制）

- `Session.resume` 抛异常时，禁止立即对同一 `session_id` 执行 `Session.create`
- 原因：同 ID `create` 可能清空 `context.jsonl`，导致历史上下文丢失
- 正确做法：抛错并终止，或提示用户新建会话（新 `session_id`）

### 5. 启动脚本密钥覆盖（强制）

- 禁止在启动脚本中设置 `export KIMI_API_KEY=${KIMI_API_KEY:-""}`
- 这会把空值注入进程环境并覆盖 `.env` 中的有效密钥
- 仅在外部明确传入非空值时才 `export KIMI_API_KEY`

---

## AskUser 工具规则

AskUser 用于 Agent 需要人工确认或补充信息的场景。实现时必须遵守以下规则。

### R1. 只用于真正需要人工确认的节点

适用场景：
- 敏感操作确认
- 关键参数缺失
- 需要用户在多个方案中做选择

不适用场景：
- 可以通过已有上下文自动推断的信息
- 纯展示性通知
- 可由默认策略安全兜底的普通参数

### R2. "暂停并恢复"，不是"打断并重来"

- 工具发起后，Agent 应等待用户响应
- 用户响应后，应继续当前执行链路
- 禁止把 AskUser 设计成"用户回答后重新启动整轮任务"

### R3. 请求必须具备稳定标识

每个 AskUser 请求至少应具备：
- `request_id`
- `type`
- `title`
- `message`
- `tool_call_id`（如存在）

### R4. 类型必须收敛到有限集合

当前支持：
- `confirm`
- `input`
- `select`
- `multi_select`

### R5. 事件流必须走 session 隔离

- AskUser 事件发送器必须按 `session_id` 绑定
- 待处理请求存储必须支持会话隔离
- 多会话并发时，不能把 A 会话的弹窗显示到 B 会话上

### R6. 前后端契约必须闭环

完整链路：
1. Agent 调用 AskUser 工具
2. 后端创建请求并发送 `ask_user_request`
3. 前端显示对话框
4. 用户提交响应
5. 后端 `resolve`
6. 工具 Future 完成
7. Agent 继续执行

### R7. 超时与取消必须可预期

- AskUser 应有明确超时
- 用户取消应返回可识别结果
- 超时、取消、请求不存在等情况，都要给出明确结果，不允许静默失败

### R8. 会话上下文贯穿始终

- AskUser 请求、等待、响应都必须带会话语义
- 不要把 AskUser 当成全局弹窗或全局状态
- 修改 AskUser 时同时检查前端对话框、后端路由和事件发送器

---

## Agent 核心业务逻辑

### 动态提示词渲染

Agent 启动或恢复前，需要感知当前运行环境的能力：

1. **环境检测**：从 `IPythonBox` 获取当前活跃镜像的配置（Python 版本、安装的包）
2. **模板填充**：使用 Jinja2 渲染 prompt 模板
3. **临时配置**：为每个 Session 生成临时的 `.yaml` 和 `.md` 配置文件，存放在 `.temp/` 目录下
4. **动态加载**：调用 `Session.create` 或 `Session.resume` 时注入该临时配置

关键约束：
- 提示词模板不应硬编码在业务逻辑里，后端只负责渲染和注入
- 动态生成失败时必须回退到稳定默认配置，不能因为渲染失败导致整个 Session 创建链路不可用
- 临时配置文件按 `user_id / session_id` 隔离，不同会话不相互污染
- 变量来源必须可解释：当前运行环境信息、明确的系统配置、受控的 Session 上下文

### 会话并发控制

相同 `user_id/session_id` 的请求通过 `asyncio.Lock` 串行化，防止状态竞争。

中断机制：通过 `session.cancel()` 主动中断推理流，确保资源及时回收。

工作目录隔离：通过 `KaosPath` 确保每个 Session 拥有独立的物理目录，防止路径遍历攻击。`workspaces/{user_id}/{session_id}/` 映射至容器内的 `/workspace/`，使用 `contextvars.ContextVar` (`current_workspace`) 在异步链条中安全传递当前会话的工作路径。

### 流式输出协议

将 SDK 内部消息项（`TextPart`, `ThinkPart`, `ToolCall`, `ToolResult`, `SubagentEvent`）转换为统一的 SSE 事件：

| 事件类型 | 说明 |
|---------|------|
| `content` | 模型输出（文本或思考过程） |
| `tool_call` | 工具调用开始 |
| `tool_result` | 工具执行返回值 |
| `subagent_event` | 子代理嵌套逻辑 |
| `file_changes` | 工具执行后 `workspace/` 目录的文件变更差异 |
| `status` | 状态同步（如"检查历史会话..."、"开始分析任务..."） |

### 提示词工程准则

- 系统提示词存放在 `agents/config/`，禁止在后端代码中硬编码
- 变量语法统一使用 `${VAR}` 占位符，由 `agent_service._render_system_prompt_template` 统一渲染
- 动态 Prompt 优先注入影响工具调用成败、代码兼容性、依赖判断的信息

---

## 后端主链路与问题排查

### 主链路概述

```
会话建立/恢复 → 生成 Agent 配置 → 装载工具 → SSE 流式输出 → AskUser 等待 → 持久化
```

核心入口文件：
- `apps/backend/app/services/agent_service.py`
- `apps/backend/app/services/session_manager.py`
- `apps/backend/app/agents/config/data_analysis.yaml`
- `apps/backend/app/agents/tools/ask_user/tool.py`

### 关键规则

**Prompt 与 Agent 配置应从配置文件生成**：不要把系统 Prompt 长文直接硬编码进业务代码。动态 Prompt、Agent YAML、子 Agent 配置都应优先复用现有配置文件和渲染逻辑。

**会话隔离优先**：每个会话都有独立工作目录。Session 相关改动必须考虑 `user_id/session_id` 维度。涉及并发时优先维持串行化与状态一致性。

**MCP 装载点在会话启动阶段**：用户级配置和会话级配置都可能影响最终工具集，但会话开始后工具不会自动热更新。需要大改动时通常需要新会话或显式重建流程。

**流式事件协议是前后端契约**：新增事件类型前同步检查前端事件解析；调整结束条件前同步检查 `useAgentStream` / `useSSEStream`。不要只改后端事件名而不改前端映射。

### 问题排查顺序

**Agent 无法正确执行**：
1. 看 `agent_service.py`
2. 看当前 Agent 配置文件
3. 看 Session 是否正确创建或恢复
4. 再看具体工具实现

**AskUser 异常**：
1. 看 `app/agents/tools/ask_user/`
2. 看 `app/api/routes/ask_user.py`
3. 看前端 `AskUserDialog`
4. 看流式事件是否正确到达

**MCP 工具未生效**：
1. 区分用户级配置还是会话级配置
2. 核对当前会话是否已经启动
3. 核对前端调用的是哪套会话级 API
4. 再检查 Agent 装载时拿到的 SDK 配置

---

## Agent 配置

### YAML 配置结构

```yaml
version: 1
agent:
  name: "research"
  model: "kimi"

  tools:
    # 核心工具
    - "kimi_cli.tools.todo:SetTodoList"
    - "kimi_cli.tools.agent:Agent"

    # 业务工具
    - "app.agents.tools.ipython_tool:IPythonBox"
    - "app.agents.tools.paper_downloader_tool:PaperSearch"
    - "app.agents.tools.paper_downloader_tool:PaperDownload"

    # 交互工具
    - "app.agents.tools.ask_user.tool:AskUserTool"

  system_prompt_path: ./research_prompt.md

  subagents:
    worker:
      path: ./research_sub.yaml
```

### 工具配置原则

**工具顺序有讲究**：工具列表的顺序会影响 Agent 的选择倾向。先列核心/常用工具，然后业务工具，最后通用/备用工具。

**避免工具冗余**：不要同时配置功能重叠的工具（如两个搜索工具）。只配置一个或明确分工。

**配置验证清单**：
- [ ] YAML 语法正确，无缩进错误
- [ ] 所有引用的工具类路径正确
- [ ] 系统提示词文件存在且可读
- [ ] 子代理配置路径正确（如果使用）
- [ ] 模型名称有效
- [ ] 工具列表中没有重复或冲突的工具

### 子代理配置

使用子代理的场景：
1. **任务解耦**：主代理负责任务分解，子代理负责具体执行
2. **资源隔离**：耗时操作放在子代理中，避免阻塞主代理
3. **能力复用**：通用的执行逻辑封装为子代理

分工模式：
```
主代理 (Coordinator)
├── 接收用户请求
├── 任务分解和规划
├── 调用子代理执行具体任务
├── 整合子代理结果
└── 向用户汇报

子代理 (Worker)
├── 接收主代理分配的任务
├── 使用工具执行任务
├── 返回执行结果
└── 不直接与用户交互
```

### 常见配置错误

**工具路径错误**：
```yaml
# 错误 - 类名拼写错误
tools:
  - "app.agents.tools.ipython_tool:IPythonTool"  # 实际类名是 IPythonBox

# 正确
tools:
  - "app.agents.tools.ipython_tool:IPythonBox"
```

**循环依赖**：Agent A 的子代理配置指向 B，B 的又指向 A。

**提示词文件路径错误**：相对路径的基准是 yaml 文件所在目录，不是进程 cwd。

---

## 工具描述编写规范

工具描述是 Agent 决定何时、如何使用工具的唯一依据。模糊或不完整的描述会导致错误选择工具、跳过关键步骤、参数填写错误。

### 必须包含的要素

**核心用途说明**：一句话概括工具功能和适用场景。

```python
# 不好的描述
description = "下载论文的工具"

# 好的描述
description = """
下载指定学术论文的 PDF 文件。

【使用场景】
- 已用 PaperSearch 筛选出重要论文，需要获取完整 PDF 深入阅读
- 复现某篇论文的方法，需要获取完整 PDF
"""
```

**明确的工作流程**：如果工具是工作流中的一环，必须说明前后步骤。

```python
description = """
搜索学术论文并返回元数据（标题、摘要、作者、引用数等）。

【使用流程】
1. 使用本工具搜索，获取论文列表和元数据
2. 阅读标题和摘要，筛选出 2-3 篇最相关的论文
3. 记录这些论文的 paper_id
4. 使用 PaperDownload 工具下载选中的论文
5. 使用 PaddleOCRPDFParser 解析 PDF 内容

【重要】本工具只返回元数据，不下载 PDF！必须先筛选再下载，避免一次性下载所有论文。
"""
```

**与其他工具的协作关系**：明确前置依赖和后续工具。

```python
description = """
解析 PDF 文件提取文本内容，输出 Markdown 格式。

【前置依赖】
- 必须先用 PaperDownload 工具下载 PDF 到本地

【使用流程】
1. 先用 PaperSearch 搜索并筛选论文
2. 用 PaperDownload 下载选中的 PDF
3. 使用本工具解析 PDF 内容为 Markdown
4. 阅读 Markdown 提取关键信息
"""
```

**参数说明**：在参数 Field 的 description 中说明含义、格式、默认值和示例。

```python
class PaperDownloadParams(BaseModel):
    paper_id: str = Field(
        ...,
        description="论文 ID，格式为 'arxiv:2401.12345' 或 's2:xxxxx'。从 PaperSearch 结果中获取。"
    )
    save_dir: Optional[str] = Field(
        default=None,
        description="PDF 保存目录，默认保存到系统缓存目录"
    )
```

### 工具拆分原则

当某个工具被滥用（一次性执行过多操作），应拆分为多个独立工具：

```
不好的设计 - 一个工具做太多事
PaperDownloader: 搜索 + 自动下载前3篇 + 解析

好的设计 - 拆分为独立的工具
PaperSearch: 只搜索，返回元数据
PaperDownload: 根据 ID 下载指定论文
PaddleOCRPDFParser: 解析已下载的 PDF
```

拆分的好处：强制 Agent 先查看元数据再决定下载哪些；减少参数组合错误；每个工具职责单一，出错时更容易定位。

### 验证清单

- [ ] 描述清楚地说明了工具的用途
- [ ] 描述包含了使用场景
- [ ] 如果是工作流中的一环，明确说明了前置和后续步骤
- [ ] 明确说明了这个工具**不会**做什么（防止误用）
- [ ] 参数描述包含了格式要求和示例

---

## 错误处理与容错

### 错误类型分类

**用户输入错误**：明确告知输入哪里不对，提供正确的格式示例，不进入重试逻辑。

```python
if not params.paper_id.startswith(("arxiv:", "s2:")):
    return ToolError(
        output={"provided": params.paper_id},
        message=f"论文 ID 格式错误: {params.paper_id}",
        brief="ID 格式应为 'arxiv:xxx' 或 's2:xxx'"
    )
```

**外部服务错误**：实现重试机制，提供降级方案（如果有），记录详细的错误信息。

```python
async def call_external_api(self, url):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 429:  # Rate limit
                        wait_time = 2 ** attempt
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        raise APIError(f"HTTP {response.status}")
        except asyncio.TimeoutError:
            if attempt < max_retries - 1:
                continue
            raise
    raise APIError(f"Max retries ({max_retries}) exceeded")
```

**资源限制错误**：提前检查资源，优雅降级，向用户说明限制。

```python
file_size = Path(file_path).stat().st_size
max_size = 100 * 1024 * 1024  # 100MB
if file_size > max_size:
    return ToolError(
        output={"file_size": file_size, "max_size": max_size},
        message=f"文件过大: {file_size / 1024 / 1024:.1f}MB",
        brief=f"文件超过 {max_size/1024/1024}MB 限制，请分段处理"
    )
```

**内部逻辑错误**：记录详细日志，返回通用错误信息（不暴露内部细节），触发告警。

### 错误信息分层

```python
ToolError(
    output={              # 详细数据 - 用于调试和日志
        "error_code": "NETWORK_TIMEOUT",
        "attempted_url": url,
        "retry_count": 3,
    },
    message=f"详细错误: {str(e)}",  # 详细描述 - 给 Agent 看
    brief="网络超时，请稍后重试"      # 用户友好的简短描述
)
```

### 重试策略

**指数退避重试**：适用于网络请求、API 调用。

```python
import asyncio
from functools import wraps

def retry_with_backoff(max_retries=3, base_delay=1):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except RetryableError as e:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        await asyncio.sleep(delay)
                    else:
                        raise
            raise MaxRetriesExceeded()
        return wrapper
    return decorator
```

**断路器模式**：外部服务频繁失败时快速失败，避免持续重试耗尽资源。连续失败达到阈值后进入 OPEN 状态直接拒绝请求，经过恢复超时后进入 HALF_OPEN 状态尝试一次调用。

### 错误恢复策略

**优雅降级**：当主功能失败时，提供简化版本。

```python
try:
    result = await full_analysis(data)
    return ToolOk({"result": result, "quality": "high"})
except ResourceExhaustedError:
    logger.warning("Resource exhausted, using simplified analysis")
    result = await simplified_analysis(data)
    return ToolOk({"result": result, "quality": "reduced",
                   "note": "由于资源限制，使用了简化分析"})
```

**部分成功处理**：批量操作时，只要有成功的就返回 ToolOk，同时报告失败项。

```python
results = []
errors = []
for paper_id in paper_ids:
    try:
        result = await self.download_single(paper_id)
        results.append({"id": paper_id, "status": "success", "path": result})
    except Exception as e:
        errors.append({"id": paper_id, "status": "failed", "error": str(e)})

if results:
    return ToolOk({"successful": results, "failed": errors,
                   "summary": f"成功 {len(results)}，失败 {len(errors)}"})
```

---

## Agent 调试与性能

### 常见问题排查

**Agent 不使用工具**：检查工具是否正确注册到 Agent、工具描述是否清晰、系统提示词是否引导使用工具、工具参数定义是否正确。

**工具参数错误**：检查参数 Field 的 description 是否清晰，提供参数示例，验证 Pydantic 模型定义。

**Agent 跳过关键步骤**：检查系统提示词中的工作流程描述，确保流程是编号列表（LLM 更容易遵循），在关键步骤添加明确的指示词（如"必须按以下顺序执行"）。

**工具返回结果被误解**：检查返回数据结构是否清晰，在系统提示词中说明返回格式，提供结果解读的示例。

**循环调用**：检查是否缺少终止条件，在提示词中明确说明何时停止，必要时添加调用计数限制。

### 性能优化

**工具调用时间分析**：

```python
class TimedTool(CallableTool2):
    async def __call__(self, params):
        start = time.time()
        result = await self.execute(params)
        duration = time.time() - start
        if duration > 5:
            logger.warning(f"Tool {self.name} took {duration:.2f}s")
        return result
```

**结果缓存**：对幂等操作缓存结果，避免重复计算或重复请求。

```python
class CachedTool(CallableTool2):
    def __init__(self):
        self.cache = {}

    async def __call__(self, params):
        cache_key = self._make_key(params)
        if cache_key in self.cache:
            return ToolOk(self.cache[cache_key])
        result = await self.execute(params)
        self.cache[cache_key] = result
        return ToolOk(result)
```

**并发控制**：使用 `asyncio.Semaphore` 限制同时进行的操作数量。

```python
class RateLimitedTool(CallableTool2):
    def __init__(self):
        self.semaphore = Semaphore(3)  # 最多 3 个并发

    async def __call__(self, params):
        async with self.semaphore:
            return await self.execute(params)
```

### 结构化日志

```python
import structlog

logger = structlog.get_logger()

async def __call__(self, params):
    logger.info("tool_execution_started", tool=self.name,
                params=params.dict(), tool_call_id=tool_call_id)
    try:
        result = await self.execute(params)
        logger.info("tool_execution_succeeded", tool=self.name,
                    duration_ms=elapsed)
        return ToolOk(result)
    except Exception as e:
        logger.error("tool_execution_failed", tool=self.name,
                    error_type=type(e).__name__, error_message=str(e))
        return ToolError(...)
```

---

*Agent 是系统核心，安全第一——每一个 Tool 都可能接触用户数据，谨慎处理。*