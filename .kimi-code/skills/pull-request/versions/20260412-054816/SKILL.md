---
name: pull-request
description: |
  Compatibility alias for pull-request preparation and submission.
  Use when the user explicitly asks to open or prepare a PR; immediately load `git-workflow`
  as the canonical git skill and follow its branch / push / PR preparation steps.
---

# pull-request

`git-workflow` is now the canonical git collaboration skill.

This alias remains for prompts like:

- “帮我开个 PR”
- “整理一下然后提 PR”
- “准备提交给 GitHub / GitLab”

## 加载顺序

1. 先读取 `../git-workflow/SKILL.md`
2. 完成：
   - 精确暂存
   - 分批提交
   - 分支同步
   - push / PR 准备
3. 再按当前仓库要求使用 `gh` 或对应平台工具

## alias 规则

- 不要在这里再维护一份独立 PR 流程
- PR 标题、提交粒度、提交前检查都以 `git-workflow` 为准

**注意**: 这是 compatibility alias，不再单独演化。
