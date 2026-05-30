---
name: skill-creator
description: |
  Compatibility alias for AIASys skill authoring and optimization requests.
  Use when the user explicitly asks to create a skill, improve a skill, benchmark a skill,
  or optimize trigger wording; immediately load `skill-development-workflow` as the canonical entry,
  and reuse this directory's eval/benchmark resources only when those deeper tools are actually needed.
---

# skill-creator

`skill-development-workflow` is now the canonical skill-governance entry in this repo.

This directory stays alive for two reasons:

1. 兼容旧触发词
2. 继续承载 benchmark / eval viewer / grader / comparator 这些较重资源

---

## 何时使用这个 alias

- 用户明确说“创建一个 skill”
- 用户明确说“优化一下这个 skill”
- 用户明确说“帮我跑 skill eval / benchmark”
- 现有任务已经指向 `skill-creator`，不想立刻改口

如果用户只是想：

- 修改现有 skill
- 合并重复 skill
- 整理 `.agents/skills`
- 发布 skill

优先走 `skill-development-workflow`，不要在这里重复维护另一套主流程。

---

## 加载顺序

1. 先读取 `../skill-development-workflow/SKILL.md`
2. 以它作为主流程决定：
   - canonical skill
   - compatibility alias
   - 开发区编辑
   - 发布动作
3. 只有在以下场景，再继续使用本目录资源：
   - 需要 benchmark / grading
   - 需要 eval viewer
   - 需要 description improver
   - 需要 old-vs-new skill 对比实验

---

## 本目录资源怎么用

### benchmark / eval

用这些资源：

- `scripts/run_eval.py`
- `scripts/run_loop.py`
- `scripts/aggregate_benchmark.py`
- `eval-viewer/generate_review.py`

### 分析 / 评分

用这些资源：

- `agents/analyzer.md`
- `agents/comparator.md`
- `agents/grader.md`

### schema / 输出格式

用：

- `references/schemas.md`

---

## alias 规则

- 不要在这里维护一套和 `skill-development-workflow` 平行但不同步的治理规则
- 不要把“创建 skill”和“skill 发布流程”拆成两份独立真相
- 如果你改了本目录里的 benchmark / eval 资源，也应同步检查 `skill-development-workflow` 是否需要更新说明

---

## 最短执行方式

当这个 alias 被触发时，默认动作应该是：

1. 声明 `skill-development-workflow` 是 canonical skill
2. 读取 canonical skill
3. 只有在需要 deeper eval tooling 时，再回到本目录脚本和 agents

---

**注意**: 这是 compatibility alias，不再作为 skill 治理主入口单独演化。
