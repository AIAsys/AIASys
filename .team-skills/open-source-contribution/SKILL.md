---
name: open-source-contribution
description: |
  当 AI 或成员需要向 AIASys 或其他开源项目提交 Issue、认领 Issue、提交 PR 时使用。
  触发于"提 issue""认领 issue""提 PR""给开源项目反馈 bug""fork 项目""贡献代码"
  "open source contribution""向上游提交"等场景。
  适用于 GitHub 开源项目的 Issue 报告、Issue 认领、PR 提交、Code Review 参与。
  不适用于项目内部的纯 Git 操作（用 aiasys-git-workflow）或不涉及上游提交的代码审查。
---

# Open Source Contribution — 开源贡献与 Issue 认领

向 AIASys 等开源项目提交 Issue、认领 Issue 和提交 PR 的团队规范。核心原则：**先搜索、先认领、再动手；原子化提交；PR 必须关联 Issue**。

---

## 核心原则

1. **先搜后提 / 先搜后认领**：任何动作前先在现有 Issue / PR 中搜索，避免重复。
2. **Issue 是枢纽**：PR 必须关联 Issue；Issue 应引用相关 PR。
3. **认领后再开工**：非 trivial 改动必须在 Issue 下明确认领，防止多人重复劳动。
4. **原子化**：一个 Issue 报一个问题，一个 PR 解决一个 Issue。
5. **尊重社区规范**：先读 `CONTRIBUTING.md`、PR 模板和已合并 PR 案例。

---

## 工作流 A：提交 Issue

1. 在仓库 Issues 中搜索相关关键词，确认不重复。
2. 撰写 Issue，包含：标题、环境、复现步骤、预期/实际行为、根因分析（如有）、临时方案。
3. 提交后持续关注，补充相关 PR 引用。

---

## 工作流 B：认领 Issue

1. 在目标 Issue 下评论认领，例如：
    ```text
    I'd like to work on this. I plan to ... and expect to open a PR within X days.
    ```
    或中文：
    ```text
    我想认领这个 Issue，计划修改 ...，预计 X 天内提交 PR。
    ```
2. 等待维护者确认，或 24 小时内无反对即可开工。
3. **协调优先**：若 Issue 已有评论认领且认领者正在推进，后续贡献者应优先在 Issue 下留言表明愿意协助或 review，而非重复认领或直接另提 PR。维护者可介入协调分工或合并推进。
4. 若无法继续，及时在 Issue 下说明并取消认领，让其他人接手。
5. AI 执行时：先在本地记录任务，再到 Issue 下评论认领，最后开工。

推荐使用以下状态标签标记 Issue 进度（非强制）：

- `[认领中]` — 有人评论认领，等待维护者确认
- `[进行中]` — 认领者已开工，最好附上预计 PR 时间
- `[已有 PR]` — 已有关联 PR，优先 review 而非另开
- `[需要帮助]` — 认领者遇到困难，欢迎接手

---

## 工作流 C：提交 PR

1. 阅读项目 `CONTRIBUTING.md` 与 `AGENTS.md`（如有）。
2. 阅读 PR / Issue 模板。
3. 研究 3-5 个已合并 PR 的格式与规模。
4. 检查是否有同类 PR；有则优先 review 而非另提。
5. 实现改动，保持原子化，包含测试。
6. PR 描述必须关联 Issue：`Closes #XXX`、`Fixes #XXX` 或 `Refs #XXX`。
7. 标题遵循 Conventional Commits。
8. 通过 CI 后请求 review。

---

## 回应维护者

- 先完成要求（rebase、补信息、跑 check），再回复。
- 每次回复附带可验证进展。
- 若发现别人提了更完整的 PR，关闭自己的 Issue/PR 并去 review 对方的。

---

## 自检清单

**提 Issue 前：**
- [ ] 搜索过现有 Issue，确认不重复
- [ ] 标题包含关键信息
- [ ] 提供了复现步骤和环境

**认领 Issue 前：**
- [ ] 该 Issue 未被他人认领或维护者已分配
- [ ] 已在 Issue 下评论认领
- [ ] 已规划改动范围和预期时间

**提 PR 前：**
- [ ] 已读 `CONTRIBUTING.md`
- [ ] 已关联 Issue
- [ ] 改动原子化，不包含无关变更
- [ ] 已跑 lint / test / typecheck
- [ ] 已 rebase 到最新目标分支（AIASys 通常是 `dev`）

---

## 关联文档

- `CONTRIBUTING.md`：AIASys 贡献指南（权威）
- `.team-skills/aiasys-git-workflow`：项目内部 Git 工作流
- `.team-skills/pr-check`：PR 提交前检查
