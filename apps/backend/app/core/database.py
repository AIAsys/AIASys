"""
数据库配置

使用 SQLAlchemy + SQLite 存储用户数据
"""

import logging
import os
from contextlib import contextmanager

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import DATA_DIR
from app.core.time import utc_now_naive

logger = logging.getLogger(__name__)

# 数据库文件路径（放在 data 目录下）
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR}/aiasys.db")

# 创建引擎
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    """设置 SQLite PRAGMA：WAL 模式 + 外键约束。"""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# 会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 基类
Base = declarative_base()


class User(Base):
    """用户模型"""

    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=True)
    name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    role = Column(String, default="user", nullable=False)  # "admin" | "user"
    hashed_password = Column(String, nullable=True)
    avatar_color = Column(String, nullable=True)
    avatar_char = Column(String, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)


class DatabaseConnectorORM(Base):
    """数据库连接器配置表（替代 JSON 文件）"""

    __tablename__ = "database_connectors"

    connector_id = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True)
    workspace_id = Column(String, nullable=True, index=True)
    scope = Column(String, default="global", nullable=False, index=True)
    name = Column(String, nullable=False)
    db_type = Column(String, nullable=False)
    connection_mode = Column(String, default="fields")
    host = Column(String, nullable=True)
    port = Column(Integer, nullable=True)
    database_name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    password_encrypted = Column(String, nullable=True)
    api_token_encrypted = Column(String, nullable=True)
    connection_url_encrypted = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    allow_notebook_access = Column(Integer, default=0)
    allowed_schemas = Column(JSON, default=list)
    allowed_tables = Column(JSON, default=list)
    query_timeout_seconds = Column(Integer, default=15)
    row_limit = Column(Integer, default=1000)
    last_test_status = Column(String, default="untested")
    last_test_message = Column(String, nullable=True)
    last_tested_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)


class SessionAttachmentORM(Base):
    """会话挂载关系表（替代 JSON 文件）"""

    __tablename__ = "session_attachments"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=True, index=True)
    session_id = Column(String, nullable=False, index=True)
    connector_id = Column(String, nullable=False, index=True)
    handle = Column(String, nullable=True)
    attached_at = Column(DateTime, default=utc_now_naive)


class SubAgentConfigORM(Base):
    """子 Agent 配置表。"""

    __tablename__ = "subagent_configs"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True)
    workspace_id = Column(String, nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    scope = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    manifest = Column(JSON, default=dict)
    system_prompt = Column(Text, nullable=True)
    yaml_path = Column(Text, nullable=True)
    prompt_path = Column(Text, nullable=True)
    source = Column(String, default="custom", nullable=False)
    status = Column(String, default="active", nullable=False)
    builtin_baseline_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)


class WorkspaceResourceDefaultORM(Base):
    """工作区默认资源选择表（替代 .aiasys/database-mounts.json）"""

    __tablename__ = "workspace_resource_defaults"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True)
    workspace_id = Column(String, nullable=False, index=True)
    resource_type = Column(String, nullable=False, index=True)
    resource_id = Column(String, nullable=False, index=True)
    resource_scope = Column(String, default="workspace", nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    meta_info = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)


def init_db():
    """初始化数据库表"""
    Base.metadata.create_all(bind=engine)


@contextmanager
def db_session() -> Session:
    """获取数据库会话（上下文管理器）。

    用于不在 FastAPI 依赖注入上下文中的代码（如服务层、工具函数、后台任务）。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db():
    """获取数据库会话（依赖注入）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
