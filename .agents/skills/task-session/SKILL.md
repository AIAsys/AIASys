---
name: task-session
description: |
  管理复杂开发任务的 Task Session 工作流。用于多步骤、跨会话、需记录决策的长期任务。
  核心约束：首版质量必须达到"别人能接手的水平"——执行边界明确、Todo 细粒度可执行、上下文材料完整。
  创建、维护、关闭 Task Session 时使用此 skill。
---

# Task Session 管理

结构化追踪复杂任务。目标不是"记流水账"，而是让另一个 AI（或未来的自己）打开文件后能直接接手，不需要回头问。

---

## 何时使用 Task Session

**必须使用：**
- 复杂多步骤任务（3+ 步骤）
- 预计跨越多次 AI 交互的任务
- 需要研究/探索的任务
- 需要记录决策过程的任务
- 涉及前后端联调、需要多方协作的任务

**可以使用：**
- 需要跟踪进度的长期任务
- 涉及多个文件修改的 refactor
- 需要分阶段验收的功能开发

**不使用：**
- 简单问答（单次交互可完成）
- 单文件编辑
- 用户给出了极其具体的一步指令

---

## 质量标准：别人能接手的水平

一个合格的 Task Session 文件，让另一个 AI 打开后应该能回答以下 5 个问题：

| 问题 | 对应章节 |
|------|----------|
| 要做什么、做到什么程度算完成？ | Goal + 成功标准 |
| 为什么做、有什么背景和约束？ | Context（问题背景、约束条件） |
| 从哪里开始？相关代码在哪？ | Context（相关文档、关联规范） |
| 具体怎么做、分几步？ | Execution Todos（FE/BE/INT 表格） |
| 当前做到哪了、卡在哪里？ | Progress Log（进度日志 + 阻塞项） |

如果打开文件后这 5 个问题有任何一个无法回答，说明 Task Session 不达标，需要补全。

---

## 执行边界：必须明确的三个边界

Task Session 创建时必须写清楚三条边界。这不是可选的。

### 边界 1：做什么（Scope In）

列出本次任务明确要做的事情。用具体条目而非模糊描述。

```
正确：实现 WebSocket 断连后 PTY session 保留，支持重连 attach
错误：优化终端体验
```

### 边界 2：不做什么（Scope Out）

列出明确排除的事项。这比 Scope In 更重要——防止执行中范围蔓延。

```
本次不做：
- buffer 持久化（第二阶段再做）
- PTY Host 独立进程（保持 FastAPI 直接管理）
- 前端 UI 重构（只改状态机逻辑）
```

### 边界 3：为什么不做（Rationale）

对关键的 Scope Out 决策给出理由。后来者看到不会重新踩坑。

```
buffer 持久化暂不做：0-1 阶段优先解决核心体验问题（session 保留），
buffer 序列化需要引入 headless xterm，复杂度高且收益不在此阶段。
```

---

## 上下文材料：必须列出的阅读入口

Task Session 的 Context 章节必须包含以下材料清单，让接手者知道从哪读起。

### 必填项

| 材料类型 | 说明 | 示例 |
|----------|------|------|
| 相关 skill | 本次任务涉及的开发规范 | `frontend-pattern`、`api-dev`、`agent-dev` |
| 设计文档 | 设计分析、技术方案 | `design-draft/design/design-thinking/` 下的对应文档 |
| 入口代码 | 主要改动的代码文件 | `apps/backend/app/api/routes/terminal.py` |
| 参考实现 | 借鉴的外部项目或旧实现 | VS Code 终端 PTY 源码、旧版实现路径 |

### 可选项

| 材料类型 | 何时需要 |
|----------|----------|
| PRD / 需求文档 | 功能开发任务 |
| 相关 Task Session | 与历史任务有关联或继承关系 |
| 测试用例 | 回归验证需要参考现有测试 |

格式参考 TEMPLATE.md 的 2.2 节表格。

---

## 创建 Task Session

### 初始化

```bash
bash .agents/task-sessions/scripts/init-session.sh <type> "<description>" <version>
```

**参数说明：**
- `type`: 任务类型（feature, bugfix, refactor, research, docs）
- `description`: 任务描述（简洁明了）
- `version`: 版本号（如 v0.3.2）

### 创建后检查清单

以下检查项全部通过后才算"首版达标"，可以进入执行：

- [ ] Goal 和成功标准已填写，不是模板占位符
- [ ] Context 包含问题背景、约束条件、相关文档表格
- [ ] Scope Out 已明确写出，关键排除项有理由
- [ ] Execution Todos 包含 FE + BE + INT 三类表格
- [ ] 每个 Todo 有依赖、范围、交付物、验证方式、验收标准
- [ ] 阶段验收门已定义
- [ ] 相关 skill 和设计文档已列出

---

## Task Session 执行规则

### 规则 0：计划默认对齐目标态

当用户已经明确最终目标形态时，Task Session 必须默认围绕目标态组织计划与验收。不要把"MVP / 过渡版 / 先分阶段再说"当成默认计划模板。

### 规则 0a：未对齐先补文档，不直接开工

当任务目标、范围、验收标准尚未对齐时，Task Session 必须先承担对齐职责。先补 Goal / Scope / AC / Risks 等基线内容，在对齐完成前不推进实现。

### 规则 1：定期记录发现

每 2 次查看/搜索后，必须记录发现：

```markdown
### 查看的文件
- `src/api/mcp.ts` - MCP 配置接口定义
- `src/pages/Settings/MCPConfig.tsx` - 现有配置页面

### 关键发现
- 接口已支持 CRUD 操作
- 缺少批量导入功能
- UI 使用表单验证但缺少错误提示

### 下一步
- 设计批量导入界面
- 补充错误处理逻辑
```

### 规则 2：错误必须记录

所有错误必须记录到 Issues & Risks 章节。格式：

```markdown
## Issue-003: MCP 配置保存失败

**现象**: 点击保存后接口返回 500
**原因**: 请求体格式与后端期望不符（缺少 `version` 字段）
**解决方案**: 在提交前补充 version 字段
**状态**: 已解决
**时间**: 2026-03-30 11:00
```

### 规则 3：技术决策必须记录

所有技术决策必须记录到 Findings 的决策记录表。格式：

```markdown
| 决策 | 可选方案 | 选择理由 | 决策时间 |
|------|----------|----------|----------|
| 使用 React Hook Form | 原生表单 / Formik / React Hook Form | 减少样板代码、内置验证、更好的 TS 集成 | 2026-03-30 |
```

### 规则 4：中途插入的新任务默认排队

用户插入新问题时，默认继续当前主任务。新问题记录进 Queue，只有用户明确要求"立刻切换优先级"或当前任务被新 blocker 否定时，才中断。

### 规则 4a：优先新建 Task Session，不要膨胀已有 Session

与当前 Session 目标无关的新任务，优先创建新的 Task Session。一个 Session 只聚焦一个明确目标。文件超过 30KB 是警示线。

### 规则 5：控制 Task Session 大小，适时拆分

- 文件超过 20KB 时考虑拆分，超过 30KB 时必须拆分
- 跨越超过 3 个主要阶段时每个阶段结束后关闭当前 Session、新建继续
- 单个 Session 持续超过 2 天仍未完成时检查目标是否过大

### 规则 6：及时关闭与归档

Session 达到完成条件后立即从 `active/` 移动到 `completed/`。不要因为"后续可能还要改"而拖延归档。如需后续跟进，在后续工作中列清，新建 Session 处理。

### 规则 7：进度实时更新

每次阶段性完成后更新 Progress Log，包含：当前状态、已完成项、进行中项、阻塞项、下一步。

---

## Task Session 关闭

### 完成条件检查

- [ ] 所有计划任务已完成
- [ ] Summary 部分已填写
- [ ] 最终状态已记录
- [ ] 执行边界（Scope Out）中的排除项已确认未误入
- [ ] 代码已提交（遵循提交规范）

### 关闭命令

```bash
# 使用脚本
bash .agents/task-sessions/scripts/complete-session.sh <filepath>

# 或手动移动
mv .agents/task-sessions/active/<filename>.md .agents/task-sessions/completed/
```

### Summary 必填内容

```markdown
## Summary（总结）

**完成时间**: 2026-03-30
**实际耗时**: 4 小时
**目标达成**: 完全达成 / 部分达成 / 未达成
**主要交付**: [交付物列表]
**遗留问题**: [无 / 列出]
**后续工作**: [列出]
**文档同步**:
- [ ] 本轮是否修改了任何 skill 的 SKILL.md（包括 description、职责范围、关联引用）？
  - 是 → 搜索该 skill 名称在 `.agents/skills/` 下的所有引用，确认无失效引用
- [ ] 本轮是否修改了 AGENTS.md 的约束规则？
  - 是 → 检查受影响的 skill 是否需要同步更新
- [ ] 本轮是否新增/废弃/合并了 skill？
  - 是 → 搜索该 skill 名称在所有 skill 和 AGENTS.md 中的引用，更新或删除失效引用
```

---

## 任务闭环后的系统维护义务

本轮任务涉及 skill 的修改、合并、删除，或反复因同一文档/路径错误而失败时，结案前必须执行以下维护：

### 强制动作

1. **搜索关联引用**：搜索被修改 skill 的名称在 `.agents/skills/` 和 `AGENTS.md` 中的所有引用位置
2. **逐条判断**：不是所有引用都要改，只改那些因变更而失效或误导的引用（description 中的"不替代 XXX"声明、正文中的"详见 XXX"链接、关联 Skill 章节）
3. **同步更新**：如需更新，直接修改引用方的文档，并在 task session 中记录修改原因
4. **验证**：确认更新后所有引用路径可正常跳转

### 禁止行为

- 只在对话里描述引用失效，不碰文件
- 只在某一处修，放任其他引用同一失效信息的地方继续误导
- 把修复责任推给用户

---

## Task Session 文件结构

```
.agents/task-sessions/
├── README.md        # 使用说明（快速参考）
├── TEMPLATE.md      # Task Session 模板
├── active/          # 进行中（保持精简，不超过 3-5 个）
│   └── YYYY-MM-DD-{type}-{description}.md
├── paused/          # 暂停中（等待外部输入）
│   └── YYYY-MM-DD-{type}-{description}.md
├── completed/       # 已完成（按类型分目录）
│   ├── 01-feature/
│   ├── 02-refactor/
│   ├── 03-bugfix/
│   ├── 04-docs/
│   ├── 05-research/
│   ├── 06-perf/
│   └── 08-memory/
├── archive/         # 历史批量归档（含 handoffs 等）
│   └── ...
└── scripts/         # 管理脚本
    ├── init-session.sh
    ├── complete-session.sh
    ├── list-sessions.sh
    └── archive-old-sessions.sh
```

### 提交规则

**Task Session 是个人工作记录，不应提交到远程仓库。**

`.gitignore` 已排除 `active/`、`paused/`、`completed/`、`archive/`、`handoffs/` 等运行时目录。唯一允许提交的是 `scripts/` 管理脚本和 `TEMPLATE.md` 模板（项目共享）。

AI Agent 在 commit 时**不得**将 `.agents/task-sessions/` 下的 session 文件（含 README.md）加入暂存区。如果发现已提交，应立即 revert。

---

## 快速参考

| 动作 | 命令/操作 |
|------|-----------|
| 创建 Session | `bash .agents/task-sessions/scripts/init-session.sh <type> "<desc>" <version>` |
| 关闭 Session | `bash .agents/task-sessions/scripts/complete-session.sh <filepath>` |
| 列出活跃 Session | `bash .agents/task-sessions/scripts/list-sessions.sh` |
| 归档旧 Session | `bash .agents/task-sessions/scripts/archive-old-sessions.sh` |