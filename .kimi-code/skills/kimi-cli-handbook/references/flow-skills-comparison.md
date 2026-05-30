# Flow Skills 跨项目对比分析

调研了 Kimi CLI、Codex、Hermes Agent、Claude Code 系列（cheetahclaws、claw-code、claude-leaked）共 6 个项目的 flow/workflow skill 机制。

---

## 核心结论

**Kimi CLI 是目前唯一实现"从 Mermaid/D2 图解析声明式状态机驱动 Agent 多步执行"的项目。** 这是一个独特的设计决策，其他项目要么没有状态机机制，要么图结构硬编码在代码里。

---

## Kimi CLI Flow Skills 架构

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
| `src/kimi_cli/skill/__init__.py` | Skill 解析入口，`parse_skill_text()` 检测 `type: flow` |
| `src/kimi_cli/skill/flow/__init__.py` | Flow 数据结构（FlowNode/FlowEdge/Flow）、`parse_choice()` 正则提取 `<choice>` |
| `src/kimi_cli/skill/flow/mermaid.py` | Mermaid flowchart 解析器，支持 `flowchart TD/LR`、形状识别、边解析 |
| `src/kimi_cli/skill/flow/d2.py` | D2 flowchart 解析器，支持链式边、`|md` 块字符串 |
| `src/kimi_cli/utils/frontmatter.py` | YAML frontmatter 解析 |

### 执行层

```
KimiSoul._build_slash_commands()
    → 注册 /flow:<name> → FlowRunner(flow).run
            │
            ▼
    FlowRunner.run()
        begin → task → [decision → <choice>匹配 → 分支] → end
```

**关键文件：**

| 文件 | 作用 |
|------|------|
| `src/kimi_cli/soul/kimisoul.py` | `FlowRunner` 类（line 1534-1710），核心执行引擎 |
| `klips/klip-10-agent-flow.md` | 完整设计文档 |

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

**与 Kimi 对比：**
- 相似点：都是状态机驱动的多步执行
- 差异：cheetahclaws 的图是硬编码的 Python 枚举，Kimi 是从 Mermaid/D2 解析的动态图
- cheetahclaws 有"收敛判断 + 回退 + 持久化"机制，Kimi FlowRunner 没有
- cheetahclaws 是针对单一场景（论文生成）的垂直优化，Kimi Flow 是通用框架

### cheetahclaws — Modular Skill 系统

纯 prompt template 注入（Markdown + YAML frontmatter），类似 Kimi 的普通 Skill。**不是状态机。**

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

**与 Kimi 对比：**
- 都是多步骤执行，但机制完全不同
- Hermes 是自然语言计划 + 手动派发
- Kimi 是声明式状态机图 + 自动执行

### claw-code — 无

Skills 目录已 archived，代码中的 `workflow_scope` 是事件所有权标记，不是 skill 机制。

---

## 总结

| 项目 | 状态机执行 | Mermaid/D2 | 图定义方式 | 与 Kimi 相似度 |
|------|-----------|-----------|-----------|--------------|
| **Kimi CLI** | 有 | **支持** | 声明式（SKILL.md 内嵌 Mermaid/D2） | — |
| cheetahclaws | 有 | 不支持 | 硬编码（Python 枚举） | 中等 |
| Claude Code | 可能有 | 未知 | 未知（WorkflowTool 源码缺失） | 未知 |
| Codex | 无 | 不支持 | — | 无 |
| Hermes Agent | 无 | 不支持 | — | 无 |
| claw-code | 无 | 不支持 | — | 无 |

Kimi CLI 的 Flow Skills 是**唯一将声明式流程图解析 + 状态机驱动 Agent 执行结合起来的实现**。这个设计让非程序员也能通过画流程图来定义多步 Agent 工作流，而不是写代码或手动描述步骤。