---
name: api-dev
description: Develop FastAPI backend APIs following AIASys best practices. Use when creating new API endpoints, designing request/response models, implementing CRUD operations, or working with FastAPI routers. This skill covers API routing, Pydantic models, error handling, and async database operations. Always use this skill when the user asks you to create an API endpoint, implement a backend route, or work with FastAPI in the AIASys project.
---

# FastAPI API 开发

基于 FastAPI 的后端 API 开发规范，包含路由组织、模型定义、错误处理和数据库操作。

---

## 核心原则

1. **使用 APIRouter**：禁止直接在 `app` 上注册路由
2. **显式响应模型**：所有响应都必须有 Pydantic 模型
3. **异步优先**：数据库操作必须异步
4. **统一错误格式**：使用 `HTTPException`

---

## 项目结构

```
apps/backend/app/
├── api/
│   └── v1/
│       ├── __init__.py
│       ├── router.py          # 主路由聚合
│       ├── mcp.py             # MCP 相关 API
│       ├── sessions.py        # 会话 API
│       └── users.py           # 用户 API
├── models/
│   ├── __init__.py
│   ├── base.py                # 基础模型
│   ├── mcp.py                 # MCP 模型
│   └── user.py                # 用户模型
├── schemas/
│   ├── __init__.py
│   ├── mcp.py                 # MCP Schema
│   └── common.py              # 通用 Schema
└── services/
    ├── __init__.py
    └── mcp_service.py         # 业务逻辑
```

---

## APIRouter 使用

### 正确做法

```python
# api/v1/mcp.py
from fastapi import APIRouter, HTTPException
from app.schemas.mcp import MCPConfig, MCPConfigCreate

router = APIRouter(prefix="/mcp", tags=["MCP"])

@router.get("/configs", response_model=list[MCPConfig])
async def list_mcp_configs():
    """获取所有 MCP 配置"""
    configs = await mcp_service.get_all_configs()
    return configs

@router.post("/configs", response_model=MCPConfig, status_code=201)
async def create_mcp_config(config: MCPConfigCreate):
    """创建 MCP 配置"""
    try:
        new_config = await mcp_service.create_config(config)
        return new_config
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/configs/{config_id}", response_model=MCPConfig)
async def get_mcp_config(config_id: UUID):
    """获取单个 MCP 配置"""
    config = await mcp_service.get_config(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    return config

@router.put("/configs/{config_id}", response_model=MCPConfig)
async def update_mcp_config(config_id: UUID, config: MCPConfigUpdate):
    """更新 MCP 配置"""
    updated = await mcp_service.update_config(config_id, config)
    if not updated:
        raise HTTPException(status_code=404, detail="配置不存在")
    return updated

@router.delete("/configs/{config_id}", status_code=204)
async def delete_mcp_config(config_id: UUID):
    """删除 MCP 配置"""
    deleted = await mcp_service.delete_config(config_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="配置不存在")
    return None
```

### 错误做法

```python
# (错误) 不要这样做
from fastapi import FastAPI

app = FastAPI()

@app.get("/mcp/configs")  # 禁止直接在 app 上注册
def get_configs():        # 缺少 async
    return db.query(...)  # 同步数据库操作
```

---

## 路由聚合

```python
# api/v1/router.py
from fastapi import APIRouter
from app.api.v1 import mcp, sessions, users

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(mcp.router)
api_router.include_router(sessions.router)
api_router.include_router(users.router)

# main.py
from fastapi import FastAPI
from app.api.v1.router import api_router

app = FastAPI()
app.include_router(api_router)
```

---

## Pydantic 模型

### 请求模型

```python
# schemas/mcp.py
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Literal

class MCPConfigBase(BaseModel):
    """MCP 配置基础字段"""
    name: str = Field(..., min_length=1, max_length=100, description="配置名称")
    type: Literal["stdio", "sse"] = Field(..., description="MCP 类型")
    description: str | None = Field(None, max_length=500, description="配置描述")

class MCPConfigCreate(MCPConfigBase):
    """创建 MCP 配置请求"""
    command: str = Field(..., min_length=1, description="执行命令")
    args: list[str] = Field(default=[], description="命令参数")
    env: dict[str, str] = Field(default={}, description="环境变量")

class MCPConfigUpdate(BaseModel):
    """更新 MCP 配置请求（所有字段可选）"""
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    command: str | None = Field(None, min_length=1)
    args: list[str] | None = None
    env: dict[str, str] | None = None

class MCPConfig(MCPConfigBase):
    """MCP 配置响应模型"""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    command: str
    args: list[str]
    env: dict[str, str]
    created_at: datetime
    updated_at: datetime
```

### 响应包装

```python
# schemas/common.py
from pydantic import BaseModel, Generic
from typing import TypeVar, Generic

T = TypeVar("T")

class APIResponse(BaseModel, Generic[T]):
    """标准 API 响应包装"""
    success: bool = True
    data: T | None = None
    message: str | None = None
    error_code: str | None = None

class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应"""
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int
```

---

## 错误处理

### 统一错误格式

```python
# exceptions.py
from fastapi import HTTPException

class APIError(HTTPException):
    """API 错误基类"""
    def __init__(self, status_code: int, detail: str, error_code: str):
        super().__init__(status_code=status_code, detail={
            "message": detail,
            "error_code": error_code
        })

class NotFoundError(APIError):
    """资源不存在"""
    def __init__(self, resource: str):
        super().__init__(404, f"{resource} 不存在", "NOT_FOUND")

class ValidationError(APIError):
    """参数验证错误"""
    def __init__(self, detail: str):
        super().__init__(400, detail, "VALIDATION_ERROR")

class ConflictError(APIError):
    """资源冲突"""
    def __init__(self, detail: str):
        super().__init__(409, detail, "CONFLICT")
```

### 全局异常处理

```python
# main.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理"""
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "服务器内部错误",
            "error_code": "INTERNAL_ERROR"
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP 异常处理"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.detail if isinstance(exc.detail, str) else exc.detail.get("message"),
            "error_code": exc.detail.get("error_code") if isinstance(exc.detail, dict) else None
        }
    )
```

---

## 异步数据库操作

### SQLAlchemy 异步模型

```python
# models/base.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

# 异步引擎
engine = create_async_engine(
    "postgresql+asyncpg://user:pass@localhost/db",
    echo=False,
    future=True
)

# 异步会话
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# 依赖注入
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

### 数据库模型

```python
# models/mcp.py
from sqlalchemy import Column, String, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import Base
from datetime import datetime
from uuid import uuid4

class MCPConfigModel(Base):
    __tablename__ = "mcp_configs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(100), nullable=False, unique=True)
    type = Column(String(20), nullable=False)
    description = Column(String(500))
    command = Column(String(500), nullable=False)
    args = Column(JSON, default=list)
    env = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### CRUD 操作

```python
# services/mcp_service.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.mcp import MCPConfigModel
from app.schemas.mcp import MCPConfigCreate, MCPConfigUpdate

class MCPService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_all_configs(self) -> list[MCPConfigModel]:
        """获取所有配置"""
        result = await self.db.execute(select(MCPConfigModel))
        return result.scalars().all()
    
    async def get_config(self, config_id: UUID) -> MCPConfigModel | None:
        """获取单个配置"""
        result = await self.db.execute(
            select(MCPConfigModel).where(MCPConfigModel.id == config_id)
        )
        return result.scalar_one_or_none()
    
    async def create_config(self, config: MCPConfigCreate) -> MCPConfigModel:
        """创建配置"""
        # 检查名称是否已存在
        existing = await self.db.execute(
            select(MCPConfigModel).where(MCPConfigModel.name == config.name)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"配置名称 '{config.name}' 已存在")
        
        db_config = MCPConfigModel(**config.model_dump())
        self.db.add(db_config)
        await self.db.flush()
        return db_config
    
    async def update_config(
        self, 
        config_id: UUID, 
        config: MCPConfigUpdate
    ) -> MCPConfigModel | None:
        """更新配置"""
        db_config = await self.get_config(config_id)
        if not db_config:
            return None
        
        update_data = config.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_config, field, value)
        
        await self.db.flush()
        return db_config
    
    async def delete_config(self, config_id: UUID) -> bool:
        """删除配置"""
        db_config = await self.get_config(config_id)
        if not db_config:
            return False
        
        await self.db.delete(db_config)
        return True
```

---

## 依赖注入

```python
# dependencies.py
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import get_db
from app.services.mcp_service import MCPService

async def get_mcp_service(db: AsyncSession = Depends(get_db)) -> MCPService:
    return MCPService(db)

# 使用
@router.get("/configs")
async def list_configs(
    service: MCPService = Depends(get_mcp_service)
):
    return await service.get_all_configs()
```

---

## 分页实现

```python
from fastapi import Query

@router.get("/configs", response_model=PaginatedResponse[MCPConfig])
async def list_configs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    service: MCPService = Depends(get_mcp_service)
):
    """分页获取 MCP 配置"""
    configs, total = await service.get_configs_paginated(page, page_size)
    
    return PaginatedResponse(
        items=configs,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size
    )
```

---

## 快速检查清单

**创建 API 时：**
- [ ] 使用 APIRouter，不在 app 直接注册
- [ ] 定义请求/响应 Pydantic 模型
- [ ] 使用异步函数
- [ ] 处理异常情况
- [ ] 添加路由文档字符串

**数据库操作时：**
- [ ] 使用 AsyncSession
- [ ] 正确处理事务（commit/rollback）
- [ ] 使用依赖注入获取 session
- [ ] 查询使用 `select()` 而非 `query()`

---

*后端 API 是系统的脊梁——稳固、清晰、可靠。*
