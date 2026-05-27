# GraphRAG 模块

系统级知识图谱构建与查询模块，适配当前 AIASys 的异步架构。

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        GraphRAGService                          │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ EntityExtractor │  │ EntityResolver  │  │CommunityDetector│ │
│  │    (LLM抽取)     │  │   (实体消歧)     │  │   (社区发现)     │ │
│  └────────┬────────┘  └─────────────────┘  └─────────────────┘ │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────┐  ┌─────────────────┐                      │
│  │   GraphStore    │  │ CommunityReporter│                     │
│  │  (NetworkX存储)  │  │   (报告生成)     │                     │
│  └────────┬────────┘  └─────────────────┘                      │
│           │                                                     │
└───────────┼─────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Storage Layer                              │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │   NetworkX      │  │  sqlite-vec     │  │    GraphML      │ │
│  │   (内存图)       │  │  (实体向量)      │  │  (文件持久化)    │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## 代码统计

```
总代码行数: ~2000 行

核心组件:
- service.py          343 行  # 对外服务接口
- community_detection 286 行  # 社区发现与报告
- entity_resolution   258 行  # 实体消歧
- graph_store.py      242 行  # 图存储管理
- entity_extractor    222 行  # 实体抽取
- cache.py            157 行  # 缓存管理（支持 Redis/内存）
- locks.py            144 行  # 分布式锁（支持 Redis/内存）
- extraction.py       100 行  # Prompt 模板

代码来源:
- 以当前仓库主线实现为准
- 抽取逻辑已按现有异步架构和存储模型收口
- FastAPI 路由、服务层与存储层均为当前实现
```

## 快速开始

### 1. 基本使用

```python
from app.graphrag.service import GraphRAGService

# 创建服务
service = GraphRAGService(
    storage_path="./data/workspaces/local_default/global_workspace/resources/graphs",
    kb_id="my_kb",
    llm_client=llm_client,  # 可选
    enable_resolution=True,
    enable_communities=True
)

# 添加文档
result = await service.add_document(
    content="Alice is a software engineer at Google...",
    doc_id="doc_001",
    resolve_entities=True
)
print(f"Extracted {result['entity_count']} entities")

# 查询
response = await service.query(
    question="What does Alice do?",
    top_k=5,
    depth=2
)
print(response["context"])
```

### 2. 独立使用核心组件

```python
from app.graphrag.core import GraphStore, EntityResolver
from app.graphrag.models import Entity, Relation

# 图存储
store = GraphStore(
    storage_path="./data/workspaces/local_default/global_workspace/resources/graphs",
    kb_id="test",
)
await store.add_entity(Entity(name="Alice", entity_type="PERSON", ...))
await store.add_relation(Relation(source_entity="Alice", target_entity="Bob", ...))

# 实体消歧
resolver = EntityResolver(llm_client)
merge_map = await resolver.resolve(entities)
merged = resolver.merge_entities(entities, merge_map)
```

## 依赖说明

### 必需依赖
- `networkx` - 图数据结构和算法
- `numpy` - 数值计算

### 可选依赖（已安装）
- `redis>=7.3.0` - 分布式缓存和锁
- `graspologic>=3.4.4` - Leiden 社区检测算法
- `editdistance>=0.8.1` - 快速编辑距离计算
- `aiofiles` - 异步文件操作

### 安装
```bash
# 已添加到 pyproject.toml，自动安装
uv sync

# 或手动安装
pip install networkx numpy redis graspologic editdistance aiofiles
```

## 核心功能

### 1. 实体抽取 (Entity Extraction)
- 从文本中抽取实体和关系
- 支持多轮提取（gleaning）
- 基于 Prompt 的 LLM 提取

### 2. 实体消歧 (Entity Resolution)
- 编辑距离预筛选
- LLM 辅助判断
- 自动合并相似实体

### 3. 社区发现 (Community Detection)
- 支持 Leiden 算法（需 graspologic）
- 备选：简单连通分量检测
- 多层级社区结构

### 4. 社区报告 (Community Report)
- 基于 LLM 的社区摘要生成
- 关键实体识别
- 关系模式分析

### 5. 图存储 (Graph Storage)
- NetworkX 内存图
- GraphML 文件持久化
- sqlite-vec 向量集成（可选）

## API 端点

```
POST /api/graph/documents          # 添加文档
POST /api/graph/query              # 查询图谱
GET  /api/graph/entities           # 列出实体
GET  /api/graph/entities/{name}    # 获取实体详情
GET  /api/graph/search             # 搜索实体
GET  /api/graph/communities        # 获取社区
GET  /api/graph/statistics         # 图谱统计
```

## 配置

```python
# 环境变量
GRAPHRAG_STORAGE_PATH="./data/workspaces/local_default/global_workspace/resources/graphs"
GRAPHRAG_REDIS_HOST="localhost"
GRAPHRAG_REDIS_PORT=6379
GRAPHRAG_ENABLE_RESOLUTION=true
GRAPHRAG_ENABLE_COMMUNITIES=true
GRAPHRAG_MAX_CLUSTER_SIZE=12
```

## 设计决策

### 1. 为什么不用 Elasticsearch？
- ES 需要 2GB+ 内存
- 当前 sqlite-vec + NetworkX 方案足够
- 可扩展：未来可添加 ES 支持

### 2. 为什么支持内存模式？
- 简化部署和测试
- 降低开发门槛
- 生产环境可使用 Redis

### 3. 为什么是系统级？
- 全局知识库概念
- 所有用户共享
- 简化架构

## 参考

- GraphRAG (MS): https://github.com/microsoft/graphrag
- Leiden Algorithm: https://github.com/graspologic-org/graspologic
