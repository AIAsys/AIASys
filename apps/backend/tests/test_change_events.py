"""测试文件历史变更事件聚合。"""

import shutil
import tempfile
from pathlib import Path

from app.services.file_history import FileHistoryService


def _create_test_file(workspace_root: Path, relative_path: str, content: bytes) -> None:
    file_path = workspace_root / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(content)


def test_list_change_events_groups_by_time_window() -> None:
    workspace_root = Path(tempfile.mkdtemp())
    try:
        service = FileHistoryService(max_entries_per_file=100)

        # 创建三个文件
        _create_test_file(workspace_root, "a.txt", b"a1")
        _create_test_file(workspace_root, "b.txt", b"b1")
        _create_test_file(workspace_root, "c.txt", b"c1")

        # 第一批：a 和 b 几乎同时修改
        service.record_file_before_change(
            workspace_root, "a.txt", operation="before_update", source="agent"
        )
        service.record_file_before_change(
            workspace_root, "b.txt", operation="before_update", source="agent"
        )

        # 等待一下，让第二批落在时间窗口外
        import time

        time.sleep(0.5)

        # 第二批：修改 c
        _create_test_file(workspace_root, "c.txt", b"c2")
        service.record_file_before_change(
            workspace_root, "c.txt", operation="before_update", source="user"
        )

        events = service.list_change_events(workspace_root, limit=50, time_window_seconds=0)
        assert len(events) == 3, f"时间窗口为 0 时，每个文件应独立成事件，实际 {len(events)}"

        events = service.list_change_events(workspace_root, limit=50, time_window_seconds=0.2)
        assert len(events) == 2, f"时间窗口为 0.2 秒时，应聚合成 2 个事件，实际 {len(events)}"

        # 按时间倒序，第一个事件应包含 c（最新）
        first_event = events[0]
        assert first_event.source == "user"
        assert len(first_event.files) == 1
        assert first_event.files[0].file_path == "c.txt"

        second_event = events[1]
        assert second_event.source == "agent"
        assert len(second_event.files) == 2
        paths = {f.file_path for f in second_event.files}
        assert paths == {"a.txt", "b.txt"}
    finally:
        shutil.rmtree(workspace_root, ignore_errors=True)


def test_list_change_events_empty() -> None:
    workspace_root = Path(tempfile.mkdtemp())
    try:
        service = FileHistoryService()
        events = service.list_change_events(workspace_root, limit=50)
        assert events == []
    finally:
        shutil.rmtree(workspace_root, ignore_errors=True)
