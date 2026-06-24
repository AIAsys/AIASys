"""Claw 文件 / workspace 工具 mixin."""

from __future__ import annotations

import logging
import mimetypes
import re
import shutil
from pathlib import Path

from app.models.claw import ClawAttachmentSummary
from app.utils.path_utils import as_system_path

from ._common import (
    _OUTBOUND_AIASYS_FILE_RE,
    _OUTBOUND_MARKDOWN_IMAGE_RE,
    _OUTBOUND_MARKDOWN_LINK_RE,
    _OUTBOUND_WORKSPACE_REF_RE,
    _utcnow_iso,
)

logger = logging.getLogger(__name__)


class ClawWorkspaceMixin:
    def _sanitize_workspace_filename(self, filename: str) -> str:
        candidate = Path(str(filename or "").strip()).name.replace("\x00", "").strip()
        if not candidate or candidate in {".", ".."}:
            candidate = "attachment.bin"
        candidate = re.sub(r"[^\w.\-() \u4e00-\u9fff]+", "_", candidate)
        return candidate or "attachment.bin"

    def _copy_media_into_session_workspace(
        self,
        user_id: str,
        session_id: str,
        *,
        platform: str,
        message_id: str,
        source_path: str,
        media_type: str,
        preferred_name: str | None = None,
        index: int = 0,
    ) -> ClawAttachmentSummary | None:
        source = Path(str(source_path or "").strip())
        if not source.exists() or not source.is_file():
            return None

        safe_name = self._sanitize_workspace_filename(preferred_name or source.name)
        target_dir = self._get_session_claw_inbox_dir(user_id, session_id, platform)
        message_token = re.sub(r"[^\w.-]+", "_", message_id or "message") or "message"
        target_name = f"{message_token}-{index + 1:02d}-{safe_name}"
        target_path = target_dir / target_name
        shutil.copy2(as_system_path(str(source)), as_system_path(str(target_path)))
        relative_path = target_path.relative_to(
            self._get_effective_workspace_root(user_id, session_id)
        ).as_posix()
        return ClawAttachmentSummary(
            display_name=safe_name,
            workspace_path=f"/workspace/{relative_path}",
            media_type=media_type or mimetypes.guess_type(safe_name)[0],
            size_bytes=target_path.stat().st_size,
            imported_to_workspace=True,
            imported_at=_utcnow_iso(),
        )

    def _extract_workspace_paths_from_text(self, text: str) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for pattern in (
            _OUTBOUND_AIASYS_FILE_RE,
            _OUTBOUND_MARKDOWN_IMAGE_RE,
            _OUTBOUND_MARKDOWN_LINK_RE,
            _OUTBOUND_WORKSPACE_REF_RE,
        ):
            for match in pattern.finditer(text):
                path = str(match.groupdict().get("path") or match.group(0) or "").strip()
                path = path.removeprefix("file://")
                if not path.startswith("/workspace/"):
                    continue
                if path in seen:
                    continue
                seen.add(path)
                ordered.append(path)
        return ordered

    def _resolve_workspace_file(
        self, user_id: str, session_id: str, workspace_path: str
    ) -> Path | None:
        normalized = str(workspace_path or "").strip().replace("\\", "/")
        if not normalized.startswith("/workspace/"):
            return None
        relative = Path(normalized.removeprefix("/workspace/"))
        if relative.is_absolute():
            return None
        root = self._get_effective_workspace_root(user_id, session_id).resolve()
        resolved = (root / relative).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            return None
        if not resolved.exists() or not resolved.is_file():
            return None
        return resolved
