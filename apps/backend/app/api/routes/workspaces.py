"""
任务工作区与对话主接口
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import require_auth
from app.models.user import UserInfo
from app.services.workspace_registry import get_workspace_registry_service

logger = logging.getLogger(__name__)


def _resolve_workspace_dir(user_id: str, workspace_id: str) -> Path:
    """验证工作区存在并返回其根目录。"""
    service = get_workspace_registry_service()
    try:
        service.get_workspace(user_id, workspace_id, include_conversations=False)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return service.get_workspace_root(user_id, workspace_id)


from app.api.routes.workspace_templates import router as workspace_templates_router
from app.api.routes.workspaces_core import global_experts_router
from app.api.routes.workspaces_core import router as workspaces_core_router
from app.api.routes.workspaces_resources import router as workspaces_resources_router
from app.api.routes.workspaces_runtime import router as workspaces_runtime_router

router = APIRouter(tags=["workspaces"])
router.include_router(global_experts_router)
router.include_router(workspaces_resources_router)
router.include_router(workspaces_runtime_router)
router.include_router(workspaces_core_router)
router.include_router(workspace_templates_router)
# ------------------------------------------------------------------
# File scan (独立文件变动扫描，不依赖 hooks)
# ------------------------------------------------------------------

filescan_router = APIRouter(prefix="/workspaces", tags=["workspaces"])

FILE_SCAN_STATE_RELATIVE_PATH = Path(".aiasys/workspace") / "file-scan-state.json"
MAX_HASH_BYTES = 2 * 1024 * 1024


class WorkspaceFileChange(BaseModel):
    file_path: str
    change_type: Literal["created", "modified", "deleted"]
    size: int | None = None
    mtime_ns: int | None = None


class WorkspaceFileScanResponse(BaseModel):
    workspace_id: str
    scanned_count: int
    changed_count: int
    changes: list[WorkspaceFileChange]


def _should_skip_scanned_path(path: Path, scan_root: Path) -> bool:
    try:
        relative = path.relative_to(scan_root)
    except ValueError:
        return True
    parts = relative.parts
    if not parts:
        return True
    if any(
        part
        in {
            ".git",
            "__pycache__",
            ".ipynb_checkpoints",
            ".aiasys",
        }
        for part in parts
    ):
        return True
    if path.is_symlink():
        return True
    return not path.is_file()


def _build_file_snapshot(workspace_root: Path) -> dict[str, dict]:
    scan_root = workspace_root
    if not scan_root.exists() or not scan_root.is_dir():
        return {}
    snapshot: dict[str, dict] = {}
    for path in sorted(scan_root.rglob("*")):
        if _should_skip_scanned_path(path, scan_root=scan_root):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        fingerprint: dict = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        if stat.st_size <= MAX_HASH_BYTES:
            digest = hashlib.sha256()
            try:
                with path.open("rb") as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        digest.update(chunk)
                fingerprint["sha256"] = digest.hexdigest()
            except OSError:
                continue
        rel_path = path.relative_to(scan_root).as_posix()
        snapshot[rel_path] = fingerprint
    return snapshot


def _diff_file_snapshots(
    previous: dict,
    current: dict,
) -> list[WorkspaceFileChange]:
    changes: list[WorkspaceFileChange] = []
    prev_items = {k: v for k, v in previous.items() if isinstance(v, dict)}
    for file_path in sorted(current):
        curr_fp = current[file_path]
        prev_fp = prev_items.get(file_path)
        if prev_fp is None:
            changes.append(
                WorkspaceFileChange(
                    file_path=file_path,
                    change_type="created",
                    size=curr_fp.get("size"),
                    mtime_ns=curr_fp.get("mtime_ns"),
                )
            )
            continue
        if curr_fp != prev_fp:
            changes.append(
                WorkspaceFileChange(
                    file_path=file_path,
                    change_type="modified",
                    size=curr_fp.get("size"),
                    mtime_ns=curr_fp.get("mtime_ns"),
                )
            )
    for file_path in sorted(set(prev_items) - set(current)):
        fp = prev_items[file_path]
        changes.append(
            WorkspaceFileChange(
                file_path=file_path,
                change_type="deleted",
                size=fp.get("size"),
                mtime_ns=fp.get("mtime_ns"),
            )
        )
    return changes


@filescan_router.post("/{workspace_id}/file-scan", response_model=WorkspaceFileScanResponse)
async def scan_workspace_files(
    workspace_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    workspace_dir = _resolve_workspace_dir(current_user.user_id, workspace_id)
    state_path = workspace_dir / FILE_SCAN_STATE_RELATIVE_PATH
    previous: dict = {}
    if state_path.exists():
        try:
            raw = state_path.read_text(encoding="utf-8").strip()
            if raw:
                previous = json.loads(raw)
                if not isinstance(previous, dict):
                    previous = {}
        except (json.JSONDecodeError, OSError):
            previous = {}

    current = _build_file_snapshot(workspace_dir)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(current, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    changes = _diff_file_snapshots(previous, current)
    return WorkspaceFileScanResponse(
        workspace_id=workspace_id,
        scanned_count=len(current),
        changed_count=len(changes),
        changes=changes,
    )


router.include_router(filescan_router)
