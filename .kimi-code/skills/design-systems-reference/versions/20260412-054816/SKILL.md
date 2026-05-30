---
name: design-systems-reference
description: |
  Compatibility alias for design-system reference requests.
  Use when the user explicitly asks for design system examples, component precedents,
  or concrete UI inspiration; immediately load `refero-design` as the canonical skill.
  If no Refero MCP search is needed, use `refero-design/references/design-systems-reference.md`
  as the lightweight reference appendix.
---

# design-systems-reference

`refero-design` is now the canonical design-research skill in this repo.

This alias remains for prompts like:

- “给我几个成熟的 design system 参考”
- “我想看组件库案例”
- “有哪些 B2B / 政务 / 内容产品设计系统值得参考”

---

## 加载顺序

1. 先读取 `../refero-design/SKILL.md`
2. 如果只是轻量找案例，不需要 Refero MCP：
   - 读取 `../refero-design/references/design-systems-reference.md`
3. 如果要做真实 screen / flow 研究：
   - 继续走 `refero-design` 的完整研究方法

---

## alias 规则

- 不要在这里再维护一份独立的设计研究方法论
- 不要把“案例参考”与“研究工作流”拆成两套不同真相
- 新增设计系统案例时，优先补到 `refero-design/references/design-systems-reference.md`

---

**注意**: 这是 compatibility alias，不再作为独立 canonical skill 演化。
