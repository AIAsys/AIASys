# GraphRAG 快速开始

## 1. 环境准备

确保服务已启动：
```bash
# 1. 后端服务（SQLite 主库，无需 PostgreSQL）
cd /home/ke/projects/AIASys/apps/backend
.venv/bin/uvicorn app.main:app --reload

# 2. Redis（可选，用于缓存）
cd /home/ke/projects/AIASys/infra/docker/redis
docker compose up -d

# 3. 验证 Redis
redis-cli -h localhost -p 6379 ping
# 预期输出: PONG
```

## 2. 配置环境变量

在 `apps/backend/.env` 中添加：
```bash
# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# GraphRAG
GRAPH_STORAGE_PATH=./data/workspaces/local_default/global_workspace/resources/graphs
```

## 3. 代码集成

### 3.1 初始化服务

```python
# 在你的应用启动代码中
from app.graphrag import GraphRAGService
from app.core.config import settings

# 初始化 GraphRAG 服务
graphrag_service = GraphRAGService(
    storage_path=settings.GRAPH_STORAGE_PATH,
    kb_id="system",
    # 向量检索由 sqlite-vec 提供，无需传入 collection
    llm_client=llm_client                 # 你的 LLM 客户端
)

# 注册到 API
from app.api.routes import graphrag
graphrag.init_graphrag_service(graphrag_service)
```

### 3.2 添加文档

```python
# 添加文档构建知识图谱
result = await graphrag_service.add_document(
    content="人工智能（AI）是计算机科学的一个分支...",
    doc_id="doc_001"
)

print(f"提取了 {result['entity_count']} 个实体")
print(f"提取了 {result['relation_count']} 个关系")
```

### 3.3 查询图谱

```python
# 查询知识图谱
result = await graphrag_service.query(
    question="人工智能和机器学习的关系是什么？",
    top_k=5,
    depth=1
)

print(f"找到实体: {[e['name'] for e in result['entities']]}")
print(f"上下文: {result['context']}")
```

## 4. API 测试

启动后端后测试 API：

```bash
# 1. 添加文档
curl -X POST http://localhost:13001/api/graph/documents \
  -H "Content-Type: application/json" \
  -d '{"content": "人工智能是计算机科学的一个分支...", "doc_id": "test001"}'

# 2. 查询图谱
curl -X POST http://localhost:13001/api/graph/query \
  -H "Content-Type: application/json" \
  -d '{"question": "什么是人工智能？", "top_k": 5}'

# 3. 查看统计
curl http://localhost:13001/api/graph/statistics

# 4. 获取实体列表
curl "http://localhost:13001/api/graph/entities?limit=10"
```

## 5. 项目结构

```
app/graphrag/
├── README.md                 # 项目说明
├── QUICKSTART.md            # 本文件
├── service.py               # 对外服务接口
├── core/                    # 核心逻辑
│   ├── entity_extractor.py  # 实体抽取
│   └── graph_store.py       # 图存储
├── models/                  # 数据模型
│   ├── entity.py            # 实体模型
│   └── relation.py          # 关系模型
├── prompts/                 # LLM Prompts
│   └── extraction.py        # 抽取Prompt
└── utils/                   # 工具函数
    ├── cache.py             # Redis缓存
    └── locks.py             # 分布式锁
```

## 6. 下一步

- [ ] 集成到对话流程（在 Agent 中调用）
- [ ] 添加实体消解（去重）
- [ ] 实现社区发现算法
- [ ] 添加可视化界面

## 参考文档

- [产品需求入口](../../../../.agents/skills/aiasys-product-requirements/references/current-product-prd.md)
- [系统设计入口](../../../../.agents/skills/aiasys-system-design/references/current-system-architecture.md)
