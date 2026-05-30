---
name: worktree-status
description: |
  Compatibility alias for worktree auditing requests.
  Use when the user explicitly asks about worktree status, merged branches, dirty worktrees,
  or cleanup candidates; immediately load `git-workflow` as the canonical git skill and
  use `git-workflow/references/worktree-audit.md` for the detailed audit procedure.
---

# worktree-status

`git-workflow` is now the canonical git collaboration skill.

This alias remains for prompts like:

- “看看哪些 worktree 能清”
- “所有 worktree 现在什么状态”
- “哪些分支已经 squash merge 了”

## 加载顺序

1. 先读取 `../git-workflow/SKILL.md`
2. 再读取 `../git-workflow/references/worktree-audit.md`
3. 按其中的安全审计流程输出 Markdown 表格

## alias 规则

- 不要在这里再维护第二份 worktree 审计真相
- 默认 `fetch` 优先于强制 `pull`
- 清理动作仍需用户明确批准

**注意**: 这是 compatibility alias，不再单独演化。
