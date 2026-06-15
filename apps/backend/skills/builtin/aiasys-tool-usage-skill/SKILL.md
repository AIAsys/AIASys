+++
name = "AIASys Tool Usage"
description = "AIASys 工具使用速查表。触发条件：不确定该调用哪个工具、或任务涉及环境变量/Skill/专家/Notebook/Canvas/数据表/MCP/数据库/AutoTask。加载后可获得对应工具的参数说明、使用流程和禁止事项。"
+++


# AIASys 工具使用指南

本 skill 帮助 Agent 在执行任务时选择最合适的工具。Agent 的可用工具列表是动态的（用户可能启用或禁用某些工具），因此选择工具前先搜索确认。

## 前置检查：任务开始前先想一下

在开始执行任务前，花几秒判断：

1. **这个任务能用已有 skill 加速吗？** 先用 `ListSkills` 看看当前工作区启用了哪些 skill，有相关的就先 `LoadSkill` 加载
2. **这个任务需要特定专家吗？** 先用 `ListSystemExperts` 看看有没有对口的专家角色，有的话 `InstallExpert` 安装后通过 `TaskTool` 委派
3. **不确定用什么工具？** 继续读下面的工具速查表

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
- `ListEnvVars`：列出工作区已配置的环境变量名（只返回工作区变量，不混入系统变量）
- `GetEnvVar`：读取某个环境变量的值（敏感变量自动脱敏）
- `SetEnvVar`：设置/修改工作区环境变量（持久化，跨会话可用）
- `DeleteEnvVar`：删除工作区环境变量（从 registry 永久删除，跨会话生效）

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

### MCP / 连接器
- `ListMCPServers`：列出本地仓库中的 MCP Server
- `SearchMCPMarket`：搜索外部 MCP 市场
- `InstallMCPServer`：将外部市场条目导入系统仓库
- `SearchAvailableConnectors`：搜索 AIASys 内置源仓库中的可用连接器
- `InstallConnector`：将指定连接器安装到当前工作区

约束：
- 安装 MCP Server 优先用 `InstallMCPServer` 或 `InstallConnector`，不要手动构造 curl 命令
- 优先用 `SearchAvailableConnectors` 查找 AIASys 内置连接器，找不到再用 `SearchMCPMarket`

**安装示例**：

从 AIASys 内置仓库安装连接器（推荐）：
```
SearchAvailableConnectors(query="search")
InstallConnector(capability_id="stepfun-search")
```

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

当前工作区可能启用了某些 skill，它们能提供领域知识和工作流指导。Skill 管理流程：

| 场景 | 工具 | 说明 |
|------|------|------|
| 查看已启用的 skill | `ListSkills` | 列出当前工作区已启用的所有 skill |
| 搜索仓库中的 skill | `SearchStoreSkills` | 按关键词搜索，`source=""` 不过滤，`query=""` 返回全部 |
| 启用/安装 skill | `EnableSkill` | 搜索到合适的 skill 后**必须立即调用** `EnableSkill` 安装 |
| 禁用 skill | `DisableSkill` | 用户要求"关掉""禁用""不要了"时使用，参数 `name` 为 skill 目录名 |
| 读取 skill 内容 | `LoadSkill` | 加载 skill 的 SKILL.md，了解该 skill 能做什么 |

**关键规则**：
- `SearchStoreSkills` 找到匹配的 skill 后，**必须立即调用 `EnableSkill` 安装**，不能只搜索不安装
- 用户说"禁用/关闭/卸载 skill"时，用 `DisableSkill`，不要无视或只给文字回复

### 专家管理（Expert / 子 Agent）

专家是预配置的专用 Agent，可以处理特定领域的任务。专家管理分两步：安装、调度。

#### 安装与配置

| 场景 | 工具 | 说明 |
|------|------|------|
| 查看可用专家 | `ListSystemExperts` | 列出所有系统内置专家（如 data_analyst、coder、researcher 等） |
| 安装专家 | `InstallExpert` | 将专家安装到当前工作区。参数 `name` 为专家 ID（如 "data_analyst"），`scope` 默认 "workspace" |
| 配置专家状态 | `ConfigureExpert` | 启用/禁用已安装的专家。参数 `name` 为专家 ID，`enabled=true/false` 控制启用状态 |

**安装专家的正确流程**：
1. 先调用 `ListSystemExperts` 确认有哪些专家可用
2. 用户说要装某个专家时，**找到后必须立即调用 `InstallExpert`**，不能只列出不安装
3. `InstallExpert` 的参数是 `name`（专家 ID），不是 `expert_name`

**配置专家的正确流程**：
- 用户说"关掉/禁用某个专家，但别卸载"时 → 调用 `ConfigureExpert(name="xxx", enabled=false)`
- 用户说"重新启用某个专家"时 → 调用 `ConfigureExpert(name="xxx", enabled=true)`
- 不要无视用户的禁用/启用请求，必须实际调用工具

#### 调度与动态管理

| 场景 | 工具 | 说明 |
|------|------|------|
| 委派任务给专家 | `TaskTool` | 将任务委派给子 Agent 执行。参数：`subagent_name`（专家 ID）、`description`（简短描述）、`prompt`（详细指令） |
| 列出可用子 Agent | `ListSubagentsTool` | 列出当前工作区和全局已安装的子 Agent |
| 动态创建子 Agent | `CreateSubagentTool` | 根据任务需要创建临时子 Agent，指定名称、描述、提示词和工具列表 |
| 更新子 Agent 配置 | `UpdateSubagentTool` | 修改已有子 Agent 的名称、描述、提示词或工具列表 |
| 删除子 Agent | `DeleteSubagentTool` | 删除不再需要的子 Agent |

**子 Agent 使用原则**：
- 复杂任务、需要不同技能组合的任务，优先考虑委派给对应专家
- 如果现有专家不满足需求，可以用 `CreateSubagentTool` 动态创建
- 委派后等待子 Agent 完成，不要同时自己做相同的事情

### AutoTask
- `CreateAutoTask`：创建自动任务
- `ListAutoTasks`：列出自动任务
- `UpdateAutoTask`：更新自动任务
- `ControlAutoTask`：控制自动任务（启用/禁用/删除）

### 任务计划
- `TaskCreateTool` / `TaskUpdateTool` / `TaskListTool`：创建、更新、列出任务计划
- `EnterPlanModeTool` / `ExitPlanModeTool`：Plan 模式切换

## 常见任务推荐工具

| 任务 | 推荐工具 | 不推荐 |
|------|---------|--------|
| 读取文本文件 | `ReadFile` | Shell `cat` |
| 创建/修改普通文件 | `WriteFile` / `StrReplaceFile` | Shell `echo >` / `sed` |
| 创建 notebook | `ManageNotebook` | `WriteFile` 手写 JSON |
| 执行 notebook | `ManageNotebook` | Shell `jupyter nbconvert` |
| 创建/修改 canvas | `WriteCanvas` / `BatchCanvasOperations` | `WriteFile` 手写 JSON |
| 列出环境变量 | `ListEnvVars` | Shell `env` |
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
| 搜索/安装 skill | `SearchStoreSkills` → `EnableSkill` | 手动复制文件 |
| 禁用 skill | `DisableSkill` | 只给文字回复 |
| 安装专家 | `ListSystemExperts` → `InstallExpert` | 手动创建配置 |
| 禁用专家 | `ConfigureExpert(enabled=false)` | 只给文字回复 |
| 委派复杂任务 | `TaskTool` | 自己硬做 |
| 创建临时子 Agent | `CreateSubagentTool` | 重复使用不匹配的专家 |

## 工具失败后处理

1. 分析失败原因（参数错误、资源不存在、权限不足）
2. 不要原样重复相同调用超过 2 次
3. 失败后向用户说明原因和下一步计划，严禁静默结束
