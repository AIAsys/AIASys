# .team-skills

本目录存放 AIASys 项目的团队共享 Skill，供团队成员的 AI 编码助手使用。

`.team-skills/` 通过 git 管理，和项目代码一样拉取更新。

---

## 核心 Skill

以下 Skill 是团队 Skill 体系的基础，**请勿删除**：

| Skill | 作用 |
|-------|------|
| `team-skill-guide` | 告诉 AI 当前项目有哪些可用 Skill 以及怎么选择 |
| `team-skill-governance` | 团队 Skill 的管理规则：准入标准、权限、怎么新增/修改 |

## 使用指南

团队成员的完整使用指南见 **`TEAM-SKILLS-USAGE.md`**（本文档同级目录）。

内容包括：
- 怎么用团队 Skill
- 团队 Skill 更新了怎么办
- 发现问题了怎么反馈
- 常见问题

---

## 快速原则

- **阅读使用**：`.team-skills/` 是团队共享的 Skill 消费层，供阅读和使用
- **不直接编辑**：`.team-skills/` 是部署输出，不是编辑入口。直接修改的内容会在下次部署时被覆盖
- **反馈渠道**：发现问题或改进建议，通过 Issue / 群聊告知管理员
- **获取更新**：`git pull`，和获取代码一样
- **个人 Skill 不放这里**：个人专属 Skill 放你自己的 AI 工具 Skill 目录
