"""Memory Organizer 脚本单元测试。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from organize import run_backup, run_diff, run_write
from utils import (
    atomic_write_file,
    backup_file,
    generate_diff_report,
    read_text_file,
    resolve_memory_paths,
)


def test_resolve_memory_paths(tmp_path: Path):
    paths = resolve_memory_paths(tmp_path)
    assert (
        paths["memory"]
        == tmp_path.parent / "global_workspace" / ".aiasys" / ".memory" / "MEMORY.md"
    )
    assert paths["workspace"] == tmp_path / ".aiasys" / "memory" / "workspace_memory.md"


def test_read_text_file_existing(tmp_path: Path):
    f = tmp_path / "test.md"
    f.write_text("# Hello", encoding="utf-8")
    assert read_text_file(f) == "# Hello"


def test_read_text_file_missing():
    assert read_text_file(Path("/nonexistent/file.md")) == ""


def test_atomic_write_file(tmp_path: Path):
    f = tmp_path / "target.md"
    atomic_write_file(f, "content")
    assert f.read_text(encoding="utf-8") == "content"


def test_backup_file(tmp_path: Path):
    f = tmp_path / "test.md"
    f.write_text("original", encoding="utf-8")
    backup = backup_file(f)
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == "original"
    assert "backup-" in backup.name


def test_generate_diff_report():
    original = "line1\nline2\nline3\n"
    new = "line1\nline2 modified\nline3\nline4\n"
    report = generate_diff_report(original, new, "memory")
    assert report["target"] == "memory"
    assert report["size_delta"] == len(new) - len(original)
    assert report["lines_added"] > 0
    assert report["lines_removed"] > 0
    assert "line2 modified" in report["diff"]


def test_run_backup_existing_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIASYS_WORKSPACE_ROOT", str(tmp_path))
    paths = resolve_memory_paths(tmp_path)
    paths["memory"].parent.mkdir(parents=True, exist_ok=True)
    paths["memory"].write_text("# Memory", encoding="utf-8")

    result = run_backup("memory", paths)
    assert result["mode"] == "backup"
    assert result["backup_path"] is not None
    assert Path(result["backup_path"]).exists()


def test_run_backup_missing_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIASYS_WORKSPACE_ROOT", str(tmp_path))
    paths = resolve_memory_paths(tmp_path)
    # 清理可能由其他测试残留的文件
    if paths["memory"].exists():
        paths["memory"].unlink()
    result = run_backup("memory", paths)
    assert result["backup_path"] is None


def test_run_diff(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIASYS_WORKSPACE_ROOT", str(tmp_path))
    paths = resolve_memory_paths(tmp_path)
    paths["memory"].parent.mkdir(parents=True, exist_ok=True)
    paths["memory"].write_text("# Old\nContent", encoding="utf-8")

    new_file = tmp_path / "new.md"
    new_file.write_text("# New\nContent", encoding="utf-8")

    result = run_diff("memory", paths, new_file)
    assert result["mode"] == "diff"
    assert result["lines_added"] > 0
    assert result["lines_removed"] > 0


def test_run_write_actual_change(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIASYS_WORKSPACE_ROOT", str(tmp_path))
    paths = resolve_memory_paths(tmp_path)
    paths["memory"].parent.mkdir(parents=True, exist_ok=True)
    paths["memory"].write_text("# Old\nContent", encoding="utf-8")

    new_file = tmp_path / "new.md"
    new_file.write_text("# New\nContent", encoding="utf-8")

    result = run_write("memory", paths, new_file)
    assert result["mode"] == "write"
    assert result["changed"] is True
    assert paths["memory"].read_text(encoding="utf-8") == "# New\nContent"
    assert result["backup_path"] is not None


def test_run_write_no_change(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIASYS_WORKSPACE_ROOT", str(tmp_path))
    paths = resolve_memory_paths(tmp_path)
    paths["memory"].parent.mkdir(parents=True, exist_ok=True)
    paths["memory"].write_text("# Same", encoding="utf-8")

    new_file = tmp_path / "new.md"
    new_file.write_text("# Same", encoding="utf-8")

    result = run_write("memory", paths, new_file)
    assert result["changed"] is False
