from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.services.agent.mixins.context import load_agent_instructions_for_user_message


def test_load_agent_instructions_without_any_agents_md(tmp_path: Path) -> None:
    """没有规范时返回 None。"""
    with patch("app.services.agent.mixins.context.load_agent_instructions", return_value=None):
        result = load_agent_instructions_for_user_message(workspace_dir=None)

    assert result is None


def test_load_agent_instructions_with_root_agents_md_only(tmp_path: Path) -> None:
    """只有全局规范时，应返回其内容。"""
    with patch(
        "app.services.agent.mixins.context.load_agent_instructions",
        return_value="# 项目规范\n使用中文。\n",
    ):
        result = load_agent_instructions_for_user_message(workspace_dir=None)

    assert result == "# 项目规范\n使用中文。\n"


def test_load_agent_instructions_with_workspace_and_root(tmp_path: Path) -> None:
    """工作区规范与全局规范并存时，两者都应被加载。"""
    workspace_dir = tmp_path / "user" / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)

    with patch(
        "app.services.agent.mixins.context.load_agent_instructions",
        return_value=(
            "# Agent Instructions\n\n"
            "## Global\n\n"
            "# 项目规范\n项目级内容。\n\n"
            "---\n\n"
            "## Workspace\n\n"
            "# 工作区规范\n工作区级内容。"
        ),
    ):
        result = load_agent_instructions_for_user_message(workspace_dir=workspace_dir)

    assert "# 项目规范" in (result or "")
    assert "# 工作区规范" in (result or "")


def test_load_agent_instructions_workspace_priority(tmp_path: Path) -> None:
    """load_agent_instructions 返回工作区覆盖后的内容。"""
    workspace_dir = tmp_path / "user" / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)

    with patch(
        "app.services.agent.mixins.context.load_agent_instructions",
        return_value="# 工作区\n工作区内容\n",
    ):
        result = load_agent_instructions_for_user_message(workspace_dir=workspace_dir)

    assert "# 工作区" in (result or "")
    assert "工作区内容" in (result or "")
