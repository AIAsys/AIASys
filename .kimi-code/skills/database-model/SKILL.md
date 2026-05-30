---
name: database-model
description: Design database models and schemas following SQLAlchemy and PostgreSQL best practices. Use when creating new database tables, defining SQLAlchemy models, designing relationships, or working with database migrations. This skill covers model design, relationships, indexing, and async SQLAlchemy patterns. Always use this skill when the user asks you to create a database model, design a schema, or work with SQLAlchemy in the AIASys project.
---

# 数据库模型设计

SQLAlchemy + PostgreSQL 的数据库模型设计规范，涵盖模型定义、关系设计、索引优化和异步操作。

---

## 核心原则

1. **显式优于隐式**：所有字段、关系、约束都明确定义
2. **类型安全**：使用 SQLAlchemy 2.0 类型注解风格
3. **异步优先**：所有数据库操作异步化
4. **迁移友好**：模型变更需考虑迁移脚本

---

## 基础模型

### Base 定义

```python
# models/base.py
from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy 基础模型"""
    
    # 通用字段：所有表自动包含
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
```

### 模型示例

```python
# models/user.py
from typing import TYPE_CHECKING, List
from sqlalchemy import String, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.session import Session


class User(Base):
    __tablename__ = "users"
    
    # 基本字段
    username: Mapped[str] = mapped_column(
        String(50), 
        unique=True, 
        index=True,
        nullable=False,
        comment="用户名"
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    
    # 状态字段
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )
    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )
    
    # 可选字段
    avatar_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )
    bio: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )
    
    # 关系
    sessions: Mapped[List["Session"]] = relationship(
        "Session",
        back_populates="user",
        cascade="all, delete-orphan"
    )
```

---

## 关系设计

### 一对多

```python
# models/session.py
from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.message import Message


class Session(Base):
    __tablename__ = "sessions"
    
    # 外键
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # 会话字段
    title: Mapped[str] = mapped_column(
        String(200),
        default="新会话"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        index=True
    )
    context: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="会话上下文数据"
    )
    
    # 关系
    user: Mapped["User"] = relationship("User", back_populates="sessions")
    messages: Mapped[List["Message"]] = relationship(
        "Message",
        back_populates="session",
        order_by="Message.created_at",
        cascade="all, delete-orphan"
    )
```

### 多对多

```python
# models/tag.py
from typing import List
from sqlalchemy import Table, Column, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# 关联表
session_tag_association = Table(
    "session_tag_association",
    Base.metadata,
    Column("session_id", ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
)


class Tag(Base):
    __tablename__ = "tags"
    
    name: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False
    )
    color: Mapped[str] = mapped_column(
        String(7),
        default="#6366f1",
        comment="标签颜色 (hex)"
    )
    
    # 多对多关系
    sessions: Mapped[List["Session"]] = relationship(
        "Session",
        secondary=session_tag_association,
        back_populates="tags"
    )


# 在 Session 模型中添加
class Session(Base):
    # ... 其他字段 ...
    
    tags: Mapped[List["Tag"]] = relationship(
        "Tag",
        secondary=session_tag_association,
        back_populates="sessions"
    )
```

### 一对一

```python
# models/user_profile.py
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"
    
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,  # 确保一对一
        nullable=False
    )
    
    phone: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)
    preferences: Mapped[dict | None] = mapped_column(JSON)
    
    # 关系
    user: Mapped["User"] = relationship("User", back_populates="profile")


# 在 User 模型中
class User(Base):
    # ... 其他字段 ...
    
    profile: Mapped["UserProfile"] = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,  # 明确一对一
        cascade="all, delete-orphan"
    )
```

---

## 索引设计

### 何时加索引

| 场景 | 建议 |
|------|------|
| 主键 | 自动创建 |
| 外键 | 必须创建 |
| 查询条件字段 | 建议创建 |
| 唯一约束 | 自动创建 |
| 排序字段 | 考虑创建 |
| 低基数字段（如 status） | 谨慎创建 |

### 索引示例

```python
from sqlalchemy import Index

class Message(Base):
    __tablename__ = "messages"
    
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("sessions.id"),
        nullable=False,
        index=True  # 外键索引
    )
    
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True  # 常用于过滤
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True  # 常用于排序
    )
    
    content: Mapped[str] = mapped_column(Text)
    
    # 复合索引
    __table_args__ = (
        Index(
            "ix_messages_session_role",
            "session_id",
            "role"
        ),
        Index(
            "ix_messages_created_sort",
            "session_id",
            "created_at"
        ),
    )
```

---

## 字段类型速查

| Python 类型 | SQLAlchemy 类型 | 用途 |
|-------------|-----------------|------|
| `str` | `String(n)` | 短文本（用户名、邮箱） |
| `str` | `Text` | 长文本（内容、描述） |
| `int` | `Integer` | 整数 |
| `bool` | `Boolean` | 布尔值 |
| `datetime` | `DateTime(timezone=True)` | 时间戳 |
| `UUID` | `UUID(as_uuid=True)` | 主键、外键 |
| `dict/list` | `JSON` | JSON 数据 |
| `Decimal` | `Numeric(precision, scale)` | 金额计算 |
| `bytes` | `LargeBinary` | 二进制数据 |
| `Enum` | `Enum(PyEnum)` | 枚举值 |

---

## 约束设计

```python
from sqlalchemy import CheckConstraint, UniqueConstraint

class MCPConfig(Base):
    __tablename__ = "mcp_configs"
    
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(20))
    command: Mapped[str] = mapped_column(String(500))
    
    # 表级约束
    __table_args__ = (
        # 唯一约束
        UniqueConstraint("name", name="uq_mcp_config_name"),
        
        # 检查约束
        CheckConstraint(
            "type IN ('stdio', 'sse')",
            name="ck_mcp_config_type"
        ),
        CheckConstraint(
            "char_length(name) >= 1",
            name="ck_mcp_config_name_not_empty"
        ),
    )
```

---

## 异步操作

### 会话管理

```python
# db/session.py
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine
)
from app.core.config import settings

# 创建异步引擎
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    pool_size=20,
    max_overflow=0
)

# 会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


# 依赖注入
async def get_db() -> AsyncGenerator[AsyncSession, None]:
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

### CRUD 操作

```python
# crud/user.py
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


class UserCRUD:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get(self, user_id: UUID) -> User | None:
        """根据 ID 获取用户"""
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_username(self, username: str) -> User | None:
        """根据用户名获取用户"""
        result = await self.db.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()
    
    async def get_multi(
        self, 
        *, 
        skip: int = 0, 
        limit: int = 100
    ) -> list[User]:
        """获取用户列表"""
        result = await self.db.execute(
            select(User)
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()
    
    async def create(self, obj_in: UserCreate) -> User:
        """创建用户"""
        db_obj = User(**obj_in.model_dump())
        self.db.add(db_obj)
        await self.db.flush()
        await self.db.refresh(db_obj)
        return db_obj
    
    async def update(
        self, 
        *, 
        db_obj: User, 
        obj_in: UserUpdate
    ) -> User:
        """更新用户"""
        update_data = obj_in.model_dump(exclude_unset=True)
        
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        self.db.add(db_obj)
        await self.db.flush()
        await self.db.refresh(db_obj)
        return db_obj
    
    async def delete(self, db_obj: User) -> None:
        """删除用户"""
        await self.db.delete(db_obj)
        await self.db.flush()
```

---

## 迁移（Alembic）

### 创建迁移

```bash
# 自动生成迁移
alembic revision --autogenerate -m "add user table"

# 手动创建迁移
alembic revision -m "add index"
```

### 迁移示例

```python
# alembic/versions/xxx_add_user_table.py
"""add user table

Revision ID: xxx
Revises: yyy
Create Date: 2026-03-30

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'xxx'
down_revision = 'yyy'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('username', sa.String(length=50), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('username')
    )
    op.create_index('ix_users_email', 'users', ['email'])


def downgrade() -> None:
    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('users')
```

---

## 快速检查清单

**设计模型时：**
- [ ] 每个表都有 `id`, `created_at`, `updated_at`
- [ ] 外键都有索引
- [ ] 关系方向正确（`back_populates`）
- [ ] 字段有适当的约束（nullable, default）
- [ ] 敏感字段（密码）不存储明文

**创建迁移时：**
- [ ] 审查生成的迁移脚本
- [ ] 测试迁移和回滚
- [ ] 生产环境大表添加索引使用 `CONCURRENTLY`

---

*数据是系统的核心——模型设计决定系统的可维护性。*
