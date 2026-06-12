"""
测试本地文件夹导入服务。
"""

from pathlib import Path

import pytest

from app.services.folder_import import copy_selected_files, scan_folder


@pytest.fixture
def sample_folder(tmp_path: Path):
    root = tmp_path / "sample"
    root.mkdir()
    (root / "main.py").write_text("print('hello')")
    (root / "README.md").write_text("# readme")
    (root / ".env").write_text("SECRET=1")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("git config")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "foo.js").write_text("// foo")
    return root


def test_scan_folder_excludes_defaults(sample_folder: Path):
    preview = scan_folder(sample_folder)
    paths = {f.relative_path for f in preview.files if not f.is_directory}
    assert "main.py" in paths
    assert "README.md" in paths
    assert ".env" not in preview.default_selected_files
    assert ".git/config" not in preview.default_selected_files
    assert "node_modules/foo.js" not in preview.default_selected_files
    assert "main.py" in preview.default_selected_files


def test_copy_selected_files(sample_folder: Path, tmp_path: Path):
    target = tmp_path / "target"
    copied, bytes_copied = copy_selected_files(
        sample_folder,
        target,
        ["main.py", "README.md"],
    )
    assert copied == 2
    assert (target / "main.py").exists()
    assert (target / "README.md").exists()
    assert not (target / ".env").exists()


def test_copy_selected_files_progress_callback(sample_folder: Path, tmp_path: Path):
    target = tmp_path / "target"
    progress_log = []

    def callback(progress: int, message: str) -> None:
        progress_log.append((progress, message))

    copy_selected_files(
        sample_folder,
        target,
        ["main.py", "README.md"],
        progress_callback=callback,
    )
    assert len(progress_log) > 0
    assert any(p == 90 for p, _ in progress_log)
