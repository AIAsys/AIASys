---
name: team-skill-governance
description: |
  团队 Skill 管理机制。当需要了解团队 Skill 怎么维护、怎么添加新 Skill、
  怎么更新现有 Skill、谁有权限修改、个人 Skill 怎么推广到团队、
  或团队 Skill 和个人 Skill 怎么共存时触发。
  适用于 Skill 管理决策、新 Skill 落位、权限争议、同步策略制定。
  不替代具体 Skill 的编写，只提供管理规则。
---

# 团队 Skill 治理

## 定位

管理 `.team-skills/` 的增删改查规则。确保团队 Skill：
- 自包含（不依赖外部 Skill）
- 去敏（不含个人敏感信息）
- 可维护（有明确的更新流程）

## 核心模型：个人 Skills 部署到团队

```
个人 Skills（源码仓库 skills/_global/ 或 skills/aiasys/）
    │
    │  你在个人环境中实战验证 → 证明好用
    ▼
部署到 .team-skills/                    ← 团队消费层（git 跟踪，团队可读可反馈）
    │
    │  团队使用 + 提供反馈
    ▼
你吸收反馈 → 个人 Skills 迭代
    │
    │  再次部署
    ▼
.team-skills/ 更新
```

**核心原则**：
- `.team-skills/` 是**部署输出层**，不是编辑入口
- 所有 Skill 的创建和迭代都在**个人 Skills 中**进行
- `.team-skills/` 的内容由管理员统一部署
- 团队可以**阅读和使用** `.team-skills/` 中的 Skill，也可以**提出反馈和建议**
- 团队**不直接编辑** `.team-skills/` 中的 Skill 内容
- 你有最终决定权：个人 Skills 的实战验证是团队 Skill 的唯一来源

## 权限矩阵

| 操作 | 团队贡献者 | 管理员（负责人） |
|------|-----------|--------------|
| 读取 `.team-skills/` Skill | ✅ 自由阅读 | ✅ |
| 使用 `.team-skills/` Skill | ✅ 在 AI 工具中使用 | ✅ |
| 提出修改建议 / 反馈 | ✅ 通过 Issue / PR / 群聊 | ✅ |
| 直接编辑 `.team-skills/` 内容 | ❌ | ✅（但推荐走个人 Skills 迭代后部署） |
| 创建 / 修改个人 Skills | ✅ 自由维护 | ✅ |
| 部署个人 Skills 到 `.team-skills/` | ❌ | ✅ |
| 审核个人 Skill → 团队 Skill | — | ✅ |

## 准入标准（什么 Skill 能进 `.team-skills/`）

进入团队共享区的 Skill 必须同时满足以下全部条件：

| 检查项 | 通过标准 | 应排除的示例 |
|--------|---------|------------|
| **通用性** | 团队内多数成员会用得上 | `wsl-windows-bridge`（仅特定环境用户） |
| **去个人化** | 不含个人身份、画像、偏好、私有路径 | `user-profile` |
| **去环境化** | 不绑定特定个人开发环境或私有工具链 | `windows-admin-elevator` |
| **自包含** | 不引用 `.team-skills/` 外的 Skill 路径或内容 | 引用外部 Skill 但未内嵌 |
| **去敏感** | 不涉及网盘、支付、个人账号、私有仓库地址 | `baidu-pan-manager` |
| **项目相关** | 与 AIASys 技术栈或协作流程直接相关 | 其他项目的专属 Skill |

**判定口诀**：团队里的任意一个成员拿到这个 Skill 都能直接用，不需要知道你的个人配置。

### 常见误判

- "这个 Skill 很有用" → 不等于 "团队每个人都用得上"
- "这个 Skill 是通用的" → 不等于 "不绑定我的个人环境"
- "我只是顺手放进去" → 团队 Skill 不是个人收藏夹

### 完整准入流程

```
个人 Skill 想发布到团队
    │
    ├─ 是否含个人敏感信息？（姓名、画像、偏好、私有路径）
    │   └─ 是 → 先去除敏感信息
    ├─ 是否绑定个人环境？（特定电脑、私有账号、个人工具链）
    │   └─ 是 → 替换为通用配置或去除
    ├─ 是否涉及敏感工具？（网盘、支付、个人账号）
    │   └─ 是 → 排除
    ├─ 团队多数人是否用得上？
    │   └─ 否 → 排除
    ├─ 是否与 AIASys 技术栈/协作流程相关？
    │   └─ 否 → 排除
    ├─ 是否自包含？（不引用 .team-skills/ 外的 Skill）
    │   ├─ 是 → 纳入
    │   └─ 否 → 将依赖也复制到 .team-skills/，或排除
    └─ 管理员审核 → 纳入 .team-skills/
```

## 核心原则

### 1. 自包含原则

团队 Skill 必须独立运行：
- 不引用 `.team-skills/` 外的 Skill 路径
- 不依赖外部 Skill 的内容或数据
- 不提及团队外的 Skill 仓库或来源

**如果需要外部能力**：复制到 `.team-skills/` 内独立维护，或重新编写团队版本。

### 2. 去敏原则

进入 `.team-skills/` 的 Skill 必须去除：
- 个人身份信息（姓名、画像、偏好）
- 私有路径（个人电脑路径、私有仓库地址）
- 敏感工具（网盘、支付、个人账号相关）
- 其他项目专属内容

### 3. 个人优先原则

所有 Skill 的创建和迭代都在**个人 Skills** 中进行：
- 你在个人环境中使用 Skill，验证其价值
- 经过实战验证的好 Skill，才部署到 `.team-skills/`
- `.team-skills/` 是部署输出，不是编辑入口
- 团队通过反馈提出改进需求，你在个人 Skills 中迭代后重新部署

**关键规则**：
- 不要在 `.team-skills/` 中直接创建新 Skill
- 个人 Skills 是你唯一的创新来源
- 团队 Skill 的更新 = 你的个人 Skills 经过验证后部署到团队

### 4. 团队反馈原则

团队不直接编辑 `.team-skills/`，但可以通过以下方式提供反馈：
- 使用中发现问题 → 告知你
- 提出改进建议 → 通过 Issue / PR / 群聊
- 提议新 Skill → 说明需求场景，由你在个人 Skills 中开发

## 更新流程

### 管理员更新 Team Skill（推荐流程）

```
1. 在你的个人 Skills 中创建/修改 Skill
   └─ 路径：skills/_global/<skill>/ 或 skills/aiasys/<skill>/

2. 在你的个人 AI 工具中实战验证
   └─ 确认 Skill 在实际使用中有效、有用

3. 去敏检查（去除个人身份、私有路径、个人配置）

4. 部署到 .team-skills/

5. 通知团队：Skill 已更新，git pull 获取
```

### 团队提出反馈

```
1. 使用 .team-skills/ 中的 Skill
2. 发现问题或改进建议
3. 通过以下方式告知管理员：
   - 在群里直接说
   - 提 Issue 描述问题
   - 提交 PR（仅建议，不直接改文件）
4. 管理员评估后，在个人 Skills 中迭代
5. 验证后重新部署到 .team-skills/
```

### 个人 Skill 推广到团队

```
1. 在个人 Skills 中完成 Skill 开发
2. 实战验证（使用超过 2 周，证明稳定有用）
3. 自查：去敏 + 自包含 + 通用性
4. 部署到 .team-skills/
5. 通知团队新 Skill 已上线
```

## 命名规范

| 类型 | 命名 | 示例 |
|------|------|------|
| 团队通用 | `team-*` | `team-skill-guide`、`team-skill-governance` |
| 项目专属 | `<project>-*` | `aiasys-git-workflow`、`aiasys-system-design` |
| 通用能力 | 保持原名 | `task-session`、`safe-delete` |

## 解耦原则

团队 Skill 必须自包含，禁止：

1. **引用外部 Skill 的路径** —— 所有引用必须在 `.team-skills/` 内部
2. **依赖外部 Skill 的内容** —— 团队 Skill 独立维护
3. **暴露外部 Skill 的存在** —— 不提及团队外的 Skill 仓库或来源

如果需要外部 Skill 的能力：
- 复制到 `.team-skills/` 中独立维护
- 或重新编写团队版本

## 常见问题

### Q: 团队 Skill 更新了，我怎么获取最新版？

A: `git pull`。`.team-skills/` 通过 git 管理，和代码一样拉取。

### Q: 我发现团队 Skill 有问题，可以直接改吗？

A: 不建议直接改。请通过反馈渠道告知管理员，由管理员在个人 Skills 中迭代后重新部署。直接修改 `.team-skills/` 的内容会在下次部署时丢失。

### Q: 个人 Skill 怎么变成团队 Skill？

A: 在你自己的个人 Skills 中开发 → 实战验证 → 去敏 → 部署到 `.team-skills/` → 通知团队。详见上方「个人 Skill 推广到团队」流程。

### Q: 我想提议一个新 Skill 怎么办？

A: 说明需求场景和使用方式，告知管理员。管理员会在个人 Skills 中开发，验证后再部署到团队。

### Q: `.team-skills/` 和 `skills/aiasys/` 是什么关系？

A: `skills/aiasys/` 是你个人 Skills 的源码区（创新和迭代在这里发生）。`.team-skills/` 是经过你验证后部署到团队的消费层。所有 Skill 内容都从个人 Skills 流出。

### Q: 我的个人 Skill 和团队 Skill 重复了怎么办？

A: 个人 Skill 可以保留。团队 Skill 是通用版本，你可以继续用个人定制版。个人版更新后，如觉得团队也该更新，可以重新部署。

## 输出规范

被调用时，AI 应：
1. 说明当前团队 Skill 的管理规则
2. 根据用户问题给出具体的管理建议
3. 强调自包含和去敏原则
4. 引用 `team-skill-guide` 给团队成员看使用指南
