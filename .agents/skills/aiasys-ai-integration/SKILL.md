---
name: aiasys-ai-integration
description: 区分"开发 AIASys 的 AI"和"AIASys 内置的 Agent"，约束开发 AIASys 时的 Agent 行为规范。当讨论 AIASys 的 Agent 系统架构、Hook 机制、或需要明确两类 Agent 的边界时使用。
---

# AIASys AI 集成规范

明确两个 Agent 系统的边界，约束开发 AIASys 时的 Agent 行为。

---

## 核心概念：两个 Agent 系统

AIASys 项目涉及两个完全不同的 Agent 系统，它们运行在不同的上下文、使用不同的工具集、服务于不同的目的。

### 系统一：开发 AIASys 的 AI（我们）

**这是谁**：正在读这段文字的 AI。Kimi CLI、Claude Code、或任何被用户用来开发 AIASys 代码的 AI 助手。

**运行位置**：用户的开发机上，通过 CLI 工具与文件系统和 shell 交互。

**工具集**：Shell、ReadFile、WriteFile、Grep、Glob、Agent 等本地开发工具。

**读取的规范**：`.agents/skills/` 下的协作 skill（`frontend-pattern`、`api-dev`、`agent-dev` 等）。

**管理方式**：协作 skill 由 pkm-hub 统一管理，开发区在 `pkm-hub/resources/xiaoke-project-skill/aiasys/skill-development/`，正式区在 `pkm-hub/resources/xiaoke-project-skill/aiasys/skills/`，运行时镜像在 `.agents/skills/`。

**职责**：
- 编写、修改、调试 AIASys 的源代码
- 设计系统架构和产品功能
- 修复 bug、优化性能
- 维护文档和规范

**关键约束**：
- 必须遵守 `AGENTS.md` 中的编码规范
- 必须遵守 `.agents/skills/` 中的协作 skill
- 不能把 AIASys 内置 Agent 的工具当作自己的工具使用
- 不能假设 AIASys 内置 Agent 的能力边界等同于自己的能力边界

### 系统二：AIASys 内置的 Agent（它们）

**这是谁**：运行在 AIASys 产品内部的 Agent。用户在 AIASys 工作平台中与之交互的智能体。

**运行位置**：AIASys 后端服务进程中，通过 `apps/backend/app/agents/` 下的 Agent 运行时执行。

**工具集**：由 AIASys 后端 `app/services/agent/system_presets.py` 注册的工具，包括：
- 文件操作工具（读/写/搜索工作区文件）
- Python 运行时工具（LocalIPythonBox、Notebook）
- Skill 管理工具（SearchStoreSkills、EnableSkill、DisableSkill、ListSkills、LoadSkill）
- MCP 工具桥接
- 子 Agent 委派工具（TaskTool / AgentTool）
- 知识图谱工具
- 浏览器工具
- Auto Task 工具

**读取的 Skill**：`apps/backend/skills/builtin/` 下的系统内置 skill（`aiasys-platform-skill`、`paddleocr-skill`、`pdf-translate-skill` 等）。

**管理方式**：Skill 采用全局源仓库 + 工作区副本的两层架构。安装 = `enable_skill`（`shutil.copytree` 从源复制到工作区副本），卸载 = `disable_skill`（`shutil.rmtree` 删副本）。

**职责**：
- 在用户的工作区中执行任务
- 调用 Skill 完成领域相关工作
- 通过 MCP 与外部服务交互
- 配合 Auto Task 做持续循环执行

**关键约束**：
- 运行在工作区上下文中，文件操作限定在工作区范围内
- 通过沙盒执行用户代码
- 工具列表由工作区配置决定，不是所有工具都默认加载
- 子 Agent 默认和主控共用当前工作区、全局工作区和会话上下文

---

## 开发 AIASys 的 Agent 行为规范

以下规范约束的是"开发 AIASys 的 AI"（即我们），不是 AIASys 内置的 Agent。

### 规则 1：不混淆两个 Agent 系统的能力

当我们讨论"Agent 的 hooks 机制"、"Agent 的工具"、"Agent 的 skill" 时，必须先明确说的是哪个系统。

| 概念 | 开发 AIASys 的 AI（我们） | AIASys 内置的 Agent（它们） |
|------|--------------------------|---------------------------|
| Hooks | `.claude/hooks/` 下的 shell/node 脚本，由 Claude Code 提供 | 暂无内置 hooks 机制 |
| Skills | `.agents/skills/` 下的协作 skill | `apps/backend/skills/builtin/` 下的产品 skill |
| 工具 | Shell、ReadFile、WriteFile、Grep 等 CLI 工具 | LocalIPythonBox、Skill 管理、MCP 桥接等运行时工具 |
| 配置文件 | `AGENTS.md`、`.claude/settings.json` | `workspace.json`、`.aiasys/` 下的工作区配置 |
| 运行环境 | 开发机 shell | AIASys 后端进程 + 沙盒 |

**反例**：
- "AIASys 的 Agent 有 hooks 机制" —— 实际是 `.claude/hooks/` 给 Claude Code 用的，不是 AIASys 产品功能
- "在 Agent 工具里加一个 hook" —— 要先确认是给哪个 Agent 系统加

### 规则 2：给 AIASys 内置 Agent 加功能时，不照搬我们的工具

AIASys 内置 Agent 的工具集和我们（开发 AI）的工具集是两套完全不同的实现。

- 我们要读文件 → 用 `ReadFile`（Kimi CLI 提供）
- AIASys 内置 Agent 要读文件 → 用后端实现的文件操作工具（`app/agents/tools/` 下的实现）

- 我们有 `.claude/hooks/` 做 pre/post tool hook
- AIASys 内置 Agent 如果要 hooks → 需要在后端 Agent 运行时中从零设计

**不要做的事**：
- 把 `.claude/hooks/` 的实现方式直接搬到 AIASys 后端
- 假设 AIASys 内置 Agent 能访问我们当前能访问的文件路径
- 把我们协作 skill 的内容写入 AIASys 内置 skill

### 规则 3：设计 AIASys 内置 Agent 的新能力时，参考 AGENTS.md 的产品语义

AGENTS.md 中定义了 AIASys 的核心产品语义，设计新功能时必须遵守：

- 工作区是一等对象
- 会话级配置覆盖工作区配置覆盖全局配置
- 工具分为默认加载和默认不加载
- 子 Agent 默认和主控共用上下文
- Skill 采用源仓库 + 工作区副本的两层架构
- AutoTask 是自动化任务的统一入口
- 不做向后兼容（0-1 阶段）

### 规则 4：修改 `agent-dev` skill 时，明确写的是哪个 Agent 系统

`agent-dev` skill 当前覆盖的是 AIASys 内置 Agent 的工具开发（Tool 开发、沙盒安全、Agent 状态管理、流式输出）。如果需要补充关于"开发 AIASys 的 AI"的行为规范，应该写到本 skill 而不是 `agent-dev`。

### 规则 5：验证时区分两种 Agent 的行为

当我们说"验证 Agent 是否正常工作"时：
- 如果验证的是 AIASys 内置 Agent → 通过 AIASys 前端界面操作，让内置 Agent 执行任务，观察结果
- 如果验证的是我们自己的开发行为 → 通过代码审查、测试运行、浏览器截图来验证

---

## 当前 AIASys 内置 Agent 不支持的能力

以下是我们（开发 AI）有、但 AIASys 内置 Agent 暂时没有的能力：

| 能力 | 我们有 | AIASys 内置 Agent | 备注 |
|------|--------|-------------------|------|
| Pre/Post Tool Hooks | 有（`.claude/hooks/`） | 无 | 需从零设计 |
| 浏览器控制 | 有（kimi-webbridge） | 有限 | 通过工具提供 |
| Git 操作 | 有（Shell） | 有限 | 通过沙盒执行 |
| 会话启停 Hook | 有（session-start.sh、stop-guard.sh） | 无 | 需从零设计 |
| Skill 自动推荐 | 有（skill-eval.js） | 无 | 不是产品功能 |

如果要为 AIASys 内置 Agent 添加这些能力，必须先做可行性评估（写入 `design-draft/design/design-thinking/`），评估通过后再进入设计阶段。

---

## 与其他 Skill 的关系

- `agent-dev`：AIASys 内置 Agent 的工具开发规范（Tool、沙盒、状态管理、流式输出）
- `aiasys-system-design`：AIASys 产品语义和系统设计约束
- `aiasys-product-requirements`：产品需求与 PRD 流程
- `kimi-cli-handbook`：Kimi CLI 工具使用手册（我们自己的工具参考）

---

## 快速检查清单

当讨论 Agent 相关话题时：
- [ ] 先明确说的是"开发 AIASys 的 AI"还是"AIASys 内置的 Agent"
- [ ] 如果要给 AIASys 内置 Agent 加 hooks → 先做可行性评估，不要照搬 `.claude/hooks/`
- [ ] 如果要修改 `agent-dev` → 确认改的是内置 Agent 的工具开发规范
- [ ] 如果要讨论 Skill → 确认说的是 `.agents/skills/`（协作）还是 `apps/backend/skills/builtin/`（产品）
- [ ] 如果要验证 → 区分是代码级验证还是产品功能验证