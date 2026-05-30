# Skills 正式使用区

本目录是开发 AIASys 的 AI Agent 使用的协作 skill。不是 AIASys 产品的功能 skill。

---

## 两个 Skill 系统

| | 协作 Skill（本目录） | 产品 Skill |
|---|---|---|
| 位置 | `.agents/skills/` | `apps/backend/skills/builtin/` |
| 读者 | 开发 AIASys 的 AI | AIASys 内置 Agent |
| 管理 | pkm-hub | 随系统部署 |
| 示例 | `frontend-pattern`、`api-dev` | `aiasys-platform-skill`、`paddleocr-skill` |

**不要混淆**：协作 skill 里出现了 `competition-research-skill`、`arxiv-search-skill` 这类名称，说明产品 skill 被错放了，需要移到 `apps/backend/skills/builtin/`。

---

## Skill 清单（28 个正式 + 6 个归档）

### 系统约束层

定义 AIASys 项目的专属约束，优先级高于通用 skill。

| Skill | 用途 |
|---|---|
| `aiasys-ai-integration` | 区分"开发 AIASys 的 AI"和"AIASys 内置的 Agent"，约束开发行为 |
| `aiasys-system-design` | 系统设计约束（信息架构、设置/市场/任务分离、能力接入模型） |
| `aiasys-product-requirements` | 产品需求与 PRD 工作流 |

### 开发实现

| Skill | 用途 |
|---|---|
| `frontend-pattern` | 前端开发完整规范（架构取舍 + React 19/Tailwind 4/shadcn/ui + 性能优化规则） |
| `api-dev` | FastAPI 后端 API 开发 |
| `agent-dev` | AIASys 内置 Agent 的工具开发（Tool、沙盒、状态管理、流式输出） |
| `agent-test-cases` | Agent 能力测试用例的收集与管理 |
| `database-model` | SQLAlchemy 模型设计与数据库迁移 |
| `infra-dev` | 部署与基础设施配置 |

### Agent 平台核心

| Skill | 用途 |
|---|---|
| `llm-prompt-engineering` | Prompt 模板管理、多协议 Client、Token 预算、上下文压缩 |
| `sse-real-time-communication` | SSE 事件流、多 session 并行、竞态防护 |
| `python-runtime-sandbox` | IPython Kernel 执行、UV 环境管理、Docker 沙盒 |
| `mcp-protocol` | MCP 配置合并、Client 连接管理、工具注册桥接 |

### 流程与协作

| Skill | 用途 |
|---|---|
| `todo-orchestration` | Todo 清单设计与静默执行 |
| `task-session` | 复杂多步骤任务的会话跟踪 |
| `git-workflow` | Git 提交、分支、PR 工作流 |
| `gen-docs` | 文档维护（changelog、双语同步、归档） |
| `doc-sync` | 文档-代码映射索引、变更触发规则 |
| `cx` | 语义化代码导航（tree-sitter 代码探索） |

### 质量保障

| Skill | 用途 |
|---|---|
| `testing-strategy` | pytest 异步测试、测试隔离、Playwright E2E |
| `browser-control` | 浏览器控制与前端验证（截图取证、交互验收） |
| `bug-discovery` | Bug 发现、跟踪、修复、验证完整工作流 |
| `code-simplification` | 简化代码，保持行为一致 |
| `performance-optimization` | 基于测量的性能优化 |
| `security-hardening` | 安全加固 |
| `deprecation-and-migration` | 废弃旧系统与迁移 |
| `aiasys-resource-verification` | MCP、知识库、知识图谱、数据库统一验证 |

### 工具参考

| Skill | 用途 |
|---|---|
| `kimi-cli-handbook` | Kimi CLI 工具完整参考手册 |

---

## 使用原则

- 新任务先读仓库根 `AGENTS.md` 确定语义，再按需读取 skill
- 系统约束层（`aiasys-*`）优先于通用 skill 读取
- `docs/` 给人类看，skill 给 AI 执行，不要混用

---

## 归档

`archive/` 下有两类归档：

**旧规则系统（`.ai-rules/`）**：早期用 `.ai-rules/` 目录管理的规则体系，已迁移到 skill 模式。保留供参考，不再使用。

**废弃 skill（6 个）**：

| Skill | 废弃原因 |
|---|---|
| `gh-skill-manager` | gh CLI 已不再用于管理 skill，pkm-hub 统一接管 |
| `pencil-design` | Pencil MCP 工具不再使用 |
| `pencil-render-review` | Pencil MCP 工具不再使用 |
| `refero-design` | Refero MCP 工具不再使用 |
| `state-flow` | 状态流设计已融入 `frontend-pattern` |
| `tokscale` | 工具参考，非开发规范 |