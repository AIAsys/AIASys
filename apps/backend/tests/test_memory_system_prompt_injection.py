"""System Prompt Memory Injection 功能测试。

对齐 Codex 实现：将 memory_summary.md 注入到 system prompt 中。
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def _setup_memory_dir(tmp_path: Path, user_id: str, content: str | None) -> Path:
    """创建测试用的 memory 目录结构。

    路径映射：
    tmp_path/{user_id}/ → WORKSPACE_DIR/{user_id}/
    tmp_path/{user_id}/global_workspace/.aiasys/.memory/ → 实际 memory 目录
    """
    global_workspace = tmp_path / user_id / "global_workspace"
    memory_dir = global_workspace / ".aiasys" / ".memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    if content is not None:
        summary_path = memory_dir / "memory_summary.md"
        summary_path.write_text(content, encoding="utf-8")

    return memory_dir


@pytest.fixture
def isolated_workspace(tmp_path: Path):
    """隔离 WORKSPACE_DIR 环境，确保每个测试使用独立的 workspace。"""
    # 保存原始值
    import app.core.config
    original_workspace = app.core.config.WORKSPACE_DIR

    # 设置新的 WORKSPACE_DIR
    app.core.config.WORKSPACE_DIR = tmp_path

    # 清理 resolver 模块缓存，使其重新读取 WORKSPACE_DIR
    if "app.services.memory.resolver" in __import__("sys").modules:
        del __import__("sys").modules["app.services.memory.resolver"]

    yield tmp_path

    # 恢复原始值
    app.core.config.WORKSPACE_DIR = original_workspace


def test_memory_injection_returns_none_when_summary_missing(
    tmp_path: Path, isolated_workspace: Path
) -> None:
    """当 memory_summary.md 不存在时，返回 None。"""
    work_dir = tmp_path / "user123" / "session456"
    work_dir.mkdir(parents=True, exist_ok=True)

    from app.services.agent.mixins.context import build_memory_tool_developer_instructions

    result = build_memory_tool_developer_instructions(work_dir=work_dir)

    assert result is None


def test_memory_injection_returns_none_when_summary_empty(
    tmp_path: Path, isolated_workspace: Path
) -> None:
    """当 memory_summary.md 为空时，返回 None。"""
    work_dir = tmp_path / "user123" / "session456"
    work_dir.mkdir(parents=True, exist_ok=True)

    _setup_memory_dir(tmp_path, "user123", content="   \n  ")

    from app.services.agent.mixins.context import build_memory_tool_developer_instructions

    result = build_memory_tool_developer_instructions(work_dir=work_dir)

    assert result is None


def test_memory_injection_success_with_content(
    tmp_path: Path, isolated_workspace: Path
) -> None:
    """正常场景：读取 memory_summary.md 并格式化为 developer instructions。"""
    work_dir = tmp_path / "user123" / "session456"
    work_dir.mkdir(parents=True, exist_ok=True)

    summary_content = "# Project Context\n\nThis is a test memory summary.\n"
    _setup_memory_dir(tmp_path, "user123", content=summary_content)

    from app.services.agent.mixins.context import build_memory_tool_developer_instructions

    result = build_memory_tool_developer_instructions(work_dir=work_dir)

    assert result is not None
    assert "# Project Context" in result
    assert "This is a test memory summary." in result
    assert "Memory Layout" in result
    assert "Memory Usage Guidelines" in result


def test_memory_injection_respects_max_chars(
    tmp_path: Path, isolated_workspace: Path
) -> None:
    """当内容超过 max_chars 时进行截断。"""
    work_dir = tmp_path / "user123" / "session456"
    work_dir.mkdir(parents=True, exist_ok=True)

    # 创建超过 15000 字符的内容
    long_content = "A" * 16000 + "\n\nEnd of content."
    _setup_memory_dir(tmp_path, "user123", content=long_content)

    from app.services.agent.mixins.context import build_memory_tool_developer_instructions

    result = build_memory_tool_developer_instructions(
        work_dir=work_dir, max_chars=15000
    )

    assert result is not None
    # 截断逻辑会保留最后的换行符并添加提示，所以结果会略超 max_chars
    # 但内存摘要部分（summary_text）应该被截断在 max_chars 附近
    assert "End of content." not in result  # 不应该包含结尾部分
    assert "（memory summary 已截断）" in result or "..." in result


def test_memory_injection_truncates_at_line_boundary(
    tmp_path: Path, isolated_workspace: Path
) -> None:
    """截断时应尽量在换行符处断开，避免截断行。"""
    work_dir = tmp_path / "user123" / "session456"
    work_dir.mkdir(parents=True, exist_ok=True)

    # 内容：前 10000 字符是完整行，之后是更多内容
    long_content = "A" * 10000 + "\n" + "B" * 10000
    _setup_memory_dir(tmp_path, "user123", content=long_content)

    from app.services.agent.mixins.context import build_memory_tool_developer_instructions

    result = build_memory_tool_developer_instructions(
        work_dir=work_dir, max_chars=10001
    )

    assert result is not None
    # 应该在第一个换行符处截断，不会出现 A 和 B 混合
    assert "A" * 10000 in result


def test_memory_injection_handles_exception_gracefully(
    tmp_path: Path, isolated_workspace: Path
) -> None:
    """当读取失败时，应捕获异常并返回 None。"""
    work_dir = tmp_path / "user123" / "session456"
    work_dir.mkdir(parents=True, exist_ok=True)

    _setup_memory_dir(tmp_path, "user123", content="Valid content")

    from app.services.agent.mixins.context import build_memory_tool_developer_instructions

    with patch(
        "app.services.memory.resolver._get_memory_summary_path_if_exists",
        side_effect=RuntimeError("Permission denied"),
    ):
        result = build_memory_tool_developer_instructions(work_dir=work_dir)

    assert result is None


def test_memory_injection_includes_memory_layout_section(
    tmp_path: Path, isolated_workspace: Path
) -> None:
    """结果应包含 Memory Layout 章节，说明文件结构。"""
    work_dir = tmp_path / "user123" / "session456"
    work_dir.mkdir(parents=True, exist_ok=True)

    _setup_memory_dir(tmp_path, "user123", content="# Memory\nSome info.\n")

    from app.services.agent.mixins.context import build_memory_tool_developer_instructions

    result = build_memory_tool_developer_instructions(work_dir=work_dir)

    assert result is not None
    assert "## Memory Layout" in result
    assert "memory_summary.md" in result
    assert "MEMORY.md" in result
    assert "raw_memories.md" in result
    assert "rollout_summaries/" in result
    assert "workspace_memory.md" in result


def test_memory_injection_includes_usage_guidelines(
    tmp_path: Path, isolated_workspace: Path
) -> None:
    """结果应包含 Memory Usage Guidelines 章节。"""
    work_dir = tmp_path / "user123" / "session456"
    work_dir.mkdir(parents=True, exist_ok=True)

    _setup_memory_dir(tmp_path, "user123", content="# Memory\nSome info.\n")

    from app.services.agent.mixins.context import build_memory_tool_developer_instructions

    result = build_memory_tool_developer_instructions(work_dir=work_dir)

    assert result is not None
    assert "Memory Usage Guidelines" in result
    assert "Stop lookup" in result or "don't read everything" in result
    assert "Do NOT modify memory files" in result


def test_memory_injection_delimits_summary_content(
    tmp_path: Path, isolated_workspace: Path
) -> None:
    """memory_summary 内容应被分隔符包围。"""
    work_dir = tmp_path / "user123" / "session456"
    work_dir.mkdir(parents=True, exist_ok=True)

    summary_text = "## Project Decisions\n- Use TypeScript\n- Prefer functional components"
    _setup_memory_dir(tmp_path, "user123", content=summary_text)

    from app.services.agent.mixins.context import build_memory_tool_developer_instructions

    result = build_memory_tool_developer_instructions(work_dir=work_dir)

    assert result is not None
    assert "## Current Memory Summary" in result
    assert "## Project Decisions" in result
