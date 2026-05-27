from __future__ import annotations

import asyncio
from pathlib import Path

from app.utils.file_utils import scan_directory


def test_scan_directory_shows_dot_dirs_but_skips_internal_dirs(tmp_path: Path) -> None:
    (tmp_path / ".aiasys" / "session").mkdir(parents=True)
    (tmp_path / ".aiasys" / "session" / "wire.jsonl").write_text("{}", encoding="utf-8")
    (tmp_path / ".sessions").mkdir()
    (tmp_path / ".sessions" / "config.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".session-notes").mkdir()
    (tmp_path / ".session-notes" / "note.md").write_text("note", encoding="utf-8")
    (tmp_path / ".vscode").mkdir()
    (tmp_path / ".vscode" / "settings.json").write_text("{}", encoding="utf-8")

    snapshot = asyncio.run(scan_directory(tmp_path))

    assert ".aiasys/session/wire.jsonl" not in snapshot
    assert ".sessions/config.json" in snapshot
    assert ".session-notes/note.md" in snapshot
    assert ".vscode/settings.json" in snapshot
