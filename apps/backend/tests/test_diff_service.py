from __future__ import annotations

from pathlib import Path

from app.services.diff_service import DiffService, DiffTooLargeError


def test_compare_text_returns_unified_diff_and_stats() -> None:
    service = DiffService()

    result = service.compare_text(
        "title\nold\n",
        "title\nnew\n",
        left_label="history/notes.md",
        right_label="current/notes.md",
    )

    assert result.status == "modified"
    assert result.can_show_content is True
    assert "--- history/notes.md" in result.unified_diff
    assert "+++ current/notes.md" in result.unified_diff
    assert "-old\n" in result.unified_diff
    assert "+new\n" in result.unified_diff
    assert result.stats.additions == 1
    assert result.stats.deletions == 1


def test_compare_files_skips_binary_content(tmp_path: Path) -> None:
    left = tmp_path / "left.bin"
    right = tmp_path / "right.bin"
    left.write_bytes(b"abc\x00old")
    right.write_bytes(b"abc\x00new")

    result = DiffService().compare_files(left, right)

    assert result.status == "modified"
    assert result.can_show_content is False
    assert result.is_binary is True
    assert result.unified_diff == ""
    assert result.skip_reason == "二进制文件不展示内容差异"


def test_compare_files_skips_large_content(tmp_path: Path) -> None:
    left = tmp_path / "left.txt"
    right = tmp_path / "right.txt"
    left.write_text("old content\n", encoding="utf-8")
    right.write_text("new content\n", encoding="utf-8")

    result = DiffService(max_file_size=4).compare_files(left, right)

    assert result.status == "modified"
    assert result.can_show_content is False
    assert result.is_too_large is True
    assert "超过 4 字节限制" in (result.skip_reason or "")


def test_compare_directories_returns_path_summary(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "same.md").write_text("same\n", encoding="utf-8")
    (right / "same.md").write_text("same\n", encoding="utf-8")
    (left / "deleted.md").write_text("deleted\n", encoding="utf-8")
    (right / "added.md").write_text("added\n", encoding="utf-8")
    (left / "changed.md").write_text("old\n", encoding="utf-8")
    (right / "changed.md").write_text("new\n", encoding="utf-8")

    result = DiffService().compare_directories(left, right)

    assert result.counts["added"] == 1
    assert result.counts["deleted"] == 1
    assert result.counts["modified"] == 1
    assert result.counts["unchanged"] == 1
    assert {entry.path: entry.status for entry in result.files} == {
        "added.md": "added",
        "changed.md": "modified",
        "deleted.md": "deleted",
    }


def test_compare_directories_enforces_file_limit(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "a.md").write_text("a\n", encoding="utf-8")
    (right / "b.md").write_text("b\n", encoding="utf-8")

    try:
        DiffService().compare_directories(left, right, max_files=1)
    except DiffTooLargeError as exc:
        assert "目录文件数量超过限制" in str(exc)
    else:
        raise AssertionError("应限制目录文件数量")


def test_compare_text_block_move_detected_as_modify() -> None:
    """代码块移动场景：移动后原位置删除、新位置新增。"""
    left = "a\nb\nc\nd\n"
    right = "a\nc\nb\nd\n"
    result = DiffService().compare_text(left, right)
    assert result.status == "modified"
    assert result.stats.additions > 0
    assert result.stats.deletions > 0


def test_compare_text_trailing_newline_change() -> None:
    """文件末尾换行符变化。"""
    left = "line1\nline2"
    right = "line1\nline2\n"
    result = DiffService().compare_text(left, right)
    assert result.status == "modified"


def test_compare_text_whitespace_only_change() -> None:
    """纯空白字符变化。"""
    left = "def foo():\n    pass\n"
    right = "def foo():\n  pass\n"
    result = DiffService().compare_text(left, right)
    assert result.status == "modified"
    assert result.stats.additions == 1
    assert result.stats.deletions == 1


def test_compare_text_large_file_tiny_change() -> None:
    """大文件中极小差异。"""
    left = "x\n" * 1000 + "target\n" + "y\n" * 1000
    right = "x\n" * 1000 + "modified\n" + "y\n" * 1000
    result = DiffService().compare_text(left, right)
    assert result.status == "modified"
    assert result.stats.additions >= 1
    assert result.stats.deletions >= 1
    assert result.stats.left_lines == 2001
    assert result.stats.right_lines == 2001


def test_compare_directories_skips_excluded_dirs(tmp_path: Path) -> None:
    """目录对比跳过 .git 和 node_modules。"""
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / ".git" / "config").parent.mkdir(parents=True)
    (left / ".git" / "config").write_text("git\n", encoding="utf-8")
    (left / "node_modules" / "pkg" / "index.js").parent.mkdir(parents=True)
    (left / "node_modules" / "pkg" / "index.js").write_text("js\n", encoding="utf-8")
    (left / "src" / "main.py").parent.mkdir(parents=True)
    (left / "src" / "main.py").write_text("old\n", encoding="utf-8")
    (right / "src" / "main.py").parent.mkdir(parents=True)
    (right / "src" / "main.py").write_text("new\n", encoding="utf-8")

    result = DiffService().compare_directories(left, right)
    paths = {entry.path for entry in result.files}
    assert ".git/config" not in paths
    assert "node_modules/pkg/index.js" not in paths
    assert "src/main.py" in paths
    assert result.counts["modified"] == 1
