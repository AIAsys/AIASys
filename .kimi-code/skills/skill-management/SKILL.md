---
name: skill-management
description: |
  Skill 体系管理总规范。当涉及 Skill 目录结构变更、三区对齐、项目专属 Skill 落位、
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

- 新增 Skill，需要确定落位位置（通用区还是项目区）
- 开发区和正式区不一致，需要对齐
- 开发区有但正式区没有（孤儿），或正式区有但开发区没有（幽灵）
- 第三方 Skill 收集后需要分类决策
- 已归档 Skill 需要清理
- 任何"Skill 管理策略应该是什么"的问题

## 何时不要用

- 单个 Skill 的创建、修改、验证、发布：去 `skill-development-workflow`
- Skill 从对话中进化（识别改进点、更新内容）：去 `self-evolving-skill`
- 具体能力的执行：去对应领域的 Skill
- Git 操作：去 `git-workflow`
- AI 能力栈分层、多 CLI 共存、Skill/Plugin/Hook 边界：去 `pkm-ai-integration`

---

## 总体架构

Skill 体系按**源码仓库 + 部署目标**两层组织，外加**收集区**作为第三方来源。

### 两层 + 收集区关系

```
resources/xiaoke-collection-skills/     ← 收集区：第三方 Skill 原样存档
    │                                       只读参考，不直接修改
    │  筛选评估后，值得用的 → 迁入源码仓库做二次开发
    ▼
resources/xiaoke-skill-development/     ← 源码仓库：唯一 Skill 源码
    │                                       所有 Skill 在这里创建、修改、迭代
    │                                       开发完成后 → 部署到各目标
    │
    │  同步方向：单向（源码仓库 → 部署目标）
    │
    ├──→ .agents/skills/                ← 部署目标：Agent 的 Skill 读取
    ├──→ .kimi/skills/                  ← 部署目标：Kimi CLI 的 Skill 读取
    ├──→ .kimi-code/skills/             ← 部署目标：Kimi Code 用户级 Skill
    ├──→ .claude/skills/                ← 部署目标：Claude Code 的 Skill 读取
    ├──→ .codex/skills/                 ← 部署目标：Codex CLI 的 Skill 读取
    └──→ WSL AIASys .agents/skills/     ← 部署目标：联邦项目
```

**一句话区分**：收集区是「别人的东西」，源码仓库是「我们的东西」，部署目标是「工具读的东西」。

### 核心原则

1. **唯一源码**：所有 Skill 的创建、修改、迭代都在 `resources/xiaoke-skill-development/` 完成。禁止直接在部署目标修改 Skill 内容。
2. **单向同步**：源码仓库 → 部署目标。部署目标的任何变更都不应回写（如果发现不一致，应该用源码仓库覆盖部署目标，并追查不一致的原因）。
3. **部署目标独立**：各部署目标各自持有独立副本，不再使用硬链接。每个工具的 skills 目录内容一致但互不影响。
4. **按需部署**：不是所有部署目标都需要所有 Skill。例如 `kimi-webbridge` 是 Kimi Code 专属的，其他工具不需要。部署时按目标工具的实际需求选择。

### 各区读写规则

| 层级 | 路径 | 角色 | 读写规则 |
|---|---|---|---|
| **收集区** | `resources/xiaoke-collection-skills/` | 第三方 Skill 原样存档 | 只读参考，不直接修改 |
| **源码仓库** | `resources/xiaoke-skill-development/` | 唯一 Skill 源码 | 自由修改，所有变更从这里发起 |
| **部署目标** | `.agents/skills/` `.kimi/skills/` `.claude/skills/` `.codex/skills/` `~/.kimi-code/skills/` 等 | 各工具实际读取 | 只接受从源码仓库同步，禁止手工直改 |

> **注意**：项目内四个目录（`.agents/` `.kimi/` `.claude/` `.codex/`）各自独立，不再使用硬链接。`task-sessions/` 目录仍保持共享（多 CLI 共用同一会话记录）。详见 `pkm-ai-integration` 规则 3。

> `resources/xiaoke-skill-development/xiaoke-skills/` 是开发区内的第三方暂存区，与 `xiaoke-collection-skills/` 功能重叠，属于历史遗留。新收集的第三方 Skill 统一走 `xiaoke-collection-skills/`。---

## 目录结构标准

### 收集区

```
resources/xiaoke-collection-skills/
├── README.md                      # 收集区说明
├── 上游Skill跟踪台账.md            # 来源、状态、评估标记
├── _meta/                         # 元数据与历史记录
├── _collections/                  # 批量收集的 skill 集合
├── external-github/               # 外部 GitHub 仓库完整副本（可 git pull）
└── skills/                        # 单个独立 skill，按领域分类
```

### 开发区

```
resources/xiaoke-skill-development/
├── _templates/                    # Skill 创建模板
├── AGENTS.md                      # 总导航（Skill 快速选择表）
├── <skill-name>/                  # 我们自己的 skill
│   ├── SKILL.md                   # 给 agent 看（触发条件、使用边界）
│   ├── README.md                  # 给人看（可选）
│   ├── scripts/
│   ├── references/
│   └── ...
└── xiaoke-skills/                 # 历史遗留：第三方暂存区（新收集统一走 collection-skills）
```

### 正式区 → 部署目标

部署目标不再只有 `.agents/skills/`，而是多个工具的 skills 目录各自独立：

```
.agents/skills/          ← Agent CLI
.kimi/skills/            ← Kimi CLI（旧版 Python，如仍在使用）
.claude/skills/          ← Claude Code
.codex/skills/           ← Codex CLI
~/.kimi-code/skills/     ← Kimi Code 用户级（全局生效）

# 联邦项目
/home/ke/projects/AIASys/.agents/skills/   ← WSL AIASys
```

每个部署目标的结构相同，内容从源码仓库同步而来。不是所有目标都需要全部 Skill——按工具实际需求选择性部署。

> 项目内四个目录各自独立，不再使用硬链接。task-sessions/ 保持共享。

### Skill 目录的最低要求

每个 Skill 子目录必须至少有 `SKILL.md`。没有的目录不该留在开发区或正式区。

---

## 通用 Skill vs 项目专属 Skill 的边界

| 维度 | 通用 Skill | 项目专属 Skill |
|---|---|---|
| 适用范围 | 跨项目复用 | 仅特定项目使用 |
| 技术栈依赖 | 无（或极弱） | 强（如 React 19、FastAPI） |
| 示例 | git-workflow、core-standards、pdf-to-markdown | aiasys-frontend-architecture |
| 开发区 | `resources/xiaoke-skill-development/` | `resources/xiaoke-project-skill/<project>/skill-development/` |
| 命名 | 不加前缀 | 建议加项目前缀 |

**决策规则**：模糊地带优先放通用区。

---

## 能力文档与维护记录的边界

判定规则：这个文件是 AI 执行任务时需要读取的能力文档，还是 Skill 维护者管理迭代时需要的维护记录？

前者进正式区，后者留在开发区。

| 类型 | 示例 | 进正式区？ |
|------|------|-----------|
| SKILL.md | 核心能力文档 | 是 |
| 关联能力文档 | user-profile 的《思考特征》《语言特征》 | 是 |
| README.md | 给人看的说明 | 可选 |
| scripts/、references/ | 可执行脚本与参考材料 | 是 |
| CHANGELOG.md | 版本演进历史 | 否 |
| versions/、drafts/、evals/ | 历史版本、草稿、测试 | 否 |---

## 第三方 Skill 管理

### 两个区的分工

| 目录 | 放什么 | 改不改 |
|---|---|---|
| `resources/xiaoke-collection-skills/` | 别人的 skill，原样存档 | 不改，只读参考 |
| `resources/xiaoke-skill-development/` | 我们自己的 skill（含从收集区拿来二次开发改造的） | 自由修改 |

**关键区别**：收集区是「别人的东西」，开发区是「我们的东西」。从收集区拿一个 skill 到开发区做改造，就不再是原样保存了——那是二次开发，属于开发区的工作。

### 处理流程

```
1. 收集：拉取第三方 skill 到 xiaoke-collection-skills/
2. 登记：在「上游Skill跟踪台账.md」记录来源、快照日期、版本、状态
3. 评估：阅读 SKILL.md，判断质量、是否与现有 skill 重叠、是否值得二次开发
4. 决策：
   - 值得做 → 复制到 xiaoke-skill-development/，去项目化、重命名、改造
   - 纯参考 → 留在收集区，台账标注「已快照」或「待评估」
   - 无用 → 删除
5. 二次开发 → 走 skill-development-workflow 发布到正式区
```

**禁止**：未经过开发区改造的第三方 Skill 直接放入 `.agents/skills/` 正式区。

### 状态管理

收集区的 Skill 状态在台账中标记，不通过物理移动文件来反映。状态包括：「已快照」「本地化中」「已私有化」「已正式接入」。详见 `resources/xiaoke-collection-skills/上游Skill跟踪台账.md`。

---

## 已归档 Skill 处理

### 归档触发条件

- Skill 声明「已并入 XXX」
- Skill 功能被其他 Skill 完全覆盖
- Skill 被标记为废弃超过 3 个月

### 归档流程

1. 在 Skill 的 `SKILL.md` 顶部添加 `# ⚠️ 已归档（ARCHIVED）` 标记
2. 从 `.agents/skills/` 删除
3. 在 `Archives/` 下备份正式区版本
4. 开发区的副本保留作为历史记录，不再维护

### 已归档 Skill 保留清单

以下 Skill 已归档，保留在开发区但已从正式区删除：

- `directory-standards` → 并入 `pkm-content-organizer`
- `domain-learning` → 并入 `content-to-research-project`
- `entry-manager` → 并入 `pkm-content-organizer`
- `inbox-triage` → 并入 `pkm-content-organizer`
- `knowledge-cards` → 并入 `pkm-content-organizer`
- `para-manager` → 并入 `pkm-content-organizer`
- `resource-curator` → 并入 `pkm-content-organizer`
- `rule-evolution` → 并入 `pkm-content-organizer`
- `task-persistence` → 并入 `pkm-content-organizer`

已恢复的 Skill：

- `ebook-manager`（2026-05-24 恢复）

---

## 最近归档

- `playwright-cli`（2026-05-28 归档）：浏览器自动化统一使用 Kimi WebBridge。`tongyi-transcriber` 和 `pdf-to-markdown` 的 Cookie 导入链路需逐步迁移到 WebBridge。

---

## 漂移检测与同步

### 漂移类型

| 类型 | 表现 | 处理 |
|---|---|---|
| **部署目标超前** | 部署目标比源码仓库新 | 用源码仓库覆盖部署目标（部署目标不应有独立变更） |
| **源码仓库有但部署目标无** | 新 Skill 或更新未同步 | 评估后部署 |
| **部署目标有但源码仓库无** | 幽灵 Skill（历史遗留） | 回同步到源码仓库，评估后保留或归档 |

### 修改前置检查（强制）

每次修改 Skill 时，先在源码仓库修改，然后同步到需要的部署目标：

```bash
# 对比源码仓库和部署目标
diff resources/xiaoke-skill-development/<skill>/SKILL.md .agents/skills/<skill>/SKILL.md
```

| 检查结果 | 处理方式 |
|---|---|
| 一致 | 直接在源码仓库修改，改完同步 |
| 部署目标更新 | 追查不一致原因，用源码仓库覆盖部署目标 |
| 源码仓库更新 | 同步到部署目标 |

### 同步顺序

```
1. 在源码仓库完成修改
2. 确定需要同步的部署目标（不是所有目标都需要该 Skill）
3. 逐目标同步：cat "$src" > "$dst"（避免硬链接残留）
4. 更新关联 skill 的交叉引用
5. 如果是联邦项目，额外同步到 WSL AIASys 等外部目标
```

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
- 新增 Skill 时，必须在开发区 `AGENTS.md` 快速选择表登记
- 根目录 `AGENTS.md` 只保留项目级红线禁令和规范入口指向（`core-standards` + `pkm-ai-integration`），不维护 Skill 列表

### 定期检查

1. 每个 Skill 的 `description` 是否准确覆盖了触发场景
2. 已归档 Skill 是否已从正式区移出
3. Skill 分组是否合理

---

## 项目联邦（简）

有独立仓库的项目（如 AIASys），其 skills 目录从 pkm-hub 源码仓库单向同步。联邦项目的 Skill 修改先在 pkm-hub 源码仓库完成，再由联邦项目拉取同步。

同步方式：`cat pkm-hub/resources/xiaoke-skill-development/<skill>/SKILL.md > AIASys/.agents/skills/<skill>/SKILL.md`

---

## 最小验收清单

在对 Skill 体系做任何调整后，确认：

- [ ] 源码仓库是唯一的变更发生地
- [ ] 所有需要的部署目标已同步
- [ ] 已归档 Skill 已从所有部署目标删除
- [ ] 孤儿/幽灵 Skill 已处理
- [ ] 根目录 `AGENTS.md` 入口指向是否有效（应指向 `core-standards/SKILL.md` 和 `pkm-ai-integration/SKILL.md`）
- [ ] 关联 skill 的交叉引用已检查，无失效引用
- [ ] 第三方 Skill 收集库未污染源码仓库和部署目标