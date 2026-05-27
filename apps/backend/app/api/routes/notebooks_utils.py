"""Notebook API utilities."""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.agents.tools.local_ipython_box import LocalIPythonBox
from app.agents.tools.notebook_utils import (
    build_text_preview,
    ensure_notebook_shape,
    find_cell_index,
    load_notebook,
    resolve_notebook_targets,
    source_to_text,
    summarize_notebook_output,
)
from app.models.notebook import (
    NotebookArtifactSummaryResponse,
    NotebookCellInput,
    NotebookCellResponse,
    NotebookDocumentResponse,
    NotebookExecutionRecordResponse,
    NotebookKernelSummaryResponse,
    NotebookOutlineItemResponse,
    NotebookOutputSummaryResponse,
    NotebookRunCellResultResponse,
    NotebookRuntimeStateResponse,
    NotebookRuntimeSummaryResponse,
    NotebookSearchMatchResponse,
    NotebookSearchRequest,
    NotebookStateResponse,
)
from app.services.history import (
    SessionExecutionJournal,
    current_session_id,
    current_session_root,
    current_user_id,
    current_workspace,
)
from app.services.runtime.notebook_activity import _NOTEBOOK_LOCKS
from app.services.runtime.session_runtime_state import build_session_runtime_summary
from app.services.workspace_registry import get_workspace_registry_service

from .files import (
    _get_logical_workspace_root,
    _get_notebook_edit_lock_reason,
    _get_work_dir,
    _is_runtime_busy_for_session,
)

logger = logging.getLogger(__name__)


def _load_session_runtime_data(
    user_id: str, session_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    session_manager = get_workspace_registry_service().session_manager
    metadata = session_manager.get_session(session_id, user_id)
    execution_summary = session_manager.get_execution_summary(session_id, user_id)
    metadata_dict = metadata.model_dump() if metadata is not None else {}
    return metadata_dict, execution_summary


def _build_runtime_summary(
    user_id: str, session_id: str
) -> tuple[NotebookRuntimeSummaryResponse, dict[str, Any]]:
    metadata, execution_summary = _load_session_runtime_data(user_id, session_id)
    session_dir = _get_work_dir(user_id, session_id)
    runtime_summary = build_session_runtime_summary(
        session_dir=session_dir,
        session_id=session_id,
        user_id=user_id,
        sandbox_mode=metadata.get("sandbox_mode"),
        env_id=metadata.get("env_id"),
        last_runtime_state=execution_summary.get("last_runtime_state"),
        runtime_busy=_is_runtime_busy_for_session(user_id, session_id),
    )
    return NotebookRuntimeSummaryResponse(**runtime_summary), execution_summary


def _source_to_cell_input(source: NotebookCellInput) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": source.cell_id,
        "cell_type": source.cell_type,
        "source": source.source,
        "metadata": dict(source.metadata),
    }
    if source.cell_type == "code":
        payload["outputs"] = list(source.outputs)
        payload["execution_count"] = source.execution_count
    return payload


def _derive_notebook_title(notebook: dict[str, Any], fallback_name: str) -> str:
    for cell in notebook.get("cells", []):
        source = source_to_text(cell.get("source", "")).strip()
        if not source:
            continue
        first_line = source.splitlines()[0].strip()
        if not first_line:
            continue
        if first_line.startswith("#"):
            title = first_line.lstrip("#").strip()
            if title:
                return title
        return first_line[:80]
    return fallback_name


def _output_summaries(outputs: list[dict[str, Any]]) -> list[NotebookOutputSummaryResponse]:
    summaries: list[NotebookOutputSummaryResponse] = []
    for output in outputs:
        if not isinstance(output, dict):
            continue
        summary = summarize_notebook_output(output)
        summaries.append(NotebookOutputSummaryResponse(**summary))
    return summaries


def _build_cell_response(cell: dict[str, Any]) -> NotebookCellResponse:
    outputs = list(cell.get("outputs") or [])
    return NotebookCellResponse(
        cell_id=str(cell.get("id") or ""),
        cell_type=str(cell.get("cell_type") or "code"),
        source=source_to_text(cell.get("source", "")),
        metadata=dict(cell.get("metadata") or {}),
        execution_count=cell.get("execution_count"),
        outputs=outputs,
        output_summaries=_output_summaries(outputs),
    )


def _build_notebook_state(
    *,
    user_id: str,
    session_id: str,
    targets,
    edit_lock_reason: str | None,
) -> NotebookStateResponse:
    runtime_summary, execution_summary = _build_runtime_summary(user_id, session_id)
    workspace_file_exists = targets.workspace_file_path.exists()
    session_file_exists = (
        targets.session_file_path is not None and targets.session_file_path.exists()
    )
    has_session_override = session_file_exists and workspace_file_exists
    can_fork_to_session = workspace_file_exists and not session_file_exists
    will_create_session_copy = not session_file_exists and targets.session_file_path is not None
    is_reading_from_session = (
        targets.session_file_path is not None and targets.read_path == targets.session_file_path
    )
    resolved_from = "session" if is_reading_from_session else "workspace"
    write_target_scope = "session" if targets.session_file_path is not None else "workspace"
    storage_scope = "session" if is_reading_from_session else write_target_scope

    read_path = targets.read_path
    size = read_path.stat().st_size if read_path.exists() else 0
    modified_at = (
        datetime.fromtimestamp(read_path.stat().st_mtime).isoformat()
        if read_path.exists()
        else None
    )
    return NotebookStateResponse(
        notebook_path=targets.relative_path.as_posix(),
        storage_scope=storage_scope,
        resolved_from=resolved_from,
        write_target_scope=write_target_scope,
        session_file_exists=session_file_exists,
        workspace_file_exists=workspace_file_exists,
        has_session_override=has_session_override,
        can_fork_to_session=can_fork_to_session,
        will_create_session_copy=will_create_session_copy,
        writable=edit_lock_reason is None,
        edit_lock_reason=edit_lock_reason,
        exists=read_path.exists(),
        modified_at=modified_at,
        size=size,
        runtime_summary=runtime_summary,
        last_runtime_state=execution_summary.get("last_runtime_state"),
        last_execution_status=execution_summary.get("last_execution_status"),
        last_execution_record_id=execution_summary.get("last_execution_record_id"),
        execution_record_count=int(execution_summary.get("execution_record_count") or 0),
    )


def _build_document_response(
    *,
    user_id: str,
    session_id: str,
    targets,
    notebook: dict[str, Any],
    edit_lock_reason: str | None,
) -> NotebookDocumentResponse:
    notebook = ensure_notebook_shape(notebook)
    state = _build_notebook_state(
        user_id=user_id,
        session_id=session_id,
        targets=targets,
        edit_lock_reason=edit_lock_reason,
    )
    return NotebookDocumentResponse(
        notebook_path=targets.relative_path.as_posix(),
        title=_derive_notebook_title(notebook, targets.relative_path.stem),
        state=state,
        metadata=dict(notebook.get("metadata") or {}),
        nbformat=int(notebook.get("nbformat") or 4),
        nbformat_minor=int(notebook.get("nbformat_minor") or 5),
        cells=[_build_cell_response(cell) for cell in notebook.get("cells", [])],
    )


def _build_search_snippet(text: str, query: str, *, case_sensitive: bool) -> str:
    if not text:
        return ""
    haystack = text if case_sensitive else text.lower()
    needle = query if case_sensitive else query.lower()
    position = haystack.find(needle)
    if position < 0:
        return build_text_preview(text, 180)
    start = max(position - 60, 0)
    end = min(position + len(query) + 120, len(text))
    snippet = text[start:end].strip()
    if start > 0:
        snippet = f"...{snippet}"
    if end < len(text):
        snippet = f"{snippet}..."
    return snippet


def _search_notebook_cells(
    notebook: dict[str, Any],
    request: NotebookSearchRequest,
) -> list[NotebookSearchMatchResponse]:
    matches: list[NotebookSearchMatchResponse] = []
    query = request.query if request.case_sensitive else request.query.lower()

    for index, cell in enumerate(notebook.get("cells", [])):
        cell_type = str(cell.get("cell_type") or "code")
        if request.cell_type and cell_type != request.cell_type:
            continue

        source_text = source_to_text(cell.get("source", ""))
        haystack = source_text if request.case_sensitive else source_text.lower()
        if query not in haystack:
            continue

        matches.append(
            NotebookSearchMatchResponse(
                cell_id=str(cell.get("id") or ""),
                cell_index=index,
                cell_type=cell_type,  # type: ignore[arg-type]
                source_preview=build_text_preview(source_text, 120),
                snippet=_build_search_snippet(
                    source_text,
                    request.query,
                    case_sensitive=request.case_sensitive,
                ),
                matched_fields=["source"],
            )
        )
        if len(matches) >= request.max_results:
            break

    return matches


def _build_notebook_outline(notebook: dict[str, Any]) -> list[NotebookOutlineItemResponse]:
    items: list[NotebookOutlineItemResponse] = []
    for index, cell in enumerate(notebook.get("cells", [])):
        cell_id = str(cell.get("id") or "")
        cell_type = str(cell.get("cell_type") or "code")
        source_text = source_to_text(cell.get("source", ""))
        outputs = list(cell.get("outputs") or [])
        has_error_output = any(
            isinstance(output, dict) and output.get("output_type") == "error" for output in outputs
        )

        if cell_type == "markdown":
            heading_found = False
            for line in source_text.splitlines():
                stripped = line.strip()
                if not stripped.startswith("#"):
                    continue
                level = len(stripped) - len(stripped.lstrip("#"))
                title = stripped[level:].strip() or f"Markdown {index + 1}"
                items.append(
                    NotebookOutlineItemResponse(
                        item_type="heading",
                        cell_id=cell_id,
                        cell_index=index,
                        level=level,
                        title=title,
                        source_preview=build_text_preview(source_text, 120),
                        execution_count=cell.get("execution_count"),
                        has_outputs=bool(outputs),
                        has_error_output=has_error_output,
                    )
                )
                heading_found = True
            if not heading_found and source_text.strip():
                items.append(
                    NotebookOutlineItemResponse(
                        item_type="markdown_cell",
                        cell_id=cell_id,
                        cell_index=index,
                        title=f"Markdown {index + 1}",
                        source_preview=build_text_preview(source_text, 120),
                        execution_count=cell.get("execution_count"),
                        has_outputs=bool(outputs),
                        has_error_output=has_error_output,
                    )
                )
            continue

        if cell_type == "raw":
            items.append(
                NotebookOutlineItemResponse(
                    item_type="raw_cell",
                    cell_id=cell_id,
                    cell_index=index,
                    title=f"Raw {index + 1}",
                    source_preview=build_text_preview(source_text, 120),
                    execution_count=cell.get("execution_count"),
                    has_outputs=bool(outputs),
                    has_error_output=has_error_output,
                )
            )
            continue

        items.append(
            NotebookOutlineItemResponse(
                item_type="code_cell",
                cell_id=cell_id,
                cell_index=index,
                title=f"Code {index + 1}",
                source_preview=build_text_preview(source_text, 120),
                execution_count=cell.get("execution_count"),
                has_outputs=bool(outputs),
                has_error_output=has_error_output,
            )
        )

    return items


def _build_execution_count_cell_map(
    notebook: dict[str, Any],
) -> dict[int, tuple[str, int]]:
    mapping: dict[int, tuple[str, int]] = {}
    for index, cell in enumerate(notebook.get("cells", [])):
        execution_count = cell.get("execution_count")
        if isinstance(execution_count, int):
            mapping[execution_count] = (str(cell.get("id") or ""), index)
    return mapping


def _calculate_duration_ms(started_at: str | None, finished_at: str | None) -> int | None:
    if not started_at or not finished_at:
        return None
    try:
        started = datetime.fromisoformat(started_at)
        finished = datetime.fromisoformat(finished_at)
    except ValueError:
        return None
    return max(int((finished - started).total_seconds() * 1000), 0)


def _list_notebook_execution_records(
    *,
    user_id: str,
    session_id: str,
    notebook_path: str,
    notebook: dict[str, Any],
    limit: int = 50,
) -> list[NotebookExecutionRecordResponse]:
    session_root = _get_work_dir(user_id, session_id)
    journal = SessionExecutionJournal(session_root, session_id)
    execution_map = _build_execution_count_cell_map(notebook)
    records: list[NotebookExecutionRecordResponse] = []

    for record in journal.list_records(limit=max(limit * 4, limit)):
        if record.origin.target_path != notebook_path:
            continue
        source_cell_id = None
        cell_index = None
        if record.sequence in execution_map:
            source_cell_id, cell_index = execution_map[record.sequence]
        records.append(
            NotebookExecutionRecordResponse(
                record_id=record.record_id,
                sequence=record.sequence,
                status=record.status,
                started_at=record.started_at,
                finished_at=record.finished_at,
                duration_ms=_calculate_duration_ms(
                    record.started_at,
                    record.finished_at,
                ),
                source_cell_id=source_cell_id,
                cell_index=cell_index,
                execution_count=record.sequence,
                result_preview_text=record.result_preview.text,
                stdout_ref=record.stdout_ref,
                stderr_ref=record.stderr_ref,
                artifact_refs=list(record.artifact_refs),
                error=record.error,
            )
        )
        if len(records) >= limit:
            break

    return records


def _collect_notebook_artifacts(
    *,
    notebook: dict[str, Any],
    notebook_path: str,
    execution_records: list[NotebookExecutionRecordResponse],
) -> list[NotebookArtifactSummaryResponse]:
    artifacts: list[NotebookArtifactSummaryResponse] = []
    record_by_sequence = {record.sequence: record for record in execution_records}

    for index, cell in enumerate(notebook.get("cells", [])):
        cell_id = str(cell.get("id") or "")
        execution_count = cell.get("execution_count")
        outputs = list(cell.get("outputs") or [])
        for output_index, output in enumerate(outputs):
            if not isinstance(output, dict):
                continue
            if output.get("output_type") not in {"display_data", "execute_result"}:
                continue
            data = output.get("data")
            if not isinstance(data, dict):
                continue
            for mime_type in ("image/png", "image/jpeg", "text/html"):
                if mime_type not in data:
                    continue
                artifact_id = f"inline:{cell_id}:{output_index}:{mime_type}"
                artifacts.append(
                    NotebookArtifactSummaryResponse(
                        artifact_id=artifact_id,
                        artifact_kind="inline_output",
                        display_name=f"Cell {index + 1} output",
                        source_cell_id=cell_id,
                        cell_index=index,
                        execution_count=(
                            execution_count if isinstance(execution_count, int) else None
                        ),
                        record_id=(
                            record_by_sequence.get(execution_count).record_id
                            if isinstance(execution_count, int)
                            and execution_count in record_by_sequence
                            else None
                        ),
                        mime_type=mime_type,
                        inline_available=True,
                    )
                )

    for record in execution_records:
        if record.stdout_ref:
            artifacts.append(
                NotebookArtifactSummaryResponse(
                    artifact_id=f"{record.record_id}:stdout",
                    artifact_kind="stdout_log",
                    display_name=f"{record.record_id} stdout",
                    source_cell_id=record.source_cell_id,
                    cell_index=record.cell_index,
                    execution_count=record.execution_count,
                    record_id=record.record_id,
                    mime_type="text/plain",
                    relative_path=record.stdout_ref,
                )
            )
        if record.stderr_ref:
            artifacts.append(
                NotebookArtifactSummaryResponse(
                    artifact_id=f"{record.record_id}:stderr",
                    artifact_kind="stderr_log",
                    display_name=f"{record.record_id} stderr",
                    source_cell_id=record.source_cell_id,
                    cell_index=record.cell_index,
                    execution_count=record.execution_count,
                    record_id=record.record_id,
                    mime_type="text/plain",
                    relative_path=record.stderr_ref,
                )
            )
        for index, artifact_ref in enumerate(record.artifact_refs):
            artifacts.append(
                NotebookArtifactSummaryResponse(
                    artifact_id=f"{record.record_id}:file:{index}",
                    artifact_kind="file_ref",
                    display_name=Path(artifact_ref).name or artifact_ref,
                    source_cell_id=record.source_cell_id,
                    cell_index=record.cell_index,
                    execution_count=record.execution_count,
                    record_id=record.record_id,
                    relative_path=artifact_ref,
                )
            )

    return artifacts


def _build_notebook_kernel_summaries(user_id: str) -> list[NotebookKernelSummaryResponse]:
    prefix = f"{user_id}_nb:"
    results: list[NotebookKernelSummaryResponse] = []
    now = time.time()

    for key, _km in LocalIPythonBox._kernel_managers.items():
        if not key.startswith(prefix):
            continue
        notebook_path = key[len(prefix) :]
        last_active = LocalIPythonBox._last_activity.get(key, now)
        lock_key = f"{user_id}/{notebook_path}"
        notebook_lock = _NOTEBOOK_LOCKS.get(lock_key)
        is_busy = notebook_lock.locked() if notebook_lock is not None else False

        results.append(
            NotebookKernelSummaryResponse(
                notebook_path=notebook_path,
                kernel_active=True,
                is_busy=is_busy,
                last_active_at=datetime.fromtimestamp(last_active, tz=timezone.utc).isoformat(),
            )
        )

    return sorted(results, key=lambda x: x.last_active_at, reverse=True)


def _build_runtime_state_response(
    *,
    user_id: str,
    session_id: str,
    notebook_path: str,
) -> NotebookRuntimeStateResponse:
    runtime_summary, _ = _build_runtime_summary(user_id, session_id)
    # notebook 级 kernel 状态覆盖 session 级的 kernel_active
    kernel_active = LocalIPythonBox.has_kernel(
        notebook_path=notebook_path,
        user_id=user_id,
    )
    runtime_busy = bool(runtime_summary.runtime_busy)
    return NotebookRuntimeStateResponse(
        notebook_path=notebook_path,
        runtime_summary=runtime_summary,
        runtime_busy=runtime_busy,
        kernel_active=kernel_active,
        can_interrupt=kernel_active,
        can_restart=True,
        can_stop=kernel_active,
        edit_lock_reason=_get_notebook_edit_lock_reason(user_id, session_id),
    )


def _compare_cells(
    session_cell: dict[str, Any],
    workspace_cell: dict[str, Any],
) -> list[str]:
    changed_fields: list[str] = []
    for field in ("cell_type", "source", "metadata", "outputs", "execution_count"):
        if session_cell.get(field) != workspace_cell.get(field):
            changed_fields.append(field)
    return changed_fields


def _resolve_targets(user_id: str, session_id: str, notebook_path: str):
    workspace_root = _get_logical_workspace_root(user_id, session_id)
    session_root = _get_work_dir(user_id, session_id)
    try:
        return resolve_notebook_targets(
            workspace_root=workspace_root,
            notebook_path=notebook_path,
            session_root=session_root,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Operation failed") from exc


def _load_notebook_for_targets(targets) -> dict[str, Any]:
    try:
        return load_notebook(targets.read_path)
    except json.JSONDecodeError as exc:
        logger.error("Notebook JSON parse failed: %s", exc)
        raise HTTPException(status_code=400, detail="Failed to parse notebook JSON") from exc


def _resolve_reference_index(notebook: dict[str, Any], cell_id: str | None) -> int | None:
    if not cell_id:
        return None
    return find_cell_index(notebook, cell_id=cell_id, cell_index=None)


def _resolve_move_index(
    *,
    notebook: dict[str, Any],
    cell_id: str,
    direction: str | None,
    target_index: int | None,
) -> tuple[int, int]:
    source_index = find_cell_index(notebook, cell_id=cell_id, cell_index=None)
    if source_index is None:
        raise HTTPException(status_code=404, detail="Cell not found")

    if target_index is not None:
        return source_index, min(max(target_index, 0), max(len(notebook["cells"]) - 1, 0))

    if direction == "up":
        return source_index, max(source_index - 1, 0)
    if direction == "down":
        return source_index, min(source_index + 1, len(notebook["cells"]) - 1)

    raise HTTPException(status_code=400, detail="移动 cell 时必须提供 direction 或 target_index。")


@asynccontextmanager
async def _bind_notebook_execution_context(
    *,
    user_id: str,
    session_id: str,
    workspace_root: Path,
    session_root: Path,
):
    tokens = {
        "user_id": current_user_id.set(user_id),
        "session_id": current_session_id.set(session_id),
        "workspace": current_workspace.set(workspace_root),
        "session_root": current_session_root.set(session_root),
    }
    try:
        yield
    finally:
        current_session_root.reset(tokens["session_root"])
        current_workspace.reset(tokens["workspace"])
        current_session_id.reset(tokens["session_id"])
        current_user_id.reset(tokens["user_id"])


def _append_run_record(
    *,
    user_id: str,
    session_id: str,
    notebook_path: str,
    code: str,
    status: str,
    stdout_text: str,
    error_text: str | None,
) -> int:
    metadata, _ = _load_session_runtime_data(user_id, session_id)
    session_root = _get_work_dir(user_id, session_id)
    journal = SessionExecutionJournal(session_root, session_id)
    record = journal.append_record(
        code=code,
        started_at=datetime.now().isoformat(),
        finished_at=datetime.now().isoformat(),
        status=status,
        sandbox_mode=metadata.get("sandbox_mode"),
        env_id=metadata.get("env_id"),
        stdout=stdout_text or None,
        stderr=error_text,
        error=error_text,
        result_preview_text=error_text or stdout_text or None,
        origin_source="notebook_workbench",
        tool_name="RunNotebook",
        target_path=notebook_path,
    )
    return record.sequence


def _build_error_notebook_output(message: str) -> list[dict[str, Any]]:
    return [
        {
            "output_type": "error",
            "name": "Error",
            "text": message,
            "traceback": [message],
        }
    ]


def _build_run_result_cell(
    cell: dict[str, Any], *, index: int, status: str, reason: str | None = None
) -> NotebookRunCellResultResponse:
    outputs = list(cell.get("outputs") or [])
    return NotebookRunCellResultResponse(
        index=index,
        cell_id=cell.get("id"),
        cell_type=cell.get("cell_type"),
        status=status,
        reason=reason,
        execution_count=cell.get("execution_count"),
        output_count=len(outputs),
        source_preview=source_to_text(cell.get("source", "")).strip()[:120],
        output_summaries=_output_summaries(outputs),
    )
