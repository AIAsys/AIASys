---
name: gen-changelog
description: |
  Compatibility alias for changelog and release-note generation.
  Use when the user explicitly asks to generate changelog entries or release notes;
  immediately load `gen-docs` as the canonical documentation workflow and execute its changelog mode.
---

# gen-changelog

`gen-docs` is now the canonical documentation-maintenance skill.

This alias remains for prompts like:

- “帮我生成 changelog”
- “补 release notes”
- “更新 breaking changes”

## 加载顺序

1. 先读取 `../gen-docs/SKILL.md`
2. 进入 `模式 B：changelog / release notes`
3. 如涉及多语言 release notes，再按同一 canonical skill 做双语同步

## alias 规则

- 不要在这里再维护独立 changelog 工作流
- 不要绕过 `gen-docs` 直接单独改派生 release notes 页

**注意**: 这是 compatibility alias，不再单独演化。
