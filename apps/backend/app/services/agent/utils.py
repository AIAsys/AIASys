"""
Agent 服务工具函数
"""

import logging
import re
from typing import Any, Dict, Optional

from app.core.config import WORKSPACE_DIR
from app.core.workspace_path import WorkspacePath

logger = logging.getLogger(__name__)


def get_work_dir(user_id: str, session_id: str) -> WorkspacePath:
    """获取会话工作目录"""
    import app.services.agent as agent_service_module

    workspace_root = getattr(agent_service_module, "WORKSPACE_DIR", WORKSPACE_DIR)
    session_workspace = workspace_root / user_id / session_id
    session_workspace.mkdir(parents=True, exist_ok=True)
    return WorkspacePath(session_workspace)


def get_session_key(user_id: str, session_id: str) -> str:
    """生成会话键（用于锁和缓存）"""
    return f"{user_id}/{session_id}"


def _select_preferred_agent_model_id(
    models: Dict[str, Dict[str, Any]],
    providers: Dict[str, Dict[str, Any]],
    configured_default_model: Optional[str],
) -> Optional[str]:
    """选择首选的 Agent 模型 ID

    优先使用用户配置的默认模型，不再硬编码任何厂商偏好。
    """
    if configured_default_model and configured_default_model in models:
        return configured_default_model

    # 无明确默认时，返回第一个可用模型（由调用方兜底）
    if models:
        return next(iter(models))

    return configured_default_model


def _get_execution_env_info() -> Dict[str, str]:
    """
    获取当前执行环境信息

    返回当前本地执行环境的提示词变量。
    """
    packages = [
        {"name": "pandas", "version": ">=2.0.0"},
        {"name": "numpy", "version": ">=1.24.0"},
        {"name": "matplotlib", "version": ">=3.7.0"},
        {"name": "seaborn", "version": ">=0.12.0"},
        {"name": "scipy", "version": ">=1.11.0"},
        {"name": "scikit-learn", "version": ">=1.3.0"},
        {"name": "requests", "version": ">=2.31.0"},
    ]
    python_version = "3.11"
    base_image = "local-python"

    package_names = [p["name"] if isinstance(p, dict) else p for p in packages]
    if len(package_names) <= 10:
        package_list_str = ", ".join(package_names)
    else:
        package_list_str = ", ".join(package_names[:10]) + f" 等共 {len(package_names)} 个包"

    package_details_lines = ["| 包名 | 版本 |", "|------|------|"]
    for pkg in packages[:20]:
        if isinstance(pkg, dict):
            name = pkg.get("name", "unknown")
            version = pkg.get("version", "")
        else:
            name = str(pkg)
            version = ""
        package_details_lines.append(f"| {name} | {version} |")

    if len(packages) > 20:
        package_details_lines.append(f"| ... 等共 {len(packages)} 个包 | |")

    return {
        "PYTHON_VERSION": python_version,
        "BASE_IMAGE": base_image,
        "PACKAGE_LIST": package_list_str,
        "PACKAGE_DETAILS": "\n".join(package_details_lines),
    }


def is_system_reminder_message(msg: dict) -> bool:
    """检查消息是否为 SDK 内部注入的 system-reminder 消息。"""
    if msg.get("role") != "user":
        return False
    content = msg.get("content")
    if not isinstance(content, str):
        return False
    return content.strip().startswith("<system-reminder>")


def serialize_tool_output(content: Any) -> str:
    """序列化工具输出"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(serialize_tool_output(c) for c in content)
    if hasattr(content, "text"):
        return str(content.text)
    if hasattr(content, "image_url"):
        url = content.image_url.url if hasattr(content.image_url, "url") else str(content.image_url)
        url = url.removeprefix("file://")
        return f"![image]({url})"
    return str(content)


def format_prompt_for_log(prompt: str, max_length: int = 200) -> str:
    """格式化提示词用于日志"""
    cleaned = re.sub(r"\s+", " ", prompt).strip()
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[:max_length] + "..."
