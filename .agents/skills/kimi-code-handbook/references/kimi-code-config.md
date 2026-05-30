# Kimi Code 配置参考

`~/.kimi-code/config.toml` 的完整配置项说明。支持 TOML 和 JSON 两种格式。

---

## 配置文件位置与加载

| 方式 | 说明 |
|------|------|
| 默认位置 | `~/.kimi-code/config.toml` |
| 指定文件 | `kimi-code --config-file /path/to/config.toml` |
| 内联配置 | `kimi-code --config '{"default_model": "..."}'` |
| 格式 | TOML 或 JSON，按扩展名自动识别；`--config` 先按 JSON 解析，失败后回退 TOML |

如果 `config.toml` 不存在但 `config.json` 存在，CLI 会自动迁移到 TOML 并备份原文件。

---

## 顶层配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `default_model` | string | - | 默认模型名，必须匹配 `models` 中的 key |
| `default_permission_mode` | string | `"manual"` | 默认权限模式：`"manual"` / `"auto"` / `"yolo"`（替代旧版 `default_yolo`） |
| `skip_afk_prompt_injection` | bool | `false` | 隐藏 AFK 模式的系统提醒 |
| `default_plan_mode` | bool | `false` | 新会话默认以 Plan 模式启动 |
| `default_editor` | string | `""` | 默认外部编辑器命令（如 `"vim"`、`"code --wait"`） |
| `theme` | string | `"dark"` | 终端配色主题：`"dark"` / `"light"` |
| `show_thinking_stream` | bool | `true` | 是否流式展示推理过程 |
| `merge_all_available_skills` | bool | `true` | 是否合并所有品牌目录的 Skills |
| `telemetry` | bool | `true` | 是否启用匿名遥测 |
| `extra_skill_dirs` | array | `[]` | 额外 skill 目录（叠加在默认发现之上） |

---

## `thinking` - 思考模式控制

新增配置段，控制 Agent 的思考行为。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `mode` | string | `"auto"` | 思考模式：`"auto"` / `"on"` / `"off"` |
| `effort` | string | `"medium"` | 思考深度：`"low"` / `"medium"` / `"high"` / `"xhigh"` / `"max"` |

```toml
[thinking]
mode = "auto"
effort = "high"
```

---

## `permission` - 权限控制

新增配置段，替代旧版单一的 `default_yolo`。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `default_mode` | string | `"manual"` | 同顶层 `default_permission_mode` |
| `scope` | string | `"session-runtime"` | 权限作用域：`"turn-override"` / `"session-runtime"` / `"project"` / `"user"` |

```toml
[permission]
default_mode = "auto"
scope = "session-runtime"
```

---

## `providers` - API 供应商

每个 provider 用唯一名称作为 key：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 供应商类型，见下表 |
| `base_url` | string | 是 | API 基础 URL |
| `api_key` | string | 是 | API 密钥 |
| `env` | table | 否 | 创建实例前设置的环境变量 |
| `custom_headers` | table | 否 | 自定义 HTTP 头 |

**供应商类型：**

| type | 说明 |
|------|------|
| `kimi` | Kimi 平台（Moonshot AI） |
| `openai_legacy` | OpenAI 兼容接口（chat/completions） |
| `openai_responses` | OpenAI Responses API |
| `anthropic` | Anthropic Messages API |
| `google_genai` | Google Generative AI |
| `gemini` | Google Gemini |
| `vertex_ai` | Google Vertex AI |

**示例：**

```toml
[providers.moonshot]
type = "kimi"
base_url = "https://api.moonshot.cn/v1"
api_key = "sk-xxx"

[providers.openai]
type = "openai_legacy"
base_url = "https://api.openai.com/v1"
api_key = "sk-xxx"
```

**OAuth 认证（Kimi Code 平台）：**

```toml
[providers."managed:kimi-code"]
type = "kimi"
base_url = "https://api.kimi.com/coding/v1"
api_key = ""

[providers."managed:kimi-code".oauth]
storage = "file"
key = "oauth/kimi-code"
```

OAuth 方式不需要手动填 `api_key`，通过 `/login` 自动获取。

---

## `models` - 模型定义

每个 model 用唯一名称作为 key。**注意：如果 key 包含 `.`，必须用引号包裹**（如 `"gpt-4.1"`），否则 TOML 会把 `.` 解析为嵌套路径。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `provider` | string | 是 | 使用的 provider 名称 |
| `model` | string | 是 | API 中使用的模型 ID |
| `max_context_size` | int | 是 | 最大上下文长度（token 数） |
| `capabilities` | array | 否 | 模型能力列表 |
| `display_name` | string | 否 | 界面中显示的友好名称 |

**能力标识：**

| 能力 | 说明 |
|------|------|
| `thinking` | 支持思考模式 |
| `always_thinking` | 始终开启思考 |
| `image_in` | 支持图片输入 |
| `video_in` | 支持视频输入 |

**示例：**

```toml
[models."kimi-for-coding"]
provider = "managed:kimi-code"
model = "kimi-for-coding"
max_context_size = 262144
capabilities = ["thinking", "image_in", "video_in"]
display_name = "Kimi-k2.6"

[models."deepseek-v4-pro"]
provider = "stepfun-api"
model = "deepseek-v4-pro"
max_context_size = 1000000
capabilities = []
```

---

## `loop_control` - Agent 循环控制

控制 Agent 执行循环的步数、重试和上下文压缩行为。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_steps_per_turn` | int | `1000` | 单轮最大步数（别名：`max_steps_per_run`）。复杂任务需要更多步数时可以调大 |
| `max_retries_per_step` | int | `3` | 单步最大重试次数 |
| `max_ralph_iterations` | int | `0` | Ralph Loop 迭代次数；`0` 关闭，`-1` 无限 |
| `reserved_context_size` | int | `50000` | 预留给 LLM 响应的 token 数。当 `context_tokens + reserved >= max_context` 时触发自动压缩 |
| `compaction_trigger_ratio` | float | `0.85` | 上下文使用率阈值（0.5-0.99）。当 `context_tokens >= max_context * ratio` 时触发自动压缩。与 `reserved_context_size` 先触发者生效 |

**调优建议：**

- 复杂多文件修改任务如果频繁触发 `max_steps_reached`，可调大 `max_steps_per_turn`（如 2000-3000）
- 自动压缩过于频繁时，提高 `compaction_trigger_ratio`（如 0.9）
- 自动压缩不够及时导致上下文溢出时，降低 `compaction_trigger_ratio`（如 0.75）

---

## `background` - 后台任务控制

控制后台任务（`Bash(run_in_background=true)` 和 `Agent(run_in_background=true)`）的运行时行为。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_running_tasks` | int | `4` | 最大并发后台任务数 |
| `keep_alive_on_exit` | bool | `false` | CLI 退出时是否保留后台任务运行 |
| `kill_grace_period_ms` | int | `2000` | 退出时 SIGTERM 后等待的宽限期（毫秒） |
| `agent_task_timeout_s` | int | `900` | **后台 Agent 任务最大运行时间（秒）**。超时后标记为失败并通知主 Agent |
| `print_wait_ceiling_s` | int | `3600` | `--print` 模式下等待后台任务的最大秒数 |

**重要：** `agent_task_timeout_s` 默认 15 分钟。如果你经常需要后台 Agent 跑长时间任务（如大项目构建），记得调大这个值。

---

## `services` - 外部服务

### `moonshot_search`

配置网页搜索服务。不配置时 `WebSearch` 工具不可用。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `base_url` | string | 是 | 搜索服务 API URL |
| `api_key` | string | 是 | API 密钥 |

### `moonshot_fetch`

配置网页抓取服务。不配置时 `FetchURL` 用本地 HTTP 请求。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `base_url` | string | 是 | 抓取服务 API URL |
| `api_key` | string | 是 | API 密钥 |

Kimi Code 平台通过 `/login` 自动配置这两个服务。

---

## `mcp` - MCP 客户端

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `client.tool_call_timeout_ms` | int | `60000` | MCP 工具调用超时（毫秒） |

---

## `hooks` - 生命周期 Hook

Hooks 系统在 Agent 生命周期的关键节点执行自定义命令，实现自动化工作流、安全检查、通知提醒。

### 使用场景

- **代码格式化**：文件编辑后自动运行 `prettier` 或 `black`
- **安全检查**：阻止危险的 shell 命令（如 `rm -rf /`）
- **敏感文件保护**：防止修改 `.env` 等配置文件
- **桌面通知**：在需要人工审批时发送通知
- **任务验证**：会话结束前检查未完成任务

### 14 种事件类型

| 事件 | 触发时机 | Matcher 过滤 | 可用上下文 |
|------|----------|-------------|-----------|
| `PreToolUse` | 工具调用前 | 工具名称 | `tool_name`, `tool_input`, `tool_call_id` |
| `PostToolUse` | 工具成功执行后 | 工具名称 | `tool_name`, `tool_input`, `tool_output` |
| `PostToolUseFailure` | 工具执行失败后 | 工具名称 | `tool_name`, `tool_input`, `error` |
| `UserPromptSubmit` | 用户提交输入前 | 无 | `prompt` |
| `Stop` | Agent 轮次结束时 | 无 | `stop_hook_active` |
| `StopFailure` | 轮次因错误结束时 | 错误类型 | `error_type`, `error_message` |
| `SessionStart` | 会话创建/恢复时 | `startup` / `resume` | `source` |
| `SessionEnd` | 会话关闭时 | 原因 | `reason` |
| `SubagentStart` | 子 Agent 启动时 | Agent 名称 | `agent_name`, `prompt` |
| `SubagentStop` | 子 Agent 结束时 | Agent 名称 | `agent_name`, `response` |
| `PreCompact` | 上下文压缩前 | 触发原因 | `trigger`, `token_count` |
| `PostCompact` | 上下文压缩后 | 触发原因 | `trigger`, `estimated_token_count` |
| `Notification` | 通知发送到 sink 时 | sink 名称 | `sink`, `notification_type`, `title`, `body`, `severity` |

### 配置语法

使用 `[[hooks]]` 数组语法定义。Hook 配置字段严格限制为 4 个：`event`、`matcher`、`command`、`timeout`。

```toml
# 文件编辑后自动格式化
[[hooks]]
event = "PostToolUse"
matcher = "Write|Edit"
command = "jq -r '.tool_input.file_path' | xargs prettier --write"

# 阻止修改 .env 文件
[[hooks]]
event = "PreToolUse"
matcher = "Write|Edit"
command = ".kimi-code/hooks/protect-env.sh"
timeout = 10

# 需要审批时发送桌面通知
[[hooks]]
event = "Notification"
matcher = "permission_prompt"
command = "osascript -e 'display notification \"Kimi needs attention\" with title \"Kimi CLI\"'"

# 会话结束前检查任务完成情况
[[hooks]]
event = "Stop"
command = ".kimi-code/hooks/check-complete.sh"
```

| 字段 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `event` | 是 | — | 事件类型，必须是 14 种之一 |
| `command` | 是 | — | 要执行的 shell 命令，通过 stdin 接收 JSON 上下文 |
| `matcher` | 否 | `""` | **JS 正则表达式**过滤，空字符串匹配所有（新版是 JS 正则，不是普通字符串） |
| `timeout` | 否 | `30` | 超时秒数，超时后按 fail-open 处理 |

### 通信协议

**输入（标准输入）**：Hook 命令从 stdin 接收 JSON 格式的上下文信息。

```json
{
  "session_id": "abc123",
  "cwd": "/path/to/project",
  "hook_event_name": "PreToolUse",
  "tool_name": "Bash",
  "tool_input": {"command": "rm -rf /"}
}
```

**输出（退出码）**：

| 退出码 | 行为 | 反馈 |
|--------|------|------|
| `0` | 允许继续 | stdout 内容（非空时）添加到上下文 |
| `2` | 阻止操作 | stderr 内容反馈给 LLM 作为修正建议 |
| 其他 | 允许继续 | stderr 仅记录日志，不展示给 LLM |

**结构化 JSON 输出**（退出码 0 时）：

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "请使用 rg 代替 grep"
  }
}
```

当 `permissionDecision` 为 `"deny"` 时，会阻止操作并将 `permissionDecisionReason` 反馈给 LLM。

### 脚本示例

**保护敏感文件**（`.kimi-code/hooks/protect-env.sh`）：

```bash
#!/bin/bash
read JSON
echo "$JSON" | jq -r '.tool_input.file_path' | grep -qE '\.env$|\.env\.local$'
if [ $? -eq 0 ]; then
  echo "Error: Direct modification of .env files is not allowed. Use .env.example instead." >&2
  exit 2
fi
exit 0
```

**自动格式化代码**（`.kimi-code/hooks/auto-format.sh`）：

```bash
#!/bin/bash
FILE=$(python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))")
if [[ "$FILE" == *.js ]] || [[ "$FILE" == *.ts ]]; then
  prettier --write "$FILE" 2>/dev/null
elif [[ "$FILE" == *.py ]]; then
  black "$FILE" 2>/dev/null
fi
exit 0
```

**检查未完成任务**（`.kimi-code/hooks/check-complete.sh`）：

```bash
#!/bin/bash
if kimi-code task list --active 2>/dev/null | grep -q "running"; then
  echo '{"hookSpecificOutput":{"permissionDecision":"deny","permissionDecisionReason":"还有后台任务在运行，请先检查 /task"}}'
  exit 0
fi
exit 0
```

### 设计原则

- **Fail-Open 策略**：所有 hook 执行失败（超时、崩溃、正则错误）都按"允许"处理，不阻塞 Agent 正常工作。日志可查看失败原因。
- **并行执行**：同一事件的多个 hook 并行执行。相同命令自动去重。
- **Stop Hook 防循环**：Stop hook 最多重新触发一次，防止无限循环。重新触发时 `stop_hook_active` 字段为 `true`，hook 可据此提前退出。
- **上下文变量**：Session ID 通过 `ContextVar` 传递，避免每次工具调用显式传递参数。

### 查看已配置 Hooks

使用 `/hooks` 命令：

```
/hooks
```

输出示例：

```
Configured Hooks:
  PostToolUse: 1 hook(s)
  PreToolUse: 1 hook(s)
  Notification: 1 hook(s)
  Stop: 1 hook(s)
```

---

## 自定义 Agent 文件

通过 `--agent-file` 参数加载 YAML 格式的自定义 agent：

```sh
kimi-code --agent-file /path/to/my-agent.yaml
```

### 基本结构

```yaml
version: 1
agent:
  name: my-agent
  system_prompt_path: ./system.md
  tools:
    - "kimi_code.tools.shell:Bash"
    - "kimi_code.tools.file:Read"
    - "kimi_code.tools.file:Write"
```

### 继承默认 agent

```yaml
version: 1
agent:
  extend: default          # 继承 default agent 的全部配置
  system_prompt_path: ./my-prompt.md  # 覆盖系统提示词
  exclude_tools:           # 排除不需要的工具
    - "kimi_code.tools.web:WebSearch"
    - "kimi_code.tools.web:FetchURL"
```

### 定义自定义子 Agent

```yaml
version: 1
agent:
  extend: default
  subagents:
    my-coder:
      path: ./my-coder-sub.yaml
      description: "我的自定义编码子 Agent"
    my-reviewer:
      path: ./my-reviewer-sub.yaml
      description: "我的代码审查子 Agent"
```

子 agent 文件也是标准 agent 格式，通常继承主 agent：

```yaml
# my-coder-sub.yaml
version: 1
agent:
  extend: ./agent.yaml    # 继承主 agent
  system_prompt_args:
    ROLE_ADDITIONAL: |
      你现在作为子 Agent 运行，专注于编码任务。
```

### 系统提示词模板变量

系统提示词 Markdown 文件中可以使用这些变量：

| 变量 | 说明 |
|------|------|
| `${KIMI_NOW}` | 当前时间（ISO 格式） |
| `${KIMI_WORK_DIR}` | 工作目录路径 |
| `${KIMI_WORK_DIR_LS}` | 工作目录文件列表 |
| `${KIMI_AGENTS_MD}` | 项目 AGENTS.md 合并内容 |
| `${KIMI_SKILLS}` | 已加载的 Skills 列表 |
| `${KIMI_ADDITIONAL_DIRS_INFO}` | `--add-dir` 添加的额外目录 |

通过 `system_prompt_args` 自定义变量：

```yaml
agent:
  system_prompt_args:
    MY_VAR: "自定义值"
```

提示词中用 `${MY_VAR}` 引用。

### 配置字段总览

| 字段 | 说明 | 必填 |
|------|------|------|
| `extend` | 继承的 agent，`default` 或相对路径 | 否 |
| `name` | Agent 名称 | 继承时可省略 |
| `system_prompt_path` | 系统提示词文件路径 | 继承时可省略 |
| `system_prompt_args` | 自定义模板变量 | 否 |
| `tools` | 工具列表，格式 `module:ClassName` | 继承时可省略 |
| `exclude_tools` | 排除的工具 | 否 |
| `subagents` | 子 Agent 定义 | 否 |

### 内置子 Agent 类型

| 类型 | 用途 | 可用工具 |
|------|------|----------|
| `coder` | 通用软件工程 | Bash、Read、Glob、Grep、Write、Edit、WebSearch、FetchURL |
| `explore` | 快速只读探索 | Bash、Read、Glob、Grep、WebSearch、FetchURL（无写入工具） |
| `plan` | 实现规划 | Read、Glob、Grep、WebSearch、FetchURL（无 Bash、无写入） |

所有子 Agent 均不可嵌套使用 `Agent` 工具。

---

## 常见调优场景

### 场景 1：复杂任务频繁 max_steps_reached

```toml
[loop_control]
max_steps_per_turn = 3000   # 从默认 1000 调大
```

### 场景 2：后台 Agent 任务 15 分钟不够

```toml
[background]
agent_task_timeout_s = 3600   # 从默认 900 调到 1 小时
```

### 场景 3：上下文自动压缩过于频繁

```toml
[loop_control]
compaction_trigger_ratio = 0.90   # 从 0.85 提高
reserved_context_size = 80000     # 从 50000 提高
```

### 场景 4：添加自定义编码子 Agent

```yaml
# ~/.kimi-code/agents/my-coder.yaml
version: 1
agent:
  extend: default
  subagents:
    coder:
      # 保留内置 coder，也可以覆盖它
```

### 场景 5：禁用遥测

```toml
telemetry = false
```

### 场景 6：切换到自动审批模式

```toml
[permission]
default_mode = "auto"
```

启动时仍可通过 `kimi-code --yolo` 临时开启全自动模式。

---

## 新旧配置对照

| 旧版 Kimi CLI | 新版 Kimi Code | 说明 |
|--------------|---------------|------|
| `~/.kimi/config.toml` | `~/.kimi-code/config.toml` | 配置路径变更 |
| `~/.kimi/skills/` | `~/.kimi-code/skills/` | Skills 路径变更 |
| `~/.kimi/mcp.json` | `~/.kimi-code/mcp.json` | MCP 配置路径变更 |
| `~/.kimi/plugins/` | `$KIMI_CODE_HOME/plugins/` | Plugin 路径变更 |
| `default_yolo` | `permission.default_mode` | 权限模式重构 |
| 无 `thinking` 段 | `thinking.mode` + `thinking.effort` | 新增思考控制 |
| 无 `permission` 段 | `permission.default_mode` + `permission.scope` | 新增权限作用域 |
| 无 `background` 段 | `background.*` | 后台任务控制独立成段 |
| Hook matcher 为普通字符串 | Hook matcher 为 JS 正则 | matcher 语义变化 |
| 13 种 Hook 事件 | 14 种 Hook 事件 | 新增/合并事件 |
| `Shell` / `ReadFile` / `WriteFile` / `StrReplaceFile` | `Bash` / `Read` / `Write` / `Edit` | 工具重命名 |
| `kimi_cli.*` | `kimi_code.*` | Agent 文件中的模块路径变更 |
| `/flow:<name>` | `/skill:<name>` | Flow Skills 统一入口 |
| `kimi plugin install` | `/plugins install` | Plugin 管理方式变更 |