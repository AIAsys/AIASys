+++
name = "AIASys Platform Guide"
description = "AIASys 工作平台的完整使用指南。覆盖核心概念、Agent 工具目录、Auto Task 配合模式、\nUV 运行环境、Docker 沙盒资源、环境变量、多维数据表、Skill 协作方式。\n当 Agent 需要了解 AIASys 平台能力、选择工具、或配合 Auto Task 工作时使用。"
+++


# AIASys Platform Guide

本 Skill 是 AIASys 内置 Agent 的入职手册，涵盖平台概念、工具选择、后台任务配合和常用系统操作。

---

## 一、平台概览

AIASys 是 AI Agent 工作平台。内核为科研和数据分析场景深度优化，同时通过 MCP 市场和 Skill 市场覆盖通用办公和日常提效场景。

### 核心定位

- **目标用户**：科研人员、数据分析师、独立开发者、普通办公人群
- **产品形态**：桌面应用（Electron）优先，同时支持 Web 界面
- **核心能力**：Agent 工作流推进、工作区管理、Skill 扩展、Auto Task 自动循环

### 核心概念

**工作区（Workspace）**

工作区是一等对象。它是 Agent 执行任务的持久化上下文，包含：
- 文件系统（数据、代码、产物）
- Skill 集合（工作区启用的能力）
- 运行环境物料（`.env/`，由 `RuntimeEnvironment` 管理）
- 环境变量配置（`.workspace/workspace.json` 的 `runtime_binding.env_vars`）
- 知识图谱（GraphRAG）
- Python/UV 运行环境（宿主机 Notebook、IPython、普通 Python 任务）
- Docker 沙盒资源（显式登记或创建后，用于容器内 Shell 任务）
- Auto Task 配置

工作区之间隔离。一个工作区的 Skill、环境、数据不影响另一个。

**全局工作区**

每个用户有一个全局工作区 `global_workspace/`，路径为 `workspaces/{user_id}/global_workspace/`，存放跨工作区共享的资源和配置。普通工作区继承全局工作区的默认配置，也可以单独覆盖。

Agent 文件工具通过 `/global/` 访问全局工作区内容，`/workspace/` 访问当前工作区内容，两者是独立命名空间。

**会话（Session）**

会话是工作区内的分支。同一个工作区可以开多个会话，每个会话有独立的对话历史和执行状态，但共享工作区的文件和 Skill。

右侧边栏默认承接当前任务工作区，不默认承接执行流。

**Agent**

Agent 是执行任务的智能体。AIASys 中的 Agent：
- 运行在工作区上下文中
- 可以调用 Skill、工具、MCP
- 支持子 Agent 委派（TaskTool / AgentTool）
- 支持 Auto Task 持续循环

**Skill**

Skill 是 Agent 的能力扩展，以目录包形式存在，至少包含一个 SKILL.md 入口文件。

两类 Skill：
1. **通用 Skill**：不依赖 AIASys 内部服务，如 paddleocr-skill（调用 PaddleOCR API）
2. **系统 Skill**：依赖 AIASys 内部服务或内置对象模型，如本 skill（平台操作）、competition-research-skill（单分支竞赛实验）、competition-runtime-prep-skill（竞赛环境准备）、competition-parallel-research-skill（竞赛并行编排）、aiasys-canvas-skill（Canvas 对象编辑）

Agent 可以通过工具管理 Skill：
- `SearchStoreSkills`：搜索全局仓库 skill
- `EnableSkill`：启用 skill 到当前工作区或全局
- `DisableSkill`：从当前工作区或全局禁用
- `ListSkills`：列出工作区已启用的 skill
- `LoadSkill`：读取 skill 内容

**Auto Task**

Auto Task 是定时触发的 Agent 任务循环。配置后，系统按设定间隔自动运行 Agent 执行指定任务。

典型场景：
- 竞赛自动实验（continuous 模式绑定 session，循环跑实验）
- 定时文献检索（interval / cron 模式）
- 数据监控和报警

**MCP（Model Context Protocol）**

MCP 是 AIASys 与外部工具/服务集成的标准协议。通过 MCP 市场，用户可以接入外部 API、使用第三方工具链、构建自定义 MCP Server。

MCP 和 Skill 的区别：
- Skill：面向 Agent 的"能力扩展"，以 SKILL.md + 脚本形式存在，Agent 主动读取后按规则执行
- MCP：面向系统的"工具集成"，以 Server 形式运行，Agent 通过标准协议调用其暴露的工具

### 路径约定

- `/workspace/`：当前工作区根目录
- `/global/`：全局工作区根目录
- `.aiasys/`：工作区配置目录（skill 启用状态、MCP 配置等）
- `.env/`：工作区 UV 环境物料目录，包含 `environments.json`、`pyproject.toml`、`uv.lock`、`.python-version` 和 `.venv/`
- `.workspace/`：工作区元数据目录（sessions、auto_tasks、workspace.json）

### 前端产物渲染

Agent 生成的文件如果类型匹配，前端对话框会自动渲染为可视化组件，不需要额外操作。

**不限制目录，只看后缀**。文件放在 `/workspace/` 或 `/global/` 下任意子目录中，前端都能根据文件名后缀自动识别并渲染。

| 产物类型 | 匹配规则 | 前端表现 |
|---------|---------|---------|
| ECharts 图表 | 文件名以 `.chart.echarts.json` 或 `.echarts.json` 结尾 | 内嵌 ECharts 图表，支持交互和自适应缩放 |
| CSV 表格 | 文件名以 `.csv` 结尾 | 可滚动表格，超过 100 行时自动 head-tail 折叠（前 50 + 后 50） |
| Markdown GFM 表格 | Markdown 正文中的 `\| 表头 \|` 语法 | 内联渲染为表格 |
| Mermaid 图表 | Markdown 代码块标记为 `mermaid` | 渲染为流程图、时序图等 |
| 数学公式 | 内容含 `$$`、 `\(`、 `\[` 等 LaTeX 语法 | KaTeX 渲染 |
| PDF | 文件名以 `.pdf` 结尾 | 预览卡片，支持翻页 |
| 图片 | `.png`、 `.jpg`、 `.gif`、 `.svg` 等 | 内联展示 |
| Markdown | 文件名以 `.md` 结尾 | 渲染为富文本卡片 |
| Word / PPT | `.docx` / `.pptx` | 下载卡片 |

**Agent 输出建议**：
- 需要可视化图表时，输出 `.echarts.json` 文件而不是纯文本描述
- 需要导出 PNG 时，在 ECharts 资产里启用 `toolbox.feature.saveAsImage`；AIASys 图表预览卡片右上角也提供统一导出入口；论文定稿图优先用 matplotlib 另存静态图
- 需要展示结构化数据时，输出 `.csv` 文件而不是 Markdown 表格（CSV 支持更大规模数据和大表格折叠）
- 产物路径用 `/workspace/` 或 `/global/` 前缀，前端引用时会自动解析

---

## 二、Agent 工具目录

AIASys Agent 可调用的内置工具按职责分组：

### 文件与代码

| 工具 | 用途 |
|------|------|
| `ReadFile` | 读取文本文件 |
| `WriteFile` | 写入/覆盖文本文件 |
| `StrReplaceFile` | 文本替换 |
| `Shell` | 执行 Shell 命令，可显式进入已登记 Docker 容器 |
| `ListDirectory` | 列出目录内容 |

### Notebook 与代码执行

| 工具 | 用途 |
|------|------|
| `CreateNotebook` | 创建 Jupyter Notebook |
| `ExecuteNotebookCell` | 执行 Notebook Cell |
| `NotebookSession` | 管理 Notebook Session（attach/list/close） |
| `RegisterKernelEnv` | 为 Notebook Kernel 注册环境变量 |
| `RemoveKernelEnv` | 移除 Kernel 环境变量 |
| `LocalIPythonBox` | 本地 IPython 代码执行（非 Notebook） |

### 数据与知识

| 工具 | 用途 |
|------|------|
| `DatabaseQuery` | 执行 SQL 查询（工作区 SQLite） |
| `ListKnowledgeGraphs` | 列出知识图谱 |
| `CreateKnowledgeGraph` | 创建知识图谱 |
| `DeleteKnowledgeGraph` | 删除知识图谱 |
| `GraphEntitySearch` | 知识图谱实体搜索 |
| `GetGraphEntityDetail` | 知识图谱实体详情 |
| `CreateGraphEntity` | 创建知识图谱实体 |
| `UpdateGraphEntity` | 更新知识图谱实体 |
| `DeleteGraphEntity` | 删除知识图谱实体 |
| `CreateGraphRelation` | 创建知识图谱关系 |
| `QueryEntityRelations` | 知识图谱关系查询 |
| `GetCommunityReport` | 知识图谱社区报告 |
| `UploadDocumentsToGraph` | 上传文件到知识图谱 |
| `KnowledgeQuery` | 知识库查询 |
| `ListKnowledgeBases` | 列出可用知识库 |
| `CreateKnowledgeBase` | 创建知识库 |
| `UpdateKnowledgeBase` | 更新知识库配置 |
| `UploadDocumentsToKnowledgeBase` | 上传文档到知识库 |
| `ListKnowledgeBaseDocuments` | 列出知识库文档 |
| `DeleteDocumentsFromKnowledgeBase` | 从知识库删除文档 |
| `DeleteKnowledgeBase` | 删除知识库 |

### 运行环境与配置

| 工具 | 用途 |
|------|------|
| `RuntimeEnvironment` | 管理工作区 Python 执行环境（list/ensure_uv/register_python/install_packages/bind/inspect/unregister） |
| `SetEnvVar` | 设置工作区环境变量 |
| `DeleteEnvVar` | 删除工作区环境变量 |

### 自动任务

| 工具 | 用途 |
|------|------|
| `CreateAutoTask` | 创建自动任务 |
| `ListAutoTasks` | 列出当前工作区自动任务 |
| `UpdateAutoTask` | 更新自动任务配置 |
| `ControlAutoTask` | 控制任务生命周期（pause/resume/complete/run/delete） |
| `auto_task_signal` | 连续任务信号（complete/pause/get） |

### Skill 与任务

| 工具 | 用途 |
|------|------|
| `ListSkills` | 列出可用 Skill |
| `LoadSkill` | 加载指定 Skill 内容 |
| `SearchStoreSkills` | 搜索全局仓库 Skill |
| `EnableSkill` | 启用 Skill 到工作区 |
| `DisableSkill` | 禁用 Skill |
| `TaskPlan` | 生成子任务计划 |
| `ReadMedia` | 读取图片/视频文件 |

### 工具选择建议

- 需要持久化、可复现的数据分析 → 优先 Notebook（CreateNotebook + ExecuteNotebookCell）
- 快速验证、小片段代码 → LocalIPythonBox
- 系统级操作、批量处理 → Shell
- 结构化数据存储 → DatabaseQuery 或 DataTable（见第六节）
- 缺 Python 包、需要 Notebook 交互 → RuntimeEnvironment（UV）
- 需要系统依赖、固定 Linux 工具链或强隔离 → 先确认 Docker 沙盒资源，再用 Shell(container=...)
- 长期后台循环 → Auto Task（见第三节）

---

## 三、Auto Task 配合模式

Auto Task 是 AIASys 的"永不停止的 Agent"。竞赛自动实验、定时文献检索等场景都靠它驱动。

### 触发类型

| 类型 | 说明 | 典型场景 |
|------|------|---------|
| `continuous` | 完成审计后自动触发下一轮，无间隔 | 竞赛自动实验循环 |
| `interval` | 按秒级间隔触发 | 定时数据同步 |
| `cron` | 按 cron 表达式触发 | 每日报告生成 |
| `once` | 指定时间执行一次 | 延迟任务 |

### 会话策略

- **bind_session**：绑定已有 session，每次触发在同一上下文中执行，保留历史记忆
- **new_each_time**：每次触发新建 session，上下文隔离

竞赛自动实验必须选 `bind_session`，因为 Agent 需要知道之前做了什么实验、哪些方向已失败。

### 核心参数

创建 continuous 模式 Auto Task 时的关键配置：

```json
{
  "trigger_type": "continuous",
  "prompt": "你是竞赛自动研究 agent。当前在电力价格预测竞赛...",
  "bind_session_id": "<session_id>",
  "continuation_prompt": "上一轮实验结果已记录，继续下一轮实验循环。避免重复 anti_patterns 中的方向。",
  "max_continuations": -1,
  "stop_on_signal": true,
  "stop_on_consecutive_errors": 10,
  "overlap_policy": "skip"
}
```

参数说明：
- `prompt`：每轮注入给 Agent 的目标指令
- `continuation_prompt`：每轮追加的推进说明（系统会自动追加完成审计和停止信号规则）
- `bind_session_id`：绑定同一 session，保持上下文记忆
- `max_continuations`：最大触发次数，-1 表示不限制
- `stop_on_signal`：允许 Agent 通过 `auto_task_signal` 主动标记完成或暂停
- `stop_on_consecutive_errors`：连续错误达到阈值后禁用
- `overlap_policy`：skip（跳过并发）/ queue（排队）/ parallel（并行，仅非绑定模式）

Session 预算由当前分支的预算控制统一管理，不是 Auto Task 参数。预算耗尽后运行时会阻止该分支继续执行；如果 continuous Auto Task 绑定了这条分支，系统会同步暂停该任务。

### Agent 在 continuous 模式下的行为

每轮触发时，系统会注入一个组合 prompt：

```
目标: <task.prompt>

本轮推进要求:
<continuation_prompt>

完成审计（Completion Audit）——在标记目标完成前必须执行:
1. 把目标拆解为具体的、可验证的交付物清单
2. 检查每个交付物是否已产出且可定位
3. 只有全部交付物确认存在，才允许标记完成

停止信号规则:
- 目标已完全达成 → 调用 auto_task_signal(action=complete)
- 遇到阻塞需要人工介入 → 调用 auto_task_signal(action=pause)
```

Agent 每轮执行完后，系统会检查：
1. Agent 是否调用了 `auto_task_signal(action=complete/pause)`
2. Session 预算是否耗尽
3. 连续错误次数是否达到阈值

### 与竞赛 Skill 的配合

竞赛自动研究的典型配置：

1. 先用 `competition-research-skill` 的 `init` 命令创建项目目录
2. 创建一个 session 用于竞赛研究
3. 需要大依赖、GPU 或 runner smoke 时，先用 `competition-runtime-prep-skill` 准备可用 `env_id`
4. 创建 continuous Auto Task，绑定该 session，prompt 里指示 Agent 读取 `experiments/index.json`、`AGENTS.md` 和 `runtime_contract`，决定本轮动作
5. Agent 每轮按 `competition-research-skill` 的单分支循环执行：preflight、跑实验、记录结果、更新研究视图
6. 实验完成后 Agent 更新 `experiments/index.json`
7. 系统检查 `auto_task_signal`，决定是否进入下一轮

多分支、多环境并行探索不直接塞进单条 continuous Auto Task。用户明确授权并行时，先用 `competition-parallel-research-skill` 规划 lane、`env_id`、session、AutoTask 和写回顺序。

---

## 四、运行环境与 Docker 沙盒

Agent 在 AIASys 中执行代码时，先区分宿主机 UV 运行环境和 Docker 沙盒资源。核心边界：

- 不修改 `apps/backend/.venv`，后端自身 Python 环境只用于运行 AIASys
- 工作区默认 UV 物料目录是 `.env/`
- `workspace-default` 是默认环境 ID
- Python 依赖安装、UV 环境创建、检查和默认绑定优先调用 `RuntimeEnvironment` 工具
- `RuntimeEnvironment` 只管理 UV，不登记 Docker
- Docker 适合系统依赖、强隔离、容器内工具链、固定 Linux 环境和长脚本任务
- Docker 容器自带系统和 Python 环境，不复用工作区 `.env/.venv`
- 容器通过 `/workspace` 读写任务文件、数据和产物

### 先判断再操作

1. 先调用 `RuntimeEnvironment` 的 `list` 或 `inspect` 查看当前工作区 UV 状态
2. 如果只是缺 Python 包，优先使用 UV
3. 如果任务需要 Notebook 单元格交互、变量驻留或富媒体结果，优先使用 UV
4. 如果需要系统库、命令行工具、特定 Linux 环境、GPU、浏览器或更强隔离，再使用 Docker 沙盒资源
5. 如果任务要在 Docker 中运行，把逻辑保存成脚本，再用 `Shell(container=...)` 显式进入容器执行

### UV 工作流

适用场景：安装 Python 包、跑 Notebook / IPython、跑普通 Python 脚本、数据分析、论文复现、机器学习实验。

工作区 UV 物料落点：

```text
.env/
├── environments.json
├── pyproject.toml
├── uv.lock
├── .python-version
└── .venv/
```

不要直接改 `.env/environments.json`。需要新增、绑定、检查或删除环境时，调用 `RuntimeEnvironment`。如果确实要人工检查文件，只把它当作诊断材料。

创建或刷新 UV 环境：

```json
{
  "action": "ensure_uv",
  "env_id": "workspace-default",
  "display_name": "Workspace UV",
  "python_version": "3.11",
  "packages": ["pandas", "numpy"],
  "create_venv": true,
  "sync": true,
  "activate": true
}
```

补安装依赖：

```json
{
  "action": "install_packages",
  "env_id": "workspace-default",
  "packages": ["scikit-learn", "xgboost"],
  "sync": true
}
```

绑定已登记环境：

```json
{
  "action": "bind",
  "env_id": "workspace-default"
}
```

检查环境状态：

```json
{
  "action": "inspect",
  "env_id": "workspace-default"
}
```

读取工作区环境列表：

```json
{
  "action": "list",
  "inspect": true
}
```

取消登记环境：

```json
{
  "action": "unregister",
  "env_id": "workspace-default"
}
```

`unregister` 只取消工作区环境登记和默认绑定，不等于清理所有环境物料。需要清理大体积依赖目录时，先确认没有运行中的会话正在使用，再按工作区文件规则处理。

只为执行一次工具链时，优先使用工具自己的隔离入口。例如 `pdf-translate-skill` 会用 `uvx --from pdf2zh pdf2zh` 或 `uv tool run --from pdf2zh pdf2zh`，避免把重依赖写进工作区默认环境。

### Docker 沙盒资源工作流

适用场景：需要系统依赖或容器内已有工具链、需要强隔离、长时间脚本或批处理实验、UV 无法解决底层依赖。

挂载能力的作用：
- 容器内统一用 `/workspace` 访问当前工作区文件，不写宿主机绝对路径
- Agent 写入的脚本、用户上传的数据和已有项目文件可以直接被容器读取
- 容器生成的结果、报告、图表和中间文件会直接回到工作区，前端和后续 Agent 可以继续使用
- 容器删除或替换后，工作区里的产物仍然保留

使用边界：
- 容器登记由工作区容器资源接口或前端"沙盒策略 -> Docker 沙盒"管理
- 当前工具面没有独立 `ContainerResource` Agent 工具时，不要调用 `RuntimeEnvironment` 登记 Docker
- 已知容器 ID 或名称后，用 `Shell` 的 `container` 参数执行命令
- 容器默认从镜像和容器内安装获得运行环境
- 工作区根目录挂载到容器内 `/workspace`，用于共享代码、数据和产物
- 工作区 `.env/` 是 AIASys 管理的宿主机 UV 运行材料目录，容器命令不要依赖其中的 `.venv` 或 Python 可执行文件
- 工作区环境变量会按运行时注入容器，适合传递 API Key、代理、数据库连接串和任务参数

容器内缺依赖时，优先使用镜像本身的包管理方式。例如在容器内运行 `pip install`、`uv sync`、`apt-get`、`conda`，或提醒用户换一个包含依赖的镜像。不要把宿主机 `.env/.venv` 当作容器依赖来源。

示例：

```json
{
  "command": "python scripts/experiment.py",
  "container": "aiasys-task-env",
  "timeout": 300
}
```

### 失败处理

- UV 安装失败：检查包名、版本约束、Python 版本和网络；必要时降级版本或改用 Docker
- Docker daemon 不可用：向用户说明当前机器无法使用 Docker，回退 UV 或本地脚本
- 未知容器 ID 或名称：先让用户在 Docker 沙盒面板登记或确认容器名称，再执行 Shell
- Notebook 需要 Docker：当前不支持 Docker 持久 Notebook kernel。把代码保存为脚本，在 Docker 中脚本式运行

---

## 五、环境变量管理

环境变量和 UV 运行环境是两类配置，不要混在一起处理。

| 配置 | 存放位置 | 用途 | 管理入口 |
|------|----------|------|----------|
| UV 运行环境物料 | `.env/` | Python 版本、依赖声明、锁文件、虚拟环境 | `RuntimeEnvironment` |
| 工作区环境变量 | `.workspace/workspace.json` 的 `runtime_binding.env_vars` | API key、token、服务地址等运行时变量 | `SetEnvVar` / `DeleteEnvVar` |
| 全局环境变量 | 用户全局配置 | 跨工作区默认变量，工作区变量优先覆盖 | 前端全局设置或 `/global-env-vars` API |

Agent 执行时会合并全局环境变量和工作区环境变量，工作区同名变量优先。修改变量后，一般从下一次执行或重建运行态开始稳定生效。

### 安全

- 读取时自动检测敏感变量名（含 KEY/SECRET/TOKEN/PASSWORD 等），自动脱敏显示
- 设置/删除仅影响当前工作区，不修改系统进程环境变量
- 不要把真实密钥写入 `.env/pyproject.toml`、脚本源码、Notebook 或 Markdown 报告
- `.env.example` 只适合作为示例模板，不是 AIASys 工作区环境变量事实源

### 使用方式

优先直接调用 Agent 工具。脚本入口主要用于诊断或手工修复。运行脚本前必须有 `AIASYS_WORKSPACE_ROOT`。

```bash
# 查看某个环境变量
python3 skills/builtin/aiasys-platform-skill/scripts/env_vars.py get --name MY_VAR

# 设置环境变量
python3 skills/builtin/aiasys-platform-skill/scripts/env_vars.py set --name MY_VAR --value "hello"

# 删除环境变量
python3 skills/builtin/aiasys-platform-skill/scripts/env_vars.py delete --name MY_VAR
```

读取敏感变量时，脚本会返回脱敏值。需要验证变量是否真的可用，应该运行目标工具或最小 API 探测，不要要求系统回显明文。

---

## 六、多维数据表

在工作区中创建和管理结构化多维数据表，以 SQLite 存储，支持文本、数字、日期、单选、多选等字段类型。

运行时如果已经有 Agent 工具面，优先使用 `CreateDataTable`、`ReadDataTableSchema`、`ReadDataTableRecords`、`InsertDataTableRecords`、`UpdateDataTableRecord`、`DeleteDataTableRecord`、`AddDataTableColumn`、`UpdateDataTableColumn`、`RemoveDataTableColumn`。下面的脚本主要用于 skill 工作流、命令行批处理和工具面不可用时的兜底。

### 字段类型

| 类型 | 说明 |
|------|------|
| `text` | 文本 |
| `number` | 数字 |
| `date` | 日期 |
| `single_select` | 单选 |
| `multi_select` | 多选 |
| `checkbox` | 勾选框 |
| `file` | 文件 |
| `url` | 链接 |

### 使用方式

```bash
# 创建数据表
python3 skills/builtin/aiasys-platform-skill/scripts/datatable.py create \
  --name "销售跟踪" --id sales-tracking \
  --columns '[{"name":"客户","type":"text"},{"name":"金额","type":"number"}]'

# 列出所有数据表
python3 skills/builtin/aiasys-platform-skill/scripts/datatable.py list

# 查看 schema
python3 skills/builtin/aiasys-platform-skill/scripts/datatable.py query \
  --file sales-tracking.table.db --operation schema

# 查看记录
python3 skills/builtin/aiasys-platform-skill/scripts/datatable.py query \
  --file sales-tracking.table.db --operation records --limit 20

# 插入记录
python3 skills/builtin/aiasys-platform-skill/scripts/datatable.py insert \
  --file sales-tracking.table.db \
  --records '[{"客户":"Acme","金额":50000}]'

# 更新记录
python3 skills/builtin/aiasys-platform-skill/scripts/datatable.py update \
  --file sales-tracking.table.db --record-id <_id> \
  --data '{"金额": 60000}'

# 删除记录
python3 skills/builtin/aiasys-platform-skill/scripts/datatable.py delete \
  --file sales-tracking.table.db --record-id <_id>

# 修改列结构
python3 skills/builtin/aiasys-platform-skill/scripts/datatable.py modify-column \
  --file sales-tracking.table.db --action add \
  --column-name "状态" --column-type single_select \
  --options '["进行中","已完成","已取消"]'
```

---

## 七、Skill 协作方式

AIASys 内置 skill 之间可以组合使用。常见协作模式：

### 竞赛研究场景

```
competition-research-skill → 创建项目结构
    ↓
competition-runtime-prep-skill → 准备或验证 env_id（按需）
    ↓
arxiv-search-skill → 下载 PDF
    ↓
pymupdf4llm-pdf-to-markdown-skill → 转 Markdown
    ↓
competition-research-skill → 摄入知识图谱
    ↓
competition-research-skill → 单分支 preflight + 实验规划
    ↓
Auto Task (continuous) → 串行循环执行
```

需要并行探索时：

```text
competition-runtime-prep-skill → 准备多个 env_id
    ↓
competition-parallel-research-skill → 规划 lane / session / AutoTask
    ↓
competition-research-skill → 每条 lane 内串行实验
    ↓
competition-parallel-research-skill → 汇总结果和主线建议
```

### 文献翻译场景

```
arxiv-search-skill → 搜论文 + 下载 PDF
    ↓
pdf-translate-skill → 保版式翻译
    ↓
paddleocr-skill → OCR 提取（扫描版 PDF）
    ↓
pymupdf4llm-pdf-to-markdown-skill → 转 Markdown 供阅读
```

### 数据管理场景

```
aiasys-platform-skill (datatable) → 创建多维数据表
    ↓
DatabaseQuery / Notebook → 分析数据
    ↓
aiasys-platform-skill (env vars) → 配置 API Key
    ↓
aiasys-platform-skill (runtime) → 安装分析依赖
```

### 发现和调用其他 Skill

Agent 不需要记住所有 skill 的名称，通过工具动态发现：

1. `ListSkills` — 列出当前工作区已启用的 skill
2. `SearchStoreSkills` — 搜索全局仓库（builtin + store）中的 skill
3. `LoadSkill` — 读取指定 skill 的 SKILL.md，了解具体用法
4. `EnableSkill` / `DisableSkill` — 启用或禁用 skill

建议：不确定某个能力由哪个 skill 提供时，先用 `SearchStoreSkills` 搜索关键词，再用 `LoadSkill` 读取详细说明。

---

## 八、知识图谱与知识库

AIASys 提供两种知识管理方式：知识图谱（GraphRAG）和知识库（RAG）。两者定位不同，不要混淆。

| 维度 | 知识图谱 | 知识库 |
|------|---------|--------|
| 核心能力 | 实体识别、关系抽取、社区发现 | 语义检索、文档分块、向量匹配 |
| 查询方式 | 实体搜索、关系遍历、社区报告 | 自然语言语义查询 |
| 输出 | 实体详情、关系网络、结构化摘要 | 相关文档片段 |
| 适用场景 | 论文关系、概念网络、竞赛方法追踪 | 文档问答、资料检索、长文档阅读 |
| 存储 | SQLite + 社区分层索引 | SQLite + 向量索引 |

### 挂载机制

知识图谱和知识库通过任务资源上下文挂载到当前 session。Agent 在调用查询工具时，默认优先使用已挂载的资源。如果当前任务没有挂载，工具会回退到列出当前用户的全部资源。

用户可以在前端"任务资源"面板中挂载/卸载知识图谱和知识库。Agent 不需要手动挂载，只需要调用查询工具即可。

### 知识图谱工作流

**1. 列出已挂载/可用的知识图谱**

```json
{
  "scope": "mounted"
}
```

返回：id、entity_count、relation_count、document_count

**2. 搜索实体**

```json
{
  "query": "transformer",
  "graph_id": "<图谱ID>",
  "entity_type": "concept",
  "top_k": 10
}
```

**3. 查看实体详情**

```json
{
  "entity_name": "Transformer",
  "graph_id": "<图谱ID>"
}
```

返回：实体属性、所属社区、关联文档、关键描述

**4. 查询实体关系**

```json
{
  "base_id": "<图谱ID>",
  "entity_name": "Transformer",
  "direction": "both",
  "limit": 20
}
```

**5. 生成社区报告**

```json
{
  "base_id": "<图谱ID>",
  "level": 0
}
```

社区报告按层级组织，level 0 是最顶层社区摘要。适合快速了解图谱的整体结构。

**6. 上传文档到知识图谱**

```json
{
  "base_id": "<图谱ID>",
  "files": ["/workspace/papers/paper1.md", "/workspace/papers/paper2.pdf"],
  "extraction_mode": "enhanced",
  "resolve_entities": true
}
```

extraction_mode 可选：auto / basic / enhanced / docling。enhanced 抽取质量更高但耗时更长。

### 知识库工作流

**1. 列出已挂载/可用的知识库**

```json
{
  "scope": "mounted"
}
```

**2. 创建知识库**

```json
{
  "name": "竞赛论文库",
  "description": "电力价格预测竞赛相关论文",
  "kind": "document"
}
```

返回知识库 ID，后续操作都需要这个 ID。

**3. 上传文档到知识库**

```json
{
  "base_id": "<知识库ID>",
  "files": ["/workspace/papers/paper1.md", "/global/references/survey.pdf"]
}
```

支持 `/workspace/`、`/session/`、`/global/` 前缀的路径。

**4. 查询知识库**

```json
{
  "query": "注意力机制在时序预测中的应用",
  "knowledge_base_id": "<知识库ID>",
  "top_k": 5
}
```

返回最相关的文档片段，包含来源文档和相似度分数。

**5. 删除文档**

```json
{
  "base_id": "<知识库ID>",
  "doc_ids": ["doc_001", "doc_002"]
}
```

**6. 删除知识库**

```json
{
  "base_id": "<知识库ID>"
}
```

删除前应先向用户确认，因为会同时删除该库下的所有文档和分块数据。

### 典型使用场景

**竞赛论文追踪（知识图谱）**

```
competition-research-skill (init) → 初始化项目，创建知识图谱 .db
    ↓
arXiv 搜索 + 下载 PDF → 获取论文
    ↓
pymupdf4llm 转 Markdown → 标准化格式
    ↓
UploadDocumentsToGraph → 论文摄入图谱，抽取实体关系
    ↓
GraphEntitySearch / QueryEntityRelations → 追踪方法演进脉络
    ↓
competition-research-skill (experiment) → 基于图谱发现的方法设计实验
```

**长文档阅读辅助（知识库）**

```
上传 PDF/MD 到知识库 → 向量索引
    ↓
KnowledgeQuery → 针对具体问题语义检索相关片段
    ↓
Notebook 中复现/验证 → 把检索到的方法落地
```

**项目资料管理（知识库 + 知识图谱双轨）**

```
资料文档 → 知识库（便于问答检索）
    ↓
核心论文 + 实验记录 → 知识图谱（便于关系追踪和社区发现）
```

### 选择建议

- 用户问"这篇论文讲了什么方法"→ 知识库查询
- 用户问"这些方法之间有什么关系"→ 知识图谱实体搜索 + 关系查询
- 用户说"把这几篇论文建一个知识网络"→ 知识图谱上传 + 社区报告
- 用户说"帮我找和当前问题相关的资料"→ 知识库语义检索

## 相关 Skill

| Skill | 用途 |
|-------|------|
| `competition-runtime-prep-skill` | 竞赛运行环境准备、依赖安装、GPU 和 runner smoke |
| `competition-research-skill` | 单分支、单环境、串行竞赛实验闭环 |
| `competition-parallel-research-skill` | 多分支、多环境、多 AutoTask lane 编排 |
| `skill-creator-skill` | Skill 开发工作台 |
| `uv-runtime-skill` | 当前工作区 UV/Python 运行环境 |
| `arxiv-search-skill` | arXiv 论文搜索与下载 |
| `pymupdf4llm-pdf-to-markdown-skill` | PDF 转 Markdown |
| `pdf-translate-skill` | PDF 保版式翻译 |
| `paddleocr-skill` | OCR 文档提取 |
| `aiasys-canvas-skill` | JSON Canvas 编辑 |
