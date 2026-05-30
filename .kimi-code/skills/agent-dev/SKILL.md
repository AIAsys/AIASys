---
name: agent-dev
description: Develop AI Agent tools and capabilities following AIASys best practices. Use when creating new tools for agents, implementing agent sessions, integrating with Kimi SDK, or working with sandbox execution. This skill covers tool development, sandbox security, agent state management, and streaming output. Always use this skill when the user asks you to create an agent tool, implement agent functionality, or work with the Kimi SDK integration.
---

# Agent 开发规范

构建安全、可靠、可扩展的 AI Agent 能力。

---

## 开发范围

**本 Skill 覆盖：**
- Tool 开发（工具函数）
- Agent 会话管理
- Kimi SDK 集成
- 沙盒执行安全
- 流式输出实现

**适用场景：**
- 新增 Agent 工具
- 修改现有 Tool 逻辑
- 实现 Agent 会话恢复
- 集成 Kimi SDK 功能

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
from app.agents.tools.ipython_tool import IPythonBox

async def tool_name(
    param1: str,
    param2: int
) -> Dict[str, Any]:
    # 参数验证
    if not param1:
        raise ValueError("param1 不能为空")
    
    # 在 IPythonBox 中执行
    try:
        result = await IPythonBox.execute(
            code=f"print({param1})",
            timeout=30
        )
        return {"status": "success", "data": result}
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
   - 所有外部代码必须在 `IPythonBox` 中执行
   - 禁止直接执行用户输入的代码
   - 敏感操作需要额外权限检查

4. **超时控制**
   ```python
   # 默认超时
   DEFAULT_TIMEOUT = 30  # 秒
   
   # 长任务超时
   LONG_TIMEOUT = 300    # 5分钟
   
   # 执行时指定
   result = await IPythonBox.execute(
       code=code,
       timeout=DEFAULT_TIMEOUT
   )
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
# IPythonBox 资源限制配置
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

## Kimi SDK 集成

### 防错清单

#### 1. resume/create 配置同源（强制）

```python
# (正确) 正确：resume 和 create 使用同一来源的 agent_file
agent_yaml_path = Path("config/agents/workspace.yaml")

# 创建会话
session = await Session.create(agent_file=agent_yaml_path)

# 恢复会话
session = await Session.resume(
    session_id=session_id,
    agent_file=agent_yaml_path  # 同一文件！
)
```

```python
# (错误) 错误：混搭使用
session = await Session.create(agent_file=static_yaml)      # 静态
session = await Session.resume(agent_file=dynamic_yaml)     # 动态
```

#### 2. AgentSpec 路径基准（强制）

```yaml
# config/agents/workspace.yaml
system_prompt: "prompts/workspace.md"  # 相对于当前 yaml 所在目录
subagents:
  coder:
    path: "subagents/coder.yaml"      # 相对于当前 yaml 所在目录
```

```python
# 动态生成 yaml 时，注意路径解析
base_config_dir = Path("config/agents")
sub_path = Path("subagents/coder.yaml")
full_path = base_config_dir / sub_path  # (正确) 正确
```

#### 3. 模板变量来源（强制）

```yaml
# 可用的模板变量：
# - builtin_args: KIMI_NOW, KIMI_WORK_DIR
# - system_prompt_args: 自定义变量

system_prompt: |
  当前时间: {{ KIMI_NOW }}
  工作目录: {{ KIMI_WORK_DIR }}
  Python版本: {{ PYTHON_VERSION }}  # 必须在 system_prompt_args 中定义
```

```python
# 在业务层预渲染
custom_vars = {"PYTHON_VERSION": "3.11"}
rendered_prompt = render_template(prompt, **custom_vars)
```

#### 4. 恢复失败回退策略（强制）

```python
# (错误) 错误：恢复失败后立即创建同 ID 会话
try:
    session = await Session.resume(session_id)
except Exception:
    session = await Session.create(session_id=session_id)  # 危险！

# (正确) 正确：恢复失败时终止或提示新建
try:
    session = await Session.resume(session_id)
except Exception as e:
    logger.error(f"恢复会话失败: {e}")
    raise SessionError("会话恢复失败，请新建会话")
```

#### 5. 启动脚本密钥覆盖（强制）

```bash
# (错误) 错误：这会覆盖 .env 中的有效密钥
export KIMI_API_KEY=${KIMI_API_KEY:-""}

# (正确) 正确：仅在外部明确传入非空值时才设置
if [ -n "$KIMI_API_KEY" ]; then
    export KIMI_API_KEY
fi
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

**集成 Kimi SDK 时：**
- [ ] resume/create 配置同源
- [ ] 正确处理路径
- [ ] 模板变量正确定义
- [ ] 恢复失败正确处理

---

## 关联参考

- 严格状态机设计规范参见 `references/state-machine.md`

---

*Agent 是系统核心，安全第一——每一个 Tool 都可能接触用户数据，谨慎处理。*
