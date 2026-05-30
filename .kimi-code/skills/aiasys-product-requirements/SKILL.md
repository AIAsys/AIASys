---
name: aiasys-product-requirements
description: Product requirements and PRD workflow for AIASys. Use when the user asks about 产品需求文档, PRD, 需求台账, docs-first iteration, requirement alignment, acceptance criteria, product semantics, or wants changes written back into product docs before or alongside implementation.
---

# AIASys 产品需求入口

这个 skill 负责把 AIASys 的产品需求、PRD、需求台账和验收口径加载正确。

---

## 何时使用

以下情况优先进入这个 skill：

- 用户提到 `PRD`、`产品需求文档`、`需求台账`
- 用户要你先整理、更新、重写、对齐产品文档
- 用户在做 docs-first 迭代，希望先定语义再做实现
- 用户问"这个功能当前产品上到底怎么定义"
- 用户要求把新的产品方向写回需求文档、交互规范、状态流或 Task Session
- 你发现实现方向依赖产品语义，但当前口径不够清楚

以下情况不要只停留在这个 skill：

- 用户已经明确要改代码，且需求口径已清楚
- 任务明确是 bug 修复或代码重构

---

## 当前执行真相

当前仓库已按“`docs/` 主要留给人类后续重写，AI 执行真相优先进入 skill / AGENTS / task session”收口。

因此这个 skill 现在优先承接：

- 产品语义判断
- 需求边界整理
- PRD 片段模板
- 当前真相 vs 目标态对齐
- 当前产品主稿维护

当前产品主稿入口：
- `.agents/skills/aiasys-product-requirements/references/current-product-prd.md`

如果用户明确要求“把人类文档也一起补回去”，再视情况同步到新的 `docs/` 结构。

---

## 使用规则

### 规则 1：先确认"当前产品真相"还是"目标态设计"

先分清用户要的是哪一种：

- 当前代码/产品实际上是什么
- 未来目标态应该怎么设计

不要把两者混写成一份结论。

### 规则 2：产品语义优先于技术实现名词

写 PRD 或产品文档时：

- 优先用用户能理解的对象和动作
- 不要默认把技术实现名词直接抬成用户主语义
- 除非文档本身就是架构设计，否则实现层名词只放到"实现说明"里

### 规则 3：需求与实现冲突时，先写清"当前真相 + 差距"

如果代码和文档不一致：

- 先明确当前代码真实行为
- 再明确当前产品希望的行为
- 再写清 gap，不要直接把未实现内容写成既成事实

### 规则 4：重要变更必须至少双写

只改一份地方不够。

涉及真实产品方向变化时，至少同步：

1. 当前 active task session
2. 对应专项 skill 或 `AGENTS.md` 中的长期规则入口
3. 如果当前仓库的人类文档已重建，再补写到新的 `docs/` 结构

---

## 输出格式

### 场景 A：写 PRD 片段

```markdown
## {功能名}

### 用户价值
{一句话}

### 验收标准 (AC)
- [ ] AC1: ...
- [ ] AC2: ...

### 范围
包含：...
不包含：...

### 实现提示（可选）
...
```

### 场景 B：对齐"当前真相 vs 目标态"

```markdown
## 当前真相
{代码/产品实际行为}

## 目标态
{产品希望的行为}

## Gap
{差距描述}

## 建议
{下一步行动}
```

---

## 写作规范

- **禁止 Emoji**：直接写文字，不要用勾号、叉号、警告图标等表情符号
- **禁止方括号状态**：使用 `状态: 已发布` 代替 `[STABLE]`

---

## 关联入口

- `AGENTS.md` —— 仓库级 AI 协作入口
- `.agents/task-sessions/` —— 当前任务边界与执行记录
- 对应专项 skill —— 长期规则入口
