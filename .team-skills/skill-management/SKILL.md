---
name: skill-management
description: |
  AIASys 项目 Team Skill 管理指南。
  明确 `.team-skills/` 的定位、内容边界、创建/更新/归档流程，
  以及 Team Skill 与私人 Skill 的区别。
  触发于：不确定某个 Skill 该放 `.team-skills/` 还是私人 Skill、
  要新增/修改 Team Skill、要判断内容是否适合团队共享。
---

# skill-management

AIASys 项目 Team Skill 的管理指南。

---

## 定位

`.team-skills/` 是 **AIASys 项目团队的共享 Skill 池**，直接在 AIASys 仓库中维护，通过项目 git 与团队共享。

它回答的问题是："**AIASys 项目团队需要共同遵守哪些规则、掌握哪些方法？**"

它**不是**：
- 私人 Skill 的备份或复制
- 管理员个人的工作流手册
- 任何个人的收藏夹或偏好集合

---

## 内容边界

### 适合放进 `.team-skills/` 的内容

| 类型 | 示例 |
|------|------|
| 项目架构约定 | `aiasys-frontend-architecture`、`aiasys-system-design` |
| 开发流程规范 | `api-dev`、`sop-workflow`、`aiasys-git-workflow` |
| 团队协作规则 | `team-skill-governance`、`pr-check` |

**共同特征**：
- 与 AIASys 技术栈或协作流程直接相关
- 团队里多人在 AIASys 开发时都用得上
- 去个人化、去环境化
- 团队成员拿到就能用，不需要了解任何人的私人配置

### 不适合放进 `.team-skills/` 的内容

| 类型 | 反例 | 原因 |
|------|------|------|
| 个人开发环境 | WSL/Windows 专属命令、个人路径 | 去环境化要求 |
| 个人账号/密钥 | API key、个人 token、私有仓库地址 | 去敏感要求 |
| 个人偏好 | 自己喜欢的 commit 格式、快捷键 | 去个人化要求 |
| 私人工作流 | 个人 Skill 部署、个人知识库管理 | 这是私人 Skill 的事 |
| 仅管理员操作 | deploy.py、私人 Skill 源码仓库管理 | 团队 Skill 不管这个 |

**判定口诀**：这是"AIASys 项目需要大家知道的事"，不是"我个人怎么顺手的事"。

---

## 管理流程

### 创建新的 Team Skill

1. 在 `.team-skills/` 下新建目录，目录名即 Skill 名
2. 编写 `SKILL.md`，frontmatter 写清楚触发条件和适用场景
3. 自检：是否去个人化？是否项目相关？团队是否用得上？
4. 提交到 AIASys git，通知团队

### 更新 Team Skill

1. 发现 Team Skill 需要改进（使用中暴露问题、项目流程变化等）
2. 直接在 `.team-skills/<skill>/SKILL.md` 中修改
3. 提交到 AIASys git，说明变更原因

### 归档 Team Skill

1. 如果某个 Team Skill 不再适用、被其他 Skill 覆盖、或发现不适合团队共享：
   - 在 `SKILL.md` 顶部添加 `# ⚠️ 已归档（ARCHIVED）`
   - 移动到 `.team-skills/_archived/<skill>/`
   - 提交到 AIASys git

---

## 与私人 Skill 的关系

```
私人 Skill（个人 .kimi-code/skills/）
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

**关键规则**：
- 不直接分发：不把私人 Skill 原样搬入 `.team-skills/`
- 不反向同步：`.team-skills/` 的改动不回写到私人 Skill
- 允许互相启发：但必须是手动提炼，不是自动同步

---

## 写作规范

Team Skill 的 `SKILL.md` 应遵循：

1. **项目视角**：用"AIASys 项目"做主语，不用"我"
2. **跨系统优先**：默认写作要同时适用于 Windows、macOS、Linux。如果必须提及某个系统，必须说明三个系统分别怎么处理，除非本 Skill 就是专门讲该系统的
3. **去环境化**：不写特定个人操作系统或开发环境的命令
4. **去个人化**：不出现个人姓名、账号、私有路径
5. **自包含**：不依赖 `.team-skills/` 外的 Skill 才能看懂
6. **可操作**：给出明确的触发条件、执行步骤、验收标准

---

## 最小自检清单

新增或修改 Team Skill 前，确认：

- [ ] 内容与 AIASys 项目直接相关
- [ ] 团队里多人能用得上
- [ ] 不含个人身份、私有路径、个人账号
- [ ] 不绑定特定开发环境（如 WSL/Windows 专属）
- [ ] 不引用外部私有资源
- [ ] 不泄露敏感信息
