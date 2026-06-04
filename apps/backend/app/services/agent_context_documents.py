"""Agent 上下文文档布局。

这里管理不是 memory 的长期上下文文件：
- `soul.md`：用户默认 Agent 身份与协作方式。
- `project_profile.md`：工作区项目画像。
"""

from __future__ import annotations

from pathlib import Path

AGENT_CONFIG_DIR_RELATIVE_PATH = Path(".aiasys") / "agent_config"
SOUL_FILE_NAME = "soul.md"
PROJECT_PROFILE_RELATIVE_PATH = Path(".aiasys") / "project_profile.md"


DEFAULT_SOUL_TEMPLATE = """# Agent Soul

## 身份
- 你是 AIASys 中代表当前用户工作的任务主控。

## 协作方式
- 先理解当前工作区、当前会话和可用工具，再开始执行。
- 对会修改文件、配置、运行环境或外部服务的操作，先判断风险和影响范围。
- 用户已经明确目标时，优先推进任务；只有缺少关键信息时才停下来询问。

## 表达偏好
- 用直白、具体的中文说明判断、动作和验证结果。
"""


def build_default_project_profile(
    *,
    title: str | None = None,
    description: str | None = None,
) -> str:
    title_text = (title or "").strip() or "未命名工作区"
    description_text = (description or "").strip() or "尚未填写。"
    return f"""# Project Profile

## 项目名称
{title_text}

## 项目说明
{description_text}

## 项目目标
- 记录这个工作区长期要完成的目标。

## 当前边界
- 记录这个项目不做什么、不能动什么、需要遵守什么限制。

## 关键资料
- 记录项目入口、核心文件、外部资料和需要优先阅读的文档。
"""


def get_user_soul_path(workspace_root: Path, user_id: str) -> Path:
    """返回用户默认 Agent Soul 文件路径。"""
    return (
        Path(workspace_root)
        / user_id
        / "global_workspace"
        / AGENT_CONFIG_DIR_RELATIVE_PATH
        / SOUL_FILE_NAME
    )


def ensure_user_soul_file(workspace_root: Path, user_id: str) -> Path:
    """确保用户默认 Agent Soul 文件存在。"""
    path = get_user_soul_path(workspace_root, user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(DEFAULT_SOUL_TEMPLATE, encoding="utf-8")
    return path


def read_user_soul_text(workspace_root: Path, user_id: str) -> str:
    """读取用户默认 Agent Soul；没有文件时先初始化。"""
    path = ensure_user_soul_file(workspace_root, user_id)
    return path.read_text(encoding="utf-8").strip()


def get_workspace_project_profile_path(workspace_dir: Path) -> Path:
    """返回工作区项目画像文件路径。"""
    return Path(workspace_dir) / PROJECT_PROFILE_RELATIVE_PATH


def ensure_workspace_project_profile_file(
    workspace_dir: Path,
    *,
    title: str | None = None,
    description: str | None = None,
) -> Path:
    """确保工作区项目画像文件存在。"""
    path = get_workspace_project_profile_path(workspace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            build_default_project_profile(title=title, description=description),
            encoding="utf-8",
        )
    return path


def read_workspace_project_profile_text(
    workspace_dir: Path,
    *,
    title: str | None = None,
    description: str | None = None,
) -> str:
    """读取工作区项目画像；没有文件时先初始化。"""
    path = ensure_workspace_project_profile_file(
        workspace_dir,
        title=title,
        description=description,
    )
    return path.read_text(encoding="utf-8").strip()
