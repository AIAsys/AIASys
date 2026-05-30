---
name: project-memory
description: |
  AIASys 项目的持久工作记忆系统。管理 `.agents/MEMORY.md` 的读写、SessionStart 自动注入、
  SessionEnd 记忆增量提取。定义两层记忆模型（项目全局层 + Task Session 层）、
  写 memory 时机判定、格式规范。当需要写入项目级架构决策、已知陷阱、约定偏好，
  或需要从 session 中提取长期记忆时使用。
---

# 项目 Memory 系统

AIASys 项目的持久工作记忆，采用**两层模型 + Hook 自动化**架构。
设计参考 AIASys 内置 Memory 系统的核心哲学（追加优先、容量感知、冻结快照），
但适配项目开发场景的简化实现。

---

## 两层模型

### 层 1：项目全局层 — `.agents/MEMORY.md`

- **作用域**：跨 session、跨 Agent 共享的项目级知识
- **存储位置**：`.agents/MEMORY.md`（已在 `.gitignore` 中）
- **内容模块**：
  - 架构决策：重大技术选型、取舍理由
  - 当前状态：项目进度、已完成/进行中/待做
  - 已知陷阱：跨环境路径映射、Hook 作用域等容易踩的坑
  - 约定与偏好：语言选择、包管理、分支策略
  - 待解决问题：未决事项和阻塞项
- **容量上限**：暂无硬限制，但建议控制在 5000 字符以内，保持精简可读

### 层 2：Task Session 层 — `.agents/task-sessions/`

- **作用域**：单个任务的上下文记忆
- **存储位置**：`.agents/task-sessions/active/`、`completed/`
- **内容**：任务目标、执行过程、技术决策、发现与风险
- **生命周期**：任务完成后归档到 `completed/`

---

## 何时写 Memory

### 必须写入（全局层）

以下事件发生时，Architect 必须将决策写入 `.agents/MEMORY.md`：

1. **架构决策**：技术选型、设计模式选择、取舍理由
2. **已知陷阱**：新发现的跨环境问题、工具限制、踩坑经验
3. **约定变更**：语言/工具/分支策略的变更
4. **状态变更**：重要模块的完成或废弃

### 不必写入

- 单次操作的临时状态（在 Task Session 中记录）
- 已经体现在代码中的实现细节
- 尚未验证的假设（标记为"待验证"后可写）

---

## 何时读 Memory

### 自动注入（Hook 驱动）

SessionStart hook（`memory-session-start.sh`）在每次新 session 启动时自动将 `.agents/MEMORY.md` 内容注入上下文。
Agent 不需要手动读取——memory 已经在上下文中。

### 手动查阅

以下场景需要主动读取 `.agents/MEMORY.md`：

- Memory 内容较长，Hook 注入可能被截断
- 需要确认某个具体决策的最新状态
- 长 session 中 memory 可能已被其他 session 更新

---

## 格式规范

`.agents/MEMORY.md` 使用以下固定结构：

```markdown
# AIASys 项目工作记忆

> 持久工作记忆。由 Architect 在 session 结束时更新。
> 按模块组织，不是时间线。
> 最后更新：YYYY-MM-DD

---

## 架构决策
...

## 当前状态
...

## 已知陷阱
...

## 约定与偏好
...

## 待解决问题
...
```

### 条目格式

- **架构决策**：`- **决策名称**：决策内容。理由：...`
- **已知陷阱**：`- **陷阱名称**：现象描述。规避方法：...`
- **约定与偏好**：`- 类别：具体约定`
- **当前状态**：`- 模块名：当前状态描述`

---

## Session 生命周期

```
SessionStart Hook 自动注入 MEMORY.md
        │
        ▼
Agent 读取 AGENTS.md + Task Sessions（启动协议）
        │
        ▼
Agent 执行任务（可能写入 Task Session 层）
        │
        ▼
Stop Hook 提醒输出记忆增量
        │
        ▼
Architect 合并记忆增量到 .agents/MEMORY.md（结束协议）
```

---

## 与 AIASys 内置 Memory 系统的关系

本 skill 管理的项目 Memory 系统参考了 AIASys 内置 Memory 的以下设计哲学：

| 哲学 | 本项目实现 |
|------|-----------|
| 两层分离 | 全局层（`.agents/MEMORY.md`）+ Task Session 层 |
| Markdown 优先 | 纯 Markdown 文件，人机可读 |
| 追加优先，整理懒执行 | 默认追加，只在内容过长时手动整理 |
| 冻结快照 | SessionStart 注入后本 session 内不自动刷新 |
| 容量感知 | 建议 5000 字符上限 |

与 AIASys 内置 Memory 的差异：
- 本项目**没有** Stage 1/2 自动流水线（暂不需要 LLM 自动提取和整理）
- 本项目**没有** SQLite 状态管理（简化实现）
- 本项目**没有** 安全扫描（项目内部文件，不暴露给外部 Agent）

---

## 快速参考

| 操作 | 方法 |
|------|------|
| 读取全局 memory | SessionStart 自动注入；手动 `Read(.agents/MEMORY.md)` |
| 写入全局 memory | Architect 在 session 结束时更新 |
| 读取 task memory | `Read(.agents/task-sessions/active/<file>)` |
| 写入 task memory | 按 task-session skill 规范执行 |