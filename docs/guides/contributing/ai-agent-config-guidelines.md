# AI Agent 协作配置提交指南

> 本文档说明哪些 AI Agent 相关的配置和文件**应该**提交到 Git 仓库，哪些**不应该**提交。

## 核心理念

AIASys 使用多种 AI 编码助手（Kimi Code、Claude Code、Codex CLI、Gemini CLI 等）进行日常开发。这些工具会产生各自的配置目录和入口文件。**大部分个人 AI 配置不应该进入项目仓库**，只有项目共享的 Agent 资源才应该提交。

## 不应提交的配置（已在 `.gitignore`）

以下目录和文件属于**个人 AI 协作配置**，已在仓库 `.gitignore` 中排除：

### AI CLI 配置目录

| 目录 | 用途 | 是否提交 |
|------|------|----------|
| `.kimi/` | Kimi CLI hooks 与配置 | 不提交 |
| `.kimi-code/` | Kimi Code CLI skills 与配置 | 不提交 |
| `.claude/` | Claude Code 配置 | 不提交 |
| `.codex/` | Codex CLI 配置 | 不提交 |
| `.codex-runs/` | Codex 运行记录 | 不提交 |
| `.gemini/` | Gemini CLI 配置 | 不提交 |
| `.opencode/` | OpenCode CLI 配置 | 不提交 |
| `.qwen/` | Qwen CLI 配置 | 不提交 |
| `.playwright/` | Playwright 浏览器数据 | 不提交 |
| `.playwright-mcp/` | Playwright MCP 数据 | 不提交 |
| `.agent/` | 通用 Agent 配置 | 不提交 |
| `.memo/` | 个人备忘录 | 不提交 |
| `.temp/` | 临时文件 | 不提交 |
| `.entire` | 个人快照文件 | 不提交 |
| `.acp_agent/` | ACP Agent 配置 | 不提交 |

### 个人 AI 协作入口文件

| 文件 | 用途 | 是否提交 |
|------|------|----------|
| `AGENTS.md` | 个人 Agent 协作章程（根目录） | 不提交 |
| `CLAUDE.md` | Claude Code 入口指令 | 不提交 |
| `GEMINI.md` | Gemini CLI 入口指令 | 不提交 |

这些文件是每个开发者根据自己的 AI 工具链和协作偏好定制的，**不应强制统一**。

## `.agents/` 目录的提交规则

`.agents/` 目录结构如下，提交规则按子目录区分：

| 路径 | 内容 | 是否提交 |
|------|------|----------|
| `.agents/MEMORY.md` | 项目工作记忆（架构决策、已知陷阱） | **提交** |
| `.agents/skills/` | 项目共享 Skill 定义 | **提交** |
| `.agents/task-sessions/TEMPLATE.md` | Task Session 模板 | **提交** |
| `.agents/context/` | Agent 运行时上下文 | 不提交 |
| `.agents/task-sessions/active/` | 活跃任务会话 | 不提交 |
| `.agents/task-sessions/archive/` | 归档任务会话 | 不提交 |
| `.agents/task-sessions/completed/` | 已完成任务会话 | 不提交 |
| `.agents/task-sessions/handoffs/` | 交接文件 | 不提交 |
| `.agents/mcp.local.json` | 本地 MCP 配置（含密钥） | 不提交 |
| `.agents/skill-development/` | Skill 开发区 | 不提交 |

### 为什么 `.agents/skills/` 要提交？

`.agents/skills/` 中的 Skill 定义是**项目共享的开发规范**，例如：

- `api-dev` — FastAPI 后端开发规范
- `frontend-pattern` — React 前端开发规范
- `testing-strategy` — 测试策略
- `github-project-management` — GitHub 项目管理规范

这些 Skill 帮助所有协作者使用统一的 AI 编码规范，是项目基础设施的一部分。

### 为什么 `.agents/MEMORY.md` 要提交？

`MEMORY.md` 记录了项目的架构决策、已知陷阱和约定偏好。新加入的协作者通过它快速了解项目的"隐性知识"，AI 助手也能在会话启动时自动加载这些上下文。

## 如何判断是否应该提交？

简单原则：

1. **所有开发者都需要的东西** → 提交（如 Skill 定义、Memory）
2. **只有你个人需要的东西** → 不提交（如个人 AI CLI 配置、个人入口文件）
3. **包含敏感信息的东西** → 不提交（如 `.env`、`mcp.local.json`）
4. **运行时生成的临时数据** → 不提交（如 task sessions、context）

## 相关链接

- [`.gitignore`](../../.gitignore) — 完整的忽略规则
- [CONTRIBUTING.md](../../../CONTRIBUTING.md) — 贡献指南
- [`.agents/skills/`](../../.agents/skills/) — 项目共享 Skill