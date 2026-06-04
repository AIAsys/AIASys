"""
核心配置 - 从 config.json 加载

存储架构：
- workspaces/{user_id}/{session_id}/          - 用户工作目录
- workspaces/{user_id}/{session_id}/.aiasys/session/ - Session 状态存储
- workspaces/{user_id}/{session_id}/*         - 用户上传/生成的文件
- logs/                                        - 日志文件
"""

import json
import logging
import os
import secrets
import tomllib
from pathlib import Path
from typing import Any, Dict, List

from app.core.runtime_storage_config import read_runtime_storage_paths

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent
RUNTIME_ROOT = Path(os.environ.get("AIASYS_RUNTIME_ROOT", str(BASE_DIR))).expanduser()


def _resolve_runtime_path(
    env_name: str,
    default_path: Path,
    stored_override: str | None = None,
) -> Path:
    override = os.environ.get(env_name)
    if override:
        return Path(override).expanduser()
    if stored_override:
        return Path(stored_override).expanduser()
    return default_path


def _load_config() -> Dict[str, Any]:
    """从 config.json 加载配置"""
    config_path = BASE_DIR / "config.json"

    if not config_path.exists():
        raise FileNotFoundError(
            f"配置文件不存在: {config_path}\n请复制 config.example.json 为 config.json 并填写配置"
        )

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _set_nested_config(config: Dict[str, Any], path: str, value: Any) -> None:
    """按 a.b.c 路径写入配置，缺失层级会自动创建。"""
    keys = path.split(".")
    target: Dict[str, Any] = config
    for key in keys[:-1]:
        child = target.get(key)
        if not isinstance(child, dict):
            child = {}
            target[key] = child
        target = child
    target[keys[-1]] = value


def _normalized_env_suffix(value: str) -> str:
    """把 provider id 转成适合环境变量的后缀。"""
    return "".join(char if char.isalnum() else "_" for char in value.upper())


def _apply_secret_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    """允许在服务端通过环境变量覆盖敏感配置，避免把真实 key 写进仓库或镜像。"""
    direct_overrides = {
        "AIASYS_EMBEDDING_API_KEY": "embedding.api_key",
        "AIASYS_AUTH_JWT_SECRET": "auth.jwt_secret",
        "AIASYS_DOCUMENT_EXTRACTION_PDF_PASSWORD": "document_extraction.pdf_password",
    }

    for env_name, path in direct_overrides.items():
        if env_name in os.environ:
            _set_nested_config(config, path, os.environ[env_name])

    llm_providers = config.get("llm", {}).get("providers", {})
    if isinstance(llm_providers, dict):
        for provider_id in llm_providers:
            suffix = _normalized_env_suffix(provider_id)
            api_key_env = f"AIASYS_LLM_PROVIDER_{suffix}_API_KEY"
            base_url_env = f"AIASYS_LLM_PROVIDER_{suffix}_BASE_URL"

            if api_key_env in os.environ:
                _set_nested_config(
                    config,
                    f"llm.providers.{provider_id}.api_key",
                    os.environ[api_key_env],
                )
            if base_url_env in os.environ:
                _set_nested_config(
                    config,
                    f"llm.providers.{provider_id}.base_url",
                    os.environ[base_url_env],
                )

    return config


# 加载配置
_CONFIG = _apply_secret_env_overrides(_load_config())


def _get_config(path: str, default: Any = None) -> Any:
    """通过路径获取配置值，如 'server.port'"""
    keys = path.split(".")
    value = _CONFIG
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key, default)
        else:
            return default
    return value if value is not None else default


# 存储目录（统一使用 data/workspaces，session 存储在 .aiasys/session/ 子目录下）
_DEFAULT_DATA_DIR = RUNTIME_ROOT / "data"
_STORED_STORAGE_PATHS = read_runtime_storage_paths(RUNTIME_ROOT)
DATA_DIR = _resolve_runtime_path(
    "AIASYS_RUNTIME_DATA_DIR",
    _DEFAULT_DATA_DIR,
    _STORED_STORAGE_PATHS.get("data_dir"),
)
LOGS_DIR = _resolve_runtime_path(
    "AIASYS_RUNTIME_LOGS_DIR",
    RUNTIME_ROOT / "logs",
    _STORED_STORAGE_PATHS.get("logs_dir"),
)
WORKSPACE_DIR = _resolve_runtime_path(
    "AIASYS_RUNTIME_WORKSPACES_DIR",
    DATA_DIR / "workspaces",
    _STORED_STORAGE_PATHS.get("workspaces_dir"),
)
GLOBAL_WORKSPACE_DIR_NAME = "global_workspace"
GLOBAL_WORKSPACE_RESOURCES_DIR_NAME = "resources"
GLOBAL_WORKSPACE_MEMORY_DIR_NAME = ".aiasys/.memory"
GLOBAL_WORKSPACE_CONFIG_DIR_NAME = ".aiasys"


def get_user_global_workspace_dir(user_id: str) -> Path:
    """返回用户默认层的物理根目录。"""
    return WORKSPACE_DIR / user_id / GLOBAL_WORKSPACE_DIR_NAME


def get_user_global_resources_dir(user_id: str) -> Path:
    """返回用户默认层资源目录。"""
    return get_user_global_workspace_dir(user_id) / GLOBAL_WORKSPACE_RESOURCES_DIR_NAME


def get_user_global_memory_dir(user_id: str) -> Path:
    """返回用户默认层 memory 目录。"""
    return get_user_global_workspace_dir(user_id) / GLOBAL_WORKSPACE_MEMORY_DIR_NAME


def get_user_global_config_dir(user_id: str) -> Path:
    """返回用户默认层配置目录。"""
    return get_user_global_workspace_dir(user_id) / GLOBAL_WORKSPACE_CONFIG_DIR_NAME


# 数据格式大版本号。破坏性存储格式变更时递增。
# 启动时检查，不匹配则拒绝启动，避免静默数据损坏。
DATA_FORMAT_VERSION = 1

# 全局工作区路径协议：
# - /global/{relative_path} 映射到 WORKSPACE_DIR / {user_id} / global_workspace / {relative_path}
# - /workspace/{relative_path} 映射到 WORKSPACE_DIR / {user_id} / {workspace_id} / {relative_path}
# - 两者是独立命名空间，Agent 文件工具均支持

# 资源上下文限制配置
GLOBAL_RESOURCE_SCAN_LIMIT = int(_get_config("resources.global_scan_limit", 100))
RESOURCE_PROMPT_ITEM_LIMIT = int(_get_config("resources.prompt_item_limit", 5))

# 确保目录存在
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _check_data_format_version() -> None:
    """检查数据目录格式版本，不匹配时抛出 RuntimeError。"""
    version_path = DATA_DIR / ".format_version"
    if not version_path.exists():
        version_path.write_text(str(DATA_FORMAT_VERSION), encoding="utf-8")
        return
    stored = version_path.read_text(encoding="utf-8").strip()
    if stored != str(DATA_FORMAT_VERSION):
        raise RuntimeError(
            f"数据格式版本不匹配: 目录要求 v{stored}，当前代码为 v{DATA_FORMAT_VERSION}。"
            f"请备份 {DATA_DIR} 后删除旧数据，或使用兼容版本启动。"
        )


def _load_app_version() -> str:
    """加载产品版本号，优先与前端版本保持一致。"""
    frontend_package_path = BASE_DIR.parent / "web" / "package.json"
    if frontend_package_path.exists():
        try:
            with open(frontend_package_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            version = data.get("version")
            if isinstance(version, str) and version.strip():
                return version.strip()
        except Exception:
            pass

    pyproject_path = BASE_DIR / "pyproject.toml"
    if pyproject_path.exists():
        try:
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
            version = data.get("project", {}).get("version")
            if isinstance(version, str) and version.strip():
                return version.strip()
        except Exception:
            pass

    return "0.2.0"


# API 配置
APP_NAME = "AI Agent Backend"
APP_VERSION = _load_app_version()
PORT = _get_config("server.port", 13001)
DEBUG = _get_config("server.debug", False)
LOG_LEVEL = _get_config("server.log_level", "info")

# LLM 配置
LLM_CONFIG = _get_config("llm", {})
DEFAULT_MODEL = _get_config("llm.default_model", "kimi-for-coding")
DEFAULT_PROVIDER = _get_config("llm.default_provider", "kimi")
LLM_PROVIDERS = _get_config("llm.providers", {})

# 文档提取配置
DOCUMENT_EXTRACTION_CONFIG = _get_config("document_extraction", {})
DOCUMENT_EXTRACTION_DEFAULT_MODE = DOCUMENT_EXTRACTION_CONFIG.get("default_mode", "enhanced")
DOCUMENT_EXTRACTION_FALLBACK_MODES = DOCUMENT_EXTRACTION_CONFIG.get("fallback_modes", ["basic"])
DOCUMENT_EXTRACTION_PDF_PASSWORD = DOCUMENT_EXTRACTION_CONFIG.get("pdf_password")

# Sandbox 配置
SANDBOX_CONFIG = _get_config("sandbox", {})


def _normalize_sandbox_modes(config: Dict[str, Any]) -> tuple[List[str], str]:
    """规范化沙盒模式配置。

    结构:
    {
      "sandbox": {
        "default_mode": "local",
        "enabled_modes": ["local"]
      }
    }
    """

    supported_modes = ("local", "docker")

    raw_enabled_modes = config.get("enabled_modes")
    enabled_modes: List[str] = []
    if isinstance(raw_enabled_modes, list):
        for mode in raw_enabled_modes:
            mode_str = str(mode).lower()
            if mode_str in supported_modes and mode_str not in enabled_modes:
                enabled_modes.append(mode_str)

    if not enabled_modes:
        enabled_modes = ["local"]

    raw_default_mode = str(config.get("default_mode", enabled_modes[0])).lower()
    if raw_default_mode not in supported_modes:
        raw_default_mode = enabled_modes[0]
    if raw_default_mode not in enabled_modes:
        enabled_modes.insert(0, raw_default_mode)

    # 确保 default_mode 排在 enabled_modes 首位，便于前端直接按顺序展示。
    enabled_modes = [raw_default_mode] + [
        mode for mode in enabled_modes if mode != raw_default_mode
    ]

    return enabled_modes, raw_default_mode


SANDBOX_ENABLED_MODES, SANDBOX_DEFAULT_MODE = _normalize_sandbox_modes(SANDBOX_CONFIG)

# ---- Timeout 配置 ----
_TIMEOUT_CONFIG_RAW = SANDBOX_CONFIG.get("timeout", {})

SANDBOX_TIMEOUT_CONFIG = {
    "local": {
        "default": _TIMEOUT_CONFIG_RAW.get("local", {}).get("default", 120),
        "min": _TIMEOUT_CONFIG_RAW.get("local", {}).get("min", 10),
        "max": _TIMEOUT_CONFIG_RAW.get("local", {}).get("max", 300),
    },
    "docker": {
        "default": _TIMEOUT_CONFIG_RAW.get("docker", {}).get("default", 120),
        "min": _TIMEOUT_CONFIG_RAW.get("docker", {}).get("min", 10),
        "max": _TIMEOUT_CONFIG_RAW.get("docker", {}).get("max", 300),
    },
}


def get_timeout_config(sandbox_mode: str) -> dict:
    """返回指定沙盒模式的 {default, min, max}。"""
    return SANDBOX_TIMEOUT_CONFIG.get(sandbox_mode, SANDBOX_TIMEOUT_CONFIG["local"])


def validate_code_timeout(timeout: int | None, sandbox_mode: str) -> int:
    """校验并 clamp 超时值到合法范围。None 返回默认值。"""
    cfg = get_timeout_config(sandbox_mode)
    if timeout is None:
        return cfg["default"]
    return max(cfg["min"], min(timeout, cfg["max"]))


SANDBOX_MODE = SANDBOX_DEFAULT_MODE  # 运行时默认模式别名


def is_sandbox_mode_enabled(mode: str) -> bool:
    """检查当前部署是否允许指定沙盒模式。"""
    return str(mode).lower() in SANDBOX_ENABLED_MODES


# 认证配置
AUTH_CONFIG_DATA = _get_config("auth", {})
AUTH_MODE = AUTH_CONFIG_DATA.get("mode", "local")
JWT_SECRET = AUTH_CONFIG_DATA.get("jwt_secret")
if not JWT_SECRET:
    JWT_SECRET = secrets.token_hex(32)
    logging.getLogger(__name__).warning(
        "auth.jwt_secret 未配置，已生成临时随机密钥。"
        "生产环境请在 config.json 中设置 jwt_secret 或使用 AIASYS_AUTH_JWT_SECRET 环境变量覆盖。"
    )
CORS_ORIGINS = _get_config("server.cors_origins", [])

# 导入 AuthConfig
from app.models.user import AuthConfig

# 管理员账号配置（从配置文件读取）
# Canvas 配置
CANVAS_AUTO_SAVE_DEBOUNCE_MS = int(_get_config("canvas.auto_save_debounce_ms", 800))

AUTH_CONFIG = AuthConfig(
    # 认证模式: none(开发离线)/local(单机默认用户)
    mode=AUTH_MODE,
    cors_origins=CORS_ORIGINS,
    cors_allow_credentials=True,
    enable_security_headers=True,
)
