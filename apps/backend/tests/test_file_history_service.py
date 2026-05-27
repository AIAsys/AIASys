from __future__ import annotations

from pathlib import Path

from app.services.file_history import FileHistoryService


def test_file_history_records_diff_restore_and_prunes(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    notes = workspace_root / "notes.md"
    notes.parent.mkdir(parents=True)
    notes.write_text("v1\n", encoding="utf-8")
    service = FileHistoryService(max_entries_per_file=1)

    first = service.record_file_before_change(
        workspace_root,
        "notes.md",
        operation="before_update",
        source="api",
        source_detail="user-a",
    )
    assert first is not None

    notes.write_text("v2\n", encoding="utf-8")
    second = service.record_file_before_change(
        workspace_root,
        "notes.md",
        operation="before_update",
        source="api",
        source_detail="user-a",
    )
    assert second is not None
    assert second.id != first.id

    entries = service.list_entries(workspace_root, "notes.md")
    assert [entry.id for entry in entries] == [second.id]

    notes.write_text("v3\n", encoding="utf-8")
    _, current_exists, diff = service.diff_entry(workspace_root, second.id)
    assert current_exists is True
    assert "-v2\n" in diff
    assert "+v3\n" in diff
    _, diff_result = service.diff_entry_result(workspace_root, second.id)
    assert diff_result.status == "modified"
    assert diff_result.left_text == "v2\n"
    assert diff_result.right_text == "v3\n"

    restored_entry, restored_size = service.restore_entry(
        workspace_root,
        second.id,
        source="api",
        source_detail="user-a",
    )
    assert restored_entry.id == second.id
    assert restored_size == len("v2\n".encode("utf-8"))
    assert notes.read_text(encoding="utf-8") == "v2\n"


def test_file_history_diff_skips_binary_content(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    binary_file = workspace_root / "data.bin"
    binary_file.parent.mkdir(parents=True)
    binary_file.write_bytes(b"old\x00payload")
    service = FileHistoryService()

    entry = service.record_file_before_change(
        workspace_root,
        "data.bin",
        operation="before_update",
        source="api",
    )
    assert entry is not None

    binary_file.write_bytes(b"new\x00payload")
    _, current_exists, diff = service.diff_entry(workspace_root, entry.id)
    _, result = service.diff_entry_result(workspace_root, entry.id)

    assert current_exists is True
    assert diff == ""
    assert result.status == "modified"
    assert result.can_show_content is False
    assert result.is_binary is True


def test_file_history_skips_internal_large_and_moves_entries(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / ".aiasys").mkdir()
    (workspace_root / ".aiasys" / "config.yaml").write_text("secret\n", encoding="utf-8")
    (workspace_root / "large.txt").write_text("too large\n", encoding="utf-8")
    (workspace_root / "docs").mkdir()
    (workspace_root / "docs" / "a.md").write_text("a\n", encoding="utf-8")
    service = FileHistoryService(max_file_size=4)

    internal = service.record_file_before_change(
        workspace_root,
        ".aiasys/config.yaml",
        operation="before_update",
        source="api",
    )
    large = service.record_file_before_change(
        workspace_root,
        "large.txt",
        operation="before_update",
        source="api",
    )
    moved = service.record_tree_before_change(
        workspace_root,
        "docs",
        operation="before_move",
        source="api",
        target_path="archive/docs",
    )
    service.move_entries(workspace_root, "docs", "archive/docs")

    assert internal is None
    assert large is None
    assert len(moved) == 1
    assert service.list_entries(workspace_root, "docs/a.md") == []
    entries = service.list_entries(workspace_root, "archive/docs/a.md")
    assert len(entries) == 1
    assert entries[0].target_path == "archive/docs/a.md"
