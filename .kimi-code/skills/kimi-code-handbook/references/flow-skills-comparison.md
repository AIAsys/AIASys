# Flow Skills 跨项目对比分析

调研了 Kimi Code（原 Kimi CLI）、Codex、Hermes Agent、Claude Code 系列（cheetahclaws、claw-code、claude-leaked）共 6 个项目的 flow/workflow skill 机制。

---

## 核心结论

**Kimi Code 是目前唯一实现"从 Mermaid/D2 图解析声明式状态机驱动 Agent 多步执行"的项目。** 这是一个独特的设计决策，其他项目要么没有状态机机制，要么图结构硬编码在代码里。

> **版本变化：** 新版 Kimi Code 中 Flow Skills 统一通过 `/skill:<name>` 调用（不再有 `/flow:` 命名空间），Flow 类型 Skill 调用时由 FlowRunner 接管执行。底层引擎保持一致。

---

## Kimi Code Flow Skills 架构

### 解析层

```
SKILL.md (type: flow + Mermaid/D2 代码块)
    │
    ▼
parse_frontmatter() → type = "flow"
    │
    ▼
_parse_flow_from_skill() → 遍历 fenced codeblock
    ├── lang == "mermaid" → parse_mermaid_flowchart()
    └── lang == "d2"      → parse_d2_flowchart()
            │
            ▼
        Flow { nodes, outgoing, begin_id, end_id }
```

**关键文件：**

| 文件 | 作用 |
|------|------|
| `src/kimi_code/skill/__init__.py` | Skill 解析入口，`parse_skill_text()` 检测 `type: flow` |
| `src/kimi_code/skill/flow/__init__.py` | Flow 数据结构（FlowNode/FlowEdge/Flow）、`parse_choice()` 正则提取 `<choice>` |
| `src/kimi_code/skill/flow/mermaid.py` | Mermaid flowchart 解析器，支持 `flowchart TD/LR`、形状识别、边解析 |
| `src/kimi_code/skill/flow/d2.py` | D2 flowchart 解析器，支持链式边、`|md` 块字符串 |
| `src/kimi_code/utils/frontmatter.py` | YAML frontmatter 解析 |

### 执行层

```
KimiSoul._build_slash_commands()
    → 注册 /skill:<name> → FlowRunner(flow).run（当 type=flow 时）
            │
            ▼
    FlowRunner.run()
        begin → task → [decision → <choice>匹配 → 分支] → end
```

**关键文件：**

| 文件 | 作用 |
|------|------|
| `src/kimi_code/soul/kimisoul.py` | `FlowRunner` 类，核心执行引擎 |

### FlowRunner 执行流程

1. 从 `begin_id` 开始，自动跳过 BEGIN 节点
2. **task 节点**：构建 prompt（直接用节点 label）→ 执行一次 LLM 对话（`soul._turn()`）→ 无条件走唯一出边。**不检查输出质量。**
3. **decision 节点**：构建 prompt（节点 label + 分支列表 + `<choice>` 格式说明）→ 执行 LLM 对话 → 正则提取 `<choice>分支名</choice>` → 精确匹配出边 label
4. **choice 匹配失败**：自动重试（while True 循环），追加提示"Your last response did not include a valid choice..."
5. 到达 **end 节点**：记录日志并返回
6. 达到 `max_moves`（默认 1000）：抛出 MaxStepsReached
7. **tool_rejected**：如果某次 turn 中工具调用被拒绝，整个流程终止

关键设计：Flow 的每一步复用标准 `soul._turn()`，不需要单独的 LLM 调用路径或工具注册。FlowRunner 类总共约 170 行。

### `<choice>` 解析

```python
_CHOICE_RE = re.compile(r"<choice>([^<]*)</choice>")

def parse_choice(text: str) -> str | None:
    matches = _CHOICE_RE.findall(text or "")
    if not matches:
        return None
    return matches[-1].strip()  # 取最后一个匹配
```

### 校验规则（`validate_flow()`）

- 恰好 1 个 BEGIN 节点
- 恰好 1 个 END 节点
- 所有节点可达
- 同一节点的多条出边 label 不能重复

---

## 各项目对比

### cheetahclaws — Research Lab 状态机

**有状态机，三层嵌套，图硬编码在 Python 枚举中。**

```
文件: research/lab/orchestrator.py (1169行)

Stage 枚举（9个）: QUESTIONING → SURVEY → OUTLINE → IMPLEMENTATION
                 → EXPERIMENT → ANALYSIS → DRAFTING → VERIFICATION → FINALIZATION

三层收敛：
  Layer 1: Stage 内 producer-reviewer loop（producer输出 → N个Reviewer评分 → PI决策）
  Layer 2: Stage 间线性推进（_drive() 中的 while True + 线性序列表）
  Layer 3: Meta-loop（iterate.py，评分4维度 → 回退到最低分对应的Stage → 重跑）

9个Agent角色（PI, Questioner, Surveyor, Designer, Engineer, Analyst, Writer, Reviewer×3, Lay Reader）
异构模型策略：PI用Claude Opus、Writer用Sonnet、Auxiliary用便宜模型、Reviewer强制不同模型家族
SQLite 5表持久化 + artifact版本化 + resume/rewind
```

**与 Kimi Code 对比：**
- 相似点：都是状态机驱动的多步执行
- 差异：cheetahclaws 的图是硬编码的 Python 枚举，Kimi Code 是从 Mermaid/D2 解析的动态图
- cheetahclaws 有"收敛判断 + 回退 + 持久化"机制，Kimi Code FlowRunner 没有
- cheetahclaws 是针对单一场景（论文生成）的垂直优化，Kimi Code Flow 是通用框架

### cheetahclaws — Modular Skill 系统

纯 prompt template 注入（Markdown + YAML frontmatter），类似 Kimi Code 的普通 Skill。**不是状态机。**

### Claude Code (claude-leaked-files) — WorkflowTool

```
Feature flag: WORKFLOW_SCRIPTS
文件引用:
  - commands/workflows/index.js    (缺失)
  - tools/WorkflowTool/WorkflowTool.js (缺失)
  - tasks.ts: LocalWorkflowTask    (缺失)
```

**最有可能存在类似机制的项目，但实现代码不在泄露文件中。** 从命名推测，可能是通过脚本定义工作流，但无法确认是否涉及 Mermaid/D2。

### Codex — 无

纯 Markdown skill 模板注入，通过 progressive disclosure 按需加载。没有任何状态机或图解析。

### Hermes Agent — Plan + Subagent 模式

两阶段流程：
1. `writing-plans` skill 生成 Markdown 计划文件
2. `subagent-driven-development` skill 按计划逐个任务派发子 Agent

**与 Kimi Code 对比：**
- 都是多步骤执行，但机制完全不同
- Hermes 是自然语言计划 + 手动派发
- Kimi Code 是声明式状态机图 + 自动执行

### claw-code — 无

Skills 目录已 archived，代码中的 `workflow_scope` 是事件所有权标记，不是 skill 机制。

---

## 总结

| 项目 | 状态机执行 | Mermaid/D2 | 图定义方式 | 与 Kimi Code 相似度 |
|------|-----------|-----------|-----------|--------------|
| **Kimi Code** | 有 | **支持** | 声明式（SKILL.md 内嵌 Mermaid/D2） | — |
| cheetahclaws | 有 | 不支持 | 硬编码（Python 枚举） | 中等 |
| Claude Code | 可能有 | 未知 | 未知（WorkflowTool 源码缺失） | 未知 |
| Codex | 无 | 不支持 | — | 无 |
| Hermes Agent | 无 | 不支持 | — | 无 |
| claw-code | 无 | 不支持 | — | 无 |

Kimi Code 的 Flow Skills 是**唯一将声明式流程图解析 + 状态机驱动 Agent 执行结合起来的实现**。这个设计让非程序员也能通过画流程图来定义多步 Agent 工作流，而不是写代码或手动描述步骤。

---

## 版本变更备注

本文档基于旧版 Kimi CLI 的 Flow Skills 分析更新。新版 Kimi Code 的关键变化：

- `/flow:<name>` → `/skill:<name>`（统一入口，Flow 类型自动走 FlowRunner）
- 底层 FlowRunner 引擎逻辑保持不变
- 模块路径从 `kimi_cli.*` 变更为 `kimi_code.*`