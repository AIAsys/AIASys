"""Notebook core CRUD endpoints."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.agents.tools.notebook_utils import (
    build_text_preview,
    default_notebook,
    ensure_notebook_shape,
    load_notebook,
    normalize_notebook_path,
    source_to_text,
    write_notebook,
)
from app.core.auth import require_auth
from app.models.notebook import (
    CreateNotebookRequest,
    ForkNotebookResponse,
    NotebookDiffCellChangeResponse,
    NotebookDiffResponse,
    NotebookDocumentResponse,
    NotebookListItemResponse,
    NotebookListResponse,
    NotebookPathRequest,
    NotebookPromoteRequest,
    NotebookPromoteResponse,
    NotebookStateResponse,
    SaveNotebookRequest,
)
from app.models.user import UserInfo
from app.services.diff_service import diff_service

from .files import (
    _check_user_access,
    _get_notebook_edit_lock_reason,
    _iter_visible_workspace_files,
)
from .notebooks_utils import (
    _build_document_response,
    _build_notebook_state,
    _compare_cells,
    _derive_notebook_title,
    _load_notebook_for_targets,
    _resolve_targets,
    _source_to_cell_input,
)

router = APIRouter()


@router.get("/{user_id}/{session_id}", response_model=NotebookListResponse)
async def list_notebooks(
    user_id: str,
    session_id: str,
    directory: str | None = Query(default=None),
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)

    normalized_directory: Path | None = None
    if directory:
        try:
            normalized_directory = normalize_notebook_path(
                f"{directory.rstrip('/')}/dummy.ipynb"
            ).parent
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    notebooks: list[NotebookListItemResponse] = []
    for relative_path, file_path in _iter_visible_workspace_files(user_id, session_id):
        if Path(relative_path).suffix.lower() != ".ipynb":
            continue
        if normalized_directory is not None:
            rel_parent = Path(relative_path).parent
            if (
                rel_parent != normalized_directory
                and normalized_directory not in rel_parent.parents
            ):
                continue

        targets = _resolve_targets(user_id, session_id, relative_path)
        try:
            notebook = load_notebook(file_path)
            parse_error = None
        except json.JSONDecodeError as exc:
            notebook = default_notebook()
            parse_error = str(exc)

        cells = list(notebook.get("cells") or [])
        notebooks.append(
            NotebookListItemResponse(
                path=relative_path,
                title=_derive_notebook_title(notebook, Path(relative_path).stem),
                storage_scope="workspace",
                resolved_from="workspace",
                session_file_exists=False,
                workspace_file_exists=targets.workspace_file_path.exists(),
                has_session_override=False,
                modified_at=datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                size=file_path.stat().st_size,
                cell_count=len(cells),
                code_cell_count=sum(1 for cell in cells if cell.get("cell_type") == "code"),
                output_cell_count=sum(1 for cell in cells if list(cell.get("outputs") or [])),
                parse_error=parse_error,
            )
        )

    notebooks.sort(key=lambda item: item.path)
    return NotebookListResponse(
        user_id=user_id,
        session_id=session_id,
        directory=directory,
        notebooks=notebooks,
        total=len(notebooks),
    )


@router.post("/{user_id}/{session_id}", response_model=NotebookDocumentResponse)
async def create_notebook(
    user_id: str,
    session_id: str,
    request: CreateNotebookRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    targets = _resolve_targets(user_id, session_id, request.notebook_path)

    if targets.read_path.exists() and not request.overwrite:
        raise HTTPException(
            status_code=409,
            detail="Notebook already exists, set overwrite=true to replace",
        )

    notebook = default_notebook()
    if request.metadata_patch:
        notebook["metadata"].update(request.metadata_patch)

    if request.initial_cells:
        notebook["cells"] = [_source_to_cell_input(cell) for cell in request.initial_cells]
    elif request.title:
        notebook["cells"] = [
            {
                "cell_type": "markdown",
                "source": f"# {request.title}",
                "metadata": {},
            }
        ]

    write_notebook(targets.write_path, notebook)
    return _build_document_response(
        user_id=user_id,
        session_id=session_id,
        targets=targets,
        notebook=notebook,
        edit_lock_reason=_get_notebook_edit_lock_reason(user_id, session_id),
    )


@router.get("/{user_id}/{session_id}/state", response_model=NotebookStateResponse)
async def get_notebook_state(
    user_id: str,
    session_id: str,
    notebook_path: str = Query(...),
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    targets = _resolve_targets(user_id, session_id, notebook_path)
    return _build_notebook_state(
        user_id=user_id,
        session_id=session_id,
        targets=targets,
        edit_lock_reason=_get_notebook_edit_lock_reason(user_id, session_id),
    )


@router.get(
    "/{user_id}/{session_id}/document/{notebook_path:path}", response_model=NotebookDocumentResponse
)
async def get_notebook_document(
    user_id: str,
    session_id: str,
    notebook_path: str,
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    targets = _resolve_targets(user_id, session_id, notebook_path)
    notebook = _load_notebook_for_targets(targets)
    return _build_document_response(
        user_id=user_id,
        session_id=session_id,
        targets=targets,
        notebook=notebook,
        edit_lock_reason=_get_notebook_edit_lock_reason(user_id, session_id),
    )


@router.put("/{user_id}/{session_id}/document", response_model=NotebookDocumentResponse)
async def save_notebook_document(
    user_id: str,
    session_id: str,
    request: SaveNotebookRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    edit_lock_reason = _get_notebook_edit_lock_reason(user_id, session_id)
    if edit_lock_reason:
        raise HTTPException(status_code=409, detail=edit_lock_reason)

    targets = _resolve_targets(user_id, session_id, request.notebook_path)
    notebook = ensure_notebook_shape(
        {
            "cells": [_source_to_cell_input(cell) for cell in request.cells],
            "metadata": dict(request.metadata),
            "nbformat": 4,
            "nbformat_minor": 5,
        }
    )
    write_notebook(targets.write_path, notebook)
    return _build_document_response(
        user_id=user_id,
        session_id=session_id,
        targets=targets,
        notebook=notebook,
        edit_lock_reason=None,
    )


@router.post("/{user_id}/{session_id}/fork", response_model=ForkNotebookResponse)
async def fork_notebook_to_session(
    user_id: str,
    session_id: str,
    request: NotebookPathRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    targets = _resolve_targets(user_id, session_id, request.notebook_path)
    notebook = _load_notebook_for_targets(targets)

    if not targets.session_file_path:
        raise HTTPException(status_code=400, detail="Cannot fork without a session target")

    # Copy notebook to session path
    write_notebook(targets.write_path, notebook)
    document = _build_document_response(
        user_id=user_id,
        session_id=session_id,
        targets=targets,
        notebook=notebook,
        edit_lock_reason=_get_notebook_edit_lock_reason(user_id, session_id),
    )
    return ForkNotebookResponse(
        notebook_path=document.notebook_path,
        state=document.state,
        document=document,
    )


@router.post("/{user_id}/{session_id}/diff", response_model=NotebookDiffResponse)
async def diff_notebook_scope_versions(
    user_id: str,
    session_id: str,
    request: NotebookPathRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    targets = _resolve_targets(user_id, session_id, request.notebook_path)
    workspace_exists = targets.workspace_file_path.exists()
    session_exists = targets.session_file_path is not None and targets.session_file_path.exists()

    if not session_exists or not workspace_exists:
        return NotebookDiffResponse(
            notebook_path=targets.relative_path.as_posix(),
            session_exists=session_exists,
            workspace_exists=workspace_exists,
            metadata_changed=False,
            changed_cells=[],
            total_changed_cells=0,
        )

    session_nb = load_notebook(targets.session_file_path)
    workspace_nb = load_notebook(targets.workspace_file_path)

    metadata_changed = session_nb.get("metadata") != workspace_nb.get("metadata")

    session_cells = list(session_nb.get("cells", []))
    workspace_cells = list(workspace_nb.get("cells", []))
    ws_by_id = {c.get("id"): c for c in workspace_cells if isinstance(c, dict)}

    changed_cells: list[NotebookDiffCellChangeResponse] = []
    for idx, s_cell in enumerate(session_cells):
        if not isinstance(s_cell, dict):
            continue
        cell_id = str(s_cell.get("id") or "")
        if cell_id not in ws_by_id:
            changed_cells.append(
                NotebookDiffCellChangeResponse(
                    cell_id=cell_id,
                    status="added",
                    cell_index_session=idx,
                    source_preview=source_to_text(s_cell.get("source", "")).strip()[:120],
                )
            )
        else:
            w_cell = ws_by_id[cell_id]
            changed_fields = _compare_cells(s_cell, w_cell)
            if changed_fields:
                session_source = source_to_text(s_cell.get("source", ""))
                workspace_source = source_to_text(w_cell.get("source", ""))
                diff_result = diff_service.compare_text(
                    session_source,
                    workspace_source,
                    left_label="session",
                    right_label="workspace",
                    include_text=False,
                )
                changed_cells.append(
                    NotebookDiffCellChangeResponse(
                        cell_id=cell_id,
                        status="changed",
                        cell_index_session=idx,
                        changed_fields=changed_fields,
                        source_preview=session_source.strip()[:120],
                        unified_diff=diff_result.unified_diff,
                    )
                )
            del ws_by_id[cell_id]

    for cell_id, w_cell in ws_by_id.items():
        changed_cells.append(
            NotebookDiffCellChangeResponse(
                cell_id=cell_id,
                status="removed",
                changed_fields=[],
                source_preview=source_to_text(w_cell.get("source", "")).strip()[:120],
            )
        )

    return NotebookDiffResponse(
        notebook_path=targets.relative_path.as_posix(),
        session_exists=True,
        workspace_exists=True,
        metadata_changed=metadata_changed,
        changed_cells=changed_cells,
        total_changed_cells=len(changed_cells),
    )


@router.post("/{user_id}/{session_id}/promote", response_model=NotebookPromoteResponse)
async def promote_notebook_to_workspace(
    user_id: str,
    session_id: str,
    request: NotebookPromoteRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    edit_lock_reason = _get_notebook_edit_lock_reason(user_id, session_id)
    if edit_lock_reason:
        raise HTTPException(status_code=409, detail=edit_lock_reason)

    targets = _resolve_targets(user_id, session_id, request.notebook_path)
    if not targets.workspace_file_path.exists() and not (
        targets.session_file_path and targets.session_file_path.exists()
    ):
        raise HTTPException(status_code=404, detail="Notebook 不存在。")

    session_exists = targets.session_file_path is not None and targets.session_file_path.exists()

    notebook = load_notebook(targets.read_path)

    if session_exists and request.overwrite:
        # Write session copy to workspace
        write_notebook(targets.workspace_file_path, notebook)

    promoted_from = "session" if session_exists else "workspace"
    document = _build_document_response(
        user_id=user_id,
        session_id=session_id,
        targets=targets,
        notebook=notebook,
        edit_lock_reason=None,
    )
    return NotebookPromoteResponse(
        notebook_path=targets.relative_path.as_posix(),
        promoted_from_scope=promoted_from,
        overwritten_workspace_copy=session_exists and request.overwrite,
        state=document.state,
        document=document,
    )
