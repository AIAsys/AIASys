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
    cursor.execute("PRAGMA busy_timeout=30000")
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


class SubAgentInstanceORM(Base):
    """子 Agent 运行实例表，用于后续把文件系统运行记录迁入 SQLite"""

    __tablename__ = "subagent_instances"

    agent_id = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True)
    workspace_id = Column(String, nullable=True, index=True)
    host_session_id = Column(String, nullable=False, index=True)
    parent_agent_id = Column(String, nullable=True, index=True)
    parent_tool_call_id = Column(String, nullable=True, index=True)
    subagent_type = Column(String, nullable=False, index=True)
    agent_path = Column(String, nullable=True, index=True)
    depth = Column(Integer, default=0, nullable=False)
    status = Column(String, default="running", nullable=False, index=True)
    model = Column(String, nullable=True)
    nickname = Column(String, nullable=True)
    meta_info = Column(JSON, default=dict)
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


def _sqlite_default_value(col) -> str | None:
    """把 SQLAlchemy Column 的 Python default 转成 SQLite 可接受的字面量。

    只处理标量默认值和常用的 list/dict 可调用默认值；复杂可调用对象
    （如 utc_now_naive）无法静态翻译，返回 None，由调用方决定是否需要
    降级为 NULLABLE。
    """
    if col.server_default is not None:
        return str(col.server_default.arg)

    default = col.default
    if default is None:
        return None

    if getattr(default, "is_scalar", False):
        val = default.arg
        if isinstance(val, str):
            return f"'{val.replace("'", "''")}'"
        if isinstance(val, bool):
            return "1" if val else "0"
        if isinstance(val, (int, float)):
            return str(val)
        return None

    if getattr(default, "is_callable", False):
        try:
            val = default.arg()
            # JSON 字段常用 list/dict 作为默认值
            if isinstance(val, list):
                return "'[]'"
            if isinstance(val, dict):
                return "'{}'"
        except Exception:
            # 无法静态调用的可调用对象（如需要参数的工厂函数）跳过
            pass

    return None


def _ensure_column(
    table_name: str, column_name: str, column_def: str, *, index_name: str | None = None
) -> None:
    """对已有 SQLite 表安全地添加缺失列（用于旧 DB 兼容）。"""
    from sqlalchemy import text

    with engine.connect() as conn:
        columns = {r[1] for r in conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()}
        if column_name not in columns:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}"))
            if index_name:
                conn.execute(
                    text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}({column_name})")
                )
            conn.commit()


def _ensure_all_model_columns() -> None:
    """自动补齐 Base 中所有已存在表的缺失列与索引。

    设计约束：
    - 不删除、不修改已有列；只做追加。
    - 主键列缺失视为表结构严重异常，不自动处理（交给 create_all 重建新表）。
    - 默认值仅使用 SQLite 字面量，避免可调用对象差异导致迁移失败。
    """
    from sqlalchemy import text
    from sqlalchemy.dialects.sqlite.base import SQLiteDialect
    from sqlalchemy.schema import CreateColumn, CreateIndex

    dialect = SQLiteDialect()
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            table_name = table.name
            existing_cols = {
                r[1] for r in conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
            }
            if not existing_cols:
                # 表不存在，Base.metadata.create_all 会负责创建
                continue

            for col in table.columns:
                if col.primary_key:
                    continue
                if col.name in existing_cols:
                    continue

                base_def = str(CreateColumn(col).compile(dialect=dialect))
                default_sql = _sqlite_default_value(col)
                parts = base_def.split()
                has_not_null = "NOT" in parts and "NULL" in parts
                if has_not_null:
                    parts = [p for p in parts if p not in ("NOT", "NULL")]
                    base_def = " ".join(parts)
                if default_sql is not None:
                    base_def += f" DEFAULT {default_sql}"
                if has_not_null:
                    base_def += " NOT NULL"

                try:
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {base_def}"))
                    conn.commit()
                    logger.info("自动迁移：表 %s 新增列 %s", table_name, col.name)
                except Exception as e:
                    logger.warning("自动迁移失败：表 %s 列 %s: %s", table_name, col.name, e)

            existing_indexes = {
                r[1] for r in conn.execute(text(f"PRAGMA index_list({table_name})")).fetchall()
            }
            for idx in table.indexes:
                if idx.name in existing_indexes:
                    continue
                try:
                    conn.execute(text(str(CreateIndex(idx).compile(dialect=dialect))))
                    conn.commit()
                    logger.info("自动迁移：表 %s 新增索引 %s", table_name, idx.name)
                except Exception as e:
                    logger.warning("自动迁移失败：表 %s 索引 %s: %s", table_name, idx.name, e)


def init_db():
    """初始化数据库表，并对旧 schema 做兼容性补丁。"""
    Base.metadata.create_all(bind=engine)
    _ensure_all_model_columns()
    # 显式兜底：确保历史变更中关键列/索引存在
    _ensure_column(
        "database_connectors",
        "workspace_id",
        "VARCHAR",
        index_name="ix_database_connectors_workspace_id",
    )
    _ensure_column(
        "database_connectors",
        "scope",
        "VARCHAR NOT NULL DEFAULT 'global'",
        index_name="ix_database_connectors_scope",
    )


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
