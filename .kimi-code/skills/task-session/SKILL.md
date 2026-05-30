---
name: task-session
description: Manage complex development tasks using Task Session workflow. Use when starting complex multi-step tasks (3+ steps), tasks spanning multiple AI interactions, research/exploration tasks, or tasks requiring decision tracking. This skill guides you through creating, maintaining, and closing Task Sessions with proper documentation and traceability. Always use this skill when the user asks to create a task session or when a task feels complex enough to need structured tracking.
---

# Task Session 管理

结构化追踪复杂任务，确保过程可控、决策可追溯、交付可验证。

---

## 何时使用 Task Session

**必须使用：**
- 复杂多步骤任务（3+ 步骤）
- 预计跨越多次 AI 交互的任务
- 需要研究/探索的任务
- 需要记录决策过程的任务

**可以使用：**
- 需要跟踪进度的长期任务
- 涉及多个文件修改的 refactor
- 需要分阶段验收的功能开发

---

## 创建 Task Session

### 初始化命令

```bash
bash .agents/task-sessions/scripts/init-session.sh <type> "<description>" <version>
```

**参数说明：**
- `type`: 任务类型（feature, bugfix, refactor, research, docs）
- `description`: 任务描述（简洁明了）
- `version`: 版本号（如 v0.3.2）

**示例：**
```bash
bash .agents/task-sessions/scripts/init-session.sh feature "实现 MCP 配置页面" v0.3.2
```

### 创建后检查清单

- [ ] Session 目录已创建（`.agents/task-sessions/active/YYYY-MM-DD-{id}/`）
- [ ] `plan.md` 已生成并包含任务目标
- [ ] `decisions.md` 已创建
- [ ] `issues-risks.md` 已创建
- [ ] `progress.md` 已创建

---

## Task Session 执行规则

### 规则 0：计划默认对齐目标态

**当用户已经明确最终目标形态时，Task Session 必须默认围绕目标态组织计划与验收：**

- 不要把“MVP / 过渡版 / 先分阶段再说”当成默认计划模板
- 只有在复杂度、风险、写集冲突确实需要时，才把任务拆成阶段
- 即使内部拆阶段，Session 也必须写清最终目标态，避免文档口径退化成中间态
- 若采用阶段化执行，必须在决策记录里说明为什么不能直接到位

### 规则 0a：未对齐先补文档，不直接开工

**当任务目标、范围、验收标准尚未对齐时，Task Session 必须先承担对齐职责，而不是直接推进实现：**

- 先补 Goal / Scope / AC / Risks 等基线内容
- 需要时先补 PRD、需求确认单或验收清单
- 在对齐完成前，Session 可以记录调研、方案比较和风险识别
- 不要把“先写一版代码再回来补文档”当成默认工作方式

### 规则 1：定期记录发现

**每 2 次查看/搜索后，必须记录发现：**

```markdown
## 2026-03-30 10:30

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

**所有错误必须记录到 `issues-risks.md`：**

```markdown
## Issue-003: MCP 配置保存失败

**现象**: 点击保存后接口返回 500
**原因**: 请求体格式与后端期望不符（缺少 `version` 字段）
**解决方案**: 在提交前补充 version 字段
**状态**: 已解决
**时间**: 2026-03-30 11:00
```

### 规则 3：技术决策必须记录

**所有技术决策必须记录到 `decisions.md`：**

```markdown
## DEC-004: 使用 React Hook Form 替代原生表单

**决策**: 采用 React Hook Form + Zod 进行表单管理
**理由**:
- 减少样板代码
- 内置验证支持
- 更好的 TypeScript 集成
**替代方案**: 原生表单（代码量大）、Formik（包体积大）
**决策时间**: 2026-03-30
**影响范围**: MCPConfig 页面及后续配置类页面
```

### 规则 4：中途插入的新任务默认排队，不打断当前主任务

**当用户在当前任务尚未完成时继续插入新问题：**

- 默认继续完成当前正在执行的主任务
- 不要因为用户补充了一个新 bug，就立刻放下当前修复切去做新问题
- 必须把新问题记录进当前 task session 的 `待解决问题`、`下一步计划` 或新增子任务说明里
- 只有用户明确要求“立刻切换优先级”或当前任务已被新 blocker 否定时，才中断当前任务

推荐记录格式：

```markdown
## Queue

- P1 当前主任务：修复正在处理的问题，直到验证与提交完成
- P2 排队问题：用户中途插入的新 bug，记录现象与复查条件，待当前任务结束后再检查
```

### 规则 4：进度实时更新

**每次阶段性完成后更新 `progress.md`：**

```markdown
## 当前状态
- **整体进度**: 65%
- **当前阶段**: 实现编码 (SOP-03)

## 已完成
- [x] 需求分析
- [x] 架构设计
- [x] 接口联调
- [x] 基础 UI 实现

## 进行中
- [ ] 批量导入功能

## 阻塞项
- 等待设计团队提供批量导入模板

## 下一步
1. 完成批量导入 UI
2. 联调批量导入接口
3. 编写单元测试
```

---

## Task Session 关闭

### 完成条件检查

关闭 Task Session 前必须确认：

- [ ] 所有计划任务已完成
- [ ] `progress.md` 已更新为 100%
- [ ] 最终状态已记录
- [ ] 需求基线已同步更新（如适用）
- [ ] 实现状态已同步（如适用）

### 关闭命令

```bash
# 手动归档 Session 目录
mv .agents/task-sessions/active/2026-03-30-feature-mcp-config \
   .agents/task-sessions/archive/2026-03-30-feature-mcp-config
```

### 最终文档更新

**关闭时必须完成：**

1. **更新任务基线**（如果是功能开发）
   - 回写当前 active task session 的 Goal / Scope / AC / 风险
   - 如有长期规则沉淀价值，再同步到对应 skill

2. **记录实现证据**
   - 在当前 task session 中补齐测试、验证和交付证据
   - 如用户明确要求，再同步到人类文档

3. **编写完成总结**
   - 在 `progress.md` 末尾添加：
   ```markdown
   ## 完成总结
   
   **完成时间**: 2026-03-30
   **实际耗时**: 4 小时
   **主要交付**: MCP 配置页面（含批量导入）
   **技术决策**: 使用 React Hook Form
   **遗留问题**: 无
   ```

---

## Task Session 文件结构

```
.agents/task-sessions/
├── active/
│   └── YYYY-MM-DD-{type}-{description}/
│       ├── plan.md          # 任务计划
│       ├── decisions.md     # 技术决策记录
│       ├── issues-risks.md  # 问题与风险
│       ├── progress.md      # 进度跟踪
│       └── notes/           # 临时笔记
│           └── exploration-*.md
└── archive/                 # 已完成的 Session
    └── ...
```

---

## 快速参考

| 动作 | 命令/操作 |
|------|-----------|
| 创建 Session | `bash .agents/task-sessions/scripts/init-session.sh <type> "<desc>" <version>` |
| 记录决策 | 编辑 `decisions.md` |
| 记录问题 | 编辑 `issues-risks.md` |
| 更新进度 | 编辑 `progress.md` |
| 关闭 Session | 移动目录到 `archive/` |

---

*Task Session 是复杂任务的保险绳——用它确保不遗漏、可追溯、高质量交付。*
