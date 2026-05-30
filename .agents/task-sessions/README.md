# Task Session 使用说明

> 完整规范见 [.agents/skills/task-session/SKILL.md](../../skills/task-session/SKILL.md)

## 目录结构

```
.agents/task-sessions/
├── active/          # 进行中（保持 3-5 个以内）
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
├── archive/         # 历史批量归档
└── scripts/         # 管理脚本
```

## 快速操作

| 动作 | 命令 |
|------|------|
| 创建 Session | `bash scripts/init-session.sh <type> "<desc>" <version>` |
| 关闭 Session | `bash scripts/complete-session.sh <filepath>` |
| 列出活跃 Session | `bash scripts/list-sessions.sh` |
| 归档旧 Session | `bash scripts/archive-old-sessions.sh` |

## 核心原则

1. **别人能接手的水平**：另一个 AI 打开文件后能直接继续，不需要回头问
2. **一个 Session 一个目标**：不膨胀已有 Session，新任务新建
3. **及时归档**：完成后立即从 active/ 移到 completed/，不拖延
4. **文件超过 30KB 必须拆分**

## 与 MEMORY.md 的关系

- Task Session：过程状态（临时，任务完成后归档）
- MEMORY.md：持久记忆（跨任务、跨 session 的决策和陷阱）

Session 结束后，关键决策应沉淀到 MEMORY.md。