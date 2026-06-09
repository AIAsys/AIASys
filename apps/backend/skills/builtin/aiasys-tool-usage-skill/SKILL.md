+++
name = "AIASys Tool Usage"
description = "AIASys 内置工具使用指南。提供当前 Agent 可用工具的选择策略、收益说明和常见任务推荐。当不确定用什么工具时，先读取本 skill 再执行。"
+++


# AIASys 工具使用指南

本 skill 帮助 Agent 在每次执行任务时选择最合适的工具。Agent 的可用工具列表是动态的（用户可能启用或禁用某些工具），因此选择工具前先搜索确认。

## 通用原则

1. **先搜索后使用**：不确定工具名时，先用 `tool_search` 搜索关键词，根据返回结果选择正确工具
2. **专用工具优先**：系统为常见任务提供了专用工具，它们比 Shell 更省心、更安全、更易审计
3. **Shell 兜底**：只有专用工具覆盖不到的场景才用 Shell（如系统命令、复杂管道、安装依赖）
4. **不要重复造轮子**：能用专用工具完成的任务，不要手写脚本或 curl 调用后端 API

## 工具速查表

按任务领域搜索对应工具：

### 文件操作
- `ReadFile`：读取文本文件，支持行号分页、尾部倒读、/global/ 前缀跨工作区读取
- `WriteFile`：创建或覆盖文件，自动校验路径安全
- `StrReplaceFile`：局部精确替换，不需要读整文件再重写

约束：
- 不要用 WriteFile 创建 `.canvas` 文件，创建画布请用 `WriteCanvas`
- 不要用 WriteFile 或 StrReplaceFile 修改 `.canvas` 文件，增删改节点和边请用 `BatchCanvasOperations`

### 环境变量
- `ListEnvVars`：列出当前工作区环境变量名（只返回工作区变量，不含系统变量，输出更干净）
- `GetEnvVar`：读取某个环境变量的值（敏感变量自动脱敏）
- `SetEnvVar`：设置/修改工作区环境变量（持久化，跨会话可用）
- `DeleteEnvVar`：删除工作区环境变量（永久删除，跨会话生效）

**禁止用 Shell 替代环境变量操作**：`echo $VAR`、`env`、`export`、`unset` 只在当前进程生效，且 `env` 会输出大量系统变量干扰判断。Windows 上 `env` 不可用，环境变量工具是跨平台的唯一正确入口。

### Notebook
- `ManageNotebook`：创建、读取、执行、编辑 notebook（统一入口）
- `ListSessionNotebooks`：列出当前会话的 notebook

约束：创建和执行 notebook 统一用 `ManageNotebook`，不要直接用 `WriteFile` 手写 .ipynb JSON。

Notebook 操作示例：

**创建 notebook 并添加 cell**：
```
ManageNotebook(action="create", notebook_path="analysis.ipynb", cells=[
  {"cell_type": "code", "source": "print('hello')"},
  {"cell_type": "markdown", "source": "# 标题"}
])
```

**读取 notebook 内容**：
```
ManageNotebook(action="read", notebook_path="analysis.ipynb")
```

**执行 notebook**：
```
ManageNotebook(action="run", notebook_path="analysis.ipynb")
```

**添加新 cell 到现有 notebook**：
```
ManageNotebook(action="edit", notebook_path="analysis.ipynb", edit_operation="upsert_cell", cell={"cell_type": "code", "source": "import numpy as np"})
```

**修改 cell 内容（局部替换）**：
```
ManageNotebook(action="edit", notebook_path="analysis.ipynb", edit_operation="patch_cell", cell_index=0, patches=[{"old": "print('hello')", "new": "print('world')"}])
```

### Canvas
- `ReadCanvas`：读取 JSON Canvas 文件
- `WriteCanvas`：创建或覆盖 JSON Canvas 文件
- `BatchCanvasOperations`：批量增删改节点和边

约束：
- 创建画布用 `WriteCanvas`，不要用 `WriteFile`
- 修改画布用 `BatchCanvasOperations`，不要用 `WriteFile` 或 `StrReplaceFile`

### 知识库
- `KnowledgeBaseQuery`：向知识库提问
- `ListKnowledgeBases`：列出可用知识库
- `CreateKnowledgeBase` / `UpdateKnowledgeBase` / `DeleteKnowledgeBase`：管理知识库
- `UploadDocumentsToKnowledgeBase`：上传文档
- `ListKnowledgeBaseDocuments`：列出知识库中的文档
- `DeleteDocumentsFromKnowledgeBase`：删除文档

### 知识图谱
- `SearchKnowledgeGraphEntities`：搜索实体
- `GetKnowledgeGraphEntityDetail`：获取实体详情
- `CreateKnowledgeGraph` / `DeleteKnowledgeGraph`：管理图谱
- `CreateGraphEntity` / `UpdateGraphEntity` / `DeleteGraphEntity`：管理实体
- `CreateGraphRelation` / `QueryEntityRelations`：管理关系
- `UploadDocumentsToGraph`：上传文档到图谱

### 数据表
- `CreateDataTable`：创建多维表
- `ReadDataTableSchema`：读取表结构（列名、类型、顺序）
- `QueryDataTable`：对多维表执行只读 SQL 查询（WHERE 过滤、ORDER BY 排序、GROUP BY 聚合等）
- `InsertDataTableRecords` / `UpdateDataTableRecord` / `DeleteDataTableRecord`：增删改记录
- `AddDataTableColumn` / `UpdateDataTableColumn` / `RemoveDataTableColumn`：管理列

**QueryDataTable 示例**：

```python
# 查看所有记录
QueryDataTable(table_path="/workspace/sales.table.db", sql="SELECT * FROM records LIMIT 10")

# 过滤 + 排序
QueryDataTable(table_path="/workspace/sales.table.db", sql="SELECT * FROM records WHERE status='active' ORDER BY amount DESC LIMIT 5")

# 聚合统计
QueryDataTable(table_path="/workspace/sales.table.db", sql="SELECT department, AVG(salary), COUNT(*) FROM records GROUP BY department")

# 查看表结构
QueryDataTable(table_path="/workspace/sales.table.db", sql="SELECT column_name, data_type FROM _schema ORDER BY order_index")
```

**约束**：
- 写操作（INSERT/UPDATE/DELETE/ALTER TABLE）**必须使用专用工具**，确保 `_schema` 表和 `records` 表同步
- `QueryDataTable` 仅支持 SELECT，非 SELECT 语句会被拒绝

### 数据库
- `DatabaseQuery`：统一数据库查询接口
- `ListDatabaseConnectors` / `ListDatabaseTables` / `DescribeDatabaseTable`：浏览数据库结构

### MCP
- `ListMCPServers`：列出本地仓库中的 MCP Server
- `SearchMCPMarket`：搜索外部 MCP 市场
- `InstallMCPServer`：安装 MCP Server 到当前工作区

约束：安装 MCP Server 优先用 `InstallMCPServer`，不要手动构造 curl 命令。

**安装示例**：

从外部市场安装（读取到 `{source_id, item_id}` 的 JSON 后，直接调用）：
```
InstallMCPServer(item_id="HRPAAA/weather", source_id="modelscope")
```

从本地仓库安装（先用 ListMCPServers 查看可用列表）：
```
InstallMCPServer(name="server-name")
```

### 代码执行
- `RunCode`：执行 Python 代码片段（适合快速实验）
- `Shell`：执行系统命令（适合复杂管道、安装依赖）

约束：数据分析、生成图表、处理 CSV 优先用 `RunCode` 或 `ManageNotebook`，不要写到 /tmp/ 再执行。

### Skill 管理
- `ListSkills`：列出当前已启用 skill
- `SearchStoreSkills`：在仓库中搜索 skill
- `EnableSkill` / `DisableSkill`：启用/禁用 skill
- `LoadSkill`：读取 skill 内容

约束：搜索到匹配的 skill 后，必须立即调用 `EnableSkill` 安装，不能只搜索不安装。

### AutoTask
- `CreateAutoTask`：创建自动任务
- `ListAutoTasks`：列出自动任务
- `UpdateAutoTask`：更新自动任务
- `ControlAutoTask`：控制自动任务（启用/禁用/删除）

### 子 Agent
- `Task`：将任务委派给子 Agent 执行（参数: subagent_name, description, prompt）
- `ListSubagents`：列出当前可用的子 Agent / 专家角色
- `TaskCreateTool` / `TaskUpdateTool` / `TaskListTool`：任务计划管理
- `EnterPlanModeTool` / `ExitPlanModeTool`：Plan 模式切换

约束：需要调用专家时，用 `Task` 工具委派，不要自己代替专家执行。

## 常见任务推荐工具

| 任务 | 推荐工具 | 不推荐 |
|------|---------|--------|
| 读取文本文件 | `ReadFile` | Shell `cat` |
| 创建/修改普通文件 | `WriteFile` / `StrReplaceFile` | Shell `echo >` / `sed` |
| 创建 notebook | `ManageNotebook` | `WriteFile` 手写 JSON |
| 执行 notebook | `ManageNotebook` | Shell `jupyter nbconvert` |
| 创建/修改 canvas | `WriteCanvas` / `BatchCanvasOperations` | `WriteFile` 手写 JSON |
| 读取环境变量 | `GetEnvVar` | Shell `echo $VAR` |
| 设置环境变量 | `SetEnvVar` | Shell `export` |
| 删除环境变量 | `DeleteEnvVar` | Shell `unset` |
| 运行 Python 片段 | `RunCode` / `ManageNotebook` | Shell `python3 /tmp/xxx.py` |
| 查询知识库 | `KnowledgeBaseQuery` | 直接读文件 |
| 搜索 MCP Server | `SearchMCPMarket` | 浏览器/手动 curl |
| 安装 MCP Server | `InstallMCPServer` | 手动 curl |
| 创建数据表 | `CreateDataTable` | Shell `sqlite3` |
| 查询数据表 | `QueryDataTable` | Shell `sqlite3` |
| 数据库查询 | `DatabaseQuery` | 裸 `psycopg2.connect` |
| 创建自动任务 | `CreateAutoTask` | Shell `curl` 调 API |

## 工具失败后处理

1. 分析失败原因（参数错误、资源不存在、权限不足）
2. 不要原样重复相同调用超过 2 次
3. 失败后向用户说明原因和下一步计划，严禁静默结束
