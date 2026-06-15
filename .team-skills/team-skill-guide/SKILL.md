---
name: team-skill-guide
description: |
  团队 Skill 使用指南（团队版）。当 AI 首次进入本项目、需要了解有哪些 Skill、
  不知道某个任务该用哪个 Skill、或需要确认 Skill 触发边界时触发。
  适用于新会话初始化、任务开始前 Skill 选择、Skill 冲突时的决策参考。
  本文件为 AIASys 项目团队 Skill 路由总览，直接在项目仓库维护。
  不替代具体 Skill 的执行，只提供路由指引。
---

# 团队 Skill 使用指南

## 定位

本项目 AI 协作的 Skill 路由总览。告诉 AI 和团队成员：本项目有哪些 Skill、它们的分工、怎么组合使用。

## 目录结构

```
AIASys/
├── .team-skills/                ← 团队共享 Skill（本指南所在，git 跟踪）
│   ├── team-skill-guide/        ← 本指南：Skill 路由总览
│   ├── team-skill-governance/   ← 管理机制
│   ├── aiasys-frontend-architecture/
│   ├── aiasys-system-design/
│   ├── aiasys-git-workflow/
│   ├── aiasys-skill-maintenance/  ← 新增：Skill 维护工作流
│   ├── aiasys-tool-dev/
│   ├── api-dev/
│   ├── frontend-pattern/
│   ├── frontend-screenshot/
│   ├── frontend-visual-review/
│   ├── sop-workflow/
│   ├── state-flow/
│   ├── workspace-ops/
│   └── ...
│
└── .kimi-code/skills/           ← 个人 CLI 读取入口
```

## Skill 快速选择表

| 用户意图/关键词 | 进入 Skill | 说明 |
|---|---|---|
| AI 应该怎么说话、输出格式、对话风格 | `ai-output-guide` | AI 输出规范 |
| 写文件、Markdown 格式、长文、笔记 | `writing-guide` | 写作场景规范 |
| 操作目录、移动文件、搜索仓库 | `workspace-ops` | 工作区操作指南 |
| 任务执行、判断诊断、交接闭环 | `task-protocol` | 任务执行协议 |
| Git 提交、分支、PR、合并、冲突 | `aiasys-git-workflow` | Git 工作流 |
| PR 检查、提交前审查、合并前验证 | `pr-check` | PR 质量检查 |
| React 19、Tailwind 4、前端组件、UI 设计 | `aiasys-frontend-architecture` | 前端架构规范 |
| 系统架构设计、服务拆分、模块边界 | `aiasys-system-design` | 系统架构规范 |
| Agent 开发、智能体设计、行为定义 | `aiasys-tool-dev` | Agent 工具开发规范 |
| API 设计、接口规范、数据格式 | `api-dev` | API 开发规范 |
| 前端模式、组件设计、状态管理 | `frontend-pattern` | 前端模式规范 |
| 前端截图、UI 测试、视觉回归 | `frontend-screenshot` | 前端截图规范 |
| 前端视觉验收、UI 问题定位与优化 | `frontend-visual-review` | 前端视觉验收与优化方法论 |
| SOP 流程、标准操作程序 | `sop-workflow` | SOP 工作流规范 |
| 状态流、状态机、流程控制 | `state-flow` | 状态流规范 |
| 团队 Skill 怎么管理、怎么添加新 Skill | `team-skill-governance` | 管理机制 |
| 代码变更后如何同步更新团队 Skill | `aiasys-skill-maintenance` | Skill 维护工作流 |
| 不知道用哪个 Skill、Skill 冲突 | `team-skill-guide`（本指南） | 路由决策 |

## 强制读取顺序

**新会话开始时**：
1. 先读 `ai-output-guide`（AI 输出规范）
2. 再读本指南（Skill 路由）
3. 然后根据任务类型进入具体 Skill

**任务执行时**：
- 涉及 Git → 读 `aiasys-git-workflow`
- 涉及代码变更后同步更新 Skill → 读 `aiasys-skill-maintenance`
- 涉及前端开发 → 读 `aiasys-frontend-architecture`
- 涉及前端验收、截图后发现 UI 问题 → 读 `frontend-visual-review`
- 涉及系统架构 → 读 `aiasys-system-design`
- 涉及 Agent 开发 → 读 `aiasys-tool-dev`
- 涉及 API 设计 → 读 `api-dev`
- 涉及文件/目录操作 → 读 `workspace-ops`
- 涉及写作/文档 → 读 `writing-guide`
- 涉及任务执行 → 读 `task-protocol`
- 涉及 Skill 管理 → 读 `team-skill-governance`

## 团队 Skill 更新了怎么办

`.team-skills/` 是 AIASys 项目仓库的一部分，通过 git 管理，获取更新和获取代码一样：

```bash
git pull
```

**更新后**：AI 工具会在下次会话时自动读取最新的 `.team-skills/` 内容，不需要额外操作。

## 发现问题怎么反馈与修改

团队 Skill 直接在 `.team-skills/` 中维护，发现问题时可以：

| 问题类型 | 处理方式 |
|---------|---------|
| 内容错误、描述不准确 | 直接提交 PR 修改 `.team-skills/<skill>/SKILL.md`，或在群里/提 Issue 讨论 |
| 缺少某个能力 | 说明需求场景；可以由团队成员直接在 `.team-skills/` 中新建 Skill，或先由个人在私人 Skill 中验证后再提炼为团队 Skill |
| 改进建议 | 通过 Issue / PR / 群聊提出 |

> **注意**：`.team-skills/` 不是从私人 Skill 部署而来。直接在 `.team-skills/` 中编辑的内容会被 git 跟踪，不会被任何部署脚本覆盖。

## 个人 Skill 和团队 Skill 怎么共存

| 维度 | 团队 Skill（`.team-skills/`） | 个人 Skill（`.kimi-code/skills/`） |
|------|------------------------------|-----------------------------------|
| **维护者** | AIASys 项目团队 | 个人 |
| **存放位置** | 项目仓库 `.team-skills/`，git 跟踪 | `.kimi-code/skills/` 索引卡片，指向 pkm-hub 私人源码 |
| **内容** | 去敏、自包含、通用 | 可含个人配置、私有路径 |
| **更新方式** | 直接在 `.team-skills/` 中编辑，随项目 git 提交 | 修改 pkm-hub 私人源码仓库后运行 `deploy.py` 生成索引卡片 |
| **适用对象** | 团队所有成员 | 仅自己 |

**核心原则**：
- 团队 Skill 的创新和迭代直接在 `.team-skills/` 中进行。
- 个人 Skill 的创新和迭代在 pkm-hub 私人源码仓库中进行，通过 `deploy.py` 部署到 `.kimi-code/skills/`。
- 两者解耦、可重复、不自动同步。
- 个人 Skill 中沉淀出项目通用经验后，可以**提炼重写**为新的团队 Skill；团队 Skill 中的好方法也可以被个人吸收进自己的私人 Skill。

## Skill 边界说明

### 本项目的 Skill 不包含

- 个人敏感 Skill（`user-profile`、`baidu-pan-manager` 等）
- 其他项目专属 Skill（`afac2026-*`、`wenyan-cli-ops` 等）

### 如果需要这些能力

本项目没有的能力，AI 应明确告知用户"本项目未配置该 Skill"。

## 解耦原则

团队 Skill 与个人 Skill 是两套独立池子：

1. **不自动同步**：`.team-skills/` 的改动不回写 `.kimi-code/skills/`，反之亦然。
2. **不互相依赖**：团队 Skill 必须自包含，不引用 `.team-skills/` 外的 Skill 路径或内容。
3. **不直接复制**：把私人 Skill 放进 `.team-skills/` 时，必须提炼重写为项目通用视角，不能原样搬运。
4. **经验双向流动**：私人 Skill 用得好可以贡献精华到团队 Skill；团队 Skill 的好方法也可以被个人吸收进私人 Skill。但都是手动提炼，不是自动同步。

如果需要外部 Skill 的能力：
- 直接在 `.team-skills/` 中编写团队版本
- 或向团队提议，由成员提炼后纳入

## 输出规范

被调用时，AI 应：
1. 列出当前项目可用的 Skill
2. 根据用户意图推荐最匹配的 Skill
3. 说明推荐理由和 Skill 边界
4. 如需涉及 Skill 修改，明确区分：
  - `.team-skills/` 中的 Skill 直接在 AIASys 仓库修改
  - `.kimi-code/skills/` 中的私人 Skill 需修改 pkm-hub 源码后运行 `deploy.py`
5. 不直接执行具体任务（只指路，不代劳）
