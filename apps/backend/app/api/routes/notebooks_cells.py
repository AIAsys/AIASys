"""Notebook cell operation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.agents.tools.notebook_utils import (
    ensure_notebook_shape,
    find_cell_index,
    write_notebook,
)
from app.core.auth import require_auth
from app.models.notebook import (
    ClearNotebookOutputsRequest,
    DeleteNotebookCellRequest,
    InsertNotebookCellRequest,
    MoveNotebookCellRequest,
    NotebookDocumentResponse,
    NotebookOutlineResponse,
    NotebookSearchRequest,
    NotebookSearchResponse,
    UpdateNotebookCellRequest,
)
from app.models.user import UserInfo

from .files_utils import (
    _check_user_access,
    _get_notebook_edit_lock_reason,
)
from .notebooks_utils import (
    _build_document_response,
    _build_notebook_outline,
    _load_notebook_for_targets,
    _resolve_move_index,
    _resolve_reference_index,
    _resolve_targets,
    _search_notebook_cells,
    _source_to_cell_input,
)

router = APIRouter()


@router.post("/{user_id}/{session_id}/search-cells", response_model=NotebookSearchResponse)
async def search_notebook_cells(
    user_id: str,
    session_id: str,
    request: NotebookSearchRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    targets = _resolve_targets(user_id, session_id, request.notebook_path)
    notebook = _load_notebook_for_targets(targets)
    matches = _search_notebook_cells(notebook, request)
    return NotebookSearchResponse(
        notebook_path=targets.relative_path.as_posix(),
        query=request.query,
        total_matches=len(matches),
        matches=matches,
    )


@router.get("/{user_id}/{session_id}/outline", response_model=NotebookOutlineResponse)
async def get_notebook_outline(
    user_id: str,
    session_id: str,
    notebook_path: str = Query(...),
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    targets = _resolve_targets(user_id, session_id, notebook_path)
    notebook = _load_notebook_for_targets(targets)
    items = _build_notebook_outline(notebook)
    return NotebookOutlineResponse(
        notebook_path=targets.relative_path.as_posix(),
        items=items,
        total=len(items),
    )


@router.post("/{user_id}/{session_id}/cells/insert", response_model=NotebookDocumentResponse)
async def insert_notebook_cell(
    user_id: str,
    session_id: str,
    request: InsertNotebookCellRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    edit_lock_reason = _get_notebook_edit_lock_reason(user_id, session_id)
    if edit_lock_reason:
        raise HTTPException(status_code=409, detail=edit_lock_reason)

    targets = _resolve_targets(user_id, session_id, request.notebook_path)
    notebook = _load_notebook_for_targets(targets)
    cells = notebook["cells"]
    new_cell = ensure_notebook_shape({"cells": [_source_to_cell_input(request.cell)]})["cells"][0]

    if request.position == "start":
        insert_index = 0
    elif request.position == "end":
        insert_index = len(cells)
    else:
        reference_index = _resolve_reference_index(notebook, request.reference_cell_id)
        if reference_index is None:
            raise HTTPException(status_code=404, detail="插入 cell 时未找到参考 cell。")
        insert_index = reference_index if request.position == "before" else reference_index + 1

    cells.insert(insert_index, new_cell)
    write_notebook(targets.write_path, notebook)
    return _build_document_response(
        user_id=user_id,
        session_id=session_id,
        targets=targets,
        notebook=notebook,
        edit_lock_reason=None,
    )


@router.post("/{user_id}/{session_id}/cells/update", response_model=NotebookDocumentResponse)
async def update_notebook_cell(
    user_id: str,
    session_id: str,
    request: UpdateNotebookCellRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    edit_lock_reason = _get_notebook_edit_lock_reason(user_id, session_id)
    if edit_lock_reason:
        raise HTTPException(status_code=409, detail=edit_lock_reason)

    targets = _resolve_targets(user_id, session_id, request.notebook_path)
    notebook = _load_notebook_for_targets(targets)
    index = find_cell_index(notebook, cell_id=request.cell_id, cell_index=None)
    if index is None:
        raise HTTPException(status_code=404, detail="Cell not found")

    cell = notebook["cells"][index]
    if request.cell_type is not None:
        cell["cell_type"] = request.cell_type
    if request.source is not None:
        cell["source"] = request.source
    if request.metadata is not None:
        cell["metadata"] = dict(request.metadata)
    if cell.get("cell_type") == "code":
        if request.outputs is not None:
            cell["outputs"] = list(request.outputs)
        if request.execution_count is not None:
            cell["execution_count"] = request.execution_count
    else:
        cell.pop("outputs", None)
        cell.pop("execution_count", None)

    notebook = ensure_notebook_shape(notebook)
    write_notebook(targets.write_path, notebook)
    return _build_document_response(
        user_id=user_id,
        session_id=session_id,
        targets=targets,
        notebook=notebook,
        edit_lock_reason=None,
    )


@router.post("/{user_id}/{session_id}/cells/move", response_model=NotebookDocumentResponse)
async def move_notebook_cell(
    user_id: str,
    session_id: str,
    request: MoveNotebookCellRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    edit_lock_reason = _get_notebook_edit_lock_reason(user_id, session_id)
    if edit_lock_reason:
        raise HTTPException(status_code=409, detail=edit_lock_reason)

    targets = _resolve_targets(user_id, session_id, request.notebook_path)
    notebook = _load_notebook_for_targets(targets)
    source_index, target_index = _resolve_move_index(
        notebook=notebook,
        cell_id=request.cell_id,
        direction=request.direction,
        target_index=request.target_index,
    )
    if source_index != target_index:
        cell = notebook["cells"].pop(source_index)
        notebook["cells"].insert(target_index, cell)
        write_notebook(targets.write_path, notebook)

    return _build_document_response(
        user_id=user_id,
        session_id=session_id,
        targets=targets,
        notebook=notebook,
        edit_lock_reason=None,
    )


@router.post("/{user_id}/{session_id}/cells/delete", response_model=NotebookDocumentResponse)
async def delete_notebook_cell(
    user_id: str,
    session_id: str,
    request: DeleteNotebookCellRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    edit_lock_reason = _get_notebook_edit_lock_reason(user_id, session_id)
    if edit_lock_reason:
        raise HTTPException(status_code=409, detail=edit_lock_reason)

    targets = _resolve_targets(user_id, session_id, request.notebook_path)
    notebook = _load_notebook_for_targets(targets)
    index = find_cell_index(notebook, cell_id=request.cell_id, cell_index=None)
    if index is None:
        raise HTTPException(status_code=404, detail="Cell not found")
    notebook["cells"].pop(index)
    write_notebook(targets.write_path, notebook)
    return _build_document_response(
        user_id=user_id,
        session_id=session_id,
        targets=targets,
        notebook=notebook,
        edit_lock_reason=None,
    )


@router.post("/{user_id}/{session_id}/clear-outputs", response_model=NotebookDocumentResponse)
async def clear_notebook_outputs(
    user_id: str,
    session_id: str,
    request: ClearNotebookOutputsRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    edit_lock_reason = _get_notebook_edit_lock_reason(user_id, session_id)
    if edit_lock_reason:
        raise HTTPException(status_code=409, detail=edit_lock_reason)

    targets = _resolve_targets(user_id, session_id, request.notebook_path)
    notebook = _load_notebook_for_targets(targets)
    if request.clear_all:
        target_cells = notebook["cells"]
    else:
        index = find_cell_index(notebook, cell_id=request.cell_id, cell_index=None)
        if index is None:
            raise HTTPException(status_code=404, detail="清空 outputs 时未找到目标 cell。")
        target_cells = [notebook["cells"][index]]

    for cell in target_cells:
        if cell.get("cell_type") != "code":
            continue
        cell["outputs"] = []
        cell["execution_count"] = None

    write_notebook(targets.write_path, notebook)
    return _build_document_response(
        user_id=user_id,
        session_id=session_id,
        targets=targets,
        notebook=notebook,
        edit_lock_reason=None,
    )
