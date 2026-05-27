# AIASys

## 开发入口

- 后端主线：`apps/backend/app/`
- 前端主线：`apps/web/src/`
- 视觉设计基线：`DESIGN.md`
- 协作文档与技能：`.agents/`

## 项目结构

```
AIASys/
├── apps/
│   ├── backend/          FastAPI 后端服务
│   │   ├── app/          业务代码主入口
│   │   ├── skills/       系统内置 skill 源（builtin/ 子目录）
│   │   ├── templates/    系统内置工作区模板
│   │   └── tests/        后端测试
│   ├── web/              React 19 + Vite 前端
│   │   ├── src/          源码主入口
│   │   │   ├── components/   React 组件
│   │   │   ├── pages/        页面级组件
│   │   │   ├── lib/          API 层与工具函数
│   │   │   ├── hooks/        自定义 Hook
│   │   │   ├── contexts/     React Context
│   │   │   ├── config/       配置文件
│   │   │   ├── types/        TypeScript 类型
│   │   │   └── utils/        通用工具
│   │   ├── public/       静态资源
│   │   └── e2e/          Playwright E2E 测试
│   └── desktop/          Electron 桌面壳（复用 web/）
│       ├── src/          主进程 / preload / 服务管理
│       ├── scripts/      启动与打包准备脚本
│       └── dist/         Electron builder 输出目录（已 gitignore）
├── design-draft/         设计产物与临时归档（已 gitignore）
│   ├── design/           正式设计文档
│   └── archive/          验证截图、测试日志、临时脚本
├── docs/                 对外公开文档（快速启动、changelog）
├── images/               README / docs 正式配图
├── infra/                部署与 Docker 配置
├── scripts/              项目级工具脚本
│   ├── design/           设计基线校验与 CSS 导出
│   ├── dev/              开发环境脚本（dev.sh、生命周期测试等）
│   └── security/         安全扫描脚本
└── .agents/              AI 协作技能与任务会话
```

## 常用命令

后端启动：

```bash
cd apps/backend
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 13001
```

前端启动：

```bash
cd apps/web
npm run dev -- --port 13000 --host 0.0.0.0
```

前端构建：

```bash
cd apps/web
npm run build
```

视觉设计基线校验：

```bash
./dev.sh design-lint
```

生成 Tailwind 4 CSS 变量草案：

```bash
./dev.sh design-export-css
```

生成当前运行时变量候选主题：

```bash
./dev.sh design-export-runtime
```

后端测试：

```bash
cd apps/backend
.venv/bin/python -m pytest <target>
```

## 项目语义

- 工作区是一等对象
- 每个用户有一个全局工作区 `global_workspace/`，路径为 `workspaces/{user_id}/global_workspace/`，存放跨工作区共享的资源和配置。普通工作区继承全局工作区的默认配置，也可以单独覆盖或禁用某项配置。Agent 文件工具通过 `/global/` 访问全局工作区内容，`/workspace/` 访问当前工作区内容，两者是独立命名空间。当前工作区和全局工作区是默认上下文，不是访问上限；在任务明确、路径明确、操作可记录的前提下，允许 Agent 跨工作区执行任务
- 工作区配置统一放在 `.aiasys/` 目录下，替代分散的 `config/` 目录。全局工作区和普通工作区都遵循这个约定。`.aiasys/` 下的目录结构：
  - `.aiasys/memory/` — 工作区记忆
  - `.aiasys/file-history/` — 文件版本历史
  - `.aiasys/skills/` — 已安装的 skill 副本
  - `.aiasys/templates/` — 用户自定义模板
  - `.aiasys/workspace/` — 工作区元数据（workspace.json、conversations.json、auto_tasks 等）
  - `.aiasys/session/` — 会话运行时状态（execution journal、subagents、runtime config 等）
  - `.aiasys/graphs/` — 知识图谱数据
- 文件历史（`.aiasys/file-history/`）每个文件默认保留最近 50 个版本，单文件上限 2MB，Agent 编辑和人类编辑共享同一个版本计数池，不做特殊合并或隔离。设计上把 Agent 视为普通编辑者，不单独维护 Agent 专用历史通道
- `session_id` 对应会话目录。会话目录只保存会话自己的信息、配置覆盖和运行相关内容（存放在 `.aiasys/session/` 子目录下），不管理工作区配置本身。配置优先级为：会话配置 > 当前工作区配置 > 全局工作区配置
- 产品文案优先使用“会话”。历史旧称按会话理解，后续改造时逐步收口命名
- 右侧边栏默认承接当前任务工作区，不默认承接执行流
- 任务级 Agent / 能力 / 运行环境通过会话配置统一管理
- 工具分为默认加载工具和默认不加载工具。默认不加载工具通过搜索查看和按需加载，用来支持动态工具加载。默认加载工具可以开启或关闭，但这会改变提示词里的工具列表，影响 prompt cache，界面和文档必须明确提醒
- 子 Agent 默认和主控共用当前工作区、全局工作区和会话上下文，不单独创建工作区。子 Agent 的指令由主控派发，当前阶段不做子 Agent 执行审批
- 专家角色是可选择的子 Agent。专家角色可以通过提示词和工具列表表达能力边界，但不要把它做成过重的权限系统。当前阶段以提示词约束为主，工具限制作为辅助配置
- `permissions` 字段当前仅作前端信息展示，不接入运行时权限拦截。敏感操作的管控通过工具级别 denylist、默认不加载机制和提示词约束实现
- AutoTask 是当前主线的自动化任务对象，统一承接原 Goal 连续推进和 Scheduler 时间触发。新实现不要恢复 `goal_tool`、`GoalPanel`、`/api/scheduler` 或独立 Goal/Scheduler 面板
- 会话级预算属于当前会话元数据，限制普通对话和 AutoTask 的累计 token 消耗；上下文占用只表示当前轮提示词大约占用多少模型窗口。文档和界面不要把这两者混成一个概念
- Claw 是工作区/会话的外部通信通道，沿用同一套 Soul、项目档案、工作区记忆和会话上下文。它只额外提供微信/IM 连接、消息收发、附件导入和远程确认能力，不是独立工作区。Agent 工具目录中不提供 Claw 工具，这是设计决策，不是功能缺失
- AIASys 与外部 IM 频道之间不做强一致性同步。外部频道只是信息发送渠道，两边的通信上下文、节奏和参与者完全不同，不需要也不应该保证内容完全一致。前端不保留手动补发/推送入口

## Memory 子系统设计边界

AIASys Memory 对标 Codex CLI 纯文本 Markdown 设计，不维护结构化 entry 对象。

**要做的：**

- 纯文本 Markdown 存储：用户默认全局工作区层 `MEMORY.md` / `memory_summary.md` / `raw_memories.md` / `rollout_summaries/`，工作区层 `workspace_memory.md`
- 两层作用域：用户默认全局工作区层（scope key 为 `user_default_global_workspace`，路径 `global_workspace/.aiasys/.memory/`）+ 工作区层（`{workspace}/.aiasys/memory/`）
- 两阶段 Pipeline：Stage 1 从 execution journal 提炼记忆，Stage 2 把 Stage 1 产物写入 Markdown。容量健康时可以追加，达到整理条件时由 consolidation 重写 `MEMORY.md` / `memory_summary.md`。实现上不能让硬容量限制挡住 consolidation 入口
- SQLite `state.db` 管理 Stage 1/2 的 job 租约、并发控制、合并水印
- `MemorySnapshotRecord` + `snapshot_hash` 检测 memory 版本漂移，触发会话重建
- Agent 通过 `ReadFile`（`/global/`、`/workspace/` 前缀）和 `Shell` 按需读取 memory 文件。`Memory` 写入工具只用于用户明确要求记住、用户纠正长期偏好、或需要持久化的稳定规则，不用于记录普通任务临时发现

**安全扫描边界（做什么、不做什么）：**

- **做的**：在 `MemoryStore.write_text()` 入口检测威胁内容并拒绝写入。覆盖 4 类威胁：invisible Unicode（10 种零宽字符/方向覆盖符）、prompt injection（7 种模式，如 ignore instructions / role hijack）、credential exfiltration（4 种模式，如 curl with $SECRET）、persistence attacks（5 种模式，如 authorized_keys / crontab）。采用 Hermes 阻止模式（拒绝写入），不是 Codex 脱敏模式（替换后继续）。
- **不做的**：不对已写入文件做周期性回溯扫描；不对用户手动编辑的内容做拦截（只拦截通过 API/tool 的写入路径）；不做 secret redaction（检测到即拒绝，不替换为 [REDACTED]）。

**实现细节说明（防止审查误报）：**

- SQLite 使用 `isolation_level=None` + 手动 `BEGIN IMMEDIATE`/`COMMIT`/`ROLLBACK` 管理事务，配合 WAL 模式，是设计意图，不是并发控制缺陷
- `MemoryResolver` 缓存按 `user_id:session_id` 存储，session cleanup 时通过 `invalidate_resolver_cache()` 自动失效，不会泄漏。任何通过 API、Agent tool、版本恢复等路径改变 memory 文件的写入，都必须同步失效 resolver 缓存或更新运行态状态，保证 next-run-only 状态可信
- Stage 2 追加通过 `claim_stage2_job()` 租约机制串行执行，单进程内不存在并发写竞态
- 版本管理（`memory_versions` 表）支持 `scope_key` 参数，workspace scope 和 `user_default_global_workspace` 共享同一套版本表。旧 `user_default` 只作为兼容输入规范化到 `user_default_global_workspace`，不能继续作为目标语义。restore API 支持 workspace scope，但恢复写回也必须走 `MemoryStore.write_text()` 或等价安全边界，不能直接绕过安全扫描和容量限制
- 内部镜像文件（`raw_memories.md`、`rollout_summaries/`）是系统内部生成，可跳过 `MemoryStore.write_text()` 安全扫描路径。consolidation 写回 `MEMORY.md` / `memory_summary.md` 必须走 `MemoryStore.write_text()`，因为它们会进入 Agent 可读 memory 主链路

**不要做的：**

- consolidation 由 LLM 主动重写，非纯追加。低信号内容会被清理。agent 或用户需要精细整理时，可通过 memory 工具或手动编辑。
- 不做结构化 entry/YAML frontmatter：删除后的 `MemoryEntry`、`MemoryStatus`、`MemoryCategory` 等模型不再恢复
- 不做向后兼容：0-1 阶段 snapshot 格式、文件布局直接替换，不保留旧数据解析逻辑

## 产品定位与技术约束

### 核心定位

AIASys 是 AI Agent 工作平台。内核为科研和数据分析场景深度优化，同时通过 MCP 市场和 Skill 市场覆盖通用办公和日常提效场景。

- 目标用户：科研人员、数据分析师、独立开发者、普通办公人群
- 产品形态：桌面应用（Electron）优先，同时支持 Web 界面
- IDE 和代码编辑器属于另一类工具，不在其产品定位之内

### 桌面应用优先

AIASys 的日常使用形态优先推荐桌面版（`apps/desktop/`），基于 Electron 薄壳，复用 `apps/web` 作为 renderer。桌面版提供原生窗口、系统托盘、本地端口自动管理。Web 版适合临时访问和远程使用场景。

### 移动端不处理

当前阶段前端不做手机移动端适配。布局、交互、断点均以桌面端（含平板横屏）为目标视口。不针对小屏手机（<768px）做响应式改造、触摸优化或布局重排。后续若需移动端支持，另行规划而非在现有代码中逐步兼容。

新增功能需要同时考虑桌面版和 Web 版的兼容性。桌面版的 packaged 模式会将 backend 运行态目录外置到用户目录（`~/.config/aiasys-desktop/backend-runtime/`），而非写回包内。

### 三端支持要求

AIASys 需要支持 Windows、macOS、Linux 三端。涉及桌面应用、本地路径、文件系统、进程启动、打包脚本、浏览器验证和文档命令时，都要按三端目标检查，不能只按当前开发机环境写死。

如果实现或验证中发现某个平台不支持，先把具体不支持点、复现命令、错误信息和影响范围告诉用户，再继续决定是否调整方案。不能把 Linux/WSL 下能跑等同于 Windows 或 macOS 已经可用。

### 不基于 VS Code 进行二次开发

仓库中的 VS Code 及 Copilot 扩展源码（`design-draft/archive/06-docs-and-references/reference_frameworks/`）**仅供架构参考**，不得作为二次开发底座。原因如下：

1. **架构不匹配**：VS Code 是 298 万行的 IDE（自定义非 React UI 框架），AIASys 的核心是 Agent 工作流与工作区语义，两者在骨架层面没有映射关系
2. **改造不可行**：VS Code Jupyter 扩展核心约 15 万行，Copilot 扩展约 67 万行。Cursor、Trae 能 fork VS Code，原因是它们本身就是 IDE。AIASys 的定位与此不同。
3. **定位偏离**：以 VS Code 为底座会把产品重心拉向代码编辑和扩展生态，与 Agent 任务推进的定位冲突

编辑器需要升级时，在现有 React 架构内替换为 Monaco Editor（独立组件）。不要动摇 React + FastAPI 的整体骨架。

## 协作规则

- **合并优于追加，删除优于保留**。发现重复或相似内容时先合并，不要让文档线性膨胀；过时、失效、不再适用的内容直接删除，不要保留历史痕迹。这条原则适用于规则文件、技术文档、代码注释等所有协作产物。
- **边界决策必须落进规范**。在协作过程中形成的硬性边界（一定要做的、绝对不要做的、某个模块的专属约束），必须写进对应的 `AGENTS.md` 或 `design-draft/design/` 文档，不能停留在口头约定。目的是让后续 AI 在打开仓库的第一时间就能读到这些约束，不需要用户反复提醒。
- **0-1 阶段不向后兼容，优先清理**。AIASys 目前处于 0-1 开发阶段，不要为旧数据或旧接口写兼容代码。设计迭代时直接替换旧实现，旧工作区数据和测试产物统一清理。向后兼容是 1-N 阶段才需要考虑的事。
- **区分"遗留代码"与"来不及集成功能"**。Agent 做代码清理时，不能仅凭"当前无引用"就判定为废弃。如果一个模块实现完整、属于产品功能链的自然环节（如模型定义、工具类、注册表方法），只是暂时未接入调用方，应视为"来不及集成"的半成品，不要删除。真正的遗留代码特征是：(1) 有明确的废弃标记或注释；(2) 属于已被替换的旧实现且调用方已迁移；(3) 有代码质量问题（如冗余逻辑、永远为真的条件）。清理前若无法判定，先向用户确认，不要擅自删除。
- **新功能实施前必须做可行性评估**。在编写任何代码之前，先完成技术栈适配性分析、依赖评估和风险识别，结果写入 `design-draft/design/design-thinking/`。评估至少覆盖：(1) 当前技术栈能否支撑；(2) 是否有现有框架/产品的成熟方案可参照，以及参照对象的真实能力边界；(3) 新增的复杂度是否与收益匹配；(4) 有无更简单的替代方案。评估通过后才能进入设计阶段。本次扩展系统的经验：Python 底座做 VSCode 级别的扩展隔离在技术栈层面不可行，如果先做评估不会走这条路。
- **架构层面发现重复、断裂或不一致时，选择彻底统一的最佳实践，不做折中**。如果系统存在两套并行实现（如两套 API、两套组件管理同一类资源），评估后应走统一架构路线：统一数据模型、统一 API 层、统一前端组件。0-1 阶段优先清理断裂，不保留"临时兼容"或"渐进迁移"的过渡代码。边界决策写入 `design-draft/design/design-thinking/` 留档。
- 优先阅读 `.agents/skills/` 下对应技能，再动代码
- 涉及前端界面、视觉风格、布局骨架、组件外观时，先阅读 `DESIGN.md`，再结合 `aiasys-system-design` 和 `frontend-pattern` 执行
- **预览面板右上角统一使用 `CanvasActionMenu`（三个点图标）**，不要放"关闭标签"文字按钮。Tab 页本身有叉号可以关闭，预览组件内部不需要再提供关闭标签。已有参考实现：`GraphPreviewPanel`、`DataTablePreviewPanel`
- 对话栏顶部的上下文占用和预算入口统一走 `TokenUsageBar`。预算设置写入 session `metadata.json` 的 `budget`，不要在 Goal、AutoTask 或模型配置里另建一套 token 预算字段
- 自动化任务入口统一走 `WorkspaceAutoTaskPanel` 和 `/api/auto-tasks`。连续推进使用 `continuous` 触发类型、绑定会话和 `auto_task_signal` 停止信号；单次、周期、固定时间触发也属于 AutoTask
- `DESIGN.md` 是 agent 和设计审查使用的视觉基线，接入运行时样式前需要专用适配，不直接覆盖 `apps/web/src/index.css`
- 复杂任务同步维护 `.agents/task-sessions/`
- 不把内部注释、迁移说明、架构解释直接渲染到用户界面
- 不要依赖旧 agent runtime 的实现细节作为当前主线依据
- 外部参考项目只作为阅读、对比和移植依据。AIASys 运行时代码不得默认 `import`、扫描、加载或依赖仓库外参考项目路径（例如 `/home/ke/projects/easy-agents/参考资料/...`），也不得靠本机目录存在让功能在当前机器刚好可用。需要复用参考实现时，必须把必要代码复制或移植到 AIASys 仓库内，纳入依赖声明、测试和打包边界。
- commit message 默认优先使用中文，只有用户明确要求英文时才改用英文

### 多终端 AI 协作开发约束

- 前后端 dev server 默认按用户本机常驻运行习惯保留，不要在验证完成后主动关闭。只有用户明确要求“测试完成就关闭”“临时启动”等一次性验证语义时，才在验证后关闭。需要浏览器验证时先复用当前端口上的服务；如果服务未运行，再手动启动并在汇报中说明。
- **验证是必做项，不是可选项**。任何涉及前端界面、交互行为、API 调用路径的修改，都必须在真实浏览器里完成端到端验证后才算完成。不要询问用户"是否需要验证"，直接执行。
- 涉及前端界面布局、视觉骨架、容器高度/滚动行为的修改，必须在真实浏览器里截图验证后才算完成。仅靠代码审查或本地构建通过不能作为验收依据。
- 遇到构建失败或运行时报错先暂停，确认这个报错是否由自己当前修改引起。
  - 是自己引起的，直接修复。
  - 不是自己引起的，向用户报告报错内容和位置，等待负责该部分的 AI 完成调试后再继续，不要盲目替别人排错。
- **改造必须一次性改彻底**。除非用户明确要求分阶段完成，否则设计方案和代码实现要一步到位，不要写"先做这个、后续再做那个"的分阶段计划。文档、代码、测试同步交付，不留尾巴。
- **前端截图与验证证据的存放路径**：browser smoke、UI 回归验证、交互验收等过程截图，统一放到 `design-draft/archive/artifacts/`。`design-draft/` 本身已被 gitignore，这些截图不会进入版本控制。需要提交到仓库的正式展示图（如 README、docs 配图）才放 `images/` 下的对应子目录。

### LLM 编码最佳实践

以下原则源自 Andrej Karpathy 对 LLM 编码陷阱的观察，用于指导 AI 协作开发行为：

#### 1. Think Before Coding（先思考再编码）

**不要假设，不要隐藏困惑。明确表述假设，呈现权衡取舍。**

- 不确定时主动提问，不要默默选择一种解释继续执行
- 存在歧义时展示多种可能的方案
- 如果存在更简单的做法，直接提出来
- 遇到不清楚的地方，明确指出哪里困惑并请求澄清

#### 2. Simplicity First（简单优先）

**用最少代码解决问题，不做任何未明确要求的额外设计。**

- 不添加未要求的功能、抽象层或"未来可能需要"的灵活性
- 不处理不可能发生的场景（按系统约束和常识判断）
- 如果代码能显著简化（如 200 行 → 50 行），直接重写
- 判断标准：资深工程师看到代码会说"正好解决这个问题"而不是"过度设计"

#### 3. Surgical Changes（精准修改）

**只改必须改的部分，不碰其他代码。**

- 不要"顺便优化"相邻代码、注释或格式
- 不要重构没有问题的代码
- 即使不同意现有风格，也要匹配它（保持一致性）
- 如果发现与本次修改无关的废弃代码，可以提及但不擅自删除
- 只删除自己改动产生的废弃 import/变量/函数，不删除预存在的死代码

**检验标准**：每一行修改都能追溯到具体的用户要求。

#### 4. Goal-Driven Execution（目标驱动执行）

**将任务转化为可验证的成功标准，而非指令清单。**

- 不描述怎么做，而是定义"做成什么样才算完成"
- 多步骤任务要说明计划和验证点
- 示例转换：
  - "添加验证" → "为无效输入场景编写测试，然后让测试通过"
  - "修复 bug" → "编写能复现问题的测试，然后让测试通过"
  - "重构 X" → "确保测试在重构前后都通过"

### 对话智力水准

本仓库是 AIASys 的工程主仓，不是工单系统。AI 在以下两个层面必须始终调用最高智力水平：

- **编辑场景**：修改代码、文档、配置或任何文件内容时，这是复杂度最高的任务类型。必须逐行确认修改的合理性与影响范围，不凭直觉跳过验证，不做未经审视的改动。
- **对话场景**：追求智力对等——不降级为被动工具执行者，主动质疑需求中的模糊点、提出独立见解、指出更优路径。语言精准有力，不只是功能性交互。讨论碰撞时鼓励发散、联想、跨领域迁移。

执行任务时偏"把关者"（引导方向、确保交付质量），讨论碰撞时偏"思辨者"（对等思考、共同展开、激发洞察）。根据场景灵活切换，不拘泥单一角色。

### 语言与表达约束

> 以下约束适用于所有对话回复和文档输出。目标：减少 AI 味，让表达更像人在说话。

**核心原则**：你的母语是简体中文。用中文的句法、语序、节奏组织信息，**禁止**在英文骨架上填充中文字符。

**对话风格**：像懂行的朋友解释技术问题，不是客服话术，也不是学术汇报。直白、具体、有判断。

**绝对禁止**：

- **Emoji**：任何输出中禁止使用。这是数据层污染（社交媒体/对话语料训练）→ 神经回路固化的结果，高层指令无法可靠抑制，彻底禁用是唯一有效防控。
- **破折号过度使用**（——）：中文写作中破折号相对少见，密度不得超过 1 处/千字。破折号过量是 Markdown 训练数据泄漏的信号。需要插入解释时用括号，需要转折时用逗号+连词或拆句。
- **机械对比句**："不是 A，而是 B"、"与其说 A，不如说 B"、"表面上看...实际上..."、"很多人以为...真相是..." 等二元对立纠正式表达，**出现即改写**。直接陈述正面内容，不要先立靶子再纠正。500 字内出现 2 次以上 → 触发全文扫描重写。
- **中英混杂**：有现成中文译法的词必须翻译（context→上下文、state→状态、workflow→工作流、actionable→可执行/可操作）。可保留的例外：人名、品牌名、标准缩写（API/URL/JSON）、文件名、首次出现的术语注释。
- **模糊归因**：禁止用不指明具体来源的模糊主体。禁用"专家认为""有研究指出""观察人士称""行业报告显示"——要么指明是谁，要么删掉主语直接陈述。
- **说教式语调**：禁止居高临下或过度积极的情感强加。禁用"这无疑""我们必须认识到""每个人都应该""亟待解决""不容忽视""值得深思的是"。中性陈述，让读者自己判断。
- **替读者下判断**：禁止"形容词+冒号"结构。禁用"逻辑很清晰：""结论很明确：""值得注意的是："。直接陈述，不要替读者做判断。

**表达约束**：

- 用直白词语，不用成语和营销词
- 用词要简单、准确、专业。不要为了显得高级而堆术语、造概念、换花哨说法；能用普通话讲清楚，就用普通话讲清楚。必要的专业词可以保留，但首次出现要用一句人话解释。
- 加粗极少（≤5 处/千字），严禁连续加粗或通篇加粗
- 标点尽量少，句子要清楚
- 不用生活化比喻，不用口头禅式动作词（"接住"、"锋利"、"hold 住"）
- **英文骨架泄漏防控**：中文写作不用英语动词的隐喻直译。禁用"接住这个需求""击穿假设""框架不崩""逻辑站不住""捏合观点"；改用"满足需求""推翻假设""稳定""逻辑不自洽""整合观点"。
- **回避基本系词**：能用"是""有"时不用花哨替代。禁用"充当""拥有""以……为特色""展现出""呈现出"；改用"是""有""用"。
- **抽象名词主语+评价词收尾**：禁止让抽象概念充当主语后句尾跟评价词。禁用"……的本质远比……复杂""……的自洽性令人担忧"；改用具体主语+具体动作，如"实际工期比估算长了40%"。
- 标题优先用大白话，专业术语放到正文里解释

**结构约束**：

- **对话回复**：默认用自然段。讨论型回复 1-3 段主线即可，不要默认分点。只有步骤流程、检查清单、对照呈现时才用列表。
- **文档输出**：按需结构，不要过度模板化。禁止每个段落结尾都收束金句，禁止强行凑三组（"A、B 和 C"），禁止段段开头都是"此外"/"值得注意的是"。
- **输出前强制扫描**：
  1. 机械句扫描：全文搜索"不是"/"并非"/"表面上"/"很多人以为"，按替换表强制改写
  2. 标点泄漏扫描：统计破折号数量，超标则替换为括号或逗号
  3. 套话扫描：全文搜索"众所周知""随着……发展""在当今社会""综上所述""未来必将"，直接删除或改写为具体事实
  4. 模糊归因扫描：全文搜索"专家认为""有研究指出""行业报告显示"，补具体来源或删主语
  5. 说教语调扫描：全文搜索"这无疑""我们必须认识到""不容忽视"，改为中性陈述

### README 与对外文档约束

README 是项目的公开门面，写给第一次见到这个项目的人看。以下约束是对外文档的额外规则，叠加在语言表达约束之上。

**READMe 例外**：README 可以使用 Emoji（仅限功能说明和标题装饰），其余文档一律禁止 Emoji。README 的目的是好看、好读、有吸引力。

**内容边界**：
- 不引用 `design-draft/design/` 目录下的文档（design-draft/design 是内部设计真相源，不对外）
- `docs/` 只放快速启动指南和 changelog，不放设计文档和 AI 内部协作内容
- 不解释"为什么不做 X"（如为什么不基于 VS Code），读者不需要知道没选什么
- 文档链接只指到 `docs/` 下的公开文档、`CONTRIBUTING.md` 和 `LICENSE`

**语气**：
- 不用"愿景""使命"这类宏大叙事开头，直接说"解决什么问题"
- 不用金句型收尾（"一个任务工作区，持续……推进下去"这类也属于套话收尾）
- 能力描述用具体场景和实际代码行为说话，不用"强大的""完善的""领先的"这类形容词

**事实准确性**：
- 修改 README 前必须先读对应代码，确保描述和实际实现一致
- 技术栈表格、配置说明、命令示例必须可运行、可验证
- 不确定的技术细节宁可少写，不要编造

## 主要技能索引

- 核心开发流程：`todo-orchestration`（Todo 清单设计与静默执行）
- 前端架构：`aiasys-frontend-architecture`（AIASys 专属前端架构与取舍）
- 前端开发：`frontend-pattern`（React 19 + Tailwind 4）
- 前端真实验证：`browser-control`（浏览器控制与截图取证）
- LLM 交互层：`llm-prompt-engineering`（Prompt 模板、多协议 Client、Token 预算、上下文压缩）
- 实时通信：`sse-real-time-communication`（SSE 事件流、多 session 并行、竞态防护）
- Python 运行时：`python-runtime-sandbox`（IPython Kernel、UV 环境、沙盒执行）
- MCP 协议：`mcp-protocol`（配置合并、Client 连接、工具注册桥接）
- 测试策略：`testing-strategy`（pytest 异步测试、Playwright E2E）
- 调试修复：`bug-discovery`（Bug 发现、跟踪、修复完整工作流）
- 代码简化：`code-simplification`
- 安全加固：`security-hardening`
- 性能优化：`performance-optimization`
- 废弃迁移：`deprecation-and-migration`

## 当前主要文档

- 产品需求：`.agents/skills/aiasys-product-requirements/`
- 系统设计：`.agents/skills/aiasys-system-design/`
- 视觉设计基线：`DESIGN.md`
- 任务会话：`.agents/task-sessions/`

## Skill 分层说明

本仓库中有两类 skill，作用和位置完全不同，不要混淆。

### 1. AI 协作开发 Skill（`.agents/skills/`）

这是给**开发 AIASys 系统的 AI**看的协作指南，**不是 AIASys 产品的功能**。

- 用途：前端开发规范、bug 分析、SOP 流程、代码审查等
- 读者：开发 AIASys 系统的 AI Agent
- 管理：由 pkm-hub 统一维护
- 示例：`frontend-pattern`、`bug-analysis`、`todo-orchestration`、`code-review`

**注意**：`.agents/skills/` 下如果出现了 `competition-research-skill`、`arxiv-search-skill` 这类名称，说明是产品功能 skill 的设计文档被错放到了协作 skill 目录，需要移到 `apps/backend/skills/builtin/`。

### 2. AIASys 系统内置 Skill（`apps/backend/skills/builtin/`）

这是 **AIASys 产品本身**的能力扩展，用户在 AIASys 工作平台中实际调用的 skill。

- 用途：数据表操作、PDF 翻译、Canvas 编辑、OCR、竞赛研究等
- 读者：AIASys 终端用户及其 AI Agent
- 管理：随 AIASys 系统部署

命名规则：

- **`aiasys-` 前缀**：依赖 AIASys 系统内部服务或内置对象模型的 skill，如 `aiasys-platform-skill`（平台操作与运行环境管理）、`aiasys-canvas-skill`（AIASys Canvas 对象编辑）。这类 skill 脱离 AIASys 无法独立运行，或不应作为通用外部 skill 分发。
- **无前缀**：通用 skill，通过外部 API 或标准文件格式独立运作，如 `paddleocr-skill`（调用 PaddleOCR API）。

当前系统内置 skill 清单：

| Skill | 类型 | 说明 |
|-------|------|------|
| `paddleocr-skill` | 通用 | PaddleOCR 文档提取 |
| `pdf-translate-skill` | 通用 | PDF 保版式翻译 |
| `aiasys-canvas-skill` | 系统 | AIASys Canvas 对象编辑与 JSON Canvas 校验 |
| `aiasys-platform-skill` | 系统 | 平台概览、Agent 工具目录、AutoTask 配合、运行环境、环境变量、数据表、Skill 协作 |
| `uv-runtime-skill` | 系统 | 当前工作区 UV/Python 运行环境管理，解释 `.env/`、`workspace-default`、依赖安装和环境绑定 |
| `competition-research-skill` | 系统 | 竞赛场景完整工作流（项目初始化、AGENTS.md 维护、文献检索、论文摄入、实验循环） |
| `competition-parallel-research-skill` | 系统 | 竞赛并行研究执行 |
| `competition-runtime-prep-skill` | 系统 | 竞赛运行环境准备 |
| `aiasys-memory-organizer-skill` | 系统 | Memory 整理与 consolidation |
| `skill-creator-skill` | 系统 | Skill 开发工作台（结构、触发测试、description 优化、版本管理、打包部署） |
| `arxiv-search-skill` | 通用 | arXiv 论文搜索与下载 |
| `pymupdf4llm-pdf-to-markdown-skill` | 通用 | PDF 转 Markdown 供 Agent 阅读 |

### 协作 Skill 管理说明

AI 协作开发 Skill 由 pkm-hub 统一管理：

- **开发区**: `pkm-hub/resources/xiaoke-project-skill/aiasys/skill-development/<skill-name>/` — 所有修改先在此迭代
- **正式区**: `pkm-hub/resources/xiaoke-project-skill/aiasys/skills/` — 评测后发布
- **运行时区**: `.agents/skills/` — AI 直接读取的运行时镜像（从 pkm-hub 正式区同步）

修改或创建协作 Skill 需先汇报，同意后方可执行。

## Skill 启用设计哲学

Skill 采用**全局源仓库 + 工作区副本**的两层架构，安装和卸载只在副本层操作：

| 层级 | 路径 | 作用 |
|------|------|------|
| 内置源 | `apps/backend/skills/builtin/{name}/` | 系统预装，不可删除 |
| 用户源 | `apps/backend/skills/store/{name}/` | 外部市场/zip 导入，可从全局仓库删除 |
| 工作区副本 | `{ws}/.aiasys/skills/{name}/` | 安装后实际运行的位置 |
| 全局副本 | `{user}/global_workspace/.aiasys/skills/{name}/` | 全局启用后跨工作区共享 |

**核心原则**：

- **安装** = `enable_skill`：`shutil.copytree` 从源仓库复制到工作区副本
- **卸载** = `disable_skill`：`shutil.rmtree` 删除工作区副本，源仓库不动
- 内置 skill 和外部 skill 的卸载逻辑完全一致，都是删副本
- 卸载后可随时重新安装，因为源始终保留
- 卡片上的"卸载"按钮只对已安装到工作区的 skill 显示，统一调用 `disable_skill`
- skill 变更对运行中会话采用 next-run-only 语义，需要下一次执行或重建运行态后才加载最新副本

**副本元数据**：

安装时在工作区副本目录下创建 `.aiasys-skill-meta.json`，记录来源信息和源目录指纹：

```json
{
  "name": "pdf-translate-skill",
  "source_type": "builtin",
  "source_name": "pdf-translate-skill",
  "source_fingerprint": "sha256:abc123...",
  "installed_at": "2026-05-25T14:30:00Z",
  "version": "1.0.0"
}
```

**重名规则**：

- 同一作用域（一个全局仓库或一个工作区）内 skill 名字唯一，禁止重名
- 安装时检测到同名 → 报错，提示先卸载
- 用户想用自己的版本替代官方版 → 先卸载官方的，再安装自己的（或 fork 时强制改名）

**Hash 检测与更新**：

- `source_fingerprint` 是安装时源目录的内容指纹，作为"副本是否被修改"的基准
- 副本 fingerprint == source_fingerprint 且源有新版本 → 显示"可更新"，用户确认后覆盖
- 副本 fingerprint != source_fingerprint → 标记"已自定义"，不提示更新，不提供自动合并
- 更新在各副本层面独立进行，全局副本更新不影响工作区副本，工作区之间互不影响
- 用户想更新一个"已自定义"的 skill → 卸载后重新安装

**Skill 热加载语义**：

Skill 在会话启动时读取一次，运行中不做热加载。Agent 上下文是动态加载的，agent 可以通过 tool_search 自行发现并加载新工具。动态加载内容允许冗余（同一工具可能在多个 skill 中出现， agent 按需选择）。界面和文档应明确告知用户：skill 变更（启用/禁用/更新）对运行中会话采用 next-run-only 语义，下一次执行或重建运行态后才生效。

**全局源与工作区副本的边界**：

Skill 是工作区附件，不是全局对象。全局工作区只提供跨工作区共享的默认配置，但删除全局仓库（store）中的 skill 源**不**级联删除任何工作区副本。每个工作区副本是独立存在的，卸载只删副本不删源。这个边界防止"删了全局源导致所有工作区 skill 失效"的意外行为。

**自定义 Skill**：

- 自定义 skill（`source_type: "custom"`）不关联任何源，不检测更新
- 从官方 skill 修改而来的自定义版本必须 fork（另存为新名字），原官方 skill 不受影响
- AIASys 不是 skill 开发环境，没有 diff/merge 决策界面

**版本号**：

- 官方/外部 skill 建议有 version（SKILL.md frontmatter 或 market API），自定义 skill 不强制
- 更新检测的核心依据是 fingerprint，version 只用于展示

**为什么不用软链接？**

早期设计考虑过软链接，但实现改为复制：桌面应用打包模式下兼容性更好，且工作区副本与源仓库解耦，全局仓库的后续更新不会意外影响已安装的工作区。

## 模板系统架构

### 当前阶段（内置优先）

模板当前内置在代码仓库 `apps/backend/templates/{name}/` 中，随系统部署。每个模板是一个子目录，包含 `template.toml`（元数据）和可选的预置文件。

| 层级 | 路径 | 作用 |
|------|------|------|
| 系统内置源 | `apps/backend/templates/{name}/` | 系统预装模板，随代码仓库部署，标记为"官方" |
| 用户自定义源 | `{user}/global_workspace/.aiasys/templates/{name}/` | 用户通过"导出工作区为模板"创建，或从市场安装 |
| 工作区应用 | `{ws}/` | 创建工作区时由模板预置文件写入 |

### 核心原则

- **内置模板默认未安装**。系统内置模板存在于代码仓库，但模板管理只展示已安装到用户目录的模板。用户需通过模板市场主动"安装"，系统才会将模板复制到 `{user}/global_workspace/.aiasys/templates/`。这保证了"内置模板未来移出系统"的迁移路径：移出后，已安装到用户目录的模板不受影响，未安装的通过市场重新获取。
- **模板管理只管理已安装模板**。`list_workspace_templates(installed_only=true)` 只扫描用户目录，不扫描系统目录。新建工作区对话框和模板市场不受此限制。
- **安装即复制**。从模板市场安装内置模板时，执行 `shutil.copytree` 将系统目录完整复制到用户目录。安装后的模板在用户视角是"已安装"，可从模板管理中卸载（删除用户目录副本）。系统内置原版始终保留，除非未来从仓库移除。
- **用户自定义模板始终可见**。通过"导出工作区为模板"创建的模板直接写入用户目录，天然属于"已安装"，不需要经过市场安装步骤。
- **当前阶段外部市场仅内置源**。`ExternalTemplateMarketService` 当前只注册了 `aiasys-builtin` 适配器，扫描 `apps/backend/templates/`。外部市场源（类似 Skill 的 `apps/backend/skills/store/`）待模板生态足够大后再引入。

### 未来迁移边界

- **内置模板未来会从代码仓库移出**，进入独立的分发包或外部市场。当前架构已预留这条路径：模板市场 API、安装/卸载机制、已安装模板与用户目录的绑定关系，都支持内置源被外部源替换。
- **不做模板继承、组合或 diff 机制**。模板之间保持完全独立，没有父子关系、没有合并规则、没有基于现有模板的增量覆盖。原因：(1) 增加用户认知负担，违背模板"降低开局成本"的初衷；(2) 调试困难，最终效果不可预测；(3) 当前 6 个内置模板（空白、代码开发、数据分析、论文精读、竞赛攻关、知识管理）场景差异大，没有强烈的共享基座需求；(4) 用户可通过"基于某模板创建工作区 → 修改 → 导出为新模板"实现等效复用。如果未来出现充分的继承需求，先提出具体实现方案再做可行性评估，不能为了灵活性引入系统混乱。

## 问题与需求登记

- Bug 汇报：`design-draft/bug-discovery/`，每个 bug 一个独立文档
- 需求登记：`design-draft/requirement-thinking/`，每个需求一个独立文档

## 文件大小例外

以下文件即使超过 500 行也不应机械拆分：

| 文件 | 行数 | 例外原因 |
|------|------|----------|
| `apps/backend/app/services/capability_registry.py` | 482 | 内聚的服务类，所有方法围绕统一能力注册表，拆分会导致循环引用或暴露内部数据结构 |
| `apps/backend/app/models/session.py` | 512 | Pydantic 模型定义集，字段和配置高度耦合，拆分会破坏模型间引用关系 |
| `apps/backend/app/api/routes/sessions.py` | 717 | Session CRUD route handler 集合，monitor 路由已抽出为 sessions_monitor.py，剩余为核心路由 |
| `apps/web/src/components/layout/WorkspaceSidebar/WorkspaceContextPanel.tsx` | 873 | 布局编排组件，核心职责是视图路由（content switch + activitySidebarContent 三元链）和布局骨架，已从 1410 行拆到极限 |

## 排查备忘

以下问题已被踩过坑，后续接手人遇到类似现象时优先对照检查，不要盲目重新排查。

### 前端 "Failed to fetch" / 页面白屏

1. **先确认前端 dev server 是否真的在监听端口**，不要只看 `ps aux` 里有没有 node 进程。用 `ss -tlnp | grep 13000` 确认。Vite 进程可能还在但已崩溃，不再监听端口。
2. **再确认后端 uvicorn 是否在跑**。同样用 `ss -tlnp | grep 13001` 确认。前后端 dev server 都可能意外停止。
3. **最后看 Vite 编译错误**。常见根因是 commit 删了文件但没清引用。已发生过的缺失文件列表：
   - `@/lib/api/roles.ts`（角色库 API）
   - `@/lib/api/llmSelection.ts`（模型选择 API）
   - `@/components/file/FileUploadToast.tsx`（上传 Toast）
   - `@/lib/api/monitors.ts`（Monitor 后台任务 API）
   - `@/lib/api/claw.ts`（Claw 托管 API）
   排查方法：看 Vite 终端日志里的 `Failed to resolve import`，从 git 历史中恢复文件即可。

### Docker PostgreSQL 初始化

- `aiasys-postgres` 容器挂载了 `infra/docker/postgres/init:/docker-entrypoint-initdb.d`，但**这个目录是空的**。容器首次启动时只创建了默认 `postgres` 用户，没有 `smoke/demo/readonly/writer` 等账号。
- 如果容器已经运行过（数据目录非空），**重启不会自动执行 init 脚本**。需要手动进容器执行 SQL，同时把脚本落盘到 `init/` 目录供下次重建使用。
- 当前已创建的用户和数据库：
  - `smoke` / `smoke` → `smoke_db`
  - `demo` / `demo` → `demo`
  - `readonly` / `readonly` → `demo`（只读权限）
  - `writer` / `writer` → `demo`（读写权限）
  - `acceptance_external_connector` 库保留原有数据，给 `smoke` 加了连接权限

### AutoTask 重启后行为

- `interval`/`cron`/`once` 任务靠 `_recover_missed_tasks()` 补执行，错过超过 60 秒的任务会在启动时立即补一轮。
- `continuous` 任务在轮询中始终 `due`，执行完后立即准备下一轮。内存锁 `_running_locks` 是进程内集合，**重启后清空**，因此 continuous 任务会立即重新触发。
- 这是设计上的允许行为，AutoTask 内部应自行幂等（如检查 `auto_task_signal` 或已产出证据），不依赖跨进程锁保证唯一执行。

### 终端操作约束

- **当前终端不支持交互式输入**。任何需要用户输入密码、确认 Y/N、选择选项的命令都会卡住。遇到权限问题不要用 `sudo` 等用户输入，改用 `docker exec` 或其他无需交互的方式解决。

## 临时文件与归档规范

以下临时产物**不得留在 apps/ 子目录内**，发现后应立即按规则处理：

| 产物类型 | 正确存放位置 | 禁止位置 | 处理方式 |
|---------|-------------|---------|---------|
| browser smoke / UI 验证截图 | `design-draft/archive/artifacts/` | `apps/web/.playwright-cli/`、`apps/web/artifacts/`、`artifacts/` | 发现即移入 archive |
| Playwright console 日志 | `design-draft/archive/playwright-cli/` | `apps/web/.playwright-cli/` | 发现即移入 archive |
| 前端一次性验证脚本 | `design-draft/archive/scripts/` | `apps/web/scripts/*.mjs`、`apps/web/scripts/*.py` | 用完即归档或删除 |
| Playwright 测试结果 | 不入版本控制 | `apps/web/test-results/` | 已 gitignore，直接删除 |
| Python 测试缓存 | 不入版本控制 | `apps/web/.pytest_cache/`、`apps/backend/.pytest_cache/`、`__pycache__/` | 已 gitignore，直接删除 |
| Vite 缓存 | 不入版本控制 | `apps/web/.vite/` | 已 gitignore，直接删除 |
| 后端运行时日志 | 不入版本控制 | `apps/backend/logs/` | 已 gitignore，直接删除或归档 |
| 后端运行时数据库 | 不入版本控制 | `apps/backend/data/` | 已 gitignore，不提交 |
| 运行时 skill 副本 | 不入版本控制 | `apps/backend/.skills/` | 已 gitignore，不提交 |
| 示例数据集 | 不入版本控制 | `apps/backend/example_datas/` | 已 gitignore，不提交 |
| 后端一次性验证脚本 | `design-draft/archive/scripts/backend/` | `apps/backend/scripts/test_*.py` | 用完即归档或删除 |
| Electron 打包产物 | 不入版本控制 | `apps/desktop/.dist/`、`apps/desktop/dist/` | 已 gitignore，直接删除 |
| npm 依赖 | 不入版本控制 | `apps/desktop/node_modules/` | 已 gitignore，不提交 |
| 根目录临时产物（兜底） | 不入版本控制 | `/artifacts/` | 已 gitignore，发现即删除或归档 |
| 项目级一次性脚本 | `design-draft/archive/scripts/` | `scripts/*.py`、`scripts/*.mjs`（非 design/dev/security 目录） | 用完即归档或删除 |

**apps/web/.gitignore**、**apps/backend/.gitignore**、**apps/desktop/.gitignore** 和 **根目录 .gitignore** 已包含上述规则。如果后续新增临时产物类型，同步补入对应 `.gitignore` 和本表。

**正式展示图**（README、docs 配图）与临时验证截图的区别：
- 正式图：经过挑选、有明确文档用途，放 `images/` 下对应子目录
- 临时图：验证过程中产生的过程截图，放 `design-draft/archive/artifacts/`
