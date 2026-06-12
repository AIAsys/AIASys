# 团队 Skill 使用指南

> 本文档面向所有团队成员，说明 `.team-skills/` 是什么、怎么用、以及更新了怎么办。

## 什么是 `.team-skills/`

`.team-skills/` 是 AIASys 项目的团队共享 AI 协作规范目录。里面存放的是由管理员在个人 Skills 中开发并实战验证后，部署到团队的 Skill 文件。

**核心原则：个人 Skills → 部署到团队**

```
管理员的个人 Skills（创新和迭代在这里发生）
    │
    │  实战验证 → 证明好用
    ▼
.team-skills/                     ← 团队消费层（git 跟踪，团队可读可反馈）
    │
    │  团队使用 + 提供反馈
    ▼
管理员吸收反馈 → 个人 Skills 迭代 → 重新部署
```

**特点**：
- 通过 git 管理，和项目代码一样拉取更新
- 所有团队成员都可以直接阅读和使用
- 团队**不直接编辑** `.team-skills/` 中的 Skill 内容
- 发现问题或改进建议，通过反馈渠道告知管理员
- 你的 AI 工具（Claude Code / Kimi Code）会自动读取这些 Skill

## 怎么用

### AI 自动使用

你不需要手动打开这些文件。当你在项目中使用 AI 工具（Claude Code、Kimi Code 等）时，AI 会自动读取 `.team-skills/` 中的相关 Skill，并根据任务类型调用对应的规范。

例如：当你让 AI 帮你写前端代码时，AI 会自动读取 `aiasys-frontend-architecture/SKILL.md` 来确保代码风格符合项目规范。

### 手动查看

如果你想了解项目有哪些可用的 Skill：

```bash
# 查看所有 Skill
ls .team-skills/

# 查看某个 Skill 的内容
cat .team-skills/<skill-name>/SKILL.md
```

## 团队 Skill 更新了怎么办

`.team-skills/` 通过 git 管理，获取更新和获取代码更新一样：

```bash
# 拉取最新代码（包含 Skill 更新）
git pull

# 查看哪些 Skill 文件有变更
git diff --name-only HEAD@{1} -- .team-skills/

# 查看某个 Skill 的具体变更
git diff HEAD@{1} -- .team-skills/<skill-name>/
```

**更新后**：AI 工具会在下次会话时自动读取最新的 Skill 内容，不需要额外操作。

## 我发现了问题，怎么反馈？

`.team-skills/` 的内容由管理员在个人 Skills 中统一维护。团队不直接编辑 `.team-skills/`，但可以通过以下方式提供反馈：

| 问题类型 | 怎么反馈 |
|---------|---------|
| 错别字、格式问题 | 群里告知管理员，或提交 Issue |
| 内容错误、描述不准确 | 群里告知管理员，说明问题和建议 |
| 缺少某个能力 | 说明需求场景，由管理员在个人 Skills 中开发后部署 |
| 改进建议 | 通过 Issue 或群聊提出 |

**反馈模板**：
```
Skill 名称：xxx
问题描述：（具体哪里不对）
建议修改：（你的方案）
影响范围：（会影响哪些成员的开发）
```

> **为什么不直接改？** `.team-skills/` 是部署输出，不是编辑入口。直接修改的内容会在下次部署时被覆盖。所有 Skill 的创建和迭代都在管理员的个人 Skills 中进行。

## 团队 Skill 怎么来的

`.team-skills/` 中的所有 Skill 都由管理员在个人 Skills 中开发并实战验证后，统一部署到团队的。

**流程**：
```
管理员的个人 Skills（创新和迭代）
    │
    │  实战验证 → 证明稳定好用
    ▼
去敏 + 自包含检查
    │
    ▼ 部署到 .team-skills/
通知团队
```

如果你是管理员，想把自己个人 Skills 中的某个 Skill 部署到团队：

```
1. 在个人 Skills 中完成 Skill 开发
2. 在你的个人 AI 工具中实战验证，确认稳定好用
3. 自查：去敏 + 自包含 + 通用性
4. 部署到 .team-skills/：
   4. 部署到 .team-skills/（由管理员统一处理）
5. 通知团队新 Skill 已上线
```

## 常见问题

**Q: 我可以直接改 `.team-skills/` 里的文件吗？**

A: 不建议。`.team-skills/` 是部署输出层，不是编辑入口。直接修改的内容会在下次部署时被覆盖。如果你发现内容有问题，请通过反馈渠道告知管理员，由管理员在个人 Skills 中迭代后重新部署。

**Q: 团队 Skill 和个人 Skill 有什么区别？**

A:
- 团队 Skill（`.team-skills/`）：管理员开发并部署，团队共同消费，通过 git 获取更新
- 个人 Skill（`.kimi-code/skills/`）：你自己维护，可以个性化定制

**Q: 我可以把个人 Skill 放到 `.team-skills/` 吗？**

A: 不行。`.team-skills/` 由管理员统一部署。如果你想提议一个新 Skill 到团队，告知管理员需求场景，由管理员开发。

**Q: 我不小心改了 `.team-skills/` 的内容，想撤销怎么办？**

A:
```bash
git checkout -- .team-skills/<skill-name>/SKILL.md
```

> 但更好的做法是：不要直接改，改完会丢失。直接告知管理员你的需求。

**Q: AI 用错了 Skill 怎么办？**

A: 告诉 AI 正确的 Skill 名称即可。如果 Skill 的触发描述（`description` 字段）不够准确，告知管理员，由管理员修改后重新部署。

---

## 新成员上手

### 1. 克隆仓库

```bash
git clone <仓库地址>
cd AIASys
```

### 2. 安装 AI 工具

根据你使用的 AI 工具选择：

| 工具 | 安装方式 | 说明 |
|------|---------|------|
| **Claude Code** | `npm install -g @anthropic-ai/claude-code` | 在项目根目录运行 `claude` 即可，会自动读取 `.team-skills/` |
| **Kimi Code** | 按官方文档安装 | 配置 skills 目录指向 `.team-skills/` |

### 3. 确认 AI 工具能读到团队 Skill

启动 AI 工具后，问它：

```
当前项目有哪些团队 Skill？
```

如果 AI 能列出 `.team-skills/` 中的 Skill，说明配置成功。

### 4. 拉取最新 Skill

```bash
git pull
```

### 5. 开始使用

启动 AI 工具，它会自动读取 `.team-skills/` 中的相关 Skill。

---

## Git 冲突解决

由于 `.team-skills/` 的内容由管理员统一部署，团队不直接编辑，正常情况下不会产生冲突。

如果出现冲突（例如 `git pull` 时提示冲突），通常是以下原因：
- 你或同事不小心修改了 `.team-skills/` 中的文件
- 管理员在你 `git pull` 之前部署了新内容

```bash
# 如果看到冲突提示
# 1. 放弃你的本地修改，恢复为远程版本
git checkout -- .team-skills/

# 2. 重新拉取
git pull
```

**遇到冲突时**：不需要手动合并。告知管理员，由管理员处理。
- 保留双方的有效修改
- 如果不确定，在群里问对方
- 合并后通知管理员审核

---

## 回滚机制

### 撤销本地修改

```bash
# 撤销对某个文件的修改（未 commit 前）
git checkout -- .team-skills/<skill-name>/SKILL.md

# 撤销对所有 .team-skills/ 文件的修改
git checkout -- .team-skills/
```

> **提醒**：.team-skills/ 不应该被直接修改。如果你发现自己需要频繁回滚，说明你的工作流可能有问题——直接告知管理员你的需求，由管理员在个人 Skills 中处理后部署。

### 撤销已 push 的修改

```bash
# 直接回退到远程版本
git revert HEAD -- .team-skills/
git push
```

### 查看历史版本

```bash
# 查看某个 Skill 的修改历史
git log --oneline -- .team-skills/<skill-name>/

# 查看某个历史版本的内容
git show <commit-hash>:.team-skills/<skill>/SKILL.md

# 恢复到某个历史版本
git checkout <commit-hash> -- .team-skills/<skill>/
git commit -m "revert: <skill-name> back to <commit-hash>"
```

---

## ⚠️ 重要提醒

### 部署由管理员负责

团队成员不需要运行任何部署脚本。`.team-skills/` 的更新由管理员审核后统一处理。

### 不要直接修改 `.team-skills/`

`.team-skills/` 是部署输出层，**不建议直接修改**。直接修改的内容会在下次部署时被覆盖。

如果你发现 `.team-skills/` 中的内容有问题，请通过反馈渠道告知管理员，由管理员在个人 Skills 中迭代后重新部署。

### 不要直接修改源码仓库

团队成员**不能直接修改** `resources/xiaoke-skill-development/`。源码仓库由管理员统一维护。
