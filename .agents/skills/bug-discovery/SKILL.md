---
name: bug-discovery
description: Bug 发现、跟踪、修复、验证、归档的完整工作流。在 AIASys 项目中发现 bug 时自动使用。涵盖认领检查、Task Session 去重、代码扫描、严重程度评估、自动/人工决策分流、子 Agent 并行修复、测试验证和归档。当用户要求检查 bug、修复 bug、或发现代码异常时触发。
---

# Bug Discovery & Fix Skill

AIASys 项目 Bug 发现与修复的标准工作流。

---

## 触发条件

以下任一情况自动使用本 skill：

- 用户主动要求"检查 bug"、"看看有没有 bug"
- 代码审查时发现潜在问题
- 测试失败时
- 定时连通性扫描发现问题
- 其他 agent 报告异常

---

## Phase 1: 认领检查（去重）

**在扫描代码之前，先检查是否已有相关 bug 记录和 task session。**

### 1.1 检查活跃 Bug 目录

扫描 `design-draft/bug-discovery/`：
- 排除 README.md，列出所有 `*.md` 文件
- 每个文件中查找 `> **认领人**:` 标记：已被认领的 bug 跳过，不重复处理
- 标记为"待修复"但未被认领的 bug：确认问题是否仍然存在（检查对应代码/文件），如果问题已不存在则标记为"误报"并归档，如果仍然存在则纳入本次修复范围
- 检查 archive/ 下是否有状态为"待修复"或"待优化"的虚假归档（应回到活跃目录或更新状态）

### 1.2 检查 Task Session 去重

扫描 `.agents/task-sessions/active/`：
- 检查是否已有针对同一批 bug 的 task session
- 如果已有：读取 session 内容，确认哪些 bug 已被分配、哪些还是 pending
- 如果有 pending 且未被认领的：纳入本次修复范围，不要创建重复的 task session
- 如果全部已完成：跳过

### 1.3 确认 Bug 是否真实存在

**对每个"待修复"的 bug，必须先验证问题是否真的存在，再决定是否修复。**

验证方式：
- 读取对应文件，检查代码是否与 bug 描述一致
- 运行相关测试确认问题是否可复现
- 如果问题已不存在（代码已修改、测试已通过）：标记为"误报"并移入 archive/
- 如果问题确实存在：纳入修复清单

**不要跳过这个步骤。** 之前出现过"批量扫描报告里的 bug 实际已修复但标记未更新"的情况，直接认领修复会浪费时间。

---

## Phase 2: 代码库扫描

如果用户要求主动扫描（而非处理已有 bug 报告），启动 explore agent 并行扫描。

### 2.1 并行启动多个 explore agent

**一次性并发启动，不要等一个完成再启动下一个。** 每个 agent 专注一个维度，用下面提供的 prompt 模板确保扫描完整、输出格式统一。

#### Agent 1: 后端代码扫描

```
你的任务是扫描 AIASys 后端代码库中的潜在 bug。请按以下检查清单逐项排查，
每发现一个问题，用固定格式记录。

扫描范围：apps/backend/app/
排除目录：apps/backend/app/vendors/

检查清单：
1. 空 except/pass：搜索 `except:` 或 `except Exception:` 后跟 `pass` 或只打日志不处理
2. fire-and-forget 任务：搜索 `asyncio.create_task(` 但没有保存引用、没有异常处理
3. SQL 注入：搜索 f-string 拼接 SQL（如 `f"SELECT * FROM {table}"`），注意区分表名参数化和值参数化
4. 路径遍历：搜索 `os.path.join(` 或 `Path(` 中直接使用用户输入作为路径组件，没有做 `..` 过滤
5. 未关闭资源：搜索 `open(` 没有 `with`、`aiofiles.open` 没有 `async with`、session 没有 close
6. 异步函数未 await：搜索 `async def` 内部调用异步函数但没有 `await`
7. 硬编码密钥：搜索 `password =`、`secret =`、`api_key =`、`token =` 后跟字符串字面量
8. 缺少输入校验：搜索路由函数参数没有 Pydantic 模型校验、没有类型注解

输出格式（每个发现用以下模板，不要自由发挥）：

### [后端] {简短标题}
- 位置: `文件路径:行号`
- 严重程度: 高/中/低
- 描述: 一段话说明问题和风险
- 建议修复: 具体的修复方向
```

#### Agent 2: 前端代码扫描

```
你的任务是扫描 AIASys 前端代码库中的潜在 bug。请按以下检查清单逐项排查，
每发现一个问题，用固定格式记录。

扫描范围：apps/web/src/

检查清单：
1. useEffect 依赖遗漏：搜索 `useEffect(`，检查依赖数组是否包含 effect 内使用的所有响应式值
2. 定时器未清理：搜索 `setInterval(`、`setTimeout(`，检查是否在 useEffect cleanup 或组件卸载时 clear
3. 全局缓存无上限：搜索 `new Map(`、`new Set(`、`[]` 用作模块级缓存，检查是否有容量限制
4. innerHTML/dangerouslySetInnerHTML 未过滤：搜索这些关键词，检查输入是否来自用户或 API
5. as any 不安全断言：搜索 `as any`，逐条判断是否可以用具体类型替代
6. 事件监听器未清理：搜索 `addEventListener(`，检查是否有对应的 `removeEventListener`
7. 缺少 key 属性：搜索 `.map(` 返回 JSX，检查是否每个子元素都有稳定的 key
8. Promise 未处理 catch：搜索 `.then(` 没有 `.catch(`，或 async 函数调用没有 try/catch
9. 条件渲染用 && 可能渲染 0：搜索 `{xxx &&`，检查 xxx 是否可能为 0 或空字符串

输出格式（每个发现用以下模板，不要自由发挥）：

### [前端] {简短标题}
- 位置: `文件路径:行号`
- 严重程度: 高/中/低
- 描述: 一段话说明问题和风险
- 建议修复: 具体的修复方向
```

#### Agent 3: API 契约检查

```
你的任务是检查 AIASys 前后端 API 契约的一致性。请按以下步骤逐项排查，
每发现一个问题，用固定格式记录。

步骤：
1. 先列出后端所有注册的路由：搜索 apps/backend/app/api/routes/ 下的 `@router.get(`、
   `@router.post(`、`@router.put(`、`@router.delete(`、`@router.patch(`，
   提取 HTTP 方法 + 路径
2. 再列出前端所有 API 调用：搜索 apps/web/src/lib/api/ 下的 `apiFetch(`、
   `fetch(` 调用，提取 HTTP 方法 + URL 路径
3. 交叉对比：
   - 前端调用了但后端没有对应路由的端点
   - 后端有路由但前端没有任何调用的端点（可能是死代码或文档缺失）
4. 抽查请求/响应模型：选 5-10 个高频端点，对比前端发送的字段和后端 Pydantic 模型定义的字段

输出格式（每个发现用以下模板，不要自由发挥）：

### [API] {简短标题}
- 位置: 前端 `文件路径:行号` / 后端 `文件路径:行号`
- 严重程度: 高/中/低
- 描述: 一段话说明不一致的具体内容
- 建议修复: 具体的修复方向
```

### 2.2 汇总扫描结果

三个 explore agent 返回后，父 Agent 执行：

1. 合并所有发现，去重（同一文件同一行号的问题只保留一条）
2. 按严重程度分类（见 2.3）
3. 对每个发现做快速真实性验证：读取对应文件确认问题确实存在
4. 生成汇总报告，进入 Phase 3 决策

### 2.3 严重程度分类

| 级别 | 标准 |
|------|------|
| 高（P0） | 数据丢失风险、安全漏洞、运行时崩溃、内存泄漏、race condition |
| 中（P1） | 功能缺口、异常静默、类型错误、API 不匹配 |
| 低（P2） | 代码异味、性能优化、未使用变量、简单依赖修复 |

---

## Phase 3: 决策（分流）

### 自动处理（无需人工确认）

满足以下全部条件：
- 严重程度为低或中
- 修复方向明确（加一行日志、改一个类型、补一个依赖）
- 影响面小（单文件或同一目录内修改）
- 不涉及架构变更、安全策略、数据模型

### 需人工确认

满足以下任一条件时，进入 Phase 3.5 标记流程，不直接自动修复：
- 严重程度为高
- 涉及架构变更（接口修改、路由重构、数据模型变更）
- 涉及安全（权限、认证、数据隔离）
- 修复方案不明确（多种可行方案需权衡）
- 跨模块影响（修改会影响多个独立模块）
- 涉及第三方库（vendor 代码、依赖升级）

**汇报格式**：
```
发现 X 个 bug，按严重程度排序：

【高严重度 — 需确认】
1. 文件:行 — 描述 — 建议方案 A/B

【中/低严重度 — 建议自动修复】
2. 文件:行 — 描述
...

请确认：
- 高严重度 bug 采用哪个方案？
- 是否启动自动修复中/低严重度 bug？
```

---

## Phase 3.5: 标记需用户决策的特殊 Bug

有些 bug 不能直接自动修复，需要在 bug 文件中明确标记，等用户决策后再处理。

### 需要标记的场景

满足以下任一条件时，不要自动修复，在 bug 文件中追加 `> **需用户决策**: <原因>` 标记：

- **涉及架构选择**：修复需要选型（如用 A 库还是 B 库、改路由还是改中间件）
- **涉及产品行为**：修复会改变用户可见的行为（如改默认值、改交互流程）
- **涉及安全策略**：权限模型、认证方式、数据隔离策略的修改
- **涉及性能权衡**：修复会以性能为代价换取正确性（如加锁、加校验）
- **涉及外部依赖**：需要升级/替换第三方库、需要配置外部服务
- **影响面无法确定**：修改可能影响多个模块但无法完整评估影响范围

### 标记格式

在 bug 文件中追加（保留原有内容，追加在描述之后）：

```markdown
> **需用户决策**: <一句话说明为什么需要用户决定>
>
> **选项 A**: <方案描述和影响>
> **选项 B**: <方案描述和影响>
> **建议**: <推荐方案及理由>
```

### 处理流程

1. 在扫描/认领阶段识别出这类 bug
2. 在 bug 文件中追加标记，处理方式保持 `待修复`
3. 在向用户汇报时单独列出"需用户决策"的 bug
4. 不要认领这类 bug（不填认领人），留给用户决策后再分配
5. 其他可直接修复的 bug 正常走 Phase 4 流程

---

## Phase 4: 执行（Task Session + 子 Agent）

### 4.1 创建或复用 Bug 报告

每个 bug 一个文件：`design-draft/bug-discovery/YYYY-MM-DD-<描述>.md`

格式：
```markdown
# 简短中文标题

> **认领人**: `<agent-id>` | **认领时间**: `YYYY-MM-DD HH:MM:SS`

- **发现时间**: YYYY-MM-DD
- **位置**: `文件路径:行号`
- **严重程度**: 简单 / 一般 / 严重
- **描述**: 一段话说明问题
- **处理方式**: 待修复
```

**注意**：
- 发现 Bug 的 Agent（扫描阶段）只负责记录和报告，不得填写认领人
- 认领标记只在修复阶段由执行修复的 Agent 填写
- 如果已有 bug 文件，不要重复创建；直接复用并在文件中补充认领标记
- 标记了 `> **需用户决策**` 的 bug 不要认领，留给用户决策

### 4.2 认领 Bug

在开始修复前，为每个要修复的 bug 文件添加认领标记：

```markdown
> **认领人**: `<当前agent-id>` | **认领时间**: `YYYY-MM-DD HH:MM:SS`
```

同时将"处理方式"改为 `已认领`。这防止多个 agent 同时修复同一个 bug。

### 4.3 创建或复用 Task Session

先检查 `.agents/task-sessions/active/` 是否已有相关 session：
- **如果已有**：读取并追加本次的 bug 清单和子 Agent 分配
- **如果没有**：创建新 session 文件 `.agents/task-sessions/active/YYYY-MM-DD-<描述>.md`

Session 内容包含：
- 创建时间、扫描来源
- Bug 清单（按严重程度排序，每个 bug 标状态）
- 子 Agent 分配表

### 4.4 子 Agent 分组与调度

**关键原则：所有子 Agent 一次性并发启动，不要串行等待。**

#### 分组规则

按 bug 的修改范围分组，每组一个 coder agent。分组目标是让每个 agent 的修改集互不重叠，避免合并冲突：

| 组别 | 匹配规则 | 说明 |
|------|----------|------|
| 后端组 | bug 位置在 `apps/backend/` 下 | 包含路由、服务层、模型、工具函数 |
| 前端组 | bug 位置在 `apps/web/src/` 下 | 包含组件、hooks、lib、utils |
| 配置/CI 组 | bug 位置在 `infra/`、`scripts/`、`.github/`、根配置文件 | Docker、部署脚本、CI 配置 |
| 文档/测试组 | bug 位置在 `docs/`、`design-draft/`、`tests/` | 文档修正、测试补充 |

如果某个组没有 bug，跳过该组。如果某个组超过 8 个 bug，考虑再按子目录拆分为两个 agent。

#### 调度策略

1. 分组完成后，在**同一个 tool call batch** 中一次性启动所有组的 coder agent
2. 使用 `run_in_background=false`（前台模式），让父 Agent 等待所有子 Agent 完成
3. 如果某些 bug 之间有依赖（B 的修复依赖 A 的修复结果），将这些 bug 放在同一组，不要跨组分配

#### 子 Agent Prompt 模板

**每个子 Agent 的 prompt 必须包含以下要素**，不能只写"修复 R1, R2, R5"：

```
你的任务是修复以下 {N} 个 bug。请按顺序逐个修复，每个修复完成后运行相关测试验证。

项目信息：
- 项目: AIASys（Python FastAPI 后端 + React 19 + TypeScript 前端）
- 前端构建: `cd apps/web && npx tsc --noEmit`
- 后端测试: `cd apps/backend && .venv/bin/python -m pytest <target> -x`

修复约束：
- 只修改 bug 描述中明确指出的文件和行，不要动无关代码
- 每个修复必须是 minimal change，不要重构、不要顺手优化
- 修复完成后必须运行相关测试，确认通过
- 如果测试失败，分析原因并修复，不要跳过
- 如果某个 bug 实际不存在（代码已修复），在输出中说明并跳过
- 不修改 `apps/backend/app/vendors/` 下的第三方代码

Bug 清单：

### Bug 1: {标题}
- 文件: `{文件路径}`
- 行号: {行号}
- 严重程度: {高/中/低}
- 问题描述: {详细描述}
- 修复方向: {具体怎么改}
- 验收方式: {怎么确认修好了，如"运行 pytest test_xxx.py"或"tsc --noEmit 通过"}

### Bug 2: ...
（同上格式）

输出要求：
修复完成后，按以下格式汇报每个 bug 的修复结果：

### Bug 1: {标题}
- 状态: 已修复 / 已跳过（原因）/ 修复失败（原因）
- 修改文件: `{文件路径}`
- 修改内容: 简述改了什么
- 测试结果: {测试命令 + 输出摘要}
```

#### 示例：一次完整的并行调度

假设扫描发现 7 个 bug：3 个后端、2 个前端、1 个配置、1 个测试。

在同一个 tool call batch 中：

```
Agent: subagent_type="coder", description="后端bug修复", prompt="
你的任务是修复以下 3 个后端 bug。请按顺序逐个修复...
（用上面的 prompt 模板，填入具体 bug 信息）
"

Agent: subagent_type="coder", description="前端bug修复", prompt="
你的任务是修复以下 2 个前端 bug。请按顺序逐个修复...
"

Agent: subagent_type="coder", description="配置修复", prompt="
你的任务是修复以下 1 个配置 bug...
"

Agent: subagent_type="coder", description="测试修复", prompt="
你的任务是修复以下 1 个测试 bug...
"
```

### 4.5 子 Agent 完成审核

**每个子 Agent 返回后，父 Agent 必须执行以下检查，不能跳过：**

1. **检查任务状态**：通过系统通知或 `TaskOutput` 确认子 Agent 是正常完成、超时还是报错
2. **审阅输出内容**：读取子 Agent 的完整输出，确认：
   - 修复范围是否和分配一致（没有漏修、没有多修）
   - 代码修改是否精准（有没有改动不该动的代码）
   - 测试是否运行过、结果如何
   - 如果子 Agent 报错或结果不完整，立即重新分配或自己接手修复
3. **人工复核修改**：对子 Agent 修改的文件做 diff 审查，确认没有引入副作用

### 4.6 修复完成后

1. 更新 bug 报告：`处理方式: ✅ 已修复`，删除认领标记
2. 将 bug 报告移入 `bug-discovery/archive/`（按模块分类：backend/、frontend/、docs/、tests/、system/、infra/）
3. 更新 `bug-discovery/README.md` 活跃列表和归档批次
4. 更新 task session：标记所有 bug 为已完成

---

## Phase 5: 验证

每个修复必须经过：

1. **代码审查**：确认修改精准、无副作用
2. **测试验证**：按 `testing-strategy` 规范执行后端 pytest 和前端 tsc 检查
3. **浏览器验证**（前端交互修改）：按 `browser-control` 规范截图取证，保存到 `design-draft/archive/artifacts/`
4. **回归检查**：确认没有引入新 bug

---

## Phase 6: 归档

1. Bug 文件移入 `archive/` 对应子目录
2. README.md 更新活跃 bug 列表和归档批次
3. Task session 移入 `.agents/task-sessions/completed/`

---

## 边界规则

- **不修改 vendor 代码**：`apps/backend/app/vendors/` 下的第三方库不主动修复
- **不修改已被认领的 bug**：活跃目录下标有"已认领"的 bug 不重复处理
- **defer 远期问题**：设计建议类、架构改造类放入 `deferred/`，等用户明确指示再执行
- **0-1 阶段不向后兼容**：修复直接替换旧实现，不写兼容代码
- **发现 Bug 的 Agent 只记录不认领**：认领标记仅留给执行修复的 Agent
- **先确认再修复**：对每个 bug 先验证问题是否真实存在，再决定是否修复
- **并行优先**：扫描、修复阶段都用并行 agent，不要串行等待

---

## 输出物清单

| 输出物 | 路径 |
|--------|------|
| Bug 报告 | `design-draft/bug-discovery/YYYY-MM-DD-<描述>.md` |
| Task Session | `.agents/task-sessions/active/YYYY-MM-DD-<描述>.md` |
| 修复后的代码 | 原文件位置 |
| 测试验证结果 | 测试输出日志 |
| 浏览器截图 | `design-draft/archive/artifacts/` |
| 归档的 Bug | `design-draft/bug-discovery/archive/` |

---

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