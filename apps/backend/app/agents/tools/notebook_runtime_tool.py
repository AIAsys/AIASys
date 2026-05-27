"""
Notebook 执行工具。

目标：
- 让 Agent 以 notebook 语义执行 code cell，而不是自己先读整份 ipynb 再拼代码
- 默认把执行结果安全写回 notebook outputs，避免把大输出/base64 直接塞回模型上下文
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.agents.tools.local_ipython_box import LocalIPythonBox
from app.agents.tools.notebook_utils import (
    find_cell_index,
    load_notebook,
    resolve_notebook_targets,
    resolve_workspace_root_from_context,
    source_to_text,
    summarize_cells,
    write_notebook,
)
from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.history import (
    SessionExecutionJournal,
    current_agent_config_snapshot,
    current_env_id,
    current_session_id,
    current_session_root,
    current_user_id,
)
from app.services.runtime.notebook_activity import get_notebook_lock, get_notebook_session_lock


class NotebookRunScope(str, Enum):
    CELL = "cell"
    RANGE = "range"
    ALL = "all"


class RunNotebookParams(BaseModel):
    notebook_path: str = Field(description="逻辑工作区中的 notebook 相对路径，仅允许 .ipynb 文件")
    scope: NotebookRunScope = Field(
        default=NotebookRunScope.ALL,
        description="执行范围：cell / range / all",
    )
    cell_id: str | None = Field(
        default=None,
        description="scope=cell 时的目标 cell id，优先于 cell_index",
    )
    cell_index: int | None = Field(
        default=None,
        description="scope=cell 时的目标 cell 下标",
    )
    start_index: int | None = Field(
        default=None,
        description="scope=range 时起始 cell 下标（含）",
    )
    end_index: int | None = Field(
        default=None,
        description="scope=range 时结束 cell 下标（含）",
    )
    restart_runtime: bool = Field(
        default=False,
        description="执行前是否重启当前会话 runtime",
    )
    clear_previous_outputs: bool = Field(
        default=True,
        description="执行前是否清空目标 code cell 旧 outputs",
    )
    stop_on_error: bool = Field(
        default=True,
        description="遇到失败后是否停止后续 cell",
    )
    persist_outputs: bool = Field(
        default=True,
        description="执行后是否把输出写回 notebook",
    )


def _resolve_selected_indices(
    notebook: dict[str, Any],
    params: RunNotebookParams,
) -> list[int]:
    cells = notebook["cells"]
    if params.scope == NotebookRunScope.ALL:
        return list(range(len(cells)))

    if params.scope == NotebookRunScope.CELL:
        target_index = find_cell_index(
            notebook,
            cell_id=params.cell_id,
            cell_index=params.cell_index,
        )
        if target_index is None:
            raise ValueError("未找到要执行的目标 cell。")
        return [target_index]

    if params.start_index is None or params.end_index is None:
        raise ValueError("scope=range 时必须提供 start_index 和 end_index。")
    if params.start_index < 0 or params.end_index < params.start_index:
        raise ValueError("range 范围无效。")
    if params.start_index >= len(cells):
        raise ValueError("start_index 超出 notebook cell 范围。")
    return list(range(params.start_index, min(params.end_index + 1, len(cells))))


def _build_success_outputs(output_text: str) -> tuple[list[dict[str, Any]], str | None]:
    normalized = (output_text or "").strip()
    if not normalized or normalized == "(代码执行成功，无输出)":
        return [], None
    return [
        {
            "output_type": "stream",
            "name": "stdout",
            "text": output_text,
        }
    ], normalized


def _build_error_outputs(
    message: str, stdout_text: str | None = None
) -> tuple[list[dict[str, Any]], str]:
    traceback_lines = [message]
    if stdout_text and stdout_text.strip():
        traceback_lines = [stdout_text.strip(), message]
    return (
        [
            {
                "output_type": "error",
                "name": "Error",
                "text": message,
                "traceback": traceback_lines,
            }
        ],
        message,
    )


def _build_run_result_entry(
    *,
    index: int,
    cell: dict[str, Any],
    status: str,
    reason: str | None = None,
) -> dict[str, Any]:
    entry = summarize_cells([cell], start_index=0)[0]
    entry["index"] = index
    entry["status"] = status
    if reason:
        entry["reason"] = reason
    return entry


def _append_notebook_run_record(
    *,
    session_root: Path,
    session_id: str,
    notebook_path: str,
    code: str,
    status: str,
    stdout_text: str,
    error_text: str | None,
    started_at: str,
) -> int:
    journal = SessionExecutionJournal(session_root, session_id)
    finished_at = datetime.now().isoformat()
    record = journal.append_record(
        code=code,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        sandbox_mode="local",
        env_id=current_env_id.get(),
        stdout=stdout_text or None,
        stderr=error_text,
        error=error_text,
        result_preview_text=error_text or stdout_text or None,
        origin_source="notebook_agent_tool",
        tool_name="RunNotebook",
        target_path=notebook_path,
        agent_config_snapshot=current_agent_config_snapshot.get(),
    )
    return record.sequence


class RunNotebook(AiasysTool):
    name: str = "RunNotebook"
    description: str = """按 notebook 语义执行当前逻辑工作区中的 `.ipynb` 文件。

适用场景：
- 执行某个 code cell
- 执行一段 cell 范围
- 执行整个 notebook 中的 code cell

特点：
- 每个 notebook 使用独立的 IPython kernel，变量状态按 notebook 隔离
- 默认把安全输出写回 notebook，不直接写入 base64 图像
- 默认只返回执行摘要，避免上下文爆炸
"""
    params: type[BaseModel] = RunNotebookParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = RunNotebookParams.model_validate(kwargs)

        workspace_root = resolve_workspace_root_from_context()
        if workspace_root is None:
            return ToolResult(
                content="当前缺少逻辑工作区上下文，无法执行 notebook。",
                is_error=True,
            )

        session_id = current_session_id.get()
        session_root = current_session_root.get()
        if not session_id or not session_root:
            return ToolResult(
                content="当前缺少 session 上下文，无法执行 notebook。",
                is_error=True,
            )

        user_id = current_user_id.get() or "default_user"
        lock = get_notebook_lock(user_id, params.notebook_path)
        session_lock = get_notebook_session_lock(user_id, session_id)
        if lock.locked() or session_lock.locked():
            return ToolResult(
                content="notebook busy",
                is_error=True,
            )

        async with session_lock:
            async with lock:
                return await self._run_with_lock(
                    params=params,
                    workspace_root=workspace_root,
                    session_root=Path(session_root),
                    session_id=session_id,
                )

    async def _run_with_lock(
        self,
        *,
        params: RunNotebookParams,
        workspace_root: Path,
        session_root: Path,
        session_id: str,
    ) -> ToolResult:
        try:
            targets = resolve_notebook_targets(
                workspace_root=workspace_root,
                notebook_path=params.notebook_path,
            )
        except ValueError as exc:
            return ToolResult(
                content=str(exc),
                is_error=True,
            )

        workspace_root_resolved = workspace_root.resolve()
        file_path = targets.read_path

        try:
            notebook = load_notebook(file_path)
        except json.JSONDecodeError as exc:
            return ToolResult(
                content=f"Notebook JSON 无法解析: {exc}",
                is_error=True,
            )

        if not file_path.exists():
            return ToolResult(
                content=f"Notebook 文件不存在: {targets.relative_path.as_posix()}",
                is_error=True,
            )

        try:
            selected_indices = _resolve_selected_indices(notebook, params)
        except ValueError as exc:
            return ToolResult(
                content=str(exc),
                is_error=True,
            )

        box = LocalIPythonBox()
        box.workspace = workspace_root_resolved
        box.session_id = session_id
        box.notebook_path = params.notebook_path
        box.record_execution = False

        executed_code_cells = 0
        run_results: list[dict[str, Any]] = []
        stopped_on_error = False
        stopped_reason: str | None = None
        latest_error: str | None = None

        for index in selected_indices:
            cell = notebook["cells"][index]
            if cell.get("cell_type") != "code":
                run_results.append(
                    _build_run_result_entry(
                        index=index,
                        cell=cell,
                        status="skipped",
                        reason="仅 code cell 会被执行。",
                    )
                )
                continue

            if params.clear_previous_outputs:
                cell["outputs"] = []
                cell["execution_count"] = None

            code = source_to_text(cell.get("source", ""))
            started_at = datetime.now().isoformat()
            executed_code_cells += 1
            try:
                execution = await box.execute_notebook_code(
                    code=code,
                    restart=params.restart_runtime and executed_code_cells == 1,
                )
            except Exception as exc:  # noqa: BLE001
                preview_text = str(exc)
                execution_sequence = _append_notebook_run_record(
                    session_root=session_root,
                    session_id=session_id,
                    notebook_path=targets.relative_path.as_posix(),
                    code=code,
                    status="failed",
                    stdout_text="",
                    error_text=preview_text,
                    started_at=started_at,
                )
                output_payload, _ = _build_error_outputs(message=preview_text)
                if params.persist_outputs:
                    cell["outputs"] = output_payload
                    cell["execution_count"] = execution_sequence
                latest_error = preview_text
                run_results.append(
                    _build_run_result_entry(
                        index=index,
                        cell=cell,
                        status="failed",
                        reason=preview_text,
                    )
                )
                if params.stop_on_error:
                    stopped_on_error = True
                    stopped_reason = preview_text
                    break
                continue

            result_output = str(execution.get("stdout_text") or "")
            error_message = execution.get("error_output")
            output_payload = list(execution.get("notebook_outputs") or [])
            execution_sequence = _append_notebook_run_record(
                session_root=session_root,
                session_id=session_id,
                notebook_path=targets.relative_path.as_posix(),
                code=code,
                status="failed" if error_message else "completed",
                stdout_text=result_output,
                error_text=str(error_message) if error_message else None,
                started_at=started_at,
            )

            if error_message:
                preview_text = str(error_message)
                if not output_payload:
                    output_payload, _ = _build_error_outputs(
                        message=preview_text,
                        stdout_text=result_output,
                    )
                if params.persist_outputs:
                    cell["outputs"] = output_payload
                    cell["execution_count"] = execution_sequence
                latest_error = preview_text
                run_results.append(
                    _build_run_result_entry(
                        index=index,
                        cell=cell,
                        status="failed",
                        reason=preview_text,
                    )
                )
                if params.stop_on_error:
                    stopped_on_error = True
                    stopped_reason = preview_text
                    break
                continue

            preview_text = result_output.strip() or None
            if not output_payload:
                output_payload, preview_text = _build_success_outputs(result_output)
            if params.persist_outputs:
                cell["outputs"] = output_payload
                cell["execution_count"] = execution_sequence
            run_results.append(
                _build_run_result_entry(
                    index=index,
                    cell=cell,
                    status="completed",
                    reason=preview_text,
                )
            )

        if params.persist_outputs:
            serialized = write_notebook(targets.write_path, notebook)
            notebook_size = len(serialized.encode("utf-8"))
        else:
            notebook_size = file_path.stat().st_size

        status = "success"
        if latest_error and executed_code_cells == 1 and params.stop_on_error:
            status = "failed"
        elif latest_error:
            status = "partial_success"

        return ToolResult(
            content=json.dumps(
                {
                    "status": status,
                    "operation": "run",
                    "notebook_path": targets.relative_path.as_posix(),
                    "workspace_root": str(workspace_root_resolved),
                    "storage_scope": "workspace",
                    "resolved_from": "workspace",
                    "written_to": "workspace",
                    "scope": params.scope.value,
                    "selected_cell_count": len(selected_indices),
                    "executed_code_cell_count": executed_code_cells,
                    "stopped_on_error": stopped_on_error,
                    "stopped_reason": stopped_reason,
                    "persist_outputs": params.persist_outputs,
                    "size": notebook_size,
                    "cells": run_results,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
