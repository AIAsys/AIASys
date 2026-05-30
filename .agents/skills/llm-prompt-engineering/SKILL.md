---
name: llm-prompt-engineering
description: |
  AIASys 的 LLM 交互层开发指南。覆盖系统提示词管理、多协议 LLM Client、Token 预算、上下文压缩、
  模型配置等核心模块。用于修改 prompt 模板、新增 LLM provider、调整 token 预算策略、或修改上下文压缩逻辑时。
---

# LLM 与 Prompt 工程

AIASys 中 LLM 交互层的完整开发指南。Prompt 以 Markdown 模板存储，Jinja2 渲染；LLM Client 通过协议工厂统一多 provider 接口；Token 预算和上下文压缩是 session 级 mixin，嵌入 ReAct 循环。

---

## 系统提示词管理

### 模板存储

Prompt 模板以 Markdown 文件存储在 `apps/backend/app/agents/local_sandbox_agent_config/`：

| 文件 | 用途 |
|------|------|
| `general_host_prompt.md` | 主控 Agent 的 system prompt |
| `subagent_coder_prompt.md` | Coder 子 Agent prompt |
| `subagent_data_analyst_prompt.md` | 数据分析子 Agent prompt |
| `subagent_researcher_prompt.md` | 研究子 Agent prompt |
| `subagent_reviewer_prompt.md` | 审查子 Agent prompt |

### 模板渲染

`services/agent/config.py` 的 `_render_system_prompt_template()` 负责渲染：

- 使用 Jinja2，变量语法 `${VAR}`（非标准 `{{ VAR }}`）
- `StrictUndefined` 模式：未定义变量直接报错，不会静默吞掉
- 注入的变量来自 `env_info` 字典（workspace 路径、运行时环境信息等）
- 渲染失败时返回原始模板内容，避免完全失败

### System Preset 机制

`services/agent/system_presets.py` 定义 `SystemAgentBaseline` frozen dataclass：

- 每个角色硬编码 model、prompt 路径、工具策略、MCP/skill 继承策略
- `_ROLE_TYPE_TOOL_MAP` 按角色类型动态注入工具集
- `when_to_use` 字段定义角色触发条件
- 子 Agent baseline 集中管理，不在各处分散定义

### 动态配置生成

`config.py` 的 `_build_manifest_from_system_baseline()` 流程：

1. 从 baseline 读取 prompt 模板路径
2. Jinja2 渲染模板 → 得到 system prompt 字符串
3. 检查用户自定义配置（session 级配置覆盖）
4. 应用用户自定义 prompt 合并（如果存在）
5. 写入临时文件 `runtime-agent-config/prompt_{user}_{session}_{timestamp}.md`
6. 生成最终 agent manifest（含 tools、subagents、MCP 配置）

### 修改 Prompt 的原则

- **模板和代码分离**：Prompt 内容改 Markdown 文件，渲染逻辑改 `_render_system_prompt_template()`
- **新增角色**：在 `system_presets.py` 添加 `SystemAgentBaseline` 实例 + 对应 prompt 模板
- **修改工具集**：改 `_ROLE_TYPE_TOOL_MAP`，不要在各处硬编码工具列表
- **用户自定义 prompt**：通过 session 配置覆盖，走 `config.py` 的合并流程

---

## 多协议 LLM Client

### 架构

`services/agent/runtime_backends/aiasys/llm_clients/`：

```
base.py          — BaseLlmClient 抽象 + LlmChunk/LlmDelta/LlmRequestOptions
openai_client.py — OpenAI Chat Completions 协议
anthropic_client.py — Anthropic Messages 协议
codex_client.py  — OpenAI Responses / Codex 协议
__init__.py      — create_llm_client() 工厂函数 + MultiProtocolClient
```

### 工厂函数

`create_llm_client(provider, model)` 根据 `provider.protocol` 选择实现：

| protocol 值 | 对应 Client |
|-------------|-------------|
| `openai_chat_completions` | `OpenAIChatClient` |
| `openai_responses` | `CodexChatClient` |
| `anthropic_messages` | `AnthropicChatClient` |
| `codex` / `openai-codex` | `CodexChatClient` |

### 新增 Provider 的步骤

1. 在 `llm_clients/` 下创建 `xxx_client.py`，继承 `BaseLlmClient`
2. 实现 `chat_stream()` 方法（async generator，yield `LlmChunk`）
3. 在 `create_llm_client()` 添加新 protocol 分支
4. 在 `LlmProviderConfig` 模型（`models/llm_config.py`）中确认 protocol 字段支持新值

### MultiProtocolClient

`MultiProtocolClient` 是对 `BaseLlmClient` 的薄包装，对外暴露统一的 `chat_stream()` 接口。上层代码通过它调用 LLM，不需要知道底层协议。

---

## Token 预算管理

### Session Budget

`services/agent/runtime_backends/aiasys/session_budget.py` 的 `SessionBudgetMixin`：

- Budget 状态存储在 session 的 `metadata.json` 中（`SessionMetadata.budget`）
- 字段：`token_budget`（总预算）、`tokens_used`（已用）、`context_tokens`（上下文占用）、`time_budget`（时间预算）
- 每次 LLM 调用后更新 `tokens_used`
- 耗尽时设置 `budget_limited` 状态，阻止后续调用

### 上下文 Token 独立记录

`_save_context_tokens_to_metadata()` 将当前上下文占用 token 数独立写入 `metadata.json`：

- 与预算是否开启无关
- LLM 返回精确 `prompt_tokens` 后调用
- 确保 session 关闭后 API 查询不回退到启发式估算

### 修改预算策略的注意点

- Budget 数据在 `metadata.json`，不要另建存储
- 前端展示统一走 `TokenUsageBar` 组件
- 预算设置入口在 session 的 `metadata.json` 的 `budget` 字段，不在 Goal、AutoTask 或模型配置里另建

---

## 上下文压缩

### Compaction 触发条件

`services/agent/runtime_backends/aiasys/session_compaction.py` 的 `SessionCompactionMixin`：

- `compaction_trigger_ratio`（默认 0.85）：当前 token 数超过 `max_context_size * ratio` 时触发
- `reserved_context_size`（默认 50000）：当前 token + 预留空间超过 max 时触发
- 两种条件满足任一即触发压缩

### 压缩流程

1. 分离 system messages 和 chat messages
2. 用 `estimate_text_tokens()` 估算当前 token 数
3. 检查触发条件
4. 创建 `SimpleCompaction` 实例，配置 `max_preserved_messages`、`max_summary_tokens`、`tool_snip_max_chars`
5. 可用专用 compaction 模型（`task_models.compaction`），独立于主对话模型
6. 压缩后更新 `self.messages`

### 修改压缩逻辑的注意点

- `compaction_trigger_ratio` 和 `reserved_context_size` 在 `loop_control` 配置中
- 压缩使用独立的 LLM client，可选独立模型，不要用主对话模型做压缩（避免 token 消耗叠加）
- 压缩后的 messages 必须保留 system messages 完整

---

## 模型配置

### LlmConfig 模型

`services/agent/models/llm_config.py` 定义：

- `LlmProviderConfig`：protocol、base_url、api_key、credential pool
- `LlmModelConfig`：max_context_size、temperature、max_tokens、thinking_effort
- `AiasysLlmConfig`：default_model、fallback_order、task_models（compaction 等专用模型）

### 配置 API

`api/routes/llm_config.py` 提供 provider 和 model 的 CRUD，支持 fetch remote models、test provider connectivity。

---

## 关键文件索引

| 文件 | 职责 |
|------|------|
| `agents/local_sandbox_agent_config/*.md` | Prompt 模板 |
| `services/agent/system_presets.py` | System preset 定义 |
| `services/agent/config.py` | 动态配置生成 + Jinja2 渲染 |
| `services/agent/models/llm_config.py` | LLM 配置模型 |
| `services/agent/runtime_backends/aiasys/llm_clients/` | 多协议 LLM Client |
| `services/agent/runtime_backends/aiasys/session_budget.py` | Token 预算管理 |
| `services/agent/runtime_backends/aiasys/session_compaction.py` | 上下文压缩 |
| `api/routes/llm_config.py` | LLM 配置 API |

---

## 动态 Prompt 注入优先级

来自早期后端规范的补充：Prompt 渲染注入变量时，优先注入对执行正确性影响最大的信息。

注入优先级从高到低：

1. **影响工具调用成败的信息**：Python 版本、可用包列表、系统路径等直接影响 Agent 能否正确调用工具
2. **影响代码兼容性的信息**：运行时环境类型（Docker/本地）、操作系统、架构差异
3. **影响依赖判断的信息**：预装包集合、虚拟环境路径、pip/uv 版本

非执行关键信息（如欢迎语、通用建议）放最后，避免挤占有限的 context 窗口。

---

*Prompt 是 Agent 与 LLM 的契约——精确、完整、可验证。*