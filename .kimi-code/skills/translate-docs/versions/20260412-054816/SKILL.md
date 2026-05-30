---
name: translate-docs
description: |
  Compatibility alias for bilingual documentation sync.
  Use when the user explicitly asks to translate docs or keep Chinese/English docs in sync;
  immediately load `gen-docs` as the canonical documentation workflow and execute its bilingual-sync mode.
---

# translate-docs

`gen-docs` is now the canonical documentation-maintenance skill.

This alias remains for prompts like:

- “把这份文档翻成英文/中文”
- “同步双语文档”
- “保持中英版本一致”

## 加载顺序

1. 先读取 `../gen-docs/SKILL.md`
2. 进入 `模式 C：双语同步`
3. 明确当前事实源语言，再执行逐段同步

## alias 规则

- 不要在这里再维护一份独立翻译规则真相
- changelog / release notes 如需翻译，也仍由 `gen-docs` 统一判断方向

**注意**: 这是 compatibility alias，不再单独演化。
