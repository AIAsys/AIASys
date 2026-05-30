---
name: docs-archiving
description: |
  Compatibility alias for documentation archiving and legacy-doc cleanup.
  Use when the user explicitly asks to archive old docs, sink historical materials,
  or remove outdated docs from current entrypoints; immediately load `gen-docs` as the canonical docs workflow
  and execute its archiving mode with `gen-docs/references/docs-archiving.md`.
---

# docs-archiving

`gen-docs` is now the canonical documentation-maintenance skill.

This alias remains for prompts like:

- “把旧 docs 归档”
- “把历史材料下沉到 archive”
- “清掉 docs 主入口里的遗留文档”

## 加载顺序

1. 先读取 `../gen-docs/SKILL.md`
2. 进入 `模式 D：文档归档 / 历史材料下沉`
3. 再读取 `../gen-docs/references/docs-archiving.md`

## alias 规则

- 不要在这里维护一套独立 docs 治理真相
- 归档动作仍归属于 canonical docs workflow
- 新的归档规则优先补到 `gen-docs` 或其 references

**注意**: 这是 compatibility alias，不再单独演化。
