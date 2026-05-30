---
name: kimi-cli-handbook
description: |
  Kimi CLI 完整使用手册。覆盖全部 19 个可用工具的详细参数、默认值、边界限制、常见错误和规避策略，
  以及超时规避、幂等性防护等使用模式。同时覆盖 Hooks 系统（13 种生命周期事件）、自定义插件系统、
  Flow Skills、自定义 Agent 文件等进阶能力。
  当需要确认工具参数行为、排查调用失败原因、设计长任务执行策略、配置 Hooks 自动化、
  开发自定义插件工具、设计声明式工作流时使用。
  配置文件说明见 references/kimi-cli-config.md，Flow Skills 详细语法见 references/kimi-cli-skills.md。
---

# Kimi CLI 使用手册

完整覆盖当前可用工具的参数说明、边界限制、默认行为、常见错误和规避策略。同时覆盖 Hooks 系统（13 种生命周期事件）、自定义插件系统、Flow Skills 和自定义 Agent 文件。所有结论来自实际调用验证 + 官方文档确认。

配置文件（`~/.kimi/config.toml`）的完整说明见 `references/kimi-cli-config.md`，其中包含 hooks 详细配置和脚本示例。插件系统详情见下方「自定义插件系统」章节。

当前可用工具共 19 个：Agent、AskUserQuestion、SetTodoList、Shell、ReadFile、ReadMediaFile、Glob、Grep、WriteFile、StrReplaceFile、SearchWeb、FetchURL、Think、SendDMail、EnterPlanMode、ExitPlanMode、TaskList、TaskOutput、TaskStop。

---

## 1. Shell

执行 bash 命令。每次调用是独立 shell 环境，不保留变量、工作目录或 shell 历史。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `command` | string | 必填 | 要执行的命令 |
| `description` | string | `""` | 后台任务描述，仅 `run_in_background=true` 时需要 |
| `run_in_background` | bool | `false` | 是否作为后台任务运行 |
| `timeout` | int | 60 | 超时秒数 |

**超时边界：**

| 模式 | 最小值 | 最大值 | 说明 |
|------|--------|--------|------|
| 前台 | 1s | **300s (5分钟)** | 超过 300s 会直接拒绝调用，不是超时后才报错 |
| 后台 | 1s | **86400s (24小时)** | 后台任务无 300s 限制 |

**重要行为：**

- 每次调用是全新 shell，`cd`、`export` 等不跨调用生效。需要跨调用保留状态时用 `&&` 或 `;` 串联。
- 超时 kill 后**可能有部分产物残留**。命令中途被 kill 时，已执行的写入/修改不会回滚。
- 后台任务启动后返回 `task_id`，通过 `TaskOutput` 获取结果。
- 后台任务运行中 output 不可用（`retrieval_status: not_ready`），只有完成后才能拿到输出。

**常见错误：**

```
# 错误：前台 timeout 设 301 以上会直接拒绝
Shell: command="sleep 10", timeout=301
# 报错：timeout must be <= 300s for foreground commands

# 正确：长命令用后台
Shell: command="sleep 10", run_in_background=true, timeout=86400, description="长任务"
```

---

## 2. ReadFile

读取文本文件内容。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `path` | string | 必填 | 文件绝对路径 |
| `line_offset` | int | 1 | 起始行号，负数从尾部读取（绝对值不超过 1000） |
| `n_lines` | int | 1000 | 读取行数，最大 1000 |

**行为说明：**

- 文件不存在返回 ERROR。
- 行宽超过 2000 字符的行会被截断（末尾加 `...`）。
- `line_offset=-100` 读取最后 100 行。

---

## 3. WriteFile

写入或追加文件内容。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `path` | string | 必填 | 文件绝对路径 |
| `content` | string | 必填 | 要写入的内容 |
| `mode` | string | `"overwrite"` | `"overwrite"` 覆盖，`"append"` 追加 |

**重要：append 不会自动加换行符。** 追加多行内容时必须在 content 开头手动加 `\n`：

```
# 错误：追加内容会粘在最后一行后面
WriteFile: path="file.txt", mode="append", content="new line"

# 正确
WriteFile: path="file.txt", mode="append", content="\nnew line"
```

---

## 4. StrReplaceFile

字符串精确替换。支持单次编辑和批量编辑。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `path` | string | 必填 | 文件绝对路径 |
| `edit` | object 或 array | 必填 | 单个 `{old, new, replace_all?}` 或该结构的数组 |

**edit 对象字段：**

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `old` | string | 必填 | 要替换的原字符串，支持多行 |
| `new` | string | 必填 | 替换后的字符串 |
| `replace_all` | bool | `false` | 是否替换所有匹配项 |

**使用方式：**

- 单个替换：传单个 `{old, new, replace_all}` 对象
- 批量替换：传上述对象的数组，一次调用完成多个替换
- old 必须精确匹配（包括空白字符），否则替换失败

---

## 5. Glob

文件 glob 模式搜索。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `pattern` | string | 必填 | glob 模式，支持 `*`、`?`、`**` |
| `directory` | string | 工作目录 | 搜索目录的绝对路径 |
| `include_dirs` | bool | `true` | 是否在结果中包含目录 |

**限制：**

- 禁止 `**` 开头的模式（会递归整个文件系统），必须加前缀如 `src/**/*.py`
- 禁止搜索 `node_modules`、`venv`、`.venv`、`__pycache__`、`target` 等依赖/构建目录

---

## 6. Grep

基于 ripgrep 的内容搜索。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `pattern` | string | 必填 | ripgrep 正则模式 |
| `path` | string | `"."` | 搜索路径 |
| `glob` | string | 无 | 文件名过滤，如 `*.py`、`*.{ts,tsx}` |
| `output_mode` | string | `"files_with_matches"` | `"content"` / `"files_with_matches"` / `"count_matches"` |
| `-A` / `-B` / `-C` | int | 无 | 上下文行数（仅 `output_mode="content"` 时有效） |
| `-i` | bool | `false` | 大小写不敏感 |
| `-n` | bool | `true` | 显示行号（仅 content 模式） |
| `head_limit` | int | 250 | 输出上限，0 为不限制 |
| `offset` | int | 0 | 跳过前 N 条结果 |
| `include_ignored` | bool | `false` | 是否搜索 gitignore 排除的文件 |
| `multiline` | bool | `false` | 多行模式 |
| `type` | string | 无 | 按文件类型搜索，如 `py`、`js`、`ts` |

**使用注意：**

- `head_limit` 默认 250，结果超过此数会被截断。需要更多结果时用 `offset` 分页。
- `.env` 等敏感文件始终被过滤，即使 `include_ignored=true`。
- `{` `}` 等正则特殊字符需要转义：`\\{`、`\\}`。

---

## 7. SearchWeb

网页搜索。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | string | 必填 | 搜索关键词 |
| `limit` | int | 5 | 结果数量，最大 20 |
| `include_content` | bool | `false` | 是否返回网页全文 |

**注意：** `include_content=true` 会大幅消耗 token，仅在需要详细内容时开启。

---

## 8. FetchURL

抓取网页正文。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `url` | string | 必填 | 目标 URL |

提取的是网页正文内容（去除 HTML 标签），不包含导航、侧边栏等噪声内容。

---

## 9. Agent

启动子 Agent 实例。子 Agent 保持独立上下文历史，支持 resume 恢复。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `description` | string | 必填 | 3-5 词的简短任务描述 |
| `prompt` | string | 必填 | 任务指令 |
| `subagent_type` | string | `"coder"` | `"coder"`（读写）/ `"explore"`（只读）/ `"plan"`（规划） |
| `resume` | string | 无 | 恢复已有实例的 agent_id |
| `run_in_background` | bool | `false` | 是否后台运行 |
| `timeout` | int | 见下表 | 超时秒数 |
| `model` | string | 继承父级 | 可选模型覆盖 |

**超时边界：**

| 模式 | 最小值 | 最大值 | 默认值 |
|------|--------|--------|--------|
| 前台 | **30s** | **3600s (1小时)** | 无限制（跑到完成） |
| 后台 | 30s | 3600s | 900s (15分钟) |

**Agent 类型说明：**

| 类型 | 工具 | 用途 |
|------|------|------|
| `explore` | Shell(只读), ReadFile, Glob, Grep, SearchWeb, FetchURL | 快速代码库探索 |
| `coder` | 全部工具 | 通用软件工程任务 |
| `plan` | 只读工具 | 实现规划和架构设计 |

**重要行为：**

- `resume` 恢复的实例保留之前的完整上下文，适合长任务分段执行。
- 超时后 Agent 被终止，**可能有部分产物残留**（如已写入的文件）。
- 后台 Agent 完成后会自动通知，可通过 `TaskList` / `TaskOutput` 管理。
- 多个 explore agent 可以并行启动，互不干扰。

---

## 10. TaskList

列出后台任务。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `active_only` | bool | `true` | 仅列出活跃任务 |
| `limit` | int | 20 | 返回数量上限 |

**返回的任务 kind：** `bash`（Shell 后台）/ `agent`（Agent 后台）。

---

## 11. TaskOutput

获取后台任务的输出或状态。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `task_id` | string | 必填 | 任务 ID |
| `block` | bool | `false` | 是否等待任务完成 |
| `timeout` | int | 30 | 最大等待秒数（仅 block=true 时有效） |

**重要行为：**

- `block=true` 会阻塞等待，但 **timeout 是软限制**：到达 timeout 后返回当前状态，不会 kill 任务。
- 任务运行中 output 不可用（`retrieval_status: not_ready`）。
- 任务完成后返回完整 output，可通过返回的 `output_path` 用 `ReadFile` 读完整日志。

**典型使用模式：**

```
# 1. 启动后台任务
Shell: command="npm run build", run_in_background=true, description="前端构建"

# 2. 轮询检查状态
TaskOutput: task_id=xxx, block=false

# 3. 等状态变为 completed 后读日志
ReadFile: path=<output_path>
```

---

## 12. TaskStop

停止后台任务。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `task_id` | string | 必填 | 要停止的任务 ID |
| `reason` | string | `"Stopped by TaskStop"` | 停止原因 |

停止后任务标记为 `killed`，可通过 `TaskList(active_only=false)` 查看。

---

## 13. AskUserQuestion

向用户提问。用于需要用户决策的场景。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `questions` | array | 必填 | 1-4 个问题 |

**每个问题对象：**

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `question` | string | 必填 | 问题文本 |
| `header` | string | `""` | 短标签，最多 12 字符 |
| `options` | array | 必填 | 2-4 个选项 |
| `multi_select` | bool | `false` | 是否允许多选 |

**每个选项对象：**

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `label` | string | 必填 | 选项标签，1-5 词 |
| `description` | string | `""` | 选项说明 |

**返回值：** `{"answers": {"问题文本": "选中标签"}}`，多选时逗号分隔，如 `"标签1, 标签2"`。

**注意：** 用户始终有 "Other" 选项可输入自定义答案，无需自己创建。

---

## 14. SetTodoList

管理 Todo 清单。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `todos` | array 或 null | 无 | 更新时传数组，查询时省略，清空时传 `[]` |

**每个 todo 对象：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `title` | string | 任务标题（注意是 `title` 不是 `content`） |
| `status` | string | `"pending"` / `"in_progress"` / `"done"` |

**三种模式：**

```
# 更新模式：传完整列表
SetTodoList: todos=[{"title": "任务1", "status": "in_progress"}, ...]

# 查询模式：不传参数
SetTodoList: （无参数）

# 清空模式：传空数组
SetTodoList: todos=[]
```

**常见错误：** 把 `title` 写成 `content` 会导致验证失败。

---

## 15. EnterPlanMode / ExitPlanMode

Plan 模式用于需要用户审批的实现方案设计。

**EnterPlanMode：** 无参数。进入后只能编辑 plan 文件，不能做其他修改。

**ExitPlanMode：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `options` | array | 无 | 多方案时提供 2-3 个选项让用户选择 |

**每个 option 对象：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `label` | string | 选项名称，推荐方案加 `(Recommended)` 后缀 |
| `description` | string | 方案说明和权衡 |

**注意：** 只有一个方案时不传 `options`，用户只能 Approve/Reject。

---

## 16. ReadMediaFile

读取图片或视频文件。仅当模型支持对应输入时可用。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `path` | string | 必填 | 文件路径 |

**限制：** 文件最大 100MB。工作目录外的文件需绝对路径。

---

## 17. Think

记录思考过程，适用于复杂推理场景。仅在 `okabe` agent 或自定义 agent 中可用。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `thought` | string | 必填 | 思考内容 |

---

## 18. SendDMail

发送延迟消息（D-Mail），用于检查点回滚场景。仅在 `okabe` agent 中可用。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `message` | string | 必填 | 要发送的消息 |
| `checkpoint_id` | int | 必填 | 目标检查点 ID（>= 0） |

---

## 补充：Glob 的返回值限制

Glob 最多返回 **1000 个匹配项**。如果目录中文件超过 1000 个，结果会被截断，需要用更具体的 pattern 缩小范围。

---

## 超时规避策略

### 策略 1：长 Shell 命令用后台模式

前台 Shell 最大 300 秒，任何可能超过此限制的命令都走后台：

```
# 编译、构建、大文件处理等
Shell: command="npm run build", run_in_background=true, timeout=86400, description="前端构建"
```

### 策略 2：后台 + 轮询取结果

```
Shell: command="long_task > /tmp/result.log 2>&1", run_in_background=true
# ... 做其他事 ...
TaskOutput: task_id=xxx, block=false  # 检查是否完成
ReadFile: path=/tmp/result.log       # 完成后读日志
```

### 策略 3：Agent 长任务拆段 + resume

预计超过 1 小时的 Agent 任务，拆成多个短调用，用 `resume` 保持上下文连续性：

```
Agent: prompt="完成步骤 1-3", subagent_type="coder", timeout=1800
Agent: resume="xxx", prompt="继续步骤 4-6", timeout=1800
```

### 策略 4：幂等性防护

超时后可能有部分产物残留，关键操作设计成幂等：

```bash
# Shell 命令内加 trap 清理
trap 'rm -f /tmp/partial_result' EXIT

# 或先检查是否已完成
if [ -f /tmp/done_marker ]; then exit 0; fi
# ... 执行操作 ...
touch /tmp/done_marker
```

### 策略 5：Agent 超时设宽裕量

Agent 默认前台无超时，但给 `timeout` 参数设一个比预期执行时间大 50% 的值，既防止无限卡死，又不至于太紧张。

---

## 常见错误速查

| 错误 | 原因 | 修正 |
|------|------|------|
| `timeout must be <= 300s for foreground commands` | 前台 Shell 超时设了 301+ | 改用后台模式或降低 timeout |
| `timeout must be >= 30` (Agent) | Agent timeout 设了小于 30 | 最小 30s |
| WriteFile append 内容粘在一起 | append 不自动加换行 | content 前加 `\n` |
| SetTodoList 报 `Field required` | 用了 `content` 而非 `title` | 改为 `title` |
| `**` 开头的 Glob 被拒绝 | 模式必须以具体目录开头 | 改为 `src/**/*.py` |
| TaskOutput 返回 `not_ready` | 任务还在运行 | 等完成后重试 |
| Shell 环境变量不生效 | 每次调用是独立 shell | 用 `&&` 串联 |
| Agent 超时后部分文件残留 | timeout kill 不保证原子性 | 见策略 4 幂等性防护 |
| Glob 结果被截断 | 匹配项超过 1000 个 | 用更具体的 pattern 缩小范围 |
| 后台任务完成后找不到输出 | 忘了记 task_id | 用 `TaskList(active_only=false)` 查找 |

---

## 自定义插件系统（Beta）

> Beta 功能：实现细节和配置定义可能在未来版本调整。

插件系统让你为 Kimi Code CLI 添加自定义工具，扩展 AI 的能力。与 MCP 服务器不同，插件是轻量级的本地工具包，适合封装项目特定的脚本和实用程序。

### 插件 vs Skills vs MCP

| 特性 | 插件 | Skills | MCP |
|------|------|--------|-----|
| 本质 | 可执行工具包 | 知识性指导 | 持续运行的服务 |
| 定义文件 | `plugin.json` | `SKILL.md` | MCP server 配置 |
| AI 交互方式 | 直接调用工具获取结果 | 读取规范后遵循 | 通过协议调用工具 |
| 适用场景 | 脚本封装、项目特定工具、快速原型 | 规范、流程、领域知识 | 复杂工具编排、跨进程通信 |
| 安装位置 | `~/.kimi/plugins/` | 项目/用户 skill 目录 | 配置文件 `mcp` 段 |

### 安装与管理

使用 `kimi plugin` 命令管理插件：

```bash
# 从本地目录安装
kimi plugin install /path/to/my-plugin

# 从 ZIP 文件安装
kimi plugin install my-plugin.zip

# 从 Git 仓库安装（根目录）
kimi plugin install https://github.com/user/repo.git

# 从 Git 仓库子目录安装（多插件仓库）
kimi plugin install https://github.com/user/repo.git/plugins/my-plugin

# 指定分支
kimi plugin install https://github.com/user/repo/tree/develop/plugins/my-plugin

# 列出已安装插件
kimi plugin list

# 查看插件详情
kimi plugin info my-plugin

# 移除插件
kimi plugin remove my-plugin
```

**Git 仓库自动发现**：当仓库根目录没有 `plugin.json` 时，CLI 会检查根目录及其直接子目录，列出可用插件供选择。

### 插件结构

```
my-plugin/
├── plugin.json      # 插件配置（必需）
├── config.json      # 插件配置（可选，用于凭证注入）
├── SKILL.md         # 可选：随插件分发的 Skill
└── scripts/         # 工具脚本
    ├── greet.py
    └── calc.ts
```

### plugin.json 格式

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "My custom plugin for project X",
  "config_file": "config.json",
  "inject": {
    "api_key": "api_key",
    "endpoint": "base_url"
  },
  "tools": [
    {
      "name": "greet",
      "description": "Generate a greeting message",
      "command": ["python3", "scripts/greet.py"],
      "parameters": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string",
            "description": "Name to greet"
          }
        },
        "required": ["name"]
      }
    }
  ]
}
```

### 字段说明

**插件级字段：**

| 字段 | 说明 | 必填 |
|------|------|------|
| `name` | 插件名称，只能用小写字母、数字和连字符 | 是 |
| `version` | 语义化版本格式 | 是 |
| `description` | 插件描述 | 否 |
| `config_file` | 配置文件路径，用于凭证注入 | 否 |
| `inject` | 凭证注入映射，键为目标路径，值为源变量名 | 否 |
| `tools` | 工具列表 | 否 |

**工具级字段：**

| 字段 | 说明 | 必填 |
|------|------|------|
| `name` | 工具名称 | 是 |
| `description` | 工具描述 | 是 |
| `command` | 执行命令，字符串数组 | 是 |
| `parameters` | JSON Schema 格式的参数定义 | 否 |

### 工具脚本规范

脚本通过**标准输入**接收参数，通过**标准输出**返回结果。

**输入格式**（stdin JSON）：

```json
{"name": "World"}
```

**输出格式**（stdout）：输出的内容作为字符串返回给 Agent。结构化输出建议用 JSON：

```json
{"content": "Hello, World!"}
```

**Python 示例：**

```python
#!/usr/bin/env python3
import json, sys

params = json.load(sys.stdin)
name = params.get("name", "Guest")
result = {"content": f"Hello, {name}!"}
print(json.dumps(result))
```

**TypeScript 示例：**

```typescript
#!/usr/bin/env tsx
import * as readline from "readline";

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
  terminal: false,
});

let input = "";
rl.on("line", (line) => { input += line; });
rl.on("close", () => {
  const params = JSON.parse(input);
  const name = params.name || "Guest";
  console.log(JSON.stringify({ content: `Hello, ${name}!` }));
});
```

### 凭证注入

如果插件需要调用 LLM API，可通过 `inject` 配置自动获取 Kimi Code CLI 的凭证。

**plugin.json 配置：**

```json
{
  "config_file": "config.json",
  "inject": {
    "llm.api_key": "api_key",
    "llm.endpoint": "base_url"
  }
}
```

**支持的注入变量：**

| 变量名 | 说明 |
|--------|------|
| `api_key` | LLM 提供商的 API 密钥，支持 OAuth token 和静态 API key |
| `base_url` | LLM API 的基础 URL |

**config.json 模板：**

```json
{
  "llm": {
    "api_key": "",
    "endpoint": ""
  }
}
```

安装时 CLI 会将当前 API 密钥和 base URL 注入到指定配置文件。之后每次启动 CLI 时也会尝试将最新凭证（如刷新后的 OAuth token）写入已安装插件的配置文件。

**重要行为：**
- 切换 LLM 提供商或重新授权后，重启 CLI 即可自动刷新凭证，一般不需要重新安装插件
- 只有修改了 `config_file` 或 `inject` 映射时才需要重新安装
- `inject` 中的键名（如 `llm.api_key`）会被用作环境变量名传给工具子进程。由于包含点号，在 POSIX shell 中不能直接用 `$llm.api_key`，需通过字典方式访问：
  - Node.js: `process.env["llm.api_key"]`
  - Python: `os.environ["llm.api_key"]`
- 建议在插件中使用大写下划线格式（如 `LLM_API_KEY`）作为环境变量名

### 附带 Skill

插件可以在根目录（与 `plugin.json` 同级）放置 `SKILL.md`，CLI 启动时自动发现。

- Skill 名称优先取 `SKILL.md` frontmatter 中的 `name`，否则使用插件目录名
- 该 skill 以 `extra` 作用域被发现，同名的项目级或用户级 skill 会覆盖它
- 一个插件只能有一个 `SKILL.md`，不支持 `<plugin>/skills/<name>/SKILL.md` 嵌套布局

### 完整示例

```json
{
  "name": "sample-plugin",
  "version": "1.0.0",
  "description": "Sample plugin demonstrating Skills + Tools",
  "tools": [
    {
      "name": "py_greet",
      "description": "Generate a greeting message (Python tool)",
      "command": ["python3", "scripts/greet.py"],
      "parameters": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string",
            "description": "Name to greet"
          },
          "lang": {
            "type": "string",
            "enum": ["en", "zh", "ja"],
            "description": "Language"
          }
        },
        "required": ["name"]
      }
    },
    {
      "name": "ts_calc",
      "description": "Evaluate a math expression (TypeScript tool)",
      "command": ["npx", "tsx", "scripts/calc.ts"],
      "parameters": {
        "type": "object",
        "properties": {
          "expression": {
            "type": "string",
            "description": "Math expression to evaluate"
          }
        },
        "required": ["expression"]
      }
    }
  ]
}
```

---

## Flow Skills 使用技巧

Flow Skill 的完整语法和格式见 `references/kimi-cli-skills.md`。这里只补充从源码分析中得到的使用技巧，这些是文档里没写但实际行为中存在的细节。

### Flow 的两种调用路径

同一个 Flow Skill 注册了两个命令：

| 命令 | 行为 | 适用场景 |
|------|------|----------|
| `/flow:<name>` | FlowRunner 按图执行，BEGIN→task→decision→END | 需要严格按流程走、分支选择需要暂停确认 |
| `/skill:<name>` | SKILL.md 全文注入对话，Agent 自己理解并执行 | 流程不复杂、想让 Agent 灵活调整执行顺序 |

关键区别：`/flow:` 走状态机引擎，`/skill:` 走普通对话。两者可以互补使用——先用 `/flow:` 严格跑一遍，发现问题后 `/skill:` 灵活调整。

### decision 节点的自动重试机制

当 Agent 在 decision 节点的回复中没有输出 `<choice>分支名</choice>` 时，FlowRunner **不会静默跳过**，而是自动追加提示并重试：

```
Your last response did not include a valid choice. 
Reply with one of the choices using <choice>...</choice>.
```

这意味着：
- 不需要在 decision 节点的 prompt 里反复强调"必须用 `<choice>` 格式"——FlowRunner 会自动追加这个要求
- 但为了减少重试次数、节省 token，最好还是在节点文本里提一句"完成后用 `<choice>分支名</choice>` 选择下一步"
- 如果 Agent 反复匹配失败（比如输出的是近似但不完全匹配的分支名），会一直重试直到 `max_moves` 耗尽。所以**分支标签要简短精确**，避免用长句或容易写错的词

### `<choice>` 的匹配规则

从源码确认：`parse_choice()` 取的是文本中**最后一个** `<choice>...</choice>`，然后用 `_match_flow_edge()` 做**精确字符串比较**。

这意味着：
- Agent 在正文中提到 `<choice>` 不会干扰匹配（取最后一个，通常 Agent 会把 choice 放在回复末尾）
- 但如果你在节点文本的示例中写了 `<choice>示例</choice>`，Agent 可能照抄，导致匹配到错误分支。**不要在 prompt 里放 `<choice>` 的字面示例**
- 分支标签中的空格、大小写都必须完全一致。建议用全大写的单词（如 `CONTINUE`、`STOP`、`FIX`、`SKIP`）减少拼写错误

### 节点类型推断

Mermaid/D2 图中不需要显式声明节点类型。FlowRunner 根据以下规则自动推断：

| 条件 | 推断类型 |
|------|----------|
| label 规范化后等于 `"begin"` | `begin` |
| label 规范化后等于 `"end"` | `end` |
| 只有 1 条出边 | `task` |
| 有 2 条以上出边 | `decision` |

注意：**菱形括号 `{}` 只是 Mermaid 的视觉形状，不影响类型推断**。一个用方括号但有多条出边的节点同样会被推断为 decision。同样，一个用菱形但只有一条出边的节点会被推断为 task。

利用这个特性：如果你想要一个"展示结果后自动继续"的节点（不需要选择分支），确保它只有一条出边。

### task 节点不检查输出

task 节点的 LLM 回复内容不被解析、不被验证。Agent 执行完 task 后**无条件走唯一出边**。这意味着：
- task 节点的 prompt 必须足够自包含，让 Agent 知道产出应该是什么
- 如果需要验证 task 的输出质量，应该把验证逻辑放在下一个节点中
- 如果 task 可能失败，应该紧跟一个 decision 节点让 Agent 判断是否继续

### 解析失败自动降级

如果 SKILL.md 声明了 `type: flow` 但 Mermaid/D2 解析失败（语法错误、缺少 BEGIN/END、边 label 重复等），skill 会被**降级为 `type: standard`**，`/flow:<name>` 命令不会注册。

这意味着：
- 写 Flow Skill 后务必用 `/flow:<name>` 测试一次，确认能正常启动
- 如果 `/flow:` 不生效，用 `/skill:<name>` 仍可使用，但需要手动跟流程
- 排查时检查 SKILL.md 中：恰好 1 个 BEGIN 和 1 个 END、所有节点可达、分支节点的边都有 label 且不重复

### 流程设计建议

1. **BEGIN 后第一个节点放上下文收集**：让 Agent 先读相关文件、了解现状，再做后续决策
2. **decision 分支不超过 3 个**：分支太多 Agent 容易选错，匹配失败重试也浪费 token
3. **END 前放汇总节点**：把整个流程的产出汇总成一份报告，方便后续引用
4. **利用回边做循环**：Mermaid 中 `E --> B` 可以形成迭代循环，但注意设好退出条件（通过 decision 节点），否则会跑到 `max_moves` 耗尽
5. **max_moves 默认 1000**：每次经过 task/decision 节点算一次 move，循环设计时确保能在 1000 步内收敛

### Flow 与子 Agent 配合

FlowRunner 的每一步都调用 `soul._turn()`，这意味着 Flow 执行期间 Agent 可以使用全部工具，包括启动子 Agent。

可以利用这个特性：
- 在 task 节点中启动 explore agent 做代码库调研，等结果后继续
- 在 decision 节点中根据子 Agent 的返回结果选择分支
- 注意：子 Agent 的超时和 Flow 的 max_moves 是独立的两套限制，子 Agent 超时不会中断 Flow

### 常见错误

| 错误 | 原因 | 修正 |
|------|------|------|
| `/flow:xxx` 不生效 | Mermaid/D2 解析失败，skill 被降级为 standard | 检查图语法，确认 1 BEGIN + 1 END + 全可达 + 分支边有 label |
| Flow 卡在某个节点不动 | decision 的 `<choice>` 匹配失败，正在自动重试 | 检查分支标签是否精确匹配（空格、大小写） |
| 循环不停止 | 回边没有设退出条件 | 回边必须经过 decision 节点，且有一个指向 END 的分支 |
| Agent 选择了错误的分支 | 分支标签不够清晰，或 prompt 中有误导性的 `<choice>` 字面示例 | 用简短精确的标签，不要在 prompt 中写 `<choice>` 示例 |