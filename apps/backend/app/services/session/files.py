"""
文件快照管理 Mixin
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.utils.file_utils import compare_files, scan_directory

logger = logging.getLogger(__name__)


class FileSnapshotMixin:
    """文件快照管理功能"""

    def save_file_snapshot(
        self,
        session_id: str,
        user_id: str,
        tool_name: str,
        files_before: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        保存文件快照

        在工具调用后捕获工作区文件状态，用于后续比较。
        """
        session_dir = self._get_session_dir(session_id, user_id)
        workspace_dir = session_dir / "workspace"

        if not workspace_dir.exists():
            return {"tool": tool_name, "files": []}

        try:
            files_after = scan_directory(workspace_dir)

            if files_before is not None:
                file_changes = compare_files(files_before, files_after)
            else:
                file_changes = [{"name": f["name"], "type": f["type"]} for f in files_after]

            snapshot = {
                "tool": tool_name,
                "files": file_changes,
                "timestamp": datetime.now().isoformat(),
            }

            # 保存快照
            snapshot_path = (
                session_dir / ".aiasys/session" / "snapshots" / f"{datetime.now().timestamp()}.json"
            )
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot_path.write_text(
                json.dumps(snapshot, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            return snapshot
        except Exception as e:
            logger.warning("保存文件快照失败: %s", e)
            return {"tool": tool_name, "files": [], "error": str(e)}

    def get_file_snapshots(self, session_id: str, user_id: str) -> List[Dict[str, Any]]:
        """获取所有文件快照"""
        session_dir = self._get_session_dir(session_id, user_id)
        snapshots_dir = session_dir / ".aiasys/session" / "snapshots"

        if not snapshots_dir.exists():
            return []

        snapshots = []
        for snapshot_file in sorted(snapshots_dir.glob("*.json")):
            try:
                snapshot = json.loads(snapshot_file.read_text(encoding="utf-8"))
                snapshots.append(snapshot)
            except Exception:
                continue

        return snapshots
