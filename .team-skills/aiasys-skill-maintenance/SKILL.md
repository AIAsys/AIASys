---
name: aiasys-skill-maintenance
description: |
  AIASys Skill 维护工作流（团队版）。规定代码变更时如何同步更新团队共享 Skill，
  确保 .team-skills/ 与项目实际架构保持一致。触发于：完成开发任务后、
  发现团队 Skill 与代码不符、准备提交前。与 .team-skills/sop-workflow 配合使用。
---

# AIASys Skill 维护工作流（团队版）

## 定位

本 Skill 是 AIASys 项目团队的共享规范，解决：**代码在演进，但 `.team-skills/` 中的知识在落后**。

`.team-skills/` 是项目团队的共享 Skill 池，直接维护在 AIASys 仓库中。当代码发生架构变更时，团队 Skill 也需要同步更新，否则所有读取团队 Skill 的 AI 和成员都会在过时的假设上工作。

---

## 触发条件

以下任一情况都应读取并执行本 Skill：

1. 任务涉及新增/修改/删除页面、路由、API、数据模型、全局状态、组件目录结构。
2. 在实现过程中发现 `.team-skills/` 中的描述与当前代码不符。
3. 完成开发任务后，在汇报成功前做最终检查。
4. 准备提交代码前，作为 pre-commit 检查清单的一部分。

---

## 核心原则

1. **代码和团队 Skill 共同演进**：架构变更必须反映到 `.team-skills/`。
2. **直接维护**：团队 Skill 在 `.team-skills/` 中直接编辑，不通过外部仓库部署。
3. **去敏**：`.team-skills/` 中不保留个人身份、私有路径、个人配置、管理员专属权限。
4. **自包含**：团队 Skill 不引用 `.team-skills/` 外的私有文件或路径。
5. **小步更新**：发现一个过时点就改一个点，不要等大版本重写。

---

## 两个关键检查点

### 检查点 A：Commit 前团队 Skill 同步检查

在提交代码前，判断本次改动是否影响 `.team-skills/` 中任一主题：

| 主题 | 对应团队 Skill |
|------|---------------|
| 前端架构、路由、组件分层 | `aiasys-frontend-architecture` |
| 系统设计、工作区语义、信息架构 | `aiasys-system-design` |
| Agent 工具开发、沙盒、流式输出 | `aiasys-tool-dev` |
| FastAPI 后端 API 开发 | `api-dev` |
| 开发工作流本身 | `sop-workflow` / `aiasys-skill-maintenance`（本 Skill） |
| Git 工作流 | `aiasys-git-workflow` |

**如果影响 → 进入更新决策流程**
**如果未影响 → 跳过，正常提交**

### 检查点 B：任务完成后团队 Skill 回顾

汇报任务完成前，回答：

| 问题 | 如果为是 |
|------|---------|
| 本次任务是否揭示了团队 Skill 中的错误？ | 更新对应 `.team-skills/` Skill |
| 是否新增了需要团队共同遵守的架构约定？ | 更新对应 `.team-skills/` Skill |
| 是否改动了用户-facing 功能且需要同步用户文档？ | 更新 `docs/guides/`（见 `doc-maintenance`） |
| 是否只是临时方案/实验性改动？ | 不更新 Skill，在 task session 中标注 |

---

## 团队 Skill 更新决策流程

```
代码改动完成
        │
        ▼
是否影响 .team-skills/ 中的任一主题？
        │
        ├─ 否 ──→ 正常提交
        │
        ▼
是
        │
        ▼
更新对应 .team-skills/<skill-name>/SKILL.md
        │
        ▼
是否需要新增配套 reference 文档？
        │
        ├─ 是 ──→ 在 references/ 下新增/更新专题文档
        │
        ▼
否 / 完成后
        │
        ▼
检查 team-skill-guide 是否需要同步更新
        │
        ▼
git commit（按 aiasys-git-workflow 规范）
```

---

## 团队 Skill 更新操作步骤

### 1. 定位目标 Skill

根据变更领域找到对应的 `.team-skills/` 目录：

```
.team-skills/
├── aiasys-frontend-architecture/   ← 前端路由、组件、状态、API 层
├── aiasys-system-design/           ← 工作区语义、信息架构、系统设计
├── aiasys-tool-dev/                ← Agent 工具、流式输出、沙盒
├── api-dev/                        ← FastAPI、Pydantic、后端 API
├── sop-workflow/                   ← 开发工作流
├── aiasys-git-workflow/            ← Git 规范
└── aiasys-skill-maintenance/       ← 本 Skill
```

### 2. 直接修改 `.team-skills/<skill-name>/SKILL.md`

团队 Skill 直接在 AIASys 仓库中维护，不需要外部部署脚本。

### 3. 配套 reference 文档（可选）

如果变更涉及大量细节，可在对应 Skill 目录下创建/更新 `references/`：

```
aiasys-frontend-architecture/
├── SKILL.md
├── references/
│   ├── component-inventory.md
│   ├── api-module-map.md
│   └── ...
└── examples/
```

### 4. 同步 `team-skill-guide`

如果新增、删除或重命名了团队 Skill，或某个 Skill 的 `description` 发生显著变化，更新 `.team-skills/team-skill-guide/SKILL.md` 中的快速选择表。

### 5. 提交

按 `.team-skills/aiasys-git-workflow` 规范提交：

```
<type>(<scope>): <subject>

docs: 更新前端架构 Skill，同步 WorkspacePage Pane/Dock 布局变更
```

---

## 与私有 Skill 的关系

| 维度 | 私有 Skill（个人） | 团队 Skill（本项目） |
|------|------------------|-------------------|
| 位置 | PKM-Hub → `.kimi-code/skills/` | `.team-skills/` |
| 内容 | 可含个人配置、私有路径、管理员偏好 | 去敏、通用、自包含 |
| 修改入口 | PKM-Hub 源码 + deploy.py | AIASys 仓库直接编辑 |
| 同步方向 | 私有 → 团队（手动推广） | 团队 Skill 更新后，私有按需吸收 |
| 适用对象 | 管理员个人 AI | 项目团队所有 AI/成员 |

**经验流动方向**：

```
私有 Skill 实战迭代（PKM-Hub）
        │
        │ 提炼、去敏、项目通用化
        ▼
团队 Skill（.team-skills/）
        │
        │ 团队共享
        ▼
团队成员可参考并手动吸收到自己的私有 Skill
```

---

## 与 SOP 的集成

在 `.team-skills/sop-workflow` 的 SOP-05「测试交付」完成定义（DoD）中应包含：

> - [ ] 已执行团队 Skill 同步检查：代码改动是否导致 `.team-skills/` 过时？

---

## 与 Git Workflow 的集成

在 `.team-skills/aiasys-git-workflow` 的 pre-commit 检查清单中应包含：

> - [ ] 已检查 `.team-skills/` 中相关 Skill 是否需要同步更新

---

## 禁止事项

| 禁止 | 原因 |
|------|------|
| 把个人私有 Skill 原样复制到 `.team-skills/` | 会泄露个人路径/配置 |
| 在团队 Skill 中写死 PKM-Hub 或个人路径 | 团队其他成员无法访问 |
| 团队 Skill 引用 `.team-skills/` 外的私有文件 | 破坏自包含性 |
| 只在代码里改，不更新团队 Skill | 知识逐渐过时 |
| 所有小改动都新建一个团队 Skill | 导致 Skill 碎片化 |

---

## 快速检查清单

**Commit 前：**
- [ ] 本次改动是否影响 `.team-skills/` 中的任一主题？
- [ ] 如果影响，是否已更新对应团队 Skill？
- [ ] 是否同步更新了 `team-skill-guide`？

**任务完成后：**
- [ ] 是否发现现有团队 Skill 错误/过时？
- [ ] 是否新增需要团队共同遵守的约定？
- [ ] 是否已 git commit 团队 Skill 变更？

---

## 关联 Skill

- `.team-skills/sop-workflow`：SOP-05 完成定义嵌入本 Skill 检查
- `.team-skills/aiasys-git-workflow`：commit 前检查引用本 Skill
- `.team-skills/team-skill-governance`：团队 Skill 治理规则
- `.team-skills/team-skill-guide`：Skill 发现入口，变更后需同步
- `.team-skills/doc-maintenance`：用户-facing 文档同步规范
