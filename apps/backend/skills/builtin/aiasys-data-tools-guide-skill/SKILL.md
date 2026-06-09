+++
name = "AIASys Data Tools Guide"
description = "AIASys 数据分析领域工具指南。涵盖数据库访问、知识库、知识图谱、多维表和 Canvas 工具的使用规范。涉及对应领域时读取本 skill。"
+++

# 数据分析领域工具指南

## 数据库访问

**当前 notebook 执行环境已预置数据库 helper：`db = get_db()`。**

这个 helper 走 AIASys 当前真实数据库 broker，统一承接：
- 当前任务已挂载的外部数据库连接器
- 外部连接器的 grants / capability / 审批链路

### 先看当前有哪些数据库可用

```python
handles = db.list_handles()
print(handles)
```

返回里通常会包含：
- 已挂载外部连接器：`connector:<connector_id>`

### 读取示例

```python
# 先看表列表（需要指定外部连接器 handle）
tables = db.list_tables(handle="connector:my-connector-id")
print(tables["tables"][:10])

# 查看某张表结构
detail = db.describe_table("my_table", handle="connector:my-connector-id")
print(detail["columns"])
```

### 外部连接器读取示例

```python
handles = db.list_handles()
target_handle = "connector:my-connector-id"

result = db.query(
    "SELECT * FROM my_table LIMIT 5",
    handle=target_handle,
    limit=5,
)
print(result["rows"])
```

### 写入 / DDL 示例

```python
# 外部连接器写入
db.execute(
    "INSERT INTO my_table (id, name) VALUES (1, 'demo')",
    handle="connector:my-connector-id",
)
```

### 重要约束

- **数据库操作优先使用 `db` helper**：不要直接假设存在 `DB_DSN`、`DB_NAME`，也不要默认用裸 `psycopg2.connect()` / `sqlalchemy.create_engine()` 直连
- **先列 handles 再动手**：如果用户提到"数据库/连接器/挂载库"，先 `db.list_handles()`，确认当前任务到底能访问哪些库
- **外部连接器必须显式指定 handle**：格式是 `connector:<connector_id>`
- **外部连接器写入可能触发审批**：若出现审批等待或审批拒绝，不要重复发送同样的写入；等待用户确认或向用户说明当前阻塞点
- **失败后先分析再调整**：同类数据库写入失败后，不要盲目重复执行相同 SQL；先检查错误，再决定是否需要一次有根据的修正

---

## 知识库工具集

当任务涉及文档资料查询时，使用知识库工具：

### 1. ListKnowledgeBases - 列出知识库

**使用场景**：需要查询知识库但不知道 ID 时，先用此工具获取列表。

**返回信息**：知识库 ID、名称、描述、文档数量。

### 2. KnowledgeBaseQuery - 查询知识库内容

**使用场景**：已经知道知识库 ID，需要查询具体内容。

**参数**：
- `knowledge_base_id`: 知识库 ID（从 ListKnowledgeBases 获取）
- `query`: 查询内容
- `top_k`: 返回结果数量

### 3. 知识库管理工具

- `CreateKnowledgeBase`: 创建知识库
- `UpdateKnowledgeBase`: 更新知识库名称、描述、默认检索策略和解析配置
- `UploadDocumentsToKnowledgeBase`: 上传工作区、会话目录或全局工作区文件到知识库
- `ListKnowledgeBaseDocuments`: 列出知识库文档，获取 document_id
- `DeleteDocumentsFromKnowledgeBase`: 删除知识库文档
- `DeleteKnowledgeBase`: 删除知识库

### 注意事项

- **用户隔离**：每个用户只能看到自己的知识库
- **必须先获取 ID**：查询前必须先获得知识库 ID
- 删除文档前先用 `ListKnowledgeBaseDocuments` 确认 document_id
- **支持多知识库**：用户可以创建多个知识库，用 ID 区分

---

## 知识图谱工具集

当问题更像是在找**实体、概念、组织、设备、关系线索**时，优先使用知识图谱工具，而不是直接猜测。

### 可用工具

- `ListKnowledgeGraphs`: 列出知识图谱，获取图谱 ID
- `CreateKnowledgeGraph`: 创建知识图谱
- `DeleteKnowledgeGraph`: 删除知识图谱
- `SearchKnowledgeGraphEntities`: 搜索图谱实体
- `GetKnowledgeGraphEntityDetail`: 查看实体详情
- `CreateGraphEntity`: 创建实体
- `UpdateGraphEntity`: 更新实体
- `DeleteGraphEntity`: 删除实体
- `CreateGraphRelation`: 创建实体关系
- `QueryEntityRelations`: 查询实体关系
- `GetCommunityReport`: 读取社区报告
- `UploadDocumentsToGraph`: 上传工作区文件并构建图谱

### 1. SearchKnowledgeGraphEntities - 搜索知识图谱实体

**使用场景**：
- 用户提到某个关键词，想确认图谱里有哪些相关实体
- 需要先浏览候选实体，再决定深入查看哪一个
- 需要按实体类型筛选（例如 person、organization、technology、equipment）

### 2. GetKnowledgeGraphEntityDetail - 查看实体详情

**使用场景**：已通过搜索拿到实体名称，想查看描述和元数据。

### 3. 图谱写入工具

**使用场景**：用户明确要求创建图谱、补充实体、修改实体信息、删除实体或增加实体关系时使用。删除图谱或删除实体前，需要确认用户已经明确指定目标 ID 或名称。

### 使用原则

- 当问题包含"有没有某个实体 / 某个概念 / 某类设备 / 某类组织"时，优先用图谱搜索
- 当用户问的是**文档内容**，优先用知识库工具；当用户问的是**实体关系和图谱线索**，优先用图谱工具
- 搜索到多个候选实体时，应先列给主控或结合上下文筛选，不要武断认定唯一答案

---

## 多维表工具集

当分析结果需要沉淀成结构化记录、对比矩阵、实验台账或指标表时，使用多维表工具：
- `CreateDataTableTool`: 创建多维表
- `ReadDataTableSchemaTool`: 读取表结构
- `ReadDataTableRecordsTool`: 读取表记录
- `InsertDataTableRecordsTool`: 插入记录
- `UpdateDataTableRecordTool`: 更新记录
- `DeleteDataTableRecordTool`: 删除记录
- `AddDataTableColumnTool`: 新增列
- `UpdateDataTableColumnTool`: 更新列定义
- `RemoveDataTableColumnTool`: 删除列

多维表路径支持相对路径、`/workspace/...` 和 `/global/...`。写记录前先确认 schema，避免列名写错。

---

## Canvas 工具集

当主控要求维护 `.canvas` 视图、分析路线图或结果关系图时，使用 Canvas 工具：
- `ReadCanvasTool`: 读取 `.canvas` 文件
- `WriteCanvasTool`: 覆盖写入完整 `.canvas` 文件
- `BatchCanvasOperationsTool`: 批量增删改节点和边

Canvas 只作为视图和布局。数据事实继续保存在 notebook 输出、CSV、多维表、知识库、知识图谱或数据库里。
