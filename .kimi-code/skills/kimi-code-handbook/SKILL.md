---
name: kimi-code-handbook
description: |
  Kimi Code CLI 完整使用手册。覆盖全部 21 个内置工具的参数、默认值、边界限制和常见错误，
  以及 Hooks 系统（14 种生命周期事件 + 退出码协议）、Plugin 系统（Skills + MCP server）、
  Agent Skills（四档扫描优先级 + 斜杠命令动态注册）、Flow Skills、Sub-agent（3 种内置类型）、
  config.toml 配置参考、权限规则、环境变量和斜杠命令完整列表。
  当需要确认工具参数行为、排查调用失败原因、设计长任务执行策略、配置 Hooks 自动化、
  开发 Plugin、设计声明式工作流、配置多模型提供商、理解 Skills 加载机制时使用。
  配置文件详细说明见 references/kimi-code-config.md，Skills 详细说明见 references/kimi-code-skills.md。
---

# Kimi Code CLI 使用手册

> ⚠️ **重要：我们已全量迁移到 Kimi Code（TS 重写版，v0.5+）。旧版 Python Kimi CLI 不再使用。**
>
> 两个 Skill 的分工：
> - **`kimi-code-handbook`（本文件）**：当前在用的 Kimi Code（TS 版），覆盖全部 21 个工具、Skills 系统、Plugin、Hooks、MCP、斜杠命令等。**这是主力参考。**
> - **`kimi-cli-handbook`**：仅保留给旧版 Python Kimi CLI 的历史参考，**不再维护，不应作为当前操作的依据**。
>
> 两版关键区别：配置文件路径 `~/.kimi/` → `~/.kimi-code/`、项目 Skills 目录 `.kimi/skills/` → `.agents/skills/` + `.kimi-code/skills/`、Plugin manifest `plugin.json` → `kimi.plugin.json`、工具命名 Shell→Bash 等大量变更。不要用旧版文档指导当前操作。

完整覆盖 Kimi Code CLI（TS 重写版，v0.5+）的所有核心能力。所有结论来自实际调用验证 + 新版官方文档（`moonshotai.github.io/kimi-code/zh/`）。

配置文件（`~/.kimi-code/config.toml`）的完整说明见 `references/kimi-code-config.md`。Skills 系统详情见 `references/kimi-code-skills.md`。

当前可用工具共 21 个：Agent、AskUserQuestion、Bash、CronCreate、CronDelete、CronList、Edit、EnterPlanMode、ExitPlanMode、FetchURL、Glob、Grep、Read、ReadMediaFile、Skill、TaskList、TaskOutput、TaskStop、TodoList、WebSearch、Write。

> **命名变更提醒**：Kimi CLI → Kimi Code 中多个工具已重命名：`Shell` → `Bash`、`ReadFile` → `Read`、`WriteFile` → `Write`、`StrReplaceFile` → `Edit`、`SetTodoList` → `TodoList`、`SearchWeb` → `WebSearch`。新增 `CronCreate`、`CronDelete`、`CronList`、`Skill` 四个工具。移除 `Think`、`SendDMail`。

---

## 数据路径

| 位置 | 用途 |
|------|------|
| `~/.kimi-code/config.toml` | 全局配置文件 |
| `~/.kimi-code/mcp.json` | 用户级 MCP server 配置 |
| `.kimi-code/mcp.json` | 项目级 MCP server 配置（覆盖用户级同名条目） |
| `~/.kimi-code/skills/` | 用户级 Skills（所有项目生效） |
| `~/.agents/skills/` | 用户级 Skills（备用路径） |
| `.kimi-code/skills/` | 项目级 Skills（仅当前仓库） |
| `.agents/skills/` | 项目级 Skills（备用路径，**当前实际使用**） |
| `~/.kimi-code/plugins/` | 用户级 Plugin 安装目录 |
| `~/.kimi-code/sessions/` | 会话持久化目录 |
| `~/.kimi-code/logs/kimi-code.log` | 全局诊断日志 |

可通过 `KIMI_CODE_HOME` 环境变量覆盖 `~/.kimi-code` 根路径。

> **关键结论**：Kimi Code 新版（TS 重写）读的是 `~/.kimi-code/` 和 `.agents/skills/`。旧版 Python CLI 读的是 `~/.kimi/` 和 `.kimi/skills/`。项目内 `.kimi/` 目录仅在仍使用旧版 Python CLI 时需要。

---

## 运行模式与集成

### CLI 交互模式

```bash
kimi                 # 启动交互式 TUI
kimi -c "prompt"     # 单次执行
kimi -p "prompt"     # 同上（--prompt）
kimi --yolo          # 全自动审批
kimi --plan          # Plan 模式启动
kimi -m <model>      # 指定模型
kimi -w /path        # 指定工作目录
kimi -C              # 继续上一个会话
kimi -S <id>         # 恢复指定会话
kimi --thinking      # 启用 thinking 模式
```

### Ctrl-X 命令模式

按 `Ctrl-X` 切换到 shell 命令模式，无需退出 `kimi` 即可执行单条 shell 命令。内置命令如 `cd` 不支持此模式。

### Web UI 模式

```bash
kimi web [--port 8080] [--host 0.0.0.0] [--no-open]
```

本地浏览器访问 `http://127.0.0.1:5494`，支持会话管理、文件引用、代码高亮。

### VS Code 集成

安装官方扩展 `moonshot-ai.kimi-code`（扩展市场搜索 "Kimi Code"），侧边栏聊天 + 代码块操作。

### ACP 集成（Zed / JetBrains）

```json
{
  "agent_servers": {
    "Kimi Code CLI": {
      "type": "custom",
      "command": "kimi",
      "args": ["acp"],
      "env": {}
    }
  }
}
```

### Zsh 集成

```bash
git clone https://github.com/MoonshotAI/zsh-kimi-cli.git \
  ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/kimi-cli
```

按 `Ctrl-X` 直接进入 agent 模式。

### Kimi Agent SDK

多语言库（Go / Node.js / Python），程序化接口暴露 CLI agent 运行时，支持流式响应、审批处理和会话编排。

---

## 模型能力（Kimi K2.6）

当前旗舰模型为 Kimi K2.6（万亿参数），关键指标：

| 能力 | 规格 |
|------|------|
| 上下文窗口 | 262,144 tokens |
| Agent 集群 | 300 个子 Agent 并行，4,000+ 协作步骤 |
| 长程编码 | 13 小时不间断编码 |
| SWE-Bench Pro | 58.6 |
| 多模态 | 图片输入、视频输入 |
| 思考模式 | auto/on/off + 五级深度（low/medium/high/xhigh/max） |

---

## Skills 系统

### 存放位置与优先级

Kimi Code CLI 按四档扫描 Skills，越具体的作用域优先级越高：

**Project > User > Extra > Built-in**

| 作用域 | 路径 | 说明 |
|--------|------|------|
| Project（项目级） | `.kimi-code/skills/`、`.agents/skills/` | 仅当前仓库生效 |
| User（用户级） | `~/.kimi-code/skills/`、`~/.agents/skills/` | 所有项目生效 |
| Extra（额外） | `config.toml` 中 `extra_skill_dirs` | 手动指定 |
| Built-in（内置） | 随 CLI 分发 | 如 `kimi-cli-help`、`skill-creator` |

同名 Skill 以更高优先级为准。

### SKILL.md 格式

```markdown
---
name: code-style
description: 项目代码风格规范
type: prompt
whenToUse: 当用户编写、修改或审查代码时
disableModelInvocation: false
arguments:
  - target
---

正文内容，支持占位符：
- $ARGUMENTS：完整原始参数字符串
- $0, $1：位置参数
- $<name>：命名参数
- ${KIMI_SKILL_DIR}：Skill 文件所在目录
```

### 调用方式

- 斜杠命令：`/skill:code-style 附加文本`
- 简写：`/code-style`（前提是不与内置命令冲突）
- 模型自动调用：根据 `description` 和 `whenToUse` 自动触发（除非 `disableModelInvocation: true` 或 `type: flow`）
- `Skill` 工具：Agent 可主动调用 `type: inline` 的 Skill
- 嵌套深度上限：3 层

### Flow Skills

`type: flow` 的 Skill 支持 Mermaid/D2 流程图定义多步骤工作流。仅通过 `/skill:<name>` 手动调用，不支持模型自动调用。

---

## 斜杠命令完整列表

### 账号与配置

| 命令 | 说明 |
|------|------|
| `/login` | 登录 Kimi 账号或 Moonshot 开放平台 |
| `/logout` | 登出并清除凭据 |
| `/connect` | 从模型目录配置供应商与模型 |
| `/model` | 切换当前模型 |
| `/settings`（`/config`） | 打开设置面板 |
| `/permission` | 选择权限模式 |
| `/editor` | 配置外部编辑器（`Ctrl-G` 调用） |
| `/theme` | 切换终端配色主题 |

### 会话管理

| 命令 | 说明 |
|------|------|
| `/new`（`/clear`） | 新建会话，丢弃当前上下文 |
| `/sessions`（`/resume`） | 浏览历史会话并恢复 |
| `/tasks` | 浏览后台任务列表 |
| `/fork` | 基于当前会话 fork 新会话 |
| `/title`（`/rename`） | 查看或设置会话标题 |
| `/compact` | 压缩上下文释放 token |
| `/init` | 分析代码库生成 `AGENTS.md` |
| `/export-md` | 导出会话为 Markdown |
| `/export-debug-zip` | 导出调试 ZIP |

### 模式控制

| 命令 | 说明 |
|------|------|
| `/yolo [on\|off]` | 切换 YOLO 模式（跳过工具审批） |
| `/auto [on\|off]` | 切换 auto 权限模式 |
| `/plan [on\|off]` | 切换 Plan 模式 |
| `/plan clear` | 清除当前 plan 方案 |

### 信息与状态

| 命令 | 说明 |
|------|------|
| `/help` | 显示快捷键和命令列表 |
| `/usage` | 显示 token 用量和配额 |
| `/status` | 显示会话运行时状态 |
| `/mcp` | 列出 MCP server 连接状态 |
| `/plugins` | 打开 Plugin 管理器 |
| `/version` | 显示版本号 |
| `/feedback` | 提交反馈 |

### 退出

| 命令 | 说明 |
|------|------|
| `/exit`（`/quit`、`/q`） | 退出 Kimi Code CLI |

### Skill 动态命令

```
/skill:<name> [附加文本]
```

简写形式 `/<name>` 也支持（前提是不与内置命令冲突）。

> **注意**：Flow 类型 Skill 统一走 `/skill:<name>`，没有独立的 `/flow:` 命名空间。

---

## 权限系统

### 权限模式

| 模式 | 行为 |
|------|------|
| `manual` | 默认。写入和执行类工具需审批 |
| `auto` | 工具审批自动处理，Agent 不向用户提问 |
| `yolo` | 跳过所有普通工具审批（Plan 模式退出审批除外） |

配置：`config.toml` 中 `default_permission_mode = "manual"`。启动时 `--yolo` 可覆盖。

### 权限规则

在 `config.toml` 的 `[[permission.rules]]` 中预置：

```toml
[[permission.rules]]
decision = "allow"       # allow / deny / ask
pattern = "Bash(git *)"  # ToolName 或 ToolName(arg-pattern)
scope = "user"           # turn-override / session-runtime / project / user
reason = "Git 命令安全"
```

- `pattern` 支持 `*` 和 `**` 通配
- MCP 工具命名：`mcp__<server>__<tool>`，如 `mcp__github__*`
- 默认审批分类：只读类自动放行（Read、Grep、Glob、WebSearch、FetchURL），写入类需审批（Write、Edit、Bash、TaskStop）

---

## Sub-agent（子 Agent）

### 内置类型

| 类型 | 能力 | 适用场景 |
|------|------|----------|
| `coder`（默认） | 读写文件、执行命令、搜索代码 | 通用软件工程任务 |
| `explore` | 只读：Read、Glob、Grep、WebSearch、FetchURL | 代码库探索、搜索梳理 |
| `plan` | 只读（连 Shell 也不提供） | 实现规划与架构设计 |

### 关键特性

- **上下文隔离**：子 Agent 看不到主 Agent 对话历史，只看到显式传入的任务描述
- **结果汇总**：子 Agent 中间过程不回流传入主 Agent，仅最终结果返回
- **并行执行**：多个子 Agent 可并行运行，互不干扰
- **权限继承**：主 Agent 的权限规则自动覆盖子 Agent
- **后台运行**：`run_in_background=true`，完成时自动通知主 Agent
- **恢复实例**：通过 `resume` 参数恢复已有子 Agent 继续工作

---

## Ralph Loop

Ralph 循环将同一提示词反复喂给 Agent，让它围绕任务持续迭代，直到输出 `<choice>STOP</choice>` 或达到迭代上限。

```bash
kimi --max-ralph-iterations 10
```

配置：`config.toml` 中 `loop_control.max_ralph_iterations`。设为 `0` 关闭，`-1` 无限循环。

---

## 内置工具速查

### 文件类

| 工具 | 默认审批 | 关键参数 |
|------|----------|----------|
| `Read` | 自动 | `path`、`line_offset`（支持负数）、`n_lines`（上限 1000 行/100KB） |
| `Write` | 需审批 | `path`、`content`、`mode`（overwrite/append） |
| `Edit` | 需审批 | `path`、`old_string`（精确匹配）、`new_string`、`replace_all` |
| `Grep` | 自动 | `pattern`（ripgrep 正则）、`output_mode`、`-A`/`-B`/`-C`、`head_limit` |
| `Glob` | 自动 | `pattern`（需字面锚点，纯通配符被拒）、`path` |
| `ReadMediaFile` | 自动 | `path`（图片/视频，上限 100MB，需模型支持 `image_in`/`video_in`） |

### Shell

| 工具 | 默认审批 | 关键参数 |
|------|----------|----------|
| `Bash` | 需审批 | `command`、`cwd`、`timeout`（前台默认 60s/最长 300s；后台默认 600s/最长 86400s）、`run_in_background`、`description`（后台必填）、`disable_timeout` |

Windows 下默认使用 Git Bash（`bash.exe`）。可通过 `KIMI_SHELL_PATH` 覆盖。

### 网络类

| 工具 | 默认审批 | 关键参数 |
|------|----------|----------|
| `WebSearch` | 自动 | `query`、`limit`（1-20，默认 5）、`include_content` |
| `FetchURL` | 自动 | `url`（仅 http/https，上限 10MB） |

`WebSearch` 需要宿主注入搜索实现（如 Kimi 的 `moonshot_search` 服务或 MCP server）。

### Plan 模式

| 工具 | 默认审批 | 说明 |
|------|----------|------|
| `EnterPlanMode` | 自动 | 进入后 Write/Edit 仅允许写入计划文件，TaskStop 被拦截 |
| `ExitPlanMode` | 自动（需确认） | 读取计划文件提交审批，支持 1-3 个备选方案 |

### 状态管理

| 工具 | 默认审批 | 说明 |
|------|----------|------|
| `TodoList` | 自动 | `todos` 数组每项含 `title` + `status`（pending/in_progress/done） |

### 协作类

| 工具 | 默认审批 | 关键参数 |
|------|----------|----------|
| `Agent` | 自动 | `prompt`、`description`（3-5 词）、`subagent_type`、`resume`、`run_in_background`、`timeout`（30-3600s） |
| `AskUserQuestion` | 自动 | `questions`（1-4 题，每题 2-4 选项） |
| `Skill` | 自动 | `skill`（名称）、`args`（附加文本） |

### 后台任务

| 工具 | 默认审批 | 关键参数 |
|------|----------|----------|
| `TaskList` | 自动 | `active_only`（默认 true）、`limit`（1-100） |
| `TaskOutput` | 自动 | `task_id`、`block`、`timeout`（默认 30s） |
| `TaskStop` | 需审批 | `task_id`、`reason` |

### 定时任务

| 工具 | 默认审批 | 关键参数 |
|------|----------|----------|
| `CronCreate` | 需审批 | `cron`（5 段标准 cron）、`prompt`（≤8KB）、`recurring`（默认 true） |
| `CronList` | 自动 | 无参数 |
| `CronDelete` | 需审批 | `id`（8 位 hex） |

定时任务绑定到会话（`kimi resume` 后仍有效），不会带入全新会话。单会话上限 50 个。周期任务 7 天后自动过期。通过 `KIMI_DISABLE_CRON=1` 可整体禁用。

---

## Hooks 系统

### 配置

在 `config.toml` 中使用 `[[hooks]]` 数组表：

```toml
[[hooks]]
event = "PreToolUse"
matcher = "Bash"
command = "node ~/.kimi-code/hooks/check-bash.mjs"
timeout = 5
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `event` | 是 | 事件名（必须是下文事件表中的值） |
| `matcher` | 否 | JS 正则，匹配事件目标（空 = 匹配全部） |
| `command` | 是 | Shell 命令（`sh -c` 执行） |
| `timeout` | 否 | 1-600 秒，默认 30 |

### 返回值协议

| 退出码 | 行为 |
|--------|------|
| `0` | 放行；stdout JSON 中的 `message` 或 `hookSpecificOutput.message` 可读取 |
| `2` | 阻断；stderr 作为阻断原因 |
| 其他非零 | 默认放行（fail-open） |
| 超时/异常 | 默认放行（fail-open） |

JSON stdout 阻断：
```json
{
  "hookSpecificOutput": {
    "permissionDecision": "deny",
    "permissionDecisionReason": "Use rg instead"
  }
}
```

### 14 种生命周期事件

| 事件 | Matcher | 可阻断 | 说明 |
|------|---------|--------|------|
| `UserPromptSubmit` | 用户提交文本 | 是 | 仅真实 User 消息触发。阻断后当前轮次不再调用模型 |
| `PreToolUse` | 工具名 | 是 | 权限检查前触发。阻断后工具不执行 |
| `PostToolUse` | 工具名 | 否 | 工具成功后 fire-and-forget；`tool_output` 截断至 2000 字符 |
| `PostToolUseFailure` | 工具名 | 否 | 工具失败或被阻断后 fire-and-forget |
| `Stop` | 空字符串 | 是 | 模型准备停止时。阻断原因作为 User 消息继续对话（最多一次） |
| `StopFailure` | 错误类型 | 否 | 轮次因非取消错误失败后 fire-and-forget |
| `SessionStart` | `startup` 或 `resume` | 否 | 新会话主 Agent 创建后/恢复完成后 |
| `SessionEnd` | `exit` | 否 | 会话关闭并 flush 元数据后 |
| `SubagentStart` | 子 Agent 名称 | 否 | 子 Agent 配置完成后；`prompt` 截断至 500 字符 |
| `SubagentStop` | 子 Agent 名称 | 否 | 子 Agent 成功完成后 fire-and-forget；`response` 截断至 500 字符 |
| `PreCompact` | `manual` 或 `auto` | 否 | 上下文压缩前；返回值被忽略 |
| `PostCompact` | `manual` 或 `auto` | 否 | 压缩成功后 fire-and-forget |
| `Notification` | 通知类型 | 否 | 后台子 Agent 结果写入上下文时；`notification_type` 取值 `task.completed`/`task.failed`/`task.killed`/`task.lost` |

所有 payload 包含 `hook_event_name`、`session_id`、`cwd`。

---

## Plugin 系统

### Manifest 格式

Plugin 使用 `kimi.plugin.json`（或 `.kimi-plugin/plugin.json`）作为 manifest：

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "Plugin description",
  "skills": "./skills/",
  "sessionStart": {
    "skill": "init-skill"
  },
  "skillInstructions": "每次加载此 plugin 的 Skill 时附带的说明",
  "mcpServers": {
    "my-server": {
      "command": "node",
      "args": ["./mcp/server.mjs"]
    }
  }
}
```

**仅支持 `skills` + `mcpServers`**。`tools`、`commands`、`hooks` 等旧字段被忽略。

### 安装与管理

| 命令 | 说明 |
|------|------|
| `/plugins` | 打开交互式管理器 |
| `/plugins install <path-or-url>` | 从本地目录或 zip URL 安装 |
| `/plugins enable/disable <id>` | 启用/禁用 Plugin |
| `/plugins remove <id>` | 移除 Plugin |
| `/plugins mcp enable/disable <id> <server>` | 管理 MCP server |
| `/plugins marketplace` | 浏览官方 marketplace |

Plugin 安装到 `$KIMI_CODE_HOME/plugins/managed/<id>/`。变更只对新会话生效（需 `/new`）。

### MCP Server 配置

MCP server 可声明在 `mcp.json` 或 Plugin manifest 中：

- 用户级：`~/.kimi-code/mcp.json`
- 项目级：`.kimi-code/mcp.json`（覆盖用户级同名条目）

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    },
    "linear": {
      "url": "https://mcp.linear.app/mcp"
    }
  }
}
```

支持 stdio（本地进程）和 HTTP 两种传输方式。交互式配置入口：`/mcp-config`。查看状态：`/mcp`。

---

## config.toml 速查

### 顶层字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `default_model` | string | — | 默认模型别名 |
| `default_thinking` | boolean | false | Thinking 初始开关 |
| `default_permission_mode` | string | manual | manual/auto/yolo |
| `default_plan_mode` | boolean | false | 是否默认 Plan 模式 |
| `merge_all_available_skills` | boolean | true | 是否合并所有目录的 Skills |
| `extra_skill_dirs` | array | — | 额外 Skill 搜索目录 |
| `telemetry` | boolean | true | 匿名遥测 |

### 关键段

- `[providers.<name>]`：API 供应商配置（type: kimi/openai/anthropic/google-genai/openai_responses/vertexai）
- `[models.<alias>]`：模型别名（provider、model、max_context_size、capabilities、display_name）
- `[thinking]`：mode（auto/on/off）、effort（low/medium/high/xhigh/max）
- `[loop_control]`：max_steps_per_turn（默认 1000）、max_retries_per_step（默认 3）、reserved_context_size
- `[background]`：max_running_tasks、keep_alive_on_exit（默认 true）、agent_task_timeout_s
- `[services]`：moonshot_search、moonshot_fetch（内置搜索/抓取服务）

完整配置说明见 `references/kimi-code-config.md`。

---

## 环境变量速查

### 核心路径

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `KIMI_CODE_HOME` | 数据根目录 | `~/.kimi-code` |
| `KIMI_SHELL_PATH` | Windows Git Bash 路径（自动探测失败时使用） | — |
| `KIMI_CODE_BASE_URL` | OAuth 登录后的 API 基地址 | `https://api.kimi.com/coding/v1` |

### 运行时开关

| 变量 | 说明 |
|------|------|
| `KIMI_DISABLE_TELEMETRY=1` | 关闭遥测 |
| `KIMI_CODE_BACKGROUND_KEEP_ALIVE_ON_EXIT` | 覆盖 `[background].keep_alive_on_exit` |
| `KIMI_CODE_PLUGIN_MARKETPLACE_URL` | 覆盖 Plugin marketplace URL |
| `KIMI_MODEL_MAX_COMPLETION_TOKENS` | 单步 max_tokens 硬上限（仅 kimi 供应商） |
| `KIMI_DISABLE_CRON=1` | 禁用定时任务工具 |

### 日志

| 变量 | 默认值 |
|------|--------|
| `KIMI_LOG_LEVEL` | `info` |
| `KIMI_LOG_GLOBAL_MAX_BYTES` | 6 MB |
| `KIMI_LOG_GLOBAL_FILES` | 5 |
| `KIMI_LOG_SESSION_MAX_BYTES` | 5 MB |
| `KIMI_LOG_SESSION_FILES` | 3 |

> **重要**：供应商凭证（`KIMI_API_KEY`、`ANTHROPIC_API_KEY` 等）不会从 `process.env` 自动读取，必须写在 `config.toml` 的 `[providers.<name>]` 或 `[providers.<name>.env]` 子表中。

---

## 常见错误与规避

| 错误 | 原因 | 解决 |
|------|------|------|
| `Search failed (authentication)` | WebSearch 未认证 | 运行 `/login` 登录 Kimi 账号 |
| `Search failed (network)` | API 配额用完 | 检查 Kimi Code 套餐余量 |
| `spawn python3 ENOENT` | MCP server 中 python3 不存在 | Windows 上改为项目 `.venv/Scripts/python.exe` |
| `old_string not found` | Edit 时文件已被其他操作修改 | 重新 Read 文件后再 Edit |
| `glob pattern rejected` | Glob 使用了纯通配符 | 添加字面锚点（如 `src/**/*.ts`） |
| Hook 不触发 | `event` 字段值不在合法事件表中 | 检查拼写，必须精确匹配事件表 |
| Plugin MCP server 不启动 | Plugin 变更需新会话 | 运行 `/new` 开启新会话 |

---

## 关联文档

- `references/kimi-code-config.md` — 配置文件完整说明（providers、models、thinking、loop_control、background、services、permission、hooks 详细示例）
- `references/kimi-code-skills.md` — Agent Skills 完整说明（SKILL.md 格式、存放位置、调用方式、Flow Skills）
- `references/flow-skills-comparison.md` — Flow Skills 与普通 Skills 对比