"""全局工作区感知测试。

验证 Agent 资源上下文和文件工具对全局工作区的支持。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.history import current_global_workspace, current_user_id, current_workspace
from app.services.task_resource_context import (
    build_task_resource_context,
    format_task_resource_context_for_prompt,
    resolve_global_workspace_resources,
)


@pytest.fixture
def tmp_workspace(tmp_path: Path):
    """设置临时工作区上下文。"""
    ws_path = tmp_path / "workspace"
    ws_path.mkdir(parents=True, exist_ok=True)
    token_ws = current_workspace.set(str(ws_path))
    token_user = current_user_id.set("test-user")
    yield ws_path
    current_workspace.reset(token_ws)
    current_user_id.reset(token_user)


@pytest.fixture
def tmp_global_workspace(tmp_path: Path):
    """设置临时全局工作区上下文。"""
    global_path = tmp_path / "global"
    global_path.mkdir(parents=True, exist_ok=True)
    token = current_global_workspace.set(str(global_path))
    yield global_path
    current_global_workspace.reset(token)


# ---------------------------------------------------------------------------
# resolve_global_workspace_resources
# ---------------------------------------------------------------------------


def test_resolve_global_workspace_resources_scans_files(
    tmp_global_workspace: Path,
) -> None:
    (tmp_global_workspace / "templates").mkdir()
    (tmp_global_workspace / "templates" / "report.md").write_text("# Report", encoding="utf-8")
    (tmp_global_workspace / "data.csv").write_text("a,b\n1,2", encoding="utf-8")

    resources = resolve_global_workspace_resources()

    assert len(resources) == 2
    paths = {r["display_path"] for r in resources}
    assert "/global/templates/report.md" in paths
    assert "/global/data.csv" in paths


def test_resolve_global_workspace_resources_skips_hidden(
    tmp_global_workspace: Path,
) -> None:
    (tmp_global_workspace / ".hidden").mkdir()
    (tmp_global_workspace / ".hidden" / "secret.txt").write_text("secret", encoding="utf-8")
    (tmp_global_workspace / "visible.txt").write_text("visible", encoding="utf-8")

    resources = resolve_global_workspace_resources()

    assert len(resources) == 1
    assert resources[0]["display_path"] == "/global/visible.txt"


# ---------------------------------------------------------------------------
# build_task_resource_context
# ---------------------------------------------------------------------------


def test_build_task_resource_context_includes_global_resources(
    tmp_workspace: Path,
    tmp_global_workspace: Path,
) -> None:
    (tmp_global_workspace / "ref.md").write_text("reference", encoding="utf-8")

    ctx = build_task_resource_context(
        user_id="test-user",
        session_id="session-1",
    )

    assert "global_workspace_resources" in ctx
    assert "global_workspace_resource_count" in ctx
    assert ctx["global_workspace_resource_count"] == 1
    assert ctx["global_workspace_resources"][0]["display_path"] == "/global/ref.md"


def test_build_task_resource_context_global_dir_missing() -> None:
    """全局目录不存在时应返回空列表，不报错。"""
    token = current_global_workspace.set("/nonexistent/global/path")
    try:
        ctx = build_task_resource_context(user_id="test-user")
        assert ctx.get("global_workspace_resources") == []
        assert ctx.get("global_workspace_resource_count") == 0
    finally:
        current_global_workspace.reset(token)


# ---------------------------------------------------------------------------
# format_task_resource_context_for_prompt
# ---------------------------------------------------------------------------


def test_format_prompt_includes_global_workspace_section(
    tmp_workspace: Path,
    tmp_global_workspace: Path,
) -> None:
    (tmp_global_workspace / "shared.md").write_text("shared", encoding="utf-8")

    ctx = build_task_resource_context(
        user_id="test-user",
        session_id="session-1",
    )
    prompt = format_task_resource_context_for_prompt(ctx)

    assert "全局工作区资源" in prompt
    assert "/global/shared.md" in prompt
    assert "跨所有工作区共享" in prompt


def test_format_prompt_shows_empty_global_workspace() -> None:
    """全局资源为空时应显示'暂无'。"""
    ctx = build_task_resource_context(user_id="test-user")
    prompt = format_task_resource_context_for_prompt(ctx)

    assert "全局工作区资源：暂无" in prompt


# ---------------------------------------------------------------------------
# Direct reference object count includes global files
# ---------------------------------------------------------------------------


def test_direct_reference_count_includes_global_and_workspace_files(
    tmp_workspace: Path,
    tmp_global_workspace: Path,
) -> None:
    (tmp_global_workspace / "global-file.txt").write_text("g", encoding="utf-8")

    ctx = build_task_resource_context(
        user_id="test-user",
        session_id="session-1",
        attached_files=["/workspace/attached.txt"],
    )

    assert ctx["direct_reference_object_count"] >= 2  # global file + attached file


# ---------------------------------------------------------------------------
# Overflow / ellipsis behavior
# ---------------------------------------------------------------------------


def test_format_prompt_truncates_global_resources_with_ellipsis(
    tmp_global_workspace: Path,
) -> None:
    """全局资源超过 5 个时，应显示省略号并提示搜索。"""
    for i in range(7):
        (tmp_global_workspace / f"file{i}.txt").write_text("x", encoding="utf-8")

    ctx = build_task_resource_context(user_id="test-user")
    prompt = format_task_resource_context_for_prompt(ctx)

    assert "全局工作区资源：共 7 个文件" in prompt
    assert "... 等共 7 个文件" in prompt
    assert "文件较多" in prompt
    assert "按路径搜索" in prompt


def test_format_prompt_truncates_attached_files_with_ellipsis(
    tmp_workspace: Path,
) -> None:
    """附件超过 5 个时，应显示省略号。"""
    attached = [f"/workspace/att{i}.txt" for i in range(8)]

    ctx = build_task_resource_context(
        user_id="test-user",
        attached_files=attached,
    )
    prompt = format_task_resource_context_for_prompt(ctx)

    assert "当前轮附件：" in prompt
    assert "... 等共 8 个附件" in prompt


def test_scan_limit_caps_global_resources(
    tmp_global_workspace: Path,
) -> None:
    """扫描超过 100 个文件时应截断。"""
    for i in range(105):
        (tmp_global_workspace / f"bulk{i:03d}.txt").write_text("x", encoding="utf-8")

    ctx = build_task_resource_context(user_id="test-user")

    assert ctx["global_workspace_resource_count"] == 100
    assert len(ctx["global_workspace_resources"]) == 100
