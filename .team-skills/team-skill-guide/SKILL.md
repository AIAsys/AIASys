---
name: team-skill-guide
description: |
  团队 Skill 使用指南（团队版）。当 AI 首次进入本项目、需要了解有哪些 Skill、
  不知道某个任务该用哪个 Skill、或需要确认 Skill 触发边界时触发。
  适用于新会话初始化、任务开始前 Skill 选择、Skill 冲突时的决策参考。
  本文件为团队消费版，私有完整版见源码仓库 skills/_global/team-skill-guide/。
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
│   ├── aiasys-tool-dev/
│   ├── api-dev/
│   ├── frontend-pattern/
│   ├── frontend-screenshot/
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
| React 19、Tailwind 4、前端组件、UI 设计 | `aiasys-frontend-architecture` | 前端架构规范 |
| 系统架构设计、服务拆分、模块边界 | `aiasys-system-design` | 系统架构规范 |
| Agent 开发、智能体设计、行为定义 | `aiasys-tool-dev` | Agent 工具开发规范 |
| API 设计、接口规范、数据格式 | `api-dev` | API 开发规范 |
| 前端模式、组件设计、状态管理 | `frontend-pattern` | 前端模式规范 |
| 前端截图、UI 测试、视觉回归 | `frontend-screenshot` | 前端截图规范 |
| SOP 流程、标准操作程序 | `sop-workflow` | SOP 工作流规范 |
| 状态流、状态机、流程控制 | `state-flow` | 状态流规范 |
| 团队 Skill 怎么管理、怎么添加新 Skill | `team-skill-governance` | 管理机制 |
| 不知道用哪个 Skill、Skill 冲突 | `team-skill-guide`（本指南） | 路由决策 |

## 强制读取顺序

**新会话开始时**：
1. 先读 `ai-output-guide`（AI 输出规范）
2. 再读本指南（Skill 路由）
3. 然后根据任务类型进入具体 Skill

**任务执行时**：
- 涉及 Git → 读 `aiasys-git-workflow`
- 涉及前端开发 → 读 `aiasys-frontend-architecture`
- 涉及系统架构 → 读 `aiasys-system-design`
- 涉及 Agent 开发 → 读 `aiasys-tool-dev`
- 涉及 API 设计 → 读 `api-dev`
- 涉及文件/目录操作 → 读 `workspace-ops`
- 涉及写作/文档 → 读 `writing-guide`
- 涉及任务执行 → 读 `task-protocol`
- 涉及 Skill 管理 → 读 `team-skill-governance`

## 团队 Skill 更新了怎么办

`.team-skills/` 通过 git 管理，获取更新和获取代码一样：

```bash
git pull
```

**更新后**：AI 工具会在下次会话时自动读取最新的 `.team-skills/` 内容，不需要额外操作。

## 发现问题怎么反馈

如果你在使用团队 Skill 时发现问题或改进建议：

| 问题类型 | 怎么反馈 |
|---------|---------|
| 内容错误、描述不准确 | 在群里告知管理员，或提交 Issue |
| 缺少某个能力 | 说明需求场景，由管理员在个人 Skills 中开发 |
| 改进建议 | 通过 Issue 或群聊提出 |

> **注意**：`.team-skills/` 的内容由管理员在个人 Skills 中验证后统一部署。团队不直接编辑 `.team-skills/` 中的 Skill 内容。直接修改会被下次部署覆盖。

## 个人 Skill 和团队 Skill 怎么共存

| 维度 | 团队 Skill（`.team-skills/`） | 个人 Skill（`.kimi-code/skills/`） |
|------|------------------------------|-----------------------------------|
| **维护者** | 管理员（基于个人 Skills 部署） | 个人 |
| **存放位置** | 项目仓库 `.team-skills/`，git 跟踪 | 个人环境，符号链接 |
| **内容** | 去敏、自包含、通用 | 可含个人配置、私有路径 |
| **更新方式** | 管理员部署 | 个人手动维护 |
| **适用对象** | 团队所有成员 | 仅自己 |

**核心原则**：所有 Skill 的创新和迭代都在个人 Skills 中进行。`.team-skills/` 是经过实战验证后部署到团队的消费层。

## Skill 边界说明

### 本项目的 Skill 不包含

- 个人敏感 Skill（`user-profile`、`baidu-pan-manager` 等）
- 其他项目专属 Skill（`afac2026-*`、`wenyan-cli-ops` 等）

### 如果需要这些能力

本项目没有的能力，AI 应明确告知用户"本项目未配置该 Skill"。

## 解耦原则

团队 Skill 必须自包含，禁止：

1. **引用外部 Skill 的路径** —— 所有引用必须在 `.team-skills/` 内部
2. **依赖外部 Skill 的内容** —— 团队 Skill 独立维护
3. **暴露外部 Skill 的存在** —— 不提及团队外的 Skill 仓库或来源

如果需要外部 Skill 的能力：
- 向管理员反馈，由管理员评估后纳入
- 或重新编写团队版本

## 输出规范

被调用时，AI 应：
1. 列出当前项目可用的 Skill
2. 根据用户意图推荐最匹配的 Skill
3. 说明推荐理由和 Skill 边界
4. 不直接执行具体任务（只指路，不代劳）
