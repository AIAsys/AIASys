# 团队 Skill 使用指南

> 本文档面向所有团队成员，说明 `.team-skills/` 是什么、放什么内容、怎么维护、以及和私人 Skill 的区别。

## 什么是 `.team-skills/`

`.team-skills/` 是 **AIASys 项目的团队共享 Skill 池**，直接在 AIASys 仓库中维护，通过项目 git 与团队共享。

它存放的是：**AIASys 项目团队需要共同遵守的规则、掌握的方法、使用的流程**。

**核心原则**：Team Skill 与私人 Skill 解耦。

```
私人 Skill（.kimi-code/skills/）
        │
        │  个人工作核心，保留个人偏好和环境
        │
        ▼
   实战沉淀出项目通用经验
        │
        │  不是复制，而是提炼后重写
        │
        ▼
Team Skill（.team-skills/）
        │
        │  项目团队共享，去个人化
        │
        ▼
   团队成员可以参考、吸收到自己的私人 Skill
```

## 定位

| | Team Skill（`.team-skills/`） | 私人 Skill（`.kimi-code/skills/`） |
|---|---|---|
| **归属** | AIASys 项目团队 | 个人 |
| **位置** | AIASys 仓库内 | 个人 AI 工具配置目录 |
| **维护** | 团队直接在 `.team-skills/` 中编辑 | 管理员在个人源码仓库维护 |
| **内容** | 项目通用规则、流程、方法 | 个人偏好、私有工具、个人环境配置 |
| **关系** | 不来自私人 Skill，也不回写 | 可以参考 Team Skill，但不自动同步 |

## 什么内容适合放 `.team-skills/`

满足以下全部条件：

1. **项目相关**：与 AIASys 技术栈或协作流程直接相关
2. **团队通用**：团队里多人在 AIASys 开发时都用得上
3. **去个人化**：不含个人身份、画像、偏好、私有路径
4. **去环境化**：不绑定特定个人开发环境或私有工具链
5. **去敏感**：不涉及网盘、支付、个人账号、私有仓库地址
6. **可独立使用**：团队成员拿到就能用，不需要了解任何人的私人配置

**示例**：
- `aiasys-frontend-architecture` —— AIASys 前端架构约定
- `api-dev` —— FastAPI 开发规范
- `sop-workflow` —— 需求到交付的流程
- `frontend-visual-review` —— 前端视觉验收方法
- `pr-check` —— PR 前检查清单

## 什么内容不适合放 `.team-skills/`

| 类型 | 反例 | 原因 |
|------|------|------|
| 个人开发环境 | WSL/Windows 专属命令、个人路径 | 去环境化 |
| 个人账号/密钥 | API key、个人 token、私有仓库地址 | 去敏感 |
| 个人偏好 | 自己喜欢的 commit 格式、快捷键 | 去个人化 |
| 私人工作流 | 个人 Skill 部署、个人知识库管理 | 这是私人 Skill 的事 |
| 仅管理员操作 | 私人 Skill 源码仓库管理 | 团队 Skill 不管这个 |

## 怎么用

### AI 自动使用

你不需要手动打开这些文件。当你在项目中使用 AI 工具（Claude Code、Kimi Code 等）时，AI 会自动读取 `.team-skills/` 中的相关 Skill，并根据任务类型调用对应的规范。

例如：当你让 AI 帮你写前端代码时，AI 会自动读取 `aiasys-frontend-architecture/SKILL.md` 来确保代码风格符合项目规范。

### 手动查看

```bash
# 查看所有 Team Skill
ls .team-skills/

# 查看某个 Skill 的内容
cat .team-skills/<skill-name>/SKILL.md
```

## 怎么维护

### 创建新的 Team Skill

1. 在 `.team-skills/` 下新建目录，目录名即 Skill 名
2. 编写 `SKILL.md`，frontmatter 写清楚触发条件和适用场景
3. 自检：是否去个人化？是否项目相关？团队是否用得上？
4. 提交到 AIASys git，通知团队

### 更新 Team Skill

1. 发现 Team Skill 需要改进
2. 直接在 `.team-skills/<skill>/SKILL.md` 中修改
3. 提交到 AIASys git，说明变更原因

### 归档 Team Skill

1. 如果某个 Team Skill 不再适用、被其他 Skill 覆盖、或发现不适合团队共享：
   - 在 `SKILL.md` 顶部添加 `# ⚠️ 已归档（ARCHIVED）`
   - 移动到 `.team-skills/_archived/<skill>/`
   - 提交到 AIASys git

## 谁能改 `.team-skills/`？

| 操作 | 团队成员 | 管理员 |
|------|---------|--------|
| 阅读 `.team-skills/` Skill | ✅ | ✅ |
| 在 `.team-skills/` 中直接创建/编辑 Team Skill | ✅（经团队共识） | ✅ |
| 把私人 Skill 直接复制到 `.team-skills/` | ❌ | ❌ |
| 提议新增/修改 Team Skill | ✅ | ✅ |

**核心原则**：任何人都可以为团队 Skill 池贡献，但贡献的是**去个人化的项目经验**，不是自己的私人 Skill。

## 常见问题

**Q: 我可以直接改 `.team-skills/` 里的文件吗？**

A: 可以，但请确保你的修改是项目通用、去个人化的。如果是重大调整，建议先在群里和团队达成共识。不要直接把私人 Skill 复制进来。

**Q: 团队 Skill 和个人 Skill 有什么区别？**

A:
- 团队 Skill（`.team-skills/`）：项目通用规则，团队共同维护，通过 git 共享
- 个人 Skill（`.kimi-code/skills/`）：你自己维护，可以个性化定制

**Q: 我可以把个人 Skill 放到 `.team-skills/` 吗？**

A: 不能直接复制。如果你个人 Skill 里有适合团队通用的经验，可以提炼后重写为 Team Skill。

**Q: AI 用错了 Skill 怎么办？**

A: 告诉 AI 正确的 Skill 名称即可。如果 Skill 的触发描述（`description` 字段）不够准确，可以提交修改。

## 新成员上手

1. 克隆仓库：`git clone <仓库地址>`
2. 安装你的 AI 工具（Claude Code / Kimi Code 等）
3. 确认 AI 工具能读取 `.team-skills/`
4. 开始使用：AI 会自动根据任务调用相关 Skill

## 回滚机制

如果修改了 `.team-skills/` 后发现有问题：

```bash
# 撤销对某个文件的修改（未 commit 前）
git checkout -- .team-skills/<skill-name>/SKILL.md

# 撤销对所有 .team-skills/ 文件的修改
git checkout -- .team-skills/
```

如果已 commit 并 push，使用 `git revert` 回退。
