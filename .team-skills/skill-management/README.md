# Skill 体系管理规范

本文件描述 AIASys 项目 `.team-skills/` 的管理策略。

## 定位

`.team-skills/` 是 **AIASys 项目团队的共享 Skill 池**，与私人 Skill 完全解耦。

- **项目专用**：只放与 AIASys 技术栈、开发流程、协作方式直接相关的内容
- **团队共享**：团队里多个成员在 AIASys 开发时都用得上
- **去个人化**：不绑定任何个人的环境、账号、私有路径或个人偏好
- **直接维护**：Team Skill 直接在 `.team-skills/` 里创建和编辑

## 两层 Skill 体系

| 类型 | 位置 | 维护方式 | 内容特征 |
|------|------|----------|----------|
| **私人 Skill** | `.kimi-code/skills/` | 管理员在私人源码仓库维护 | 可含个人偏好、环境、私有路径 |
| **Team Skill** | `.team-skills/` | 团队直接在 AIASys 仓库维护 | 去个人化、去环境化、项目通用 |

## 管理流程

1. **创建**：在 `.team-skills/` 下新建目录，编写 `SKILL.md`
2. **更新**：直接在 `.team-skills/<skill>/SKILL.md` 中修改
3. **归档**：移动到 `.team-skills/_archived/<skill>/`

## 完整规则

详见 `SKILL.md`。
