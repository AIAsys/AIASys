+++
name = "aiasys-memory-organizer-skill"
description = "整理 AIASys Markdown memory 文件。用于用户明确要求整理 memory、压缩 MEMORY.md、\n刷新 memory_summary.md、合并重复偏好、清理过期工作区记忆时使用。只处理文件化\nmemory，不管理结构化 entry，也不接管自动写入链路。"
+++


# AIASys Memory Organizer

本 skill 负责整理 AIASys 的 Markdown memory 文件。它不参与普通 memory 写入。普通写入链路只追加内容，重复内容可以存在。只有用户、维护任务或 AutoTask 明确要求整理 memory 时，才加载本 skill。

## 适用场景

- 用户说"整理 memory""压缩 memory""清理重复 memory""重写 memory_summary"。
- `MEMORY.md` 很长，需要合并重复段落。
- `memory_summary.md` 已经过期，需要从当前 `MEMORY.md` 重新生成。
- 工作区 `workspace_memory.md` 里有明显重复或过时内容。
- 需要把 `raw_memories.md` 和 `rollout_summaries/` 里的高价值内容整理到主文件。

## 不适用场景

- 普通对话后自动写 memory。
- Stage 1 从 execution journal 提炼候选 memory。
- Stage 2 追加 Stage 1 产物。
- 审批 proposed / active / archived 条目。
- 解析或维护结构化 entry、YAML frontmatter、数据库 memory 行。

## 文件范围

用户默认层：

- `/global/.aiasys/.memory/MEMORY.md`
- `/global/.aiasys/.memory/memory_summary.md`
- `/global/.aiasys/.memory/raw_memories.md`
- `/global/.aiasys/.memory/rollout_summaries/`

工作区层：

- `/workspace/.aiasys/memory/workspace_memory.md`

只在这些文件内工作。不要读取原始 session transcript，除非用户明确要求回溯某次会话证据。

## 工作模式

本 skill 不提供自动整理。Agent 需要按以下步骤手动执行：

### 只给建议（dry-run）

1. 读取目标文件（MEMORY.md 或 memory_summary.md 或 workspace_memory.md）。
2. 分析重复、过时、冲突内容（Agent 自行推理，推理过程对用户可见）。
3. 列出建议：哪些段落可以合并、删除或保留。
4. **不写文件**，只输出建议报告。

### 直接整理

1. 读取目标文件。
2. 先调用脚本备份当前文件（可选但推荐）：
   ```bash
   python3 scripts/organize.py --mode backup --target memory
   ```
3. Agent 根据整理规则生成新的 Markdown 内容。
4. 将新内容写入临时文件（如 `/tmp/new_memory.md`）。
5. 调用脚本原子写入并生成 diff 报告：
   ```bash
   python3 scripts/organize.py --mode write --target memory --from-file /tmp/new_memory.md
   ```
6. 输出整理报告（修改了哪些内容、文件大小变化）。

## 整理规则

- 优先保留用户原话和项目专有名词。
- 近似重复内容可以合并，但要保留更具体的那条。
- 互相冲突的内容不要自行裁决，标注冲突并保留来源。
- 来源不明、看起来重要、或者可能还在使用的内容先保留。
- `MEMORY.md` 可以比 `memory_summary.md` 详细，不能压成几条空泛原则。
- `memory_summary.md` 只放启动时有用的索引和高频偏好，不放大段证据。
- `raw_memories.md` 和 `rollout_summaries/` 是中间材料和证据，不作为默认整理目标。
- 不删除长期 memory 文件中的内容，除非当前整理任务明确要求删除，且能说明删除依据。

## 脚本工具

本 skill 提供 `scripts/organize.py` 命令行脚本，只做文件操作，**不调用 LLM**：

### 备份

```bash
python3 scripts/organize.py --mode backup --target memory
python3 scripts/organize.py --mode backup --target summary
python3 scripts/organize.py --mode backup --target workspace
```

输出 JSON，包含备份文件路径。

### 对比报告（dry-run 验证）

```bash
python3 scripts/organize.py --mode diff --target memory --from-file /tmp/new_memory.md
```

输出 JSON 格式的 diff 报告（行增删、字符数变化、unified diff）。

### 原子写入

```bash
python3 scripts/organize.py --mode write --target memory --from-file /tmp/new_memory.md
```

自动备份 + 原子写入 + 输出 diff 报告。

### 环境变量

- `AIASYS_WORKSPACE_ROOT`: 当前工作区根目录（必需）

## 输出要求

整理完成后输出：

- 修改的文件。
- 合并了哪些主题。
- 删除或移动了哪些内容。
- 无法判断而保留的内容。
- 后续仍需人工确认的问题。

如果没有足够依据整理，直接说明原因，不要为了减少行数强行改写。
