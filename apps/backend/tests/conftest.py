from __future__ import annotations

import atexit
import os
import sys
import types
import tempfile
from pathlib import Path
from shutil import copyfile

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _is_safe_test_database_url(database_url: str) -> bool:
    """只允许 pytest 使用内存库或 /tmp 下的临时 SQLite。"""
    return (
        database_url.startswith("sqlite:///:memory:")
        or database_url.startswith("sqlite:////tmp/")
        or database_url.startswith("sqlite:///tmp/")
    )


def _default_test_database_url() -> str:
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "main")
    db_path = Path(tempfile.gettempdir()) / (
        f"aiasys-pytest-{worker_id}-{os.getpid()}.db"
    )
    return f"sqlite:///{db_path}"


_DATABASE_URL = os.getenv("DATABASE_URL", "")
if _DATABASE_URL:
    if not _is_safe_test_database_url(_DATABASE_URL):
        raise RuntimeError(
            "后端测试必须使用隔离 SQLite DATABASE_URL，"
            f"当前值会污染开发或生产数据: {_DATABASE_URL}"
        )
else:
    os.environ["DATABASE_URL"] = _default_test_database_url()

CONFIG_PATH = BACKEND_ROOT / "config.json"
CONFIG_EXAMPLE_PATH = BACKEND_ROOT / "config.example.json"
_CREATED_TEMP_CONFIG = False

if not CONFIG_PATH.exists() and CONFIG_EXAMPLE_PATH.exists():
    copyfile(CONFIG_EXAMPLE_PATH, CONFIG_PATH)
    _CREATED_TEMP_CONFIG = True


def _cleanup_temp_config() -> None:
    if _CREATED_TEMP_CONFIG and CONFIG_PATH.exists():
        CONFIG_PATH.unlink()


atexit.register(_cleanup_temp_config)

if "app.services.execution_replay_risk" not in sys.modules:
    replay_risk_stub = types.ModuleType("app.services.execution_replay_risk")

    def derive_execution_replay_risk(code: str):
        _ = code
        return {
            "level": "low",
            "tags": [],
            "reasons": [],
            "has_side_effect_risk": False,
        }

    replay_risk_stub.derive_execution_replay_risk = derive_execution_replay_risk
    sys.modules["app.services.execution_replay_risk"] = replay_risk_stub


@pytest.fixture(autouse=True)
def _clean_connector_tables():
    """每次测试前后清空隔离 SQLite 资源表，避免共享库互相污染。"""
    from sqlalchemy import text
    from app.core.database import Base, SessionLocal, engine

    database_url = os.getenv("DATABASE_URL", "")
    if not _is_safe_test_database_url(database_url):
        raise RuntimeError(
            "后端测试正在使用非隔离数据库，已停止以避免污染运行态: "
            f"{database_url}"
        )

    def _truncate():
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        try:
            for table_name in (
                "database_connectors",
                "session_attachments",
                "subagent_configs",
                "subagent_instances",
                "workspace_resource_defaults",
            ):
                try:
                    db.execute(text(f"DELETE FROM {table_name}"))
                except Exception:
                    db.rollback()
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    _truncate()
    yield
    _truncate()
