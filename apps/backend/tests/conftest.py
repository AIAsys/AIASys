from __future__ import annotations

import atexit
import os
import sys
import tempfile
import types
from pathlib import Path
from shutil import copyfile

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# 测试不应走外部代理。清除代理环境变量，避免 httpx 因缺少 socksio 而崩溃。
for _key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(_key, None)

# 测试用 JWT secret：避免测试依赖仓库中的真实/占位密钥
os.environ.setdefault(
    "AIASYS_AUTH_JWT_SECRET", "test-jwt-secret-do-not-use-in-production"
)


def _is_safe_test_database_url(database_url: str) -> bool:
    """只允许 pytest 使用内存库或系统临时目录下的临时 SQLite（跨平台兼容）。"""
    db_path = database_url.removeprefix("sqlite:///")
    if db_path == "/:memory:":
        return True
    temp_dir = tempfile.gettempdir()
    return db_path.startswith(temp_dir) or db_path.startswith("/tmp/")


def _default_test_database_url() -> str:
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "main")
    db_path = Path(tempfile.gettempdir()) / (f"aiasys-pytest-{worker_id}-{os.getpid()}.db")
    return f"sqlite:///{db_path}"


_DATABASE_URL = os.getenv("DATABASE_URL", "")
if _DATABASE_URL:
    if not _is_safe_test_database_url(_DATABASE_URL):
        raise RuntimeError(
            f"后端测试必须使用隔离 SQLite DATABASE_URL，当前值会污染开发或生产数据: {_DATABASE_URL}"
        )
else:
    os.environ["DATABASE_URL"] = _default_test_database_url()

CONFIG_PATH = BACKEND_ROOT / "config.toml"
CONFIG_EXAMPLE_PATH = BACKEND_ROOT / "config.example.toml"
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
        raise RuntimeError(f"后端测试正在使用非隔离数据库，已停止以避免污染运行态: {database_url}")

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


@pytest.fixture
def isolated_llm_config(monkeypatch, tmp_path):
    """为当前测试提供独立的 LLM 配置，包含多模态和非多模态测试模型。

    返回字典：
    - user_id: 测试用户 ID
    - service: LLMConfigService 实例
    - text_model_id: 纯文本模型 ID
    - multimodal_model_id: 多模态模型 ID

    该 fixture 不依赖 AIASys 系统的 config.toml，适合需要验证模型能力差异的测试。
    """
    from pydantic import SecretStr

    from app.core import config as core_config
    from app.models.llm_provider import LLMModelConfig, LLMProviderConfig
    from app.services.llm.llm_config_service import LLMConfigService
    from app.storage.llm_provider_storage import LLMProviderStorage

    user_id = f"test_user_{os.getpid()}"
    config_dir = tmp_path / user_id / ".aiasys"
    config_dir.mkdir(parents=True, exist_ok=True)

    from app.storage import llm_provider_storage as llm_storage_module

    def fake_get_user_global_config_dir(uid: str) -> Path:
        return tmp_path / str(uid) / ".aiasys"

    monkeypatch.setattr(core_config, "get_user_global_config_dir", fake_get_user_global_config_dir)
    monkeypatch.setattr(
        llm_storage_module, "get_user_global_config_dir", fake_get_user_global_config_dir
    )

    storage = LLMProviderStorage()
    service = LLMConfigService(storage=storage)

    provider = LLMProviderConfig(
        id="test-stepfun",
        name="Test StepFun",
        type="openai_chat_completions",
        base_url="https://api.stepfun.com/v1",
        api_key=SecretStr("test-key"),
    )
    service.create_provider(user_id, provider)

    text_model = LLMModelConfig(
        id="test-stepfun-test-step-router-v1",
        name="test-step-router-v1",
        provider="test-stepfun",
        model="test-step-router-v1",
        max_context_size=256000,
        capabilities=set(),
    )
    service.create_model(user_id, text_model)

    multimodal_model = LLMModelConfig(
        id="test-stepfun-test-step-3.7-flash",
        name="test-step-3.7-flash",
        provider="test-stepfun",
        model="test-step-3.7-flash",
        max_context_size=256000,
        capabilities={"thinking", "image_in", "video_in"},
    )
    service.create_model(user_id, multimodal_model)
    service.set_default_model(user_id, multimodal_model.id)

    return {
        "user_id": user_id,
        "service": service,
        "text_model_id": text_model.id,
        "multimodal_model_id": multimodal_model.id,
    }
