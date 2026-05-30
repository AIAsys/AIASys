---
name: aiasys-system-design
description: AIASys 系统专属设计约束。用于在 AIASys 内进行前端界面设计、任务语义收口、设置与工作区信息架构设计，以及后端能力模型、配置模型和作用域分层设计时，确保输出优先服从 AIASys 当前系统边界，而不是套用通用最佳实践。
---

# aiasys-system-design

把 AIASys 自己的产品语义、前端信息架构和后端配置边界写成系统专属约束，避免后续实现继续被通用 best practice 带偏。

---

## 使用场景

- 在 AIASys 中设计新页面、新弹层、新市场页、新设置页
- 在 AIASys 中做任务语义、工作区语义、设置语义的收口
- 在 AIASys 中设计 memory / 上下文 / 历史恢复 / 记忆展示
- 在 AIASys 中设计新的后端能力模型、配置模型、registry、status projection
- 当通用 `frontend-pattern` / `frontend-design` / `api-dev` 无法表达 AIASys 自己的产品边界时
- 当用户明确说“不要脱离我们系统本身”“要符合我们当前骨架”时

---

## 核心规则

### 规则 1：先服从 AIASys 当前产品真相，再谈最佳实践

AIASys 的设计优先级不是“理论上最优”，而是“与当前系统主骨架一致”。

必须先确认这些真相：

1. 当前产品主对象是 `长期任务工作区`
2. 当前实现层主对象仍然主要落在 `session / conversation`
3. 历史 `analysis` / `data_analysis.preset` 只作为兼容配置 ID 暂存，不代表当前存在数据分析模式
4. 当前通用任务的运行能力由工作区、分支、任务配置、能力包、skill、执行策略和是否绑定 Python 环境共同决定
5. 工作区、执行记录、文件、任务级配置仍是主骨架，不能轻易引入平行真相源
6. 设置、我的默认配置、任务配置必须分层，不允许再混成一团

如果新设计会和以上真相冲突，优先收敛设计，而不是硬推新抽象。

### 规则 1A：默认主界面骨架必须稳定

AIASys 当前默认主界面骨架应稳定为：

1. 左侧导航
   - 工作区 / 分支导航与最小系统入口
2. 中间主画布
   - 当前活跃对象
   - 例如 `workspace explorer / notebook / database / pdf / file / chart / artifact`
3. 右侧助手侧栏
   - 当前任务对话、输入、任务上下文与当前对象摘要

这里的右侧默认承接“当前任务协作与上下文”，不再要求用户在“聊天主画布”和“对象主画布”之间来回切换。

对话记录的正确落点是：

- 作为右侧助手侧栏最外沿的历史边条
- 侧栏宽度足够时可直接展开
- 空间不足时收进 `...` 或抽屉

工作区目录 / 文件树的正确落点是：

- 作为中间主画布中的 `workspace explorer` 对象
- 或者作为当前对象内部导航
- 不再长期挤占右侧与聊天抢空间

以下内容不应再作为右侧一级常驻主区与工作区并列：

- 执行流全量详情
- 大段日志
- 数据库管理页
- 市场页

这些对象应通过抽屉、次级面板或弹窗从当前任务上下文进入。

### 规则 2：前端先做信息分层，不先堆功能

AIASys 的前端最常见问题不是“功能不够”，而是：

- 信息层级不清
- 同一概念被多个组件重复解释
- 解释层和操作层混在一起
- 内部设计说明被直接渲染给用户

因此设计任何界面时，必须先分清三层：

1. 目录层：系统提供什么、有哪些可选项
2. 默认层：用户长期默认使用什么
3. 工作层：当前任务工作区这次实际怎么用

如果三层混在一个组件里，优先拆层，不优先加按钮。

### 规则 3：设置、市场、任务三类入口不能混

AIASys 当前必须明确三类入口的职责：

1. 设置
   - 放长期默认配置
   - 放市场页
   - 不直接承载当前任务的一次性工作状态

2. 市场
   - 是供给侧目录
   - 负责展示系统支持什么
   - 不直接等于“当前正在使用什么”

3. 任务配置
   - 是当前任务工作区配置
   - 负责当前任务实际启用什么
   - 不承担市场目录和长期默认配置中心职责

不要把“市场”“我的默认配置”“任务覆盖”塞到一个页面里假装统一。

### 规则 3A：工作区设置与当前分支设置不能混

AIASys 当前主线下，`工作区` 是长期对象，`分支/会话` 是工作区内的推进分支。

因此设置入口必须再细分一层：

1. 工作区设置
   - 放工作区标题、描述、新分支默认模式、共享资源挂载
   - 回答“这个长期工作区整体怎么组织”

2. 当前分支设置
   - 放当前分支 mode、当前分支 Agent 覆盖、当前分支运行态应用
   - 回答“当前这条分支这次具体怎么跑”

3. 我的默认设置
   - 放用户长期默认 Agent 配置
   - 不直接冒充当前分支设置

如果一个弹层同时在解释：

- 工作区标题 / 描述
- 当前分支运行态
- 当前分支 Agent 提示词和工具

那这个弹层已经把多个作用域混在一起了，应优先拆开，而不是继续加 tab。

### 规则 3B：设置类页面与设置类弹层统一采用左侧导航 + 右侧内容

AIASys 中凡是“设置 / 配置 / 工作区设置 / 我的设置 / 任务设置”类界面，默认骨架统一为：

1. 左侧导航
   - 承接设置分组、分类切换、局部状态摘要
   - 当前所在分组必须清晰可见

2. 右侧内容
   - 只承接当前分组的说明、表单、开关和保存动作
   - 内容区独立滚动，不让整个页面或整个弹层一起跳动

3. 适用范围
   - `工作区设置`
   - `设置中心`
   - 后续新增的设置类弹窗、抽屉、嵌入式设置面板

默认不要把设置主导航做成顶部一排 tab，尤其在内容密、字段多、需要长滚动时。

窄屏下允许折叠成“上方分组选择 + 下方内容区”，但语义仍然保持“导航层 / 内容层”分离，而不是把所有设置堆成长表单。

### 规则 4：能力接入先按适配器类型建模，不要先把 MCP 抬成总模型

AIASys 的一等对象应是“能力接入”，不是某一种协议。

当前应优先承认三类主适配器：

1. `CLI / 本地命令`
   - 适合已有成熟命令行的能力
   - 例如宿主机命令、容器内命令、已有 CLI 工具链

2. `原生 API / SDK`
   - 适合官方已经提供稳定 HTTP API、Python SDK、Node SDK 的能力
   - 像 `Tavily` 这类能力，优先考虑这一层，不必为了统一而强行先包成 MCP

3. `MCP`
   - 适合已有 MCP server 生态、需要标准 tool 协议封装、或多 Agent 共享同一工具暴露层的场景

因此：

- `MCP` 是 AIASys 的一种接入方式，不是总抽象
- `MCP 市场` 可以存在，但它表达的是“协议型接入目录”
- 不是所有外部能力都必须先进 `MCP 市场`
- capability registry 应该描述“这个能力通过什么适配器接入”，而不是默认所有能力都叫 MCP

### 规则 4A：变量和密钥必须分开，不要把前端配置直接等同于环境变量

AIASys 中后续凡是涉及 token、api key、secret、password、header credential、private endpoint 的配置，默认必须拆成两层：

1. `变量`
   - 非敏感配置
   - 可以被同作用域用户重新查看和编辑
   - 例如 base_url、workspace name、默认 region、非敏感 header 开关

2. `密钥`
   - 敏感配置
   - 默认遮蔽
   - 只允许写入、替换、删除，不默认回显原值
   - 只允许在运行时解析并注入，不应在前端被当成“可见环境变量列表”

前端“变量与密钥”页的真实职责是：

- 管理 AIASys 自己的受控配置层
- 不是直接管理宿主机真实环境变量
- 更不是让所有人看见共享 token

### 规则 5：系统提供不等于全员强制启用

AIASys 中的“系统级 MCP”默认解释为：

- 系统提供的 MCP 目录项
- 不是管理员替所有用户强制启用的 MCP

因此默认口径应是：

1. 系统提供这个 MCP
2. 用户选择是否安装到“我的 MCP”
3. 安装后才会进入自己的默认配置
4. 任务再决定这次是否实际使用

这一点更像“系统提供的 Skill”，而不是“全员绑定的全局配置”。

### 规则 6：如果要做共享，不要偷换成系统级

如果未来要支持团队共享 MCP，正确分层应该是：

`MCP 市场 -> 团队 MCP -> 我的 MCP -> 任务 MCP`

不要把“团队共用”偷换成“系统级”，否则会带来：

- 权限边界混乱
- 审计困难
- 用户误以为自己在改个人配置，实际改了全局

当前未实现团队级时，优先保持三层模型，不要提前把“系统级”做成万能筐。

### 规则 7：任务级配置可以动态保存，但不是运行中热更新

AIASys 中对任务级 MCP 的正确口径是：

- 可以在任务层动态调整和保存
- 但当前正在运行的 Agent Session 不做热更新
- 对下一次执行生效

因此不要把“可调整”写成“当前运行中立即生效”。

### 规则 8：前端文案只写用户需要知道的事

前端渲染文案只能回答：

- 这里是什么
- 这里能做什么
- 从这里会去哪里
- 当前状态是什么

禁止把以下内容直接写成用户提示文案：

- 内部实现分层
- 生命周期锁定口径
- 架构师视角的解释语句
- “mode 只决定……”
- “这里真正可编辑的是……”
- “当前只是某层配置……”

这些内容只能写到：

- 代码注释
- 架构文档
- Skill 规则
- Task session / PRD

### 规则 9：高密度界面默认支持折叠

AIASys 有大量高密度技术界面，例如：

- Agent 配置页
- MCP 市场
- 任务 MCP 面板
- 生命周期与执行记录弹层
- 多任务 / 多能力 / 多工具列表

这些界面默认必须考虑折叠策略：

1. 超过 4~6 个同类项时，优先按语义分组
2. 超过 2 个语义组时，优先使用 Accordion / Collapsible
3. 默认只展开当前最常用或最关键的一组
4. 摘要信息永远保留在折叠标题里，避免用户必须点开才能知道内容

### 规则 10：颜色只服务于语义分层，不服务于装饰

AIASys 当前前端主基调是：

- 中性背景
- 清晰边框
- 少量语义色点缀
- 不追求花哨渐变和装饰性色块

颜色规则：

1. 基础结构优先用 `background/card/border/muted/secondary`
2. 语义色只用于状态和类别
3. 同一页面内不要为每个 badge 发明一套新色
4. 颜色表达要稳定，不要频繁改含义

### 规则 11：后端优先补统一描述层和作用域模型

AIASys 当前已经有很多“能跑”的实现，但配置作用域和描述层常常不清楚。

当后端要新加抽象时，优先级通常是：

1. 先明确 scope
   - system / team / user / task / runtime
2. 再补统一描述层
3. 再补 API 契约
4. 最后再收口执行层

例如：

- capability registry 应先回答“系统目录项是什么”
- user config 应先回答“我的默认配置是什么”
- session override 应先回答“当前任务覆盖了什么”
- runtime evidence 应先回答“这一轮实际用了什么”

### 规则 12：避免平行真相源

AIASys 最容易失控的地方，是同一个概念同时被多个层表达：

- 文档一套
- 页面一套
- hook 一套
- API 一套
- session sidecar 又一套

设计或架构修改时必须问自己：

1. 当前唯一事实源在哪里
2. 哪些层是目录层、默认层、工作层、证据层
3. 我这次新增的是事实源，还是只是 projection

如果答不清，先停下来补文档，不要直接编码。

### 规则 12A：memory 要单独收口到一套目录心智，不要再拆成多套存储叙事

Memory 设计边界详见 `AGENTS.md` 中「Memory 子系统设计边界」章节。设计层面的约束：

1. memory 只是一类独立对象，不等于所有配置的继承层
2. 记忆展示应优先是文档视图，不要再做成数据库查询工作台那种字段平铺界面
3. 旧的 `memory.db`、`memory.md`、碎片化镜像都要往 `MEMORY.md` 这条主线收口，不保留多套并行真相源

### 规则 13：系统专属 skill 是优先级覆盖层，不是替代层

这个 skill 不是替代通用 skill，而是告诉 AI：

- 在 AIASys 中做设计时，先服从系统语义

当前系统架构主稿入口：
- `.agents/skills/aiasys-system-design/references/current-system-architecture.md`
- 再套用 `frontend-pattern`、`api-dev`

调用顺序建议：

1. `aiasys-system-design`
2. 相关通用 skill
3. 当前专题文档 / task session / requirements

---

## 执行步骤

1. 先确认当前任务属于“前端信息架构收口”“任务语义收口”还是“后端作用域模型收口”
2. 读取当前专题产品文档与 active task session，确认真实产品边界
3. 明确这次改动的目录层、默认层、工作层、证据层分别是什么
4. 输出最小可落地的设计方案，避免空泛理论
5. 编码实现后，检查是否新增了平行真相源或重复组件
6. 若涉及产品方向变化，同步回写 requirements / architecture / task session

---

## 与其他 Skill 的关系

相关 skill:

- `frontend-pattern` - React/Tailwind 工程实现规范（含架构取舍）
- `api-dev` - FastAPI 接口与模型规范
- `aiasys-product-requirements` - 产品语义、需求台账、PRD 回写
- `task-session` - 长任务记录和决策追踪

---

## 当前文档入口

**设计文档定位说明**：`design-draft/design/` 下的文档是 AIASys 的产品设计基线，主要面向**终端用户和项目协作者**，描述"系统当前是什么、怎么用、渲染规则是什么"。AI 开发时也应优先参考这些文档，确保实现与设计一致。`design-draft/design/design-thinking/` 是设计决策过程记录，面向开发者，记录"为什么选这个方案"。

系统架构主稿：
- `.agents/skills/aiasys-system-design/references/current-system-architecture.md`

专题文档入口：
- `.agents/skills/aiasys-system-design/references/task-workspace-information-architecture.md`
- `.agents/skills/aiasys-system-design/references/settings-center-product-design.md`
- `.agents/skills/aiasys-system-design/references/frontend-visual-style-and-page-skeleton.md`
- `.agents/skills/aiasys-system-design/references/market-and-capability-access-model.md`

---

## 示例

### 示例 1：设计 MCP 市场

```
输入:
  “我们要把 MCP 做成市场、我的默认配置、任务覆盖三层，你看看怎么设计。”

输出:
  1. 明确 `MCP 市场 -> 我的 MCP -> 任务 MCP -> 本轮运行时 MCP`
  2. 市场只展示系统目录项，不直接代表用户已安装
  3. 我的 MCP 负责长期默认和 token 配置
  4. 任务 MCP 负责当前任务工作区覆盖
  5. 当前执行结果进入证据层，不回写成默认配置
```

### 示例 2：前端把内部解释写进页面里了

```
输入:
  “这个页面为什么写了很多内部解释，像注释一样。”

输出:
  1. 删除用户可见文案中的内部设计说明
  2. 保留只回答用户操作所需的信息
  3. 把解释写回代码注释、架构文档或 skill 规则
```

### 示例 3：团队想共用 Tavily

```
输入:
  “系统级 MCP 是不是应该支持团队一起用？”

输出:
  1. 区分 system 和 team，不把团队共享偷换成系统级
  2. 如果当前未实现 team 层，先保持 system 提供目录项、user 选择安装
  3. 后续若补 team 层，走 `market -> team -> user -> task`
```

---

## 写作规范

- 禁止 Emoji：直接写文字，不要用图标符号表达规则状态
- 禁止方括号状态：使用纯文字，不写 `[STABLE]`
- 中文优先：AIASys 系统专属 skill 默认使用中文描述规则和示例
- 不要抽象空转：所有规则都应能映射到 AIASys 当前代码、页面或文档

---

注意: 本 Skill 是 AIASys 系统专属约束层，优先级高于通用 best practice，但不替代实现型 skill。
---

## 前端状态流

以下状态流描述 AIASys 关键交互链路的前端状态机。每个状态流定义了触发条件、状态转换、关键规则和验收断言，供 AI 实现和评审时参照。

### 运行环境面板状态流

**状态源总览**：

| 状态 | owner | 用途 |
|---|---|---|
| `showRuntimeEnvManager` | `useRuntimeEnvironmentPanel` | 管理面板开关 |
| `showNewTaskEnvDialog` | `useRuntimeEnvironmentPanel` | 新建任务选择弹窗开关 |
| `showSwitchConfirmDialog` | `useRuntimeEnvironmentPanel` | 当前会话切环境确认框 |
| `newTaskStage` | `useRuntimeEnvironmentPanel` | 新建任务主状态机 |
| `newTaskError` | `useRuntimeEnvironmentPanel` | 新建任务失败文案 |
| `defaultSandboxMode` | `useRuntimeEnvironmentPanel` | 未来新任务默认模式 |
| `currentSandboxMode` | `useRuntimeEnvironmentPanel` | 当前可见会话真实模式 |
| `activeEnv` | `useRuntimeEnvironments` | 当前可见会话环境 |

**面板打开/关闭**：

- 打开管理面板：`idle -> openRuntimeEnvManager() -> fetch environments / preference / active env / containers -> manager_open`
- 关闭管理面板：只允许在 `newTaskStage` 非 busy 阶段、且当前没有正在执行的会话切环境过渡时关闭。busy 阶段点击遮罩、Esc、关闭按钮都必须被拦截。

**当前会话切环境**：

```
manager_open
  -> click switch env
  -> if hasChatContent: showSwitchConfirmDialog
  -> executeSwitchEnvironment(env)
  -> refresh active env
  -> refresh containers (docker only)
  -> manager_open
```

关键规则：
1. `executeSwitchEnvironment` 只能使用 `currentSandboxMode`
2. 当前环境切换完成前，输入区 `isInitializingEnvironment = true`
3. 切换失败时保留原 `activeEnv` 和原 `currentSandboxMode`

**侧边栏"新建任务"流程**：

```
idle -> handleNewTaskWithEnv() -> showNewTaskEnvDialog = true -> newTaskStage = selecting_environment
selecting_environment -> user confirm(envId, sandboxMode) -> preparing_session -> binding_environment -> waiting_runtime? (docker only) -> activating_session -> idle
```

关键规则：
1. 选择弹窗在 busy 阶段不可关闭
2. 成功后才允许关闭弹窗
3. 失败时 `newTaskStage = error`，`newTaskError` 写明原因，保持当前可见会话不变

**管理面板内"使用此环境新建任务"流程**：复用同一套 `newTaskStage`。执行期间管理面板不可关闭。成功后关闭面板；失败后保留面板并显示错误 banner。

**后台目标会话生命周期**：

```
current visible session A
  -> prepare target session B
  -> B bind env in background
  -> B runtime ready
  -> activate B
  -> visible session becomes B
```

规则：
1. A 在 `activate B` 之前始终保持可见
2. B 的 `activeEnv` 不得在后台阶段写到全局可见状态
3. 只有 `activatePreparedSession(B)` 成功后，才允许切 URL、切 chat/task/workspace、更新 `currentSandboxMode`

**Local 与 Docker 分支**：

| 分支 | `newTaskStage` 差异 | 额外要求 |
|---|---|---|
| Docker | 会经过 `waiting_runtime` | 刷新容器列表 |
| Local | 直接跳过 `waiting_runtime` | 不显示容器预热语义 |

**验收断言**：
1. `defaultSandboxMode` 修改后，当前输入区沙盒徽章不会立刻变化
2. 新建任务失败时，当前聊天内容仍在
3. 背景目标会话绑定环境后，当前前台环境展示不变
4. Local 新建任务不会等待 Docker 容器列表才结束 busy

### 对话框输入区域状态流

**禁用状态汇总**：

| 状态名称 | 来源 | 触发场景 | 显示文案 | 禁用范围 |
|---------|------|---------|---------|---------|
| `isRunning` | `owlState.isRunning` | AI 正在执行/生成回复 | 无（不禁用输入） | 仅发送按钮 |
| `isUploading` | `useAgentFileUpload` | 文件正在上传 | "文件正在上传中..." | 输入框、附件按钮、发送按钮 |
| `isPrewarming` | `useSessionOrchestrator` | 当前前台是空白 Docker 会话，且没有待恢复历史会话时的预热兜底 | "环境预热中，请稍候..." | 输入框、附件按钮、发送按钮 |
| `isInitializingEnvironment` | `useRuntimeEnvironmentPanel` | 切换环境或新建任务时环境初始化 | "环境初始化中，请稍候..." | 输入框、附件按钮、发送按钮 |

**`isRunning` - AI 执行中**：不禁用输入框（允许用户预输入下一条消息），仅禁用发送按钮（防止重复提交），显示停止按钮。

**`isPrewarming` - 前台空白 Docker 会话预热中**：
- 触发条件：当前前台会话切换为空白会话（`chatItems.length === 0`）、沙盒模式为 `docker`、当前没有待恢复的历史会话回包
- 只负责"前台空白 Docker 会话"的短暂预热兜底
- 迟到的旧预热回包不能覆盖更新会话的状态
- 一旦当前会话已出现可见对话内容，就不应继续让输入区显示"环境预热中"

**`isInitializingEnvironment` - 环境初始化中**：
- 触发条件：切换环境时点击"切换到此环境"按钮、新建任务时点击"使用此环境新建任务"按钮或选择环境
- 禁用范围：输入框（`disabled` + 阻止键盘事件）、附件按钮（`disabled`）、发送按钮（`disabled` + 点击拦截）

**职责分离**：
- `isPrewarming` 在 `useSessionOrchestrator` 中管理，只处理当前前台空白 Docker 会话的预热兜底
- `isInitializingEnvironment` 在 `useRuntimeEnvironmentPanel` 中管理，处理显式的新建任务 / 环境切换流程
- 新建任务的忙碌态必须在切到新会话后释放：`activatePreparedSession()` 成功后，前台已经是目标会话，不应继续因为工作区刷新、环境信息读取、容器列表刷新而维持"创建中"，这些只读刷新应转为后台执行

**状态优先级矩阵**（当多个状态同时存在时）：

| 优先级 | 状态 | 显示文案 |
|-------|------|---------|
| 1 (最高) | `isInitializingEnvironment` | "环境初始化中，请稍候..." |
| 2 | `isPrewarming` | "环境预热中，请稍候..." |
| 3 | `isUploading` | "文件正在上传中..." |
| 4 (最低) | 正常状态 | "询问任何问题" |

注意：`isRunning` 不占用 placeholder，只禁用发送按钮。

**相关文件**：

| 文件 | 职责 |
|-----|------|
| `InputArea.tsx` | 输入框 UI 和禁用逻辑 |
| `useSessionOrchestrator.ts` | `isPrewarming` 状态管理 |
| `useRuntimeEnvironmentPanel.ts` | `isInitializingEnvironment` 状态管理 |
| `useAgentFileUpload.ts` | `isUploading` 状态管理 |
| `useAgentStream.ts` | `isRunning` 状态管理（owlState） |

### 会话生命周期状态流

**状态机**：

```
draft_created
  -> active (首条消息写入 / 执行开始)
  -> completed (执行成功结束)
  -> active (新一轮执行开始)
```

**状态判定规则**：
1. `message_count == 0` -> `status = draft`
2. `message_count > 0` -> `status = active`
3. `status = completed` 仅在完成后保持，执行开始时清空完成标记
4. 新消息导致 `message_count` 变化时，`completed` 会被回退到 `active`

**关键触发点**：
1. 新建任务或直接访问分析页：创建 `metadata.json` + 空 MCP 配置
2. 首条消息写入：后端更新 `message_count` 并推导 `status`
3. `GET /api/sessions/status/{session_id}`：幂等创建草稿并返回 `status/message_count/can_edit_mcp`
4. 执行开始：`mark_session_active` 清除 `completed`
5. 执行成功结束：`mark_session_completed` 写入 `completed`

**MCP 锁定规则**：
1. `message_count == 0` -> MCP 可编辑
2. `message_count > 0` -> MCP 只读锁定
3. 前端需以 `/api/sessions/status/{session_id}` 为准，避免仅依赖本地 `chatItems`

**草稿清理边界**：
1. 仅清理 `message_count == 0` 的草稿
2. `cleanup-drafts` 可携带 `currentSessionId`，后端必须跳过当前会话目录
3. 保留最新 3 个草稿；`.cleanup_marker` 草稿使用更短阈值

**当前风险**：
1. 若前端不拉取 `session/status`，MCP 锁定状态可能与真实会话不一致
2. 仅 Agent 执行路径会写入 `completed`，非 Agent 写入流程需评估是否需要补齐

### 会话删除与草稿清理状态流

**强制规则**：
1. 删除会话必须先停流，再清缓存，再调后端删除
2. 后端删除必须同时停止容器并清理 runtime env instance
3. 草稿清理只能针对 `message_count == 0` 的会话
4. 页面关闭时只能标记空草稿，不允许直接删除
5. 删除当前活跃会话时，前端必须先激活新的空白草稿，再清理旧会话缓存和后端资源
6. 草稿清理请求应携带 `currentSessionId`，后端必须跳过当前会话目录

**删除会话状态机**：

```
idle
  -> stop_stream
  -> activate_replacement_draft?   (仅当前活跃会话)
  -> clear_frontend_cache
  -> backend_delete
  -> deleted | failed
```

前端顺序：`stopSession(sid) -> (若 sid === currentSessionId，先 generateUUID -> initSession -> activatePreparedSession) -> removeChatSession(sid) -> removeMultiTaskSession(sid) -> deleteSessionApi(sid)`

后端顺序：`agent_service.stop_session -> IPythonBox.stop_container(workspace_path) -> env_service.remove_instance(user_id, session_id) -> session_manager.delete_session(session_id, user_id)`

**草稿清理状态机**：

```
draft_created
  -> idle_draft
  -> marked_for_cleanup?
  -> cleanup_scan
  -> deleted | kept
```

清理规则：
1. 只看 `message_count == 0`
2. 保留最新 3 个草稿
3. 普通草稿阈值 30 分钟
4. `.cleanup_marker` 草稿阈值 5 分钟
5. 若请求携带 `currentSessionId`，对应会话不参与清理扫描

触发点：进入分析页、新建任务前、切换历史会话前、页面关闭前 `sendBeacon mark-draft-for-cleanup`

**当前策略**：统一策略是"删除活跃会话 -> 切到新的空白草稿"，不要自动跳转到其他历史会话。该策略已覆盖 URL、前台可见会话与侧边栏占位态的一致性主链路。

### 文件导入与工作区同步状态流

**强制规则**：
1. 源会话列表必须排除当前目标会话
2. 源会话变化时必须清空旧勾选文件
3. 导入完成后必须刷新目标会话工作区文件列表
4. 导入失败时弹窗不得被强制关闭
5. 当前实现是逐文件串行导入，不能把它写成批量原子导入

**状态机**：

```
closed
  -> loading_sessions
  -> source_selected
  -> loading_source_files
  -> selecting_files
  -> importing
  -> refreshing_target_workspace
  -> success | failed
  -> closed
```

**关键流转**：

打开弹窗：`loadSessions()`，关闭时清空 `selectedSessionId`、`selectedFilenames`、`error`

选择源会话：自动选第一个非目标会话；会话变化时 `setSelectedFilenames([])` 并 `loadSourceSessionFiles(selectedSessionId)`

导入文件：当前实现为逐文件串行 `download source file -> upload to target session`

成功后刷新：`showSuccess("文件已成功导入当前会话") -> reloadWorkspaceFiles() -> 关闭导入弹窗`

**已知限制**：没有逐文件部分成功反馈；没有增量合并，只做整表刷新；文件较多时串行导入耗时较长。