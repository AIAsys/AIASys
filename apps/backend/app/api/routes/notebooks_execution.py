"""Notebook execution and runtime endpoints."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

logger = logging.getLogger(__name__)

from app.agents.tools.local_ipython_box import LocalIPythonBox
from app.agents.tools.notebook_utils import (
    find_cell_index,
    source_to_text,
    write_notebook,
)
from app.core.auth import require_auth
from app.models.notebook import (
    NotebookArtifactsResponse,
    NotebookExecutionRecordsResponse,
    NotebookKernelSummaryResponse,
    NotebookOutlineResponse,
    NotebookPathRequest,
    NotebookRunCellResultResponse,
    NotebookRunResponse,
    NotebookRuntimeControlResponse,
    NotebookRuntimeStateResponse,
    NotebookRuntimeSummaryResponse,
    NotebookStateResponse,
    NotebookVariablesResponse,
    NotebookVariableSummaryResponse,
    NotebookWorkbenchCellStatusResponse,
    NotebookWorkbenchIssueResponse,
    NotebookWorkbenchSnapshotResponse,
    NotebookWorkbenchSummaryResponse,
    RunNotebookRequest,
)
from app.models.user import UserInfo
from app.services.runtime.notebook_activity import get_notebook_lock, get_notebook_session_lock

from .files_utils import (
    _check_user_access,
    _get_logical_workspace_root,
    _get_notebook_edit_lock_reason,
    _get_work_dir,
)
from .notebooks_utils import (
    _append_run_record,
    _bind_notebook_execution_context,
    _build_document_response,
    _build_error_notebook_output,
    _build_notebook_kernel_summaries,
    _build_notebook_outline,
    _build_notebook_state,
    _build_run_result_cell,
    _build_runtime_state_response,
    _build_runtime_summary,
    _collect_notebook_artifacts,
    _list_notebook_execution_records,
    _load_notebook_for_targets,
    _resolve_targets,
)

router = APIRouter()


def _build_workbench_cell_statuses(
    notebook: dict,
    execution_records: list,
) -> list[NotebookWorkbenchCellStatusResponse]:
    latest_record_by_cell_id = {
        record.source_cell_id: record for record in execution_records if record.source_cell_id
    }
    statuses: list[NotebookWorkbenchCellStatusResponse] = []
    for index, cell in enumerate(notebook.get("cells", [])):
        cell_id = str(cell.get("id") or "")
        cell_type = str(cell.get("cell_type") or "code")
        outputs = list(cell.get("outputs") or [])
        has_error_output = any(
            isinstance(output, dict) and output.get("output_type") == "error" for output in outputs
        )
        latest_record = latest_record_by_cell_id.get(cell_id)
        record_status = getattr(latest_record, "status", None)
        if record_status in {"completed", "failed", "skipped"}:
            status = record_status
        elif has_error_output:
            status = "failed"
        elif cell.get("cell_type") == "code" and isinstance(cell.get("execution_count"), int):
            status = "completed"
        elif cell.get("cell_type") == "code":
            status = "not_run"
        else:
            status = "not_run"

        statuses.append(
            NotebookWorkbenchCellStatusResponse(
                cell_id=cell_id,
                cell_index=index,
                cell_type=cell_type,  # type: ignore[arg-type]
                status=status,  # type: ignore[arg-type]
                execution_count=cell.get("execution_count"),
                output_count=len(outputs),
                has_outputs=bool(outputs),
                has_error_output=has_error_output,
                latest_record_id=getattr(latest_record, "record_id", None),
                duration_ms=getattr(latest_record, "duration_ms", None),
                source_preview=source_to_text(cell.get("source", "")).strip()[:120],
            )
        )
    return statuses


async def _build_workbench_variables(
    *,
    user_id: str,
    session_id: str,
    notebook_path: str,
    include_variables: bool,
    issues: list[NotebookWorkbenchIssueResponse],
) -> NotebookVariablesResponse:
    runtime_summary, _ = _build_runtime_summary(user_id, session_id)
    if not include_variables:
        return NotebookVariablesResponse(
            notebook_path=notebook_path,
            runtime_summary=runtime_summary,
            variables=[],
            total=0,
        )

    try:
        workspace_root = _get_logical_workspace_root(user_id, session_id)
        session_root = _get_work_dir(user_id, session_id)
        async with _bind_notebook_execution_context(
            user_id=user_id,
            session_id=session_id,
            workspace_root=workspace_root,
            session_root=session_root,
        ):
            box = LocalIPythonBox()
            box.workspace = workspace_root
            box.notebook_path = notebook_path
            variables = await box.inspect_kernel_variables()
    except Exception as exc:  # pragma: no cover - defensive fallback for runtime adapters
        logger.warning("Failed to read notebook workbench variables: %s", exc)
        issues.append(
            NotebookWorkbenchIssueResponse(
                area="variables",
                detail="Failed to read variables",
            )
        )
        variables = []

    variable_summaries = [
        NotebookVariableSummaryResponse(**item) for item in variables if isinstance(item, dict)
    ]
    return NotebookVariablesResponse(
        notebook_path=notebook_path,
        runtime_summary=runtime_summary,
        variables=variable_summaries,
        total=len(variable_summaries),
    )


@router.get("/{user_id}/{session_id}/workbench", response_model=NotebookWorkbenchSnapshotResponse)
async def get_notebook_workbench_snapshot(
    user_id: str,
    session_id: str,
    notebook_path: str = Query(...),
    include_variables: bool = Query(default=True),
    records_limit: int = Query(default=30, ge=1, le=200),
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    targets = _resolve_targets(user_id, session_id, notebook_path)
    notebook = _load_notebook_for_targets(targets)
    resolved_path = targets.relative_path.as_posix()
    issues: list[NotebookWorkbenchIssueResponse] = []

    document = _build_document_response(
        user_id=user_id,
        session_id=session_id,
        targets=targets,
        notebook=notebook,
        edit_lock_reason=_get_notebook_edit_lock_reason(user_id, session_id),
    )
    runtime_state = _build_runtime_state_response(
        user_id=user_id,
        session_id=session_id,
        notebook_path=resolved_path,
    )
    outline_items = _build_notebook_outline(notebook)
    outline = NotebookOutlineResponse(
        notebook_path=resolved_path,
        items=outline_items,
        total=len(outline_items),
    )
    execution_records_list = _list_notebook_execution_records(
        user_id=user_id,
        session_id=session_id,
        notebook_path=resolved_path,
        notebook=notebook,
        limit=records_limit,
    )
    execution_records = NotebookExecutionRecordsResponse(
        notebook_path=resolved_path,
        records=execution_records_list,
        total=len(execution_records_list),
    )
    artifact_items = _collect_notebook_artifacts(
        notebook=notebook,
        notebook_path=resolved_path,
        execution_records=execution_records_list,
    )
    artifacts = NotebookArtifactsResponse(
        notebook_path=resolved_path,
        artifacts=artifact_items,
        total=len(artifact_items),
    )
    variables = await _build_workbench_variables(
        user_id=user_id,
        session_id=session_id,
        notebook_path=resolved_path,
        include_variables=include_variables,
        issues=issues,
    )
    cell_statuses = _build_workbench_cell_statuses(notebook, execution_records_list)
    cells = list(notebook.get("cells") or [])
    latest_record = execution_records_list[0] if execution_records_list else None
    summary = NotebookWorkbenchSummaryResponse(
        total_cell_count=len(cells),
        code_cell_count=sum(1 for cell in cells if cell.get("cell_type") == "code"),
        markdown_cell_count=sum(1 for cell in cells if cell.get("cell_type") == "markdown"),
        raw_cell_count=sum(1 for cell in cells if cell.get("cell_type") == "raw"),
        executed_code_cell_count=sum(
            1
            for cell in cells
            if cell.get("cell_type") == "code" and isinstance(cell.get("execution_count"), int)
        ),
        output_cell_count=sum(1 for cell in cells if list(cell.get("outputs") or [])),
        error_cell_count=sum(1 for status in cell_statuses if status.has_error_output),
        variable_count=variables.total,
        artifact_count=artifacts.total,
        execution_record_count=execution_records.total,
        latest_execution_status=getattr(latest_record, "status", None),
        latest_execution_record_id=getattr(latest_record, "record_id", None),
        runtime_busy=runtime_state.runtime_busy,
        kernel_active=runtime_state.kernel_active,
    )

    return NotebookWorkbenchSnapshotResponse(
        notebook_path=resolved_path,
        generated_at=datetime.now().isoformat(),
        document=document,
        runtime_state=runtime_state,
        outline=outline,
        variables=variables,
        artifacts=artifacts,
        execution_records=execution_records,
        cell_statuses=cell_statuses,
        summary=summary,
        issues=issues,
    )


@router.get("/{user_id}/kernels", response_model=List[NotebookKernelSummaryResponse])
async def list_notebook_kernels(
    user_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    return _build_notebook_kernel_summaries(user_id)


@router.post("/{user_id}/kernel/interrupt", response_model=NotebookRuntimeControlResponse)
async def interrupt_notebook_kernel(
    user_id: str,
    request: NotebookPathRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    interrupted = LocalIPythonBox.interrupt_kernel(
        notebook_path=request.notebook_path,
        user_id=user_id,
    )
    runtime_summary = NotebookRuntimeSummaryResponse()
    state = NotebookStateResponse(
        notebook_path=request.notebook_path,
        storage_scope="workspace",
        resolved_from="workspace",
        write_target_scope="workspace",
        exists=False,
        runtime_summary=runtime_summary,
    )
    return NotebookRuntimeControlResponse(
        notebook_path=request.notebook_path,
        action="interrupt",
        status="success" if interrupted else "noop",
        detail=(
            "已发送 notebook 中断信号。"
            if interrupted
            else "当前没有活跃 notebook kernel，可跳过中断。"
        ),
        runtime_summary=runtime_summary,
        state=state,
    )


@router.post("/{user_id}/kernel/restart", response_model=NotebookRuntimeControlResponse)
async def restart_notebook_kernel(
    user_id: str,
    request: NotebookPathRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    had_kernel = await LocalIPythonBox.restart_kernel(
        notebook_path=request.notebook_path,
        user_id=user_id,
    )
    runtime_summary = NotebookRuntimeSummaryResponse()
    state = NotebookStateResponse(
        notebook_path=request.notebook_path,
        storage_scope="workspace",
        resolved_from="workspace",
        write_target_scope="workspace",
        exists=False,
        runtime_summary=runtime_summary,
    )
    return NotebookRuntimeControlResponse(
        notebook_path=request.notebook_path,
        action="restart",
        status="success",
        detail=(
            "已重启 notebook kernel。"
            if had_kernel
            else "当前没有旧 kernel，已创建新的 notebook kernel。"
        ),
        runtime_summary=runtime_summary,
        state=state,
    )


@router.post("/{user_id}/kernel/stop", response_model=NotebookRuntimeControlResponse)
async def stop_notebook_kernel(
    user_id: str,
    request: NotebookPathRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    had_kernel = await LocalIPythonBox.stop_kernel(
        notebook_path=request.notebook_path,
        user_id=user_id,
    )
    runtime_summary = NotebookRuntimeSummaryResponse()
    state = NotebookStateResponse(
        notebook_path=request.notebook_path,
        storage_scope="workspace",
        resolved_from="workspace",
        write_target_scope="workspace",
        exists=False,
        runtime_summary=runtime_summary,
    )
    return NotebookRuntimeControlResponse(
        notebook_path=request.notebook_path,
        action="stop",
        status="success" if had_kernel else "noop",
        detail=(
            "已停止 notebook kernel。"
            if had_kernel
            else "当前没有活跃 notebook kernel，可跳过停止。"
        ),
        runtime_summary=runtime_summary,
        state=state,
    )


@router.get("/{user_id}/{session_id}/runtime-state", response_model=NotebookRuntimeStateResponse)
async def get_notebook_runtime_state(
    user_id: str,
    session_id: str,
    notebook_path: str = Query(...),
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    targets = _resolve_targets(user_id, session_id, notebook_path)
    return _build_runtime_state_response(
        user_id=user_id,
        session_id=session_id,
        notebook_path=targets.relative_path.as_posix(),
    )


@router.get("/{user_id}/{session_id}/variables", response_model=NotebookVariablesResponse)
async def get_notebook_variables(
    user_id: str,
    session_id: str,
    notebook_path: str = Query(...),
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    targets = _resolve_targets(user_id, session_id, notebook_path)
    _load_notebook_for_targets(targets)

    workspace_root = _get_logical_workspace_root(user_id, session_id)
    session_root = _get_work_dir(user_id, session_id)
    async with _bind_notebook_execution_context(
        user_id=user_id,
        session_id=session_id,
        workspace_root=workspace_root,
        session_root=session_root,
    ):
        box = LocalIPythonBox()
        box.workspace = workspace_root
        box.notebook_path = notebook_path
        variables = await box.inspect_kernel_variables()

    runtime_summary, _ = _build_runtime_summary(user_id, session_id)
    return NotebookVariablesResponse(
        notebook_path=targets.relative_path.as_posix(),
        runtime_summary=runtime_summary,
        variables=[
            NotebookVariableSummaryResponse(**item) for item in variables if isinstance(item, dict)
        ],
        total=len(variables),
    )


@router.get(
    "/{user_id}/{session_id}/execution-records", response_model=NotebookExecutionRecordsResponse
)
async def get_notebook_execution_records(
    user_id: str,
    session_id: str,
    notebook_path: str = Query(...),
    limit: int = Query(default=20, ge=1, le=200),
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    targets = _resolve_targets(user_id, session_id, notebook_path)
    notebook = _load_notebook_for_targets(targets)
    normalized_limit = limit if isinstance(limit, int) else 20
    records = _list_notebook_execution_records(
        user_id=user_id,
        session_id=session_id,
        notebook_path=targets.relative_path.as_posix(),
        notebook=notebook,
        limit=normalized_limit,
    )
    return NotebookExecutionRecordsResponse(
        notebook_path=targets.relative_path.as_posix(),
        records=records,
        total=len(records),
    )


@router.get("/{user_id}/{session_id}/artifacts", response_model=NotebookArtifactsResponse)
async def get_notebook_artifacts(
    user_id: str,
    session_id: str,
    notebook_path: str = Query(...),
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    targets = _resolve_targets(user_id, session_id, notebook_path)
    notebook = _load_notebook_for_targets(targets)
    records = _list_notebook_execution_records(
        user_id=user_id,
        session_id=session_id,
        notebook_path=targets.relative_path.as_posix(),
        notebook=notebook,
        limit=200,
    )
    artifacts = _collect_notebook_artifacts(
        notebook=notebook,
        notebook_path=targets.relative_path.as_posix(),
        execution_records=records,
    )
    return NotebookArtifactsResponse(
        notebook_path=targets.relative_path.as_posix(),
        artifacts=artifacts,
        total=len(artifacts),
    )


@router.post(
    "/{user_id}/{session_id}/runtime/interrupt", response_model=NotebookRuntimeControlResponse
)
async def interrupt_notebook_runtime(
    user_id: str,
    session_id: str,
    request: NotebookPathRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    targets = _resolve_targets(user_id, session_id, request.notebook_path)
    _load_notebook_for_targets(targets)

    workspace_root = _get_logical_workspace_root(user_id, session_id)
    session_root = _get_work_dir(user_id, session_id)
    async with _bind_notebook_execution_context(
        user_id=user_id,
        session_id=session_id,
        workspace_root=workspace_root,
        session_root=session_root,
    ):
        box = LocalIPythonBox()
        user_identity = box._resolve_user_id()
        interrupted = LocalIPythonBox.interrupt_kernel(
            session_id, request.notebook_path, user_identity
        )

    state = _build_notebook_state(
        user_id=user_id,
        session_id=session_id,
        targets=targets,
        edit_lock_reason=_get_notebook_edit_lock_reason(user_id, session_id),
    )
    runtime_summary, _ = _build_runtime_summary(user_id, session_id)
    return NotebookRuntimeControlResponse(
        notebook_path=targets.relative_path.as_posix(),
        action="interrupt",
        status="success" if interrupted else "noop",
        detail=(
            "已发送 notebook 中断信号。"
            if interrupted
            else "当前没有活跃 notebook kernel，可跳过中断。"
        ),
        runtime_summary=runtime_summary,
        state=state,
    )


@router.post(
    "/{user_id}/{session_id}/runtime/restart", response_model=NotebookRuntimeControlResponse
)
async def restart_notebook_runtime(
    user_id: str,
    session_id: str,
    request: NotebookPathRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    targets = _resolve_targets(user_id, session_id, request.notebook_path)
    _load_notebook_for_targets(targets)

    workspace_root = _get_logical_workspace_root(user_id, session_id)
    session_root = _get_work_dir(user_id, session_id)
    async with _bind_notebook_execution_context(
        user_id=user_id,
        session_id=session_id,
        workspace_root=workspace_root,
        session_root=session_root,
    ):
        box = LocalIPythonBox()
        box.workspace = workspace_root
        box.notebook_path = request.notebook_path
        helper_env = box._resolve_runtime_helper_env()
        user_identity = box._resolve_user_id()
        had_kernel = await LocalIPythonBox.restart_kernel(
            session_id,
            request.notebook_path,
            user_identity,
            cwd=str(workspace_root),
            helper_env=helper_env,
        )

    state = _build_notebook_state(
        user_id=user_id,
        session_id=session_id,
        targets=targets,
        edit_lock_reason=_get_notebook_edit_lock_reason(user_id, session_id),
    )
    runtime_summary, _ = _build_runtime_summary(user_id, session_id)
    return NotebookRuntimeControlResponse(
        notebook_path=targets.relative_path.as_posix(),
        action="restart",
        status="success",
        detail=(
            "已重启 notebook kernel。"
            if had_kernel
            else "当前没有旧 kernel，已创建新的 notebook kernel。"
        ),
        runtime_summary=runtime_summary,
        state=state,
    )


@router.post("/{user_id}/{session_id}/runtime/stop", response_model=NotebookRuntimeControlResponse)
async def stop_notebook_runtime(
    user_id: str,
    session_id: str,
    request: NotebookPathRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    targets = _resolve_targets(user_id, session_id, request.notebook_path)
    _load_notebook_for_targets(targets)

    workspace_root = _get_logical_workspace_root(user_id, session_id)
    session_root = _get_work_dir(user_id, session_id)
    async with _bind_notebook_execution_context(
        user_id=user_id,
        session_id=session_id,
        workspace_root=workspace_root,
        session_root=session_root,
    ):
        box = LocalIPythonBox()
        user_identity = box._resolve_user_id()
        had_kernel = await LocalIPythonBox.stop_kernel(
            session_id, request.notebook_path, user_identity
        )

    state = _build_notebook_state(
        user_id=user_id,
        session_id=session_id,
        targets=targets,
        edit_lock_reason=_get_notebook_edit_lock_reason(user_id, session_id),
    )
    runtime_summary, _ = _build_runtime_summary(user_id, session_id)
    return NotebookRuntimeControlResponse(
        notebook_path=targets.relative_path.as_posix(),
        action="stop",
        status="success" if had_kernel else "noop",
        detail=(
            "已停止 notebook kernel。"
            if had_kernel
            else "当前没有活跃 notebook kernel，可跳过停止。"
        ),
        runtime_summary=runtime_summary,
        state=state,
    )


@router.post("/{user_id}/{session_id}/run", response_model=NotebookRunResponse)
async def run_notebook(
    user_id: str,
    session_id: str,
    request: RunNotebookRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    _check_user_access(current_user, user_id)
    targets = _resolve_targets(user_id, session_id, request.notebook_path)
    notebook = _load_notebook_for_targets(targets)
    selected_indices: list[int]
    if request.scope == "all":
        selected_indices = list(range(len(notebook["cells"])))
    elif request.scope == "cell":
        if not request.cell_id:
            raise HTTPException(status_code=400, detail="scope=cell 时必须提供 cell_id。")
        index = find_cell_index(notebook, cell_id=request.cell_id, cell_index=None)
        if index is None:
            raise HTTPException(status_code=404, detail="未找到要执行的目标 cell。")
        selected_indices = [index]
    else:
        if request.start_index is None or request.end_index is None:
            raise HTTPException(
                status_code=400, detail="scope=range 时必须提供 start_index 和 end_index。"
            )
        selected_indices = list(
            range(
                request.start_index,
                min(request.end_index + 1, len(notebook["cells"])),
            )
        )

    lock = get_notebook_lock(user_id, request.notebook_path)
    session_lock = get_notebook_session_lock(user_id, session_id)
    if lock.locked() or session_lock.locked():
        raise HTTPException(status_code=409, detail="当前会话正在运行 notebook，请稍后重试。")

    workspace_root = _get_logical_workspace_root(user_id, session_id)
    session_root = _get_work_dir(user_id, session_id)
    run_results: list[NotebookRunCellResultResponse] = []
    executed_code_cell_count = 0
    stopped_on_error = False
    stopped_reason: str | None = None

    async with session_lock:
        async with lock:
            async with _bind_notebook_execution_context(
                user_id=user_id,
                session_id=session_id,
                workspace_root=workspace_root,
                session_root=session_root,
            ):
                box = LocalIPythonBox()
                box.workspace = workspace_root
                box.notebook_path = request.notebook_path
                box.record_execution = False

                for index in selected_indices:
                    cell = notebook["cells"][index]
                    if cell.get("cell_type") != "code":
                        run_results.append(
                            _build_run_result_cell(
                                cell,
                                index=index,
                                status="skipped",
                                reason="仅 code cell 会被执行。",
                            )
                        )
                        continue

                    if request.clear_previous_outputs:
                        cell["outputs"] = []
                        cell["execution_count"] = None

                    executed_code_cell_count += 1
                    try:
                        execution = await box.execute_notebook_code(
                            code=source_to_text(cell.get("source", "")),
                            restart=request.restart_runtime and executed_code_cell_count == 1,
                        )
                    except Exception as exc:  # noqa: BLE001
                        error_message = str(exc)
                        sequence = _append_run_record(
                            user_id=user_id,
                            session_id=session_id,
                            notebook_path=targets.relative_path.as_posix(),
                            code=source_to_text(cell.get("source", "")),
                            status="failed",
                            stdout_text="",
                            error_text=error_message,
                        )
                        cell["outputs"] = _build_error_notebook_output(error_message)
                        cell["execution_count"] = sequence
                        run_results.append(
                            _build_run_result_cell(
                                cell,
                                index=index,
                                status="failed",
                                reason=error_message,
                            )
                        )
                        if request.stop_on_error:
                            stopped_on_error = True
                            stopped_reason = error_message
                            break
                        continue

                    stdout_text = str(execution.get("stdout_text") or "")
                    error_output = execution.get("error_output")
                    notebook_outputs = list(execution.get("notebook_outputs") or [])
                    record_status = "failed" if error_output else "completed"
                    sequence = _append_run_record(
                        user_id=user_id,
                        session_id=session_id,
                        notebook_path=targets.relative_path.as_posix(),
                        code=source_to_text(cell.get("source", "")),
                        status=record_status,
                        stdout_text=stdout_text,
                        error_text=str(error_output) if error_output else None,
                    )
                    if notebook_outputs:
                        cell["outputs"] = notebook_outputs
                    elif not error_output:
                        cell["outputs"] = []
                    cell["execution_count"] = sequence

                    if error_output:
                        run_results.append(
                            _build_run_result_cell(
                                cell,
                                index=index,
                                status="failed",
                                reason=str(error_output),
                            )
                        )
                        if request.stop_on_error:
                            stopped_on_error = True
                            stopped_reason = str(error_output)
                            break
                    else:
                        run_results.append(
                            _build_run_result_cell(
                                cell,
                                index=index,
                                status="completed",
                            )
                        )

        write_notebook(targets.write_path, notebook)

    document = _build_document_response(
        user_id=user_id,
        session_id=session_id,
        targets=targets,
        notebook=notebook,
        edit_lock_reason=_get_notebook_edit_lock_reason(user_id, session_id),
    )
    runtime_summary, _ = _build_runtime_summary(user_id, session_id)
    status = "partial_success" if stopped_on_error else "success"
    return NotebookRunResponse(
        notebook_path=targets.relative_path.as_posix(),
        status=status,
        executed_code_cell_count=executed_code_cell_count,
        stopped_on_error=stopped_on_error,
        stopped_reason=stopped_reason,
        runtime_summary=runtime_summary,
        document=document,
        cells=run_results,
    )
