+++
name = "AIASys Notebook-first Workflow"
description = "AIASys 数据分析场景的 Notebook-first 执行指南。涵盖 notebook 工作流、cell 编辑规范和数据观察精简原则。数据分析子 Agent 在执行复杂分析前应先读取本 skill。"
+++

# Notebook-first 执行指南

数据分析、代码实验与需要 Python 执行的任务，**默认走 notebook-first 工作流**：
- 先列出当前会话私有 notebook，确认是否已有可复用分析记录
- 如果没有合适 notebook，优先创建 scratch notebook 再开展实验
- 修改或追加 cell 时，优先使用 notebook / cell 语义编辑
- 执行分析、可视化、建模时，优先运行 notebook，而不是把 REPL 当成前台主对象

你当前默认应把 notebook 视为代码分析的主工作对象，而不是先写一段临时代码再想办法保留过程。

## 推荐工具顺序

1. `ListSessionNotebooks`
2. `ManageNotebook`（action=create/read_outputs/run）
3. `EditNotebookFile`（operation=read/replace/upsert_cell/delete_cell/update_metadata/clear_cell_outputs）

## 默认工作流

1. 先列出当前会话私有 notebook，确认是否已有可复用分析上下文
2. 如果没有，就创建 scratch notebook，例如：
   - `notebooks/_scratch/`
   - `notebooks/experiments/`
3. 把分析步骤拆成 markdown / code cells，优先保留意图、代码和中间输出
4. 运行目标 cell 或整个 notebook
5. 用 notebook 输出和工作区文件向主控交付结果

## 常见调用模式

- 查看当前会话 notebook：`ListSessionNotebooks(directory="notebooks")`
- 新建 scratch notebook：`ManageNotebook(action="create", notebook_path="notebooks/_scratch/demo.ipynb", title="Demo Analysis")`
- 读取 notebook 摘要：`EditNotebookFile(operation="read", notebook_path="notebooks/analysis.ipynb")`
- 更新某个 cell：`EditNotebookFile(operation="upsert_cell", notebook_path="notebooks/analysis.ipynb", cell={...})`
- 运行单个 cell：`ManageNotebook(action="run", notebook_path="notebooks/analysis.ipynb", scope="cell", cell_id="...")`
- 运行整个 notebook：`ManageNotebook(action="run", notebook_path="notebooks/analysis.ipynb", scope="all")`
- 回看输出：`ManageNotebook(action="read_outputs", notebook_path="notebooks/analysis.ipynb")`

## 注意事项

- **工作目录**：notebook 逻辑路径在当前 workspace 下，但 notebook 私有副本默认属于当前会话
- **文件路径**：优先使用相对路径（如 `result.csv`、`_charts/chart.json`）
- **网络访问**：不要默认假设当前轮存在独立 Web 工具；如果工具面没有联网能力，而任务又必须联网，直接说明限制。确实需要在 notebook 中访问网络时，再谨慎使用 `requests`
- **连续实验**：默认把多步分析保留在 notebook，不要把关键过程只留在临时 stdout 里
- **快速验证**：即使只是一次性验证，也优先落到 scratch notebook，而不是退回裸 REPL

## Notebook 文件编辑规则

1. 优先用 `EditNotebookFile(operation="read")` 读取 notebook 摘要，先确认当前 cell 列表；默认不要请求完整 notebook JSON
2. 更新或新增单个 cell 时，优先用 `upsert_cell`
3. 删除 cell 时用 `delete_cell`
4. 清空 code cell 输出时用 `clear_cell_outputs`
5. 只在用户明确要求"完全重写 notebook 结构"时，才使用 `replace`
6. notebook 路径必须是逻辑工作区里的相对路径，例如 `notebooks/analysis.ipynb`
7. notebook 默认是"当前会话私有"的；不要把它当成所有会话共享的工作区文件，除非用户明确要求共享
8. 如果只是想补一段分析或实验步骤，默认追加或更新 cell，不要重写整份 notebook
9. notebook 输出可能包含大文本或图像；默认通过摘要看 notebook，不要主动读取完整原始 outputs
10. 执行 notebook 时优先使用 `ManageNotebook(action="run")`，不要自己先读整份 ipynb 再把 code cell 逐段拼成临时脚本执行
11. 如果 notebook 正在当前会话的运行链路里被执行，优先继续通过 notebook 工具更新它；不要引导用户手工改同一个 notebook
12. 编辑 notebook 优先使用 `EditNotebookFile` / `ManageNotebook(action="run")`；对于普通文本文件（如 `.py`、`.md`、`.json`）使用 `ReadFile` / `WriteFile` / `StrReplaceFile`，不要混用两种语义

如果 `EditNotebookFile(read)` 返回 `exists=false` / `status="missing"`，说明当前会话里暂时还没有该 notebook；这时应继续调用 `EditNotebookFile(upsert_cell/replace)` 创建它。对于 `.ipynb` 文件始终优先走 notebook 工具语义，不要直接用 `WriteFile` 手写整份 JSON。

---

## 数据观察精简原则

为防止长上下文导致响应变慢，观察数据时必须遵循"精简观察"原则：

- **推荐做法**：
  - 用 `df.head(5)` 查看前5行数据
  - 用 `df.tail(5)` 查看后5行数据
  - 用 `df.info()` 查看数据类型和缺失值
  - 用 `df.describe()` 查看统计摘要
  - 用 `df.columns.tolist()` 查看所有列名（而不是打印整个表）
  - 用 `df.index.tolist()` 查看所有行索引

- **禁止做法**：
  - 直接 `print(df)` 输出整个大型 DataFrame
  - 单次输出超过 10 行 10 列

**长表格处理技巧**：
- **列名很多时**：用 `df.columns[:10]` 查看前10列，了解命名规律即可
- **行索引很长时**：用 `df.index[:10]` 查看前10个索引，不要全部列出
- **宽表格查看**：用 `df.iloc[:5, :5]` 查看左上角 5x5 子集了解数据结构
- **列名/行名过长时**：不要直接展示全部，通过滚动查看规律，或用 `df.columns[:5]` 抽样查看
