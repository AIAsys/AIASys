---
name: skill-management
description: |
  Skill 体系管理总规范。当涉及 Skill 目录结构变更、源码仓库与部署目标对齐、项目专属 Skill 落位、
  第三方 Skill 收集、已归档 Skill 清理、Skill description 维护、联邦架构调整、
  或任何与"整个 Skill 体系怎么组织"相关的决策时触发。
  不替代 skill-development-workflow（后者处理单个 Skill 的生命周期）。
  本 Skill 处理的是"所有 Skill 放在一起应该怎么摆、怎么管"。
---
# Skill 体系管理
## 定位
本 Skill 负责架构级问题：Skill 放哪里、怎么组织、怎么保持一致、第三方怎么收、归档怎么清。
它不负责"单个 Skill 怎么写"（去 `skill-development-workflow`），也不负责"Skill 怎么从对话中进化"（去 `self-evolving-skill`）。
## 何时使用
- 新增 Skill，需要确定落位位置（`_global/` 还是 `pkm-hub/` 还是 `aiasys/`）
- 源码仓库和部署目标不一致，需要对齐
- 源码仓库有但部署目标没有（孤儿），或部署目标有但源码仓库没有（幽灵）
- 第三方 Skill 收集后需要分类决策
- 已归档 Skill 需要清理（移动到 `_archived/`）
- 任何"Skill 管理策略应该是什么"的问题
## 何时不要用
- 单个 Skill 的创建、修改、验证、发布：去 `skill-development-workflow`
- Skill 从对话中进化（识别改进点、更新内容）：去 `self-evolving-skill`
- 团队 Skill 的日常维护和审核：去 `team-skill-maintainer`
- 私有 Skill 生命周期管理（创建、推广、与团队 Skill 的关系）：去 `team-skill-maintainer`
- 具体能力的执行：去对应领域的 Skill
- Git 操作：去 `git-workflow`
- AI 能力栈分层、多 CLI 共存、Skill/Plugin/Hook 边界：去 `pkm-ai-integration`
---
## 总体架构
Skill 体系按**源码仓库 → 部署目标**两层模型组织。源码仓库（`resources/xiaoke-skill-development/`）是所有 Skill 的唯一创建与修改入口；部署目标是各项目 CLI 的 skills 目录，由部署脚本从源码仓库单向同步。
### 源码仓库结构
```
resources/xiaoke-skill-development/
├── skills/
│   ├── _global/                ← 通用 Skill（所有项目可用）
│   ├── pkm-hub/                ← pkm-hub 专属 Skill
│   ├── aiasys/                 ← AIASys 专属 Skill
│   └── _archived/              ← 已合并/废弃 Skill（不部署）
├── _collections/               ← 第三方 Skill 暂存区
├── _templates/                 ← Skill 创建模板
├── projects.json               ← 项目 Skill 分发配置
├── scripts/
│   ├── deploy.py                     ← 部署脚本（按 projects.json 分发）
│   ├── sync-team-skills-back.py      ← 团队 Skill 反向同步（.team-skills/ → skills/aiasys/）
│   ├── generate-index-cards.py       ← 索引卡片生成（保留兼容）
│   └── ...
├── AGENTS.md                   ← 总导航（Skill 快速选择表）
└── README.md
```
### 两层模型：源码仓库 → 部署目标
```
resources/xiaoke-skill-development/          ← 源码仓库：全部 Skill 源码
    │                                            _global/ → 通用
    │                                            pkm-hub/ → pkm-hub 专属
    │                                            aiasys/  → AIASys 专属
    │                                            _archived/ → 不部署
    │
    │  单向同步：deploy.py 按 projects.json 分发
    │
    ├──→ pkm-hub/.kimi-code/skills/           ← 私人 CLI：索引卡片
    ├──→ pkm-hub/.claude/skills/              ← 私人 CLI：索引卡片
    ├──→ pkm-hub/.codex/skills/               ← 私人 CLI：索引卡片
    ├──→ AIASys/.kimi-code/skills/            ← 私人 CLI：索引卡片（WSL 路径）
    └──→ AIASys/.team-skills/                 ← 团队共享：个人 Skills 部署输出
```
### 团队共享区：`.team-skills/`
```
AIASys/
├── .team-skills/              ← 个人 Skills 的部署输出（git 跟踪，纳入项目 git）
│   ├── ai-output-guide/       ← 团队输出规范（去敏后的完整副本）
│   ├── team-skill-guide/      ← Skill 路由总览
│   ├── team-skill-governance/ ← 团队 Skill 管理规则
│   └── ...                    ← 其他团队适用 Skill
│
└── .kimi-code/skills/         ← 个人 Skill 独立维护
    ├── user-profile -> /mnt/c/.../user-profile               ← 个人
    └── ...
```
**`.team-skills/` 的核心规则**：
1. **部署输出**：`.team-skills/` 是个人 Skills 经实战验证后部署到团队的消费层，不是编辑入口
2. **个人优先**：所有 Skill 的创建和迭代都在个人 Skills 中进行。`.team-skills/` 的内容由 `deploy.py` 统一部署
3. **个人配置与团队配置独立**：`.kimi-code/skills/`（个人 AI 读取）和 `.team-skills/`（团队 AI 读取）各自独立维护。个人可以有一套与团队不同的 Skill，即使重复也没关系。个人 AI 不读取 `.team-skills/` 里的内容
4. **去敏原则强化**：进入 `.team-skills/` 的 Skill 必须去除所有个人身份信息、私有路径、敏感工具
5. **自包含**：不引用 `.team-skills/` 外的 Skill 路径或内容
6. **团队反馈，个人迭代**：团队通过 Issue / 群聊 / PR 提供反馈，你在个人 Skills 中迭代后重新部署
详见 `aiasys/team-skill-governance` 的准入标准和 `aiasys/team-skill-maintainer` 的维护流程。
**部署由 `projects.json` 声明**：每个项目在 `projects.json` 中声明自己的部署路径、目标 CLI 列表、需要的 Skill 集合。`deploy.py` 读取该配置，将源码仓库中的 Skill 按声明分发到各项目的 skills 目录。
**部署目标区分表**：
| 部署目标 | 模式 | 用途 | 内容要求 |
|---------|------|------|---------|
| `.kimi-code/skills/` | 索引卡片 | 个人 AI 协作 | frontmatter + 文件树 + 源码链接 |
| `.claude/skills/` | 索引卡片 | Claude Code | frontmatter + 文件树 + 源码链接 |
| `.codex/skills/` | 索引卡片 | Codex CLI | frontmatter + 文件树 + 源码链接 |
| `.team-skills/` | **copy** | 团队共享 | 去敏后的完整 Skill 内容 |
### 关键区分：收集区 vs 源码仓库
`_collections/` 目录存放第三方 Skill 原样存档（功能等同旧 `xiaoke-collection-skills/`），只读参考。筛选评估后值得用的 Skill 迁入 `skills/_global/` 或对应项目目录做二次开发。
| | 收集区（`_collections/`） | 源码仓库（`skills/`） |
|---|--------|----------|
| **放什么** | 第三方 skill，原样存档 | 我们的 skill |
| **改不改** | 不改，只读参考 | 自由修改、迭代 |
| **来源标记** | 在「上游Skill跟踪台账.md」登记来源、版本、状态 | 不需要标记来源——进了这里就是我们的 |
| **怎么用** | 筛选评估后，值得用的迁入 `skills/` 做二次开发 | 所有 skill 创建、修改、迭代的唯一入口 |
> 核心原则：一旦某个 skill 从收集区迁入 `skills/`，它就不再是「外部引入的」——它已经是我们的 skill，会持续迭代。来源追溯通过收集区的台账完成，不在源码仓库内重复标记。
### 核心原则
1. **唯一源码**：所有 Skill 的创建、修改、迭代都在 `resources/xiaoke-skill-development/skills/` 完成。禁止直接在部署目标修改 Skill 内容。
2. **单向同步**：源码仓库 → 部署目标（由 `deploy.py` 执行）。部署目标的任何变更都不应回写。
3. **项目隔离**：各项目的 skills 目录各自独立。通用 Skill 放 `_global/`，项目专属 Skill 放 `pkm-hub/` 或 `aiasys/`。
4. **按需部署**：每个项目通过 `projects.json` 声明自己需要哪些 Skill。`deploy.py` 按声明分发，不部署未声明的 Skill。
5. **已归档不进部署**：`_archived/` 下的 Skill 保留在源码仓库作为历史记录，不部署到任何目标。
### 各区读写规则
| 层级 | 路径 | 角色 | 读写规则 |
|---|---|---|---|
| **收集区** | `resources/xiaoke-skill-development/_collections/` | 第三方 Skill 原样存档 | 只读参考，不直接修改 |
| **源码仓库** | `resources/xiaoke-skill-development/skills/` | 全部 Skill 源码 | 自由修改，所有变更从这里发起 |
| **部署目标** | 各项目的 `.kimi-code/skills/` `.claude/skills/` `.codex/skills/` | 各 CLI 工具的 Skill 发现入口 | 只接受从源码仓库生成的索引卡片，禁止手工直改 |
| **共享状态区** | `.agents/`（task-sessions/ tools/ hooks/） | 跨 CLI 共享的运行时状态和工具 | 自由读写，不包含 skills |
> **注意**：`skills/_archived/` 下的 Skill 保留在源码仓库但**不部署**到任何目标。`.agents/` 不再作为 skills 部署目标，改为跨 CLI 共享状态区（task-sessions、tools、hooks）；历史部署残留需手动清理。详见 `pkm-ai-integration` 规则 3。
## 目录结构标准
### 源码仓库（skills/）
```
resources/xiaoke-skill-development/skills/
├── _global/                       ← 通用 Skill（所有项目可用）
│   ├── skill-management/
│   ├── skill-development-workflow/
│   ├── ai-output-guide/
│   ├── writing-guide/
│   ├── workspace-ops/
│   ├── task-protocol/
│   └── ...
├── pkm-hub/                       ← pkm-hub 专属 Skill
│   ├── pkm-content-organizer/
│   ├── pkm-ai-integration/
│   └── ...
├── aiasys/                        ← AIASys 专属 Skill
│   ├── aiasys-frontend-architecture/
│   └── ...
└── _archived/                     ← 已合并/废弃 Skill（不部署）
    ├── directory-standards/
    ├── entry-manager/
    └── ...
```
### 收集区（_collections/）
```
resources/xiaoke-skill-development/_collections/
├── README.md                      # 收集区说明
├── 上游Skill跟踪台账.md            # 来源、状态、评估标记
├── _meta/                         # 元数据与历史记录
├── external-github/               # 外部 GitHub 仓库完整副本（可 git pull）
└── skills/                        # 单个独立 skill，按领域分类
```
### 部署目标
部署目标由 `projects.json` 声明，`deploy.py` 执行分发。每个项目可以有多个 CLI 目标：
```json
// projects.json 示例
{
  "projects": {
    "pkm-hub": {
      "path": "C:/Users/ke/Documents/projects/obsidian_projects/pkm-hub",
      "targets": ["kimi-code", "claude", "codex"],
      "deploy_mode": "copy",
      "skills": ["*", "pkm-hub/*"]
    },
    "aiasys": {
      "path": "//wsl.localhost/Ubuntu-22.04/home/ke/projects/AIASys",
      "targets": ["kimi-code"],
      "deploy_mode": "symlink",
      "skills": ["ai-output-guide", "writing-guide", "workspace-ops", "task-protocol", "git-workflow", "aiasys/*"]
    }
  }
}
```
部署后的目录结构（以 pkm-hub 为例）：
```
.kimi-code/skills/       ← Kimi Code（TS 版，当前主力）
.claude/skills/          ← Claude Code
.codex/skills/           ← Codex CLI
```
每个部署目标的内容由 `deploy.py` 从源码仓库按声明选择性分发。私人 CLI 目标拿到索引卡片，团队共享目标拿到去敏后的完整内容。不是所有目标都需要全部 Skill。
### Skill 目录的最低要求
每个 Skill 子目录必须至少有 `SKILL.md`。没有的目录不该留在 `skills/` 下（`_archived/` 除外，保留作为历史记录）。
---
## 通用 Skill vs 项目专属 Skill 的边界
| 维度 | 通用 Skill | 项目专属 Skill |
|---|---|---|
| 适用范围 | 跨项目复用 | 仅特定项目使用 |
| 技术栈依赖 | 无（或极弱） | 强（如 React 19、FastAPI） |
| 示例 | git-workflow、ai-output-guide、pdf-to-markdown | aiasys-frontend-architecture |
| 源码位置 | `skills/_global/` | `skills/pkm-hub/` 或 `skills/aiasys/` |
| 命名 | 不加前缀 | 建议加项目前缀 |
**决策规则**：模糊地带优先放 `_global/`。项目专属 Skill 放在对应项目子目录下。
---
## 能力文档与维护记录的边界
判定规则：这个文件是 AI 执行任务时需要读取的能力文档，还是 Skill 维护者管理迭代时需要的维护记录？
前者进部署目标，后者留在源码仓库。
| 类型 | 示例 | 进部署目标？ |
|------|------|-----------|
| SKILL.md | 核心能力文档 | 是 |
| 关联能力文档 | user-profile 的《思考特征》《语言特征》 | 是 |
| README.md | 给人看的说明 | 可选 |
| scripts/、references/ | 可执行脚本与参考材料 | 是 |
| CHANGELOG.md | 版本演进历史 | 否 |
| versions/、drafts/、evals/ | 历史版本、草稿、测试 | 否 |
## 第三方 Skill 管理
### 两个区的分工
| 目录 | 放什么 | 改不改 |
|---|---|---|
| `resources/xiaoke-skill-development/_collections/` | 别人的 skill，原样存档 | 不改，只读参考 |
| `resources/xiaoke-skill-development/skills/` | 我们的 skill（含从收集区拿来二次开发改造的） | 自由修改 |
**关键区别**：收集区是「别人的东西」，`skills/` 是「我们的东西」。从收集区拿一个 skill 到 `skills/` 做改造，就不再是原样保存了——那是二次开发，属于 `skills/` 的工作。
### 处理流程
```
1. 收集：拉取第三方 skill 到 _collections/
2. 登记：在「上游Skill跟踪台账.md」记录来源、快照日期、版本、状态
3. 评估：阅读 SKILL.md，判断质量、是否与现有 skill 重叠、是否值得二次开发
4. 决策：
   - 值得做 → 复制到 skills/_global/ 或对应项目目录，去项目化、重命名、改造
   - 纯参考 → 留在 _collections/，台账标注「已快照」或「待评估」
   - 无用 → 删除
5. 二次开发 → 走 skill-development-workflow 发布到部署目标
```
**禁止**：未经过 `skills/` 改造的第三方 Skill 直接放入任何部署目标。
### 状态管理
收集区的 Skill 状态在台账中标记，不通过物理移动文件来反映。状态包括：「已快照」「本地化中」「已私有化」「已正式接入」。详见 `_collections/上游Skill跟踪台账.md`。
---
## 已归档 Skill 处理
### 归档触发条件
- Skill 声明「已并入 XXX」
- Skill 功能被其他 Skill 完全覆盖
- Skill 被标记为废弃超过 3 个月
### 归档流程
1. 在 Skill 的 `SKILL.md` 顶部添加 `# ⚠️ 已归档（ARCHIVED）` 标记
2. 将 Skill 目录移动到 `skills/_archived/`
3. 从 `projects.json` 中移除该 Skill 的声明（如有显式声明）
4. 重新运行 `deploy.py` 确保部署目标中不再存在该 Skill
5. `_archived/` 中的副本保留作为历史记录，不再维护
### 已归档 Skill 保留清单
以下 Skill 已归档，存放在 `skills/_archived/` 中，不部署到任何目标：
**2026-06-05 物理归档**（已从 `skills/` 移动到 `skills/_archived/`）：
- `directory-standards` → 并入 `pkm-content-organizer`
- `entry-manager` → 并入 `pkm-content-organizer`
- `inbox-triage` → 并入 `pkm-content-organizer`
- `knowledge-cards` → 并入 `pkm-content-organizer`
- `para-manager` → 并入 `pkm-content-organizer`
- `requirements-analysis` → 已归档，不再部署
- `resource-curator` → 并入 `pkm-content-organizer`
- `rule-history` → 已归档，不再部署
- `task-persistence` → 并入 `pkm-content-organizer`
**2026-05-29 合并归档**：
- `citation-preferences` → 并入 `writing-qa`
- `domain-learning-framework` → 并入 `content-to-research-project`
- `gh-skill-manager` → 并入 `skill-development-workflow`
- `kimi-cli-handbook` → 旧版 Python CLI 已废弃，当前使用 `kimi-code-handbook`
- `step-web-search-skill` → 与 `step-web-search` 重复
- `terminology-guardian` → 并入 `writing-qa`
- `tongyi-transcriber` → 并入 `media-capture`
- `writing-linter` → 并入 `writing-qa`
**历史归档**：
- `domain-learning` → 并入 `content-to-research-project`
- `domain-learning-workspace` → 非 Skill，已移出
- `playwright-cli` → 浏览器自动化统一使用 Kimi WebBridge
- `rule-evolution` → 并入 `pkm-content-organizer`
- `skill-release` → 发布流程已整合到 `skill-development-workflow`
已恢复的 Skill：
- `ebook-manager`（2026-05-24 恢复）
已移出 `skills/`（非 Skill 目录）：
- `codex-agents` → 移至 `.agents/agents/codex-agents/`（agent 配置文件）
---
## 漂移检测与同步
### 漂移类型
| 类型 | 表现 | 处理 |
|---|---|---|
| **部署目标超前** | 部署目标比源码仓库新 | 用源码仓库覆盖部署目标（部署目标不应有独立变更） |
| **源码仓库有但部署目标无** | 新 Skill 或更新未同步 | 运行 `deploy.py` 部署 |
| **部署目标有但源码仓库无** | 幽灵 Skill（历史遗留） | 回同步到源码仓库，评估后保留或归档 |
### 修改前置检查（强制）
每次修改 Skill 时，先在源码仓库修改，然后运行 `deploy.py` 同步到需要的部署目标：
```bash
# 检查私人 CLI 目标是否拿到索引卡片（以 pkm-hub 的 .kimi-code 为例）
cat .kimi-code/skills/<skill>/SKILL.md
```
| 检查结果 | 处理方式 |
|---|---|
| 索引卡片指向源码仓库 | 直接在源码仓库修改，改完运行 `deploy.py` |
| 部署目标被手工改成完整正文或自定义内容 | 用 `deploy.py` 重新生成索引卡片 |
| 源码仓库更新但卡片未更新 | 运行 `deploy.py` 同步到部署目标 |
### 同步方式
```
1. 在源码仓库完成修改
2. 运行 deploy.py 按 projects.json 分发到各项目目标
3. 更新关联 skill 的交叉引用
4. 如果是 WSL 项目（如 AIASys），deploy.py 自动处理 symlink
```
**部署脚本**：`resources/xiaoke-skill-development/scripts/deploy.py`
| 命令 | 作用 |
|------|------|
| `python deploy.py` | dry-run 预览所有项目的部署计划 |
| `python deploy.py --write` | 执行部署，按 projects.json 分发所有 Skill |
| `python deploy.py --write --project pkm-hub` | 只部署到指定项目 |
| `python deploy.py --write --project pkm-hub --skill ai-output-guide` | 只部署指定 Skill 到指定项目 |
> `deploy.py` 读取 `projects.json` 中的 `skills` 声明，支持通配符（`*` = 所有 `_global/`，`<project>/*` = 该项目下所有专属 Skill）和精确名称。`_archived/` 下的 Skill 不会被部署。
> 私人 CLI 目标当前是索引卡片模式；不要用源码 SKILL.md 与部署目标 SKILL.md 做全文 diff。要验证正文，读取索引卡片指向的源码文件。
### 跨 Skill 关联同步
修改 skill 时，变更可能波及其他 skill 的引用。以下情况必须执行关联检查：
| 变更类型 | 需检查的关联方 |
|---|---|
| description 字段变更 | 其他 skill 的「何时不要用」「不替代 XXX」声明 |
| 关联 Skill 章节变更 | 被移除的 skill 是否在其他 skill 的关联章节中被引用 |
| 职责范围变更 | 被接管方的 description 是否需要更新 |
| skill 被合并/删除/归档 | 所有引用该 skill 的文档 |
执行步骤：搜索引用 → 逐条判断 → 同步更新 → 验证链接有效。
---
## Skill 索引维护
Skill 发现通过 frontmatter 的 `description` 字段自动匹配意图。`resources/xiaoke-skill-development/AGENTS.md` 的快速选择表是辅助索引。
### 维护规则
- 每个 Skill 的 `description` 是 AI 发现该 Skill 的关键入口，必须包含触发关键词和使用场景
- 新增 Skill 时，`description` 必须覆盖所有触发该 Skill 的常见用户表达
- 新增 Skill 时，必须在源码仓库 `AGENTS.md` 快速选择表登记
- 根目录 `AGENTS.md` 只保留项目级红线禁令和规范入口指向（`ai-output-guide` + `pkm-ai-integration`），不维护 Skill 列表
### 定期检查
1. 每个 Skill 的 `description` 是否准确覆盖了触发场景
2. `_archived/` 下的 Skill 是否已从 `projects.json` 和部署目标中移除
3. Skill 分组是否合理（`_global/` vs `pkm-hub/` vs `aiasys/`）
---
## 项目联邦
有独立仓库的项目（如 AIASys），其 Skill 分三层管理：
1. **项目专属 Skill**：在 `skills/aiasys/` 中维护，通过 `projects.json` 声明 `"skills": ["aiasys/*"]` 来部署到 `.kimi-code/skills/`（个人使用）。
2. **通用 Skill**：从 `skills/_global/` 中选取需要的 Skill，在 `projects.json` 中显式声明（如 `"skills": ["ai-output-guide", "git-workflow"]`）。
3. **团队共享 Skill**：从个人 Skills 中筛选出适合团队的 Skill，经过去敏和自包含检查后，通过 `deploy.py` 部署到项目仓库的 `.team-skills/` 中
`projects.json` 中的 `deploy_mode` 是历史字段：私人 CLI 目标当前统一生成索引卡片，`team-skills` 目标复制完整内容；WSL 项目的 `symlink` 标记主要用于跨平台路径展示和兼容处理。`deploy.py` 根据 `projects.json` 自动处理跨平台路径转换和目标目录选择。
### 团队 Skill 与个人 Skill 的边界
| 维度 | 团队 Skill（`.team-skills/`） | 个人 Skill（`.kimi-code/skills/`） |
|---|---|---|
| **存放位置** | 项目仓库内 `.team-skills/` | 各项目 `.kimi-code/skills/` |
| **文件形态** | 实体文件（个人 Skills 部署输出） | 索引卡片（私人 CLI 目标），卡片指向源码仓库 |
| **版本控制** | 项目 git | pkm-hub git |
| **可见范围** | 团队 AI 读取 | 个人 AI 读取 |
| **修改入口** | 个人 Skills → `deploy.py` 部署 | 修改源码仓库后 `deploy.py` |
| **典型内容** | 项目基础规范、开发流程、架构约定 | 个人画像、私有工具、跨项目通用能力 |
| **反例** | `user-profile`（个人画像）、`baidu-pan-manager`（私有网盘） | 其他项目专属 Skill（如 `wenyan-cli-ops`） |
| **重复关系** | 个人可与团队有重复 Skill，各自独立维护 | 个人 AI 不读取 `.team-skills/` 内容 |
### 个人 Skill 部署到团队的准入决策
你在个人 Skills 中开发了一个 Skill，想部署到 `.team-skills/` 时，按以下顺序判断：
```
Skill 候选
│
├─ 是否含个人敏感信息？（姓名、画像、偏好、私有路径）
│   └─ 是 → 排除
│
├─ 是否绑定个人环境？（特定电脑、私有账号、个人工具链）
│   └─ 是 → 排除
│
├─ 是否涉及敏感工具？（网盘、支付、个人账号）
│   └─ 是 → 排除
│
├─ 团队多数人是否用得上？
│   └─ 否 → 排除
│
├─ 是否与当前项目技术栈/协作流程相关？
│   └─ 否 → 排除
│
├─ 是否自包含？（不引用 .team-skills/ 外的 Skill）
│   ├─ 是 → 直接纳入
│   └─ 否 → 将依赖也复制到 .team-skills/，或排除
│
└─ 全部通过 → 纳入 .team-skills/
```
**判定口诀**：团队里的任意一个成员拿到这个 Skill 都能直接用，不需要知道你的个人配置、不依赖你的私有环境。
### 禁止放入 `.team-skills/` 的典型 Skill
| Skill | 排除原因 |
|---|---|
| `user-profile` | 含个人认知风格与协作偏好 |
| `baidu-pan-manager` | 个人网盘工具 |
| `windows-admin-elevator` | 绑定 Windows 个人环境 |
| `wsl-windows-bridge` | 绑定 WSL+Windows 个人环境 |
| `wenyan-cli-ops` | 其他项目专属运维 |
| `kimi-code-handbook` | 通用 CLI 手册，个人使用即可 |
| `self-evolving-skill` | 个人 Skill 进化方法论 |
---
## Skill 协作生命周期
### 生命周期总览
```
创建 → 开发 → 评审 → 发布 → 更新 → 废弃
```
| 阶段 | 状态标记 | 责任人 | 操作步骤 |
|------|---------|--------|---------|
| **创建** | `draft` | 贡献者 | 1. 在源码仓库 `skills/` 下新建目录<br>2. 编写初版 `SKILL.md`<br>3. 本地验证 frontmatter 和格式 |
| **开发** | `dev` | 贡献者 | 1. 完善能力描述、示例、关联引用<br>2. 自测触发关键词覆盖度<br>3. 如有脚本，验证可执行性 |
| **评审** | `review` | 管理员 | 1. 检查职责边界是否清晰（不与其他 Skill 重叠）<br>2. 检查 description 是否覆盖触发场景<br>3. 检查跨 Skill 引用是否有效<br>4. 判定落位：`_global/` / `pkm-hub/` / `aiasys/` |
| **发布** | `released` | 管理员 | 1. 更新版本号<br>2. 登记到 `AGENTS.md` 快速选择表<br>3. 运行 `deploy.py --write` 同步到部署目标<br>4. 更新 CHANGELOG |
| **更新** | `updated` | 贡献者/管理员 | 1. 在源码仓库修改<br>2. 评审变更范围（是否波及其他 Skill）<br>3. 运行 `deploy.py --write` 重新部署<br>4. 同步更新关联引用<br>5. 验证部署目标生效 |
| **废弃** | `archived` | 管理员 | 1. 在 `SKILL.md` 顶部添加 `# ⚠️ 已归档（ARCHIVED）`<br>2. 移动到 `skills/_archived/`<br>3. 从 `projects.json` 移除声明<br>4. 运行 `deploy.py --write` 清理部署目标 |
> **状态标记位置**：在 Skill 目录内维护一个 `STATUS` 文件（纯文本，一行），或在 `SKILL.md` frontmatter 中增加 `status` 字段。推荐前者，避免 frontmatter 膨胀。
### 团队贡献者工作流
```
发现 Skill 问题
    │
    ├─ 小问题（错别字、链接失效、示例错误）
    │   └─ 直接提交 PR / Issue，附 diff 或截图
    │
    └─ 大问题（职责边界调整、新增能力、结构重构）
        └─ 先开 Issue 讨论方案 → 管理员确认 → 再开发 → 提交 PR
              │
              ▼
        管理员审核（边界、质量、关联影响）
              │
              ▼
        合并到源码仓库
              │
              ▼
        运行 deploy.py --write 重新部署
```
**不同 OS 的贡献者 Git 配置**：
| OS | 核心配置 | 说明 |
|----|---------|------|
| **Mac** | `git config --global core.autocrlf input` | 提交时自动转 LF，检出时不转换 |
| **Linux** | `git config --global core.autocrlf input` | 同上，保持 LF |
| **Windows** | `git config --global core.autocrlf true` | 提交时转 LF，检出时转 CRLF（但 Skill 文件统一用 LF，见下） |
> **换行符统一**：所有 Skill 文件（`.md`、`.py`、`.json` 等）统一使用 **LF** 换行。Windows 贡献者在编辑 Skill 文件时，应在编辑器中显式设置 `EOL = LF`（VS Code 右下角可切换），避免 CRLF 污染。
### Skill 更新操作指南
#### 更新触发场景
| 场景 | 示例 | 操作路径 |
|------|------|---------|
| 改 SKILL.md 内容 | 规则更新、示例补充、description 调整 | 改源码仓库 → deploy.py |
| 改 reference 文档 | 架构文档更新、设计原则补充 | 改源码仓库 → deploy.py |
| 改关联引用 | 其他 skill 引用了本 skill，本 skill 改名或职责变更 | 改本 skill + 搜索关联 skill → 同步更新 → deploy.py |
| 改 projects.json | 新增/删除 skill、调整项目 skill 列表 | 改 projects.json → deploy.py |
| 团队 skill 与私人 skill 同步 | 团队版有 bug 修复，私人版需要吸收 | 手动 diff → 合并到私人版 → deploy.py |
#### 更新前检查清单
1. **确定变更范围**：只改了一个文件，还是波及多个 skill？
2. **检查关联引用**：用 `grep -r "skill-name" skills/` 搜索是否有其他 skill 引用本 skill
3. **检查 projects.json**：如果新增/删除/重命名 skill，需要同步改 projects.json
4. **检查 .team-skills/**：如果团队版也需要同步更新，确认去敏状态
#### 更新后验证清单
1. **deploy.py dry-run**：先预览，确认变更符合预期
2. **deploy.py --write**：执行部署
3. **验证部署目标**：检查 `.kimi-code/skills/` 或 `.team-skills/` 中的内容已更新
4. **验证关联引用**：如果改了 skill 名或 description，确认引用方没有失效链接
#### 快速更新命令
```bash
# 1. 改完源码仓库后，先 dry-run 预览
cd /mnt/c/Users/ke/Documents/projects/obsidian_projects/pkm-hub
python resources/xiaoke-skill-development/scripts/deploy.py
# 2. 确认无误后执行部署
python resources/xiaoke-skill-development/scripts/deploy.py --write
# 3. 只部署指定项目（如 AIASys）
python resources/xiaoke-skill-development/scripts/deploy.py --write --project aiasys
# 4. 检查部署目标是否已更新
diff resources/xiaoke-skill-development/skills/_global/skill-management/SKILL.md \
     /home/ke/projects/AIASys/.kimi-code/skills/skill-management/SKILL.md
```
### 私人/团队 Skill 同步规则
**核心原则**：私人 skill 是主用，团队 skill 是参考池。团队版更新后，私人版按需手动合并，不自动同步。
**双向同步决策流**：
```
团队 Skill 更新（.team-skills/）
    │
    ├─ 是否是通用能力改进？（description 更精准、示例更丰富、bug 修复）
    │   └─ 是 → 同步到私人版（源码仓库 skills/_global/）→ deploy.py 部署
    │
    └─ 是否是项目专属调整？（绑定特定技术栈、移除个人化内容）
        └─ 是 → 仅保留在团队版，不同步到私人版
私人专属 Skill 跟进团队版（如 aiasys-git-workflow-private vs aiasys-git-workflow）
    │
    ├─ 团队版是否有 bug 修复、流程改进、安全更新？
    │   └─ 是 → 合并到私人版（保留个人身份/权限配置，吸收通用改进）
    │
    └─ 团队版是否有与私人权限冲突的变更？（如分支权限调整）
        └─ 是 → 评估后手动合并，确保私人权限不被覆盖
私人 Skill 更新（源码仓库 skills/）
    │
    ├─ 是否去除个人敏感信息后即可团队通用？
    │   └─ 是 → 评估推广到团队版（.team-skills/）
    │
    └─ 是否仍依赖个人环境/偏好？
        └─ 是 → 保留在私人版，不推广
```
**同步检测方法**：
| 方法 | 命令 | 用途 |
|------|------|------|
| **dry-run 预览** | `python deploy.py` | 查看源码仓库与所有部署目标的差异计划 |
| **单文件 diff** | `diff <源码仓库>/skills/_global/<skill>/SKILL.md <部署目标>/<skill>/SKILL.md` | 精确对比某个 Skill 的差异 |
| **目录级 diff** | `diff -r <源码仓库>/skills/_global/<skill>/ <部署目标>/<skill>/` | 对比整个 Skill 目录（含脚本、附件） |
| **Git 状态** | `cd <部署目标项目> && git status` | 查看部署目标是否有未预期的本地变更 |
> **同步频率**：管理员每周至少运行一次 `deploy.py` 做 dry-run 检查，确保源码仓库与部署目标无漂移。
### 团队 Skill 回写应急处理

`.team-skills/` 是部署输出，正常情况下团队不直接编辑。如果团队 accidentally 修改了 `.team-skills/` 中的内容（下次部署会被覆盖），可以用以下脚本预览差异并决定是否吸收：

**工具**：`scripts/sync-team-skills-back.py`
```bash
# 预览：对比 .team-skills/ 与 skills/aiasys/ 的差异
python scripts/sync-team-skills-back.py

# 确认后执行同步
python scripts/sync-team-skills-back.py --write

# 只看指定 Skill 的变更
python scripts/sync-team-skills-back.py --skill skill-management
```
**脚本行为**：
- 比较 `.team-skills/` 中的每个 Skill 与 `skills/aiasys/` 中同名 Skill 的文件 hash
- 报告新增、修改（含文件级 diff 预览）、删除（幽灵 Skill）和无变更
- `--write` 模式会用 `.team-skills/` 的完整内容覆盖 `skills/aiasys/<skill>/`
- 自动跳过维护文件（`versions/`、`evals/`、`CHANGELOG.md` 等）
**应急处理决策流**：
```
团队 accidentally 修改了 .team-skills/<skill>/
    │
    ├─ 运行 sync-team-skills-back.py（dry-run 预览）
    │
    ├─ 查看 diff，确认变更内容
    │
    ├─ 判断是否有价值：
    │   ├─ 有价值的改进 → 吸收到个人 Skills → 重新部署
    │   ├─ 无价值的修改 → 忽略（下次部署会覆盖）
    │   └─ 含敏感信息 → 要求团队撤回
    │
    └─ 确认后 --write，然后在个人 Skills 中迭代 → deploy.py 重新部署
```

## 私有 Skill 管理

管理员的私有 Skill 分为三类，管理方式不同：

### 私有 Skill 分类

| 类型 | 命名 | 示例 | 说明 |
|------|------|------|------|
| **个人画像** | 原名 | `user-profile` | 纯个人，永远不会进团队 |
| **私有变体** | `-private` 后缀 | `aiasys-git-workflow-private` | 有对应的团队版，但你有额外权限/配置 |
| **项目私有** | 原名 | `aiasys-ci-release-private` | AIASys 专属但仅你使用，无团队版 |

### 私有 Skill 的部署

私有 Skill 只部署到你的个人 CLI 目标（`.kimi-code/skills/`），**不部署到 `.team-skills/`**。

```bash
# 部署私有 Skill 到个人 CLI 目标
python scripts/deploy.py --write --project aiasys --skill <private-skill-name>
```

### 私有 Skill → 团队 Skill 的推广流程

```
1. 在私有 Skill 中验证功能稳定（使用超过 2 周）
2. 评估推广可行性：
   - 去敏后内容是否仍然完整？
   - 团队多数人是否用得上？
   - 是否可以剥离个人配置？
3. 创建团队版：
   a. 复制私有 Skill 到 .team-skills/<name>/
   b. 去除个人身份、私有路径、个人配置
   c. 替换为通用配置
   d. 自包含检查（不引用外部 Skill）
4. 更新 .team-skills/team-skill-guide 的快速选择表
5. git commit + push
6. 通知团队新 Skill 已上线
```

**关键规则**：
- 私有 Skill 和团队 Skill **独立维护**，推广后不是简单的复制关系
- 团队 Skill 更新后，私有 Skill 按需手动吸收（不自动同步）
- 使用 `-private` 后缀区分有团队对应版的私有 Skill

### 私有 Skill 与团队 Skill 的边界

| 维度 | 私有 Skill | 团队 Skill |
|------|-----------|-----------|
| 存放位置 | `skills/_global/` 或 `skills/aiasys/` | `.team-skills/` |
| 内容 | 可含个人身份、私有路径、个人配置 | 去敏、自包含、通用 |
| 部署目标 | `.kimi-code/skills/`（仅你） | 全团队 |
| 修改权限 | 你随意改 | 团队可改，你审核 |
| 同步方向 | 单向：你 → 你自己 | 双向：团队 ↔ 你 |

### 私有 Skill 与团队 Skill 同名时的管理

当你有 `aiasys-git-workflow-private`，团队有 `aiasys-git-workflow`：
- 两者独立维护，互不影响
- 你的私有版可以包含额外的个人配置（如你的 git 身份、force push 权限等）
- 团队版是通用版本，不含个人配置
- 团队版更新后，你手动判断是否吸收到私有版
### 跨平台协作规范
**主力环境**：WSL + Windows 双环境。Skill 源码仓库位于 Windows 文件系统（`C:/Users/ke/...`），WSL 项目（如 AIASys）通过 `deploy.py` 的 symlink 模式引用。

#### 跨环境运行 deploy.py

源码仓库在 Windows 文件系统，WSL 可以直接通过 `/mnt/c/` 路径访问：

```bash
# WSL 中运行（AIASys 项目所在环境）
cd /mnt/c/Users/ke/Documents/projects/obsidian_projects/pkm-hub/resources/xiaoke-skill-development
python3 scripts/deploy.py --dry-run                          # 预览
python3 scripts/deploy.py --write --project aiasys           # 部署到个人 CLI 目标
python3 scripts/deploy.py --write --project aiasys-team      # 部署到 .team-skills/
python3 scripts/deploy.py --write --project aiasys --skill <name>  # 单 Skill
```

```powershell
# Windows 中运行（如果需要在 Windows 终端操作）
cd C:\Users\ke\Documents\projects\obsidian_projects\pkm-hub\resources\xiaoke-skill-development
python scripts/deploy.py --dry-run
python scripts/deploy.py --write --project aiasys
```

> **推荐**：在 WSL 中运行 deploy.py，因为 AIASys 项目本身在 WSL 中，symlink 处理和路径转换更自然。

#### 搜索优先级

pkm-hub 仓库极其庞大，**禁止使用 `**/` 递归 Glob 或 `find` 遍历整个仓库**。搜索时必须遵守以下优先级：

| 优先级 | 工具 | 适用场景 | 速度 | 可用对象 |
|:---:|------|---------|:---:|:---:|
| 1 | **ES (Everything Search)** | 按文件名/路径定位文件 | 毫秒级 | 管理员（Windows 环境） |
| 2 | **Grep** | 搜索文件内容 | 取决于范围 | 所有人 |
| 3 | **Glob** | 已知小目录内按模式匹配 | 快 | 所有人 |

**决策规则**：
- **管理员**（Windows）：找文件 → **ES**，搜内容 → **Grep**，小目录 → **Glob/ES 均可**
- **团队/其他成员**（Mac/Linux）：找文件 → **Glob**（范围小），搜内容 → **Grep**

> **核心规则**：只要是"找文件"，管理员优先用 ES。团队没有 ES，用 Glob 限定范围 + Grep 搜内容。不要用 `find` 或递归 `**/` Glob。

**ES 说明**：
- ES 是 Windows 独占工具（Everything + es.exe），仅管理员个人环境可用
- 团队 Skill 不包含 everything-search，因为：① Windows 独占 ② 依赖外部软件安装 ③ 硬编码个人路径
- `everything-search` skill 仅部署在管理员个人 CLI 目标（`.kimi-code/skills/`、`.claude/skills/`），不进 `.team-skills/`

**Mac/Linux 成员**：
- 使用标准 Git 工作流（clone → branch → commit → PR）
- 所有路径使用**相对路径**（相对于 Skill 目录或项目根目录），禁止硬编码绝对路径
- 如需引用外部资源，通过环境变量或配置文件中声明，不在 Skill 文档中写死路径
**文件权限标准**：
| 文件类型 | 权限 | 说明 |
|---------|------|------|
| `SKILL.md`、`.md`、`.json`、`.yaml` | `644`（rw-r--r--） | 文档和配置，只读执行 |
| `.py`、`.sh`、可执行脚本 | `755`（rwxr-xr-x） | 脚本需要执行权限 |
> Windows 环境下权限由 Git 通过 `core.filemode` 管理。如需在 Windows 上保留 Unix 权限位，确保 `git config core.filemode true`（默认开启）。WSL 中访问 Windows 文件系统时，权限可能显示为 `777`，不影响实际使用——以 Git 跟踪的权限为准。
---
## 最小验收清单
在对 Skill 体系做任何调整后，确认：
- [ ] 源码仓库是唯一的变更发生地
- [ ] `projects.json` 中的 Skill 声明与实际需要一致
- [ ] `deploy.py` 已运行，所有需要的部署目标已同步
- [ ] `_archived/` 下的 Skill 已从所有部署目标删除
- [ ] 孤儿/幽灵 Skill 已处理
- [ ] 根目录 `AGENTS.md` 入口指向是否有效（应指向 `ai-output-guide/SKILL.md` 和 `pkm-ai-integration/SKILL.md`）
- [ ] 关联 skill 的交叉引用已检查，无失效引用
- [ ] `_collections/` 中的第三方 Skill 未污染 `skills/` 和部署目标
---
**规范版本**: v1.8.0  
**创建日期**: 2026-04-20  
**最后更新**: 2026-06-12
**维护者**: 管理员
**v1.8.0 变更**：2026-06-12 — 新增团队 Skill 回写应急处理脚本
- 新增 `scripts/sync-team-skills-back.py`，用于应急处理团队 accidentally 对 `.team-skills/` 的修改
- 支持 `--dry-run` 预览和 `--write` 确认写入，支持 `--skill` 单 skill 同步
- 新增「团队 Skill 回写应急处理」章节，明确 `.team-skills/` 是部署输出而非编辑入口
**v1.7.0 变更**：2026-06-05 — 新增 Skill 协作生命周期章节
- 新增「Skill 协作生命周期」独立大章节，覆盖创建→开发→评审→发布→更新→废弃六阶段
- 新增「团队贡献者工作流」，含 Issue/PR 流程、管理员审核节点、不同 OS 的 Git 配置表
- 新增「私人/团队 Skill 同步规则」，含双向同步决策流和同步检测方法（dry-run / diff）
- 新增「跨平台协作规范」，含主力环境说明、Mac/Linux 成员相对路径要求、换行符统一为 LF、文件权限标准（644/755）
**v1.6.0 变更**：2026-06-05 — 强化 `.team-skills/` 部署规则与个人/团队配置隔离
- `.team-skills/` 明确使用 copy 模式（不用 symlink），团队成员拿到可直接使用的完整 Skill
- 新增「部署目标区分表」，明确 `.kimi-code/skills/`、`.claude/skills/`、`.codex/skills/`、`.team-skills/` 的模式与用途差异
- 强化「个人配置与团队配置独立」原则：个人 AI 不读取 `.team-skills/`，团队与个人可各自独立维护重复 Skill
- 去敏原则升级为「去敏原则强化」，明确必须去除所有个人身份信息、私有路径、敏感工具
- 更新「团队 Skill 与个人 Skill 的边界」对比表，新增「文件形态」「重复关系」维度
- 更新「总体架构」中 `.team-skills/` 的示例结构，移除混合 symlink 示意（改为各自独立）
**v1.5.0 变更**：2026-06-05 — 新增团队共享区 `.team-skills/` 管理规范
- 在「总体架构」中增加 `.team-skills/` 层级和混合 symlink 结构说明
- 新增「团队 Skill 与个人 Skill 的边界」对比表
- 新增「Team Skill 准入决策」流程图和判定口诀
- 新增「禁止放入 `.team-skills/` 的典型 Skill」清单
- 更新「项目联邦」为三层管理模型（项目专属 + 通用 + 团队共享）
**v1.4.0 变更**：2026-06-05 — 源码仓库架构重构：按项目分目录 + projects.json 驱动部署
- `skills/` 重构为 `_global/`（通用）、`pkm-hub/`（pkm-hub 专属）、`aiasys/`（AIASys 专属）、`_archived/`（不部署）
- 新增 `projects.json` 项目 Skill 分发配置，声明每个项目需要的 Skill 集合
- 新增 `scripts/deploy.py` 部署脚本，按 `projects.json` 分发，替代 `generate-index-cards.py` 的部署职责
- `_collections/` 替代旧 `resources/xiaoke-collection-skills/`，第三方 Skill 暂存区统一内聚到源码仓库
- 移除「项目集成区」（`resources/xiaoke-project-ai-integration/`），AIASys Skill 已迁移到 `skills/aiasys/`
- 历史归档 Skill（directory-standards 等 8 个）物理移动到 `skills/_archived/`
- 更新「项目联邦」为 `projects.json` + `deploy.py` 模型
- 漂移检测与同步章节：`generate-index-cards.py` 引用替换为 `deploy.py`
**v1.3.0 变更**：2026-06-01 — 明确收集区/源码仓库区分 + 分发脚本支持按 skill 名筛选
- 新增「关键区分：收集区 vs 源码仓库」表格：进了源码仓库就是我们的，不需要 source 字段
- 来源标记职责归收集区的「上游Skill跟踪台账.md」
- `generate-index-cards.py` 新增 `--skill` 参数，支持按 skill 名选择性部署
- 更新同步脚本章节，替换已废弃的 sync-skill.sh 引用
**v1.2.0 变更**：2026-05-29 大规模归档——合并 6 组重复/重叠 skill，净减少 8 个活跃 skill
- 合并归档：tongyi-transcriber → media-capture、domain-learning-framework → content-to-research-project、writing-linter + terminology-guardian + citation-preferences → writing-qa（新建）、step-web-search-skill → step-web-search、gh-skill-manager → skill-development-workflow、kimi-cli-handbook 归档
- 移出开发区：codex-agents（agent 配置，非 Skill）、domain-learning-workspace & rule-history & skill-release（非 Skill 目录）
- 部署目标从 81 → 55 个活跃 Skill
- 更新已归档清单为按时间分组的完整列表
**v1.1.0 变更**：执行架构对齐——解除 `.claude` 和 `.codex` 的符号链接，统一为独立部署目标
- 删除 `.claude` → `.agents` 的符号链接，重建为独立目录
- 删除 `.codex` → `.agents` 的符号链接，重建为独立目录
- 删除 `resources/xiaoke-skill-development/skills/` 物理目录
- `.kimi-code/skills/`、`.claude/skills/`、`.codex/skills/` 全部从 `resources/xiaoke-skill-development/` 单向复制
- 更新文档中所有引用 `resources/xiaoke-skill-development/skills/` 的路径为部署目标路径
- 核心原则第 5 条、归档流程第 2 步、禁止声明、漂移检测示例命令、定期检查第 2 条均已更新# test
