from __future__ import annotations

import json
from pathlib import Path

import pytest
# ToolError/ToolOk removed, use result.is_error

from app.agents.tools import notebook_runtime_tool as notebook_runtime_module
from app.agents.tools.notebook_runtime_tool import RunNotebookParams, RunNotebook
from app.services.history import (
    SessionExecutionJournal,
    current_session_id,
    current_session_root,
    current_workspace,
)
from app.services.runtime.notebook_activity import get_notebook_session_lock


def _set_context(workspace: Path, session_root: Path, session_id: str):
    return {
        "workspace": current_workspace.set(workspace),
        "session_root": current_session_root.set(session_root),
        "session_id": current_session_id.set(session_id),
    }


def _reset_context(tokens: dict[str, object]) -> None:
    current_session_id.reset(tokens["session_id"])
    current_session_root.reset(tokens["session_root"])
    current_workspace.reset(tokens["workspace"])


@pytest.mark.asyncio
async def test_run_notebook_all_updates_outputs_and_execution_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    session_root = tmp_path / "session"
    notebook_path = workspace / "notebooks" / "demo.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    session_root.mkdir(parents=True, exist_ok=True)
    notebook_path.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "id": "cell-md",
                        "cell_type": "markdown",
                        "source": "# Demo",
                        "metadata": {},
                    },
                    {
                        "id": "cell-code-1",
                        "cell_type": "code",
                        "source": "print(1)",
                        "metadata": {},
                        "outputs": [],
                        "execution_count": None,
                    },
                    {
                        "id": "cell-code-2",
                        "cell_type": "code",
                        "source": "print(2)",
                        "metadata": {},
                        "outputs": [],
                        "execution_count": None,
                    },
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    sequence_state = {"value": 0}

    class FakeLocalIPythonBox:
        def __init__(self):
            self.workspace = None
            self.session_id = None
            self.record_execution = True

        async def execute_notebook_code(self, *, code: str, restart: bool = False):
            _ = (code, restart)
            sequence_state["value"] += 1
            seq = sequence_state["value"]
            return {
                "notebook_outputs": [
                    {"output_type": "stream", "name": "stdout", "text": f"out-{seq}\n"}
                ],
                "stdout_text": f"out-{seq}\n",
                "error_output": None,
            }

    monkeypatch.setattr(
        notebook_runtime_module,
        "LocalIPythonBox",
        FakeLocalIPythonBox,
    )

    tokens = _set_context(workspace, session_root, "session-demo")
    try:
        result = await RunNotebook().invoke(**RunNotebookParams(
                notebook_path="notebooks/demo.ipynb",
                scope="all",
            ).model_dump())
    finally:
        _reset_context(tokens)

    assert not result.is_error
    payload = json.loads(result.output)
    assert payload["status"] == "success"
    assert payload["executed_code_cell_count"] == 2
    assert payload["cells"][0]["status"] == "skipped"
    assert payload["cells"][1]["status"] == "completed"
    assert payload["cells"][2]["status"] == "completed"

    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    assert notebook["cells"][1]["outputs"][0]["text"] == "out-1\n"
    assert notebook["cells"][1]["execution_count"] == 1
    assert notebook["cells"][2]["outputs"][0]["text"] == "out-2\n"
    assert notebook["cells"][2]["execution_count"] == 2


@pytest.mark.asyncio
async def test_run_notebook_stops_on_error_and_persists_error_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    session_root = tmp_path / "session"
    notebook_path = workspace / "notebooks" / "demo.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    session_root.mkdir(parents=True, exist_ok=True)
    notebook_path.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "id": "cell-code-1",
                        "cell_type": "code",
                        "source": "print('ok')",
                        "metadata": {},
                        "outputs": [],
                        "execution_count": None,
                    },
                    {
                        "id": "cell-code-2",
                        "cell_type": "code",
                        "source": "raise ValueError('boom')",
                        "metadata": {},
                        "outputs": [],
                        "execution_count": None,
                    },
                    {
                        "id": "cell-code-3",
                        "cell_type": "code",
                        "source": "print('after')",
                        "metadata": {},
                        "outputs": [],
                        "execution_count": None,
                    },
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    call_count = {"value": 0}

    class FakeLocalIPythonBox:
        def __init__(self):
            self.workspace = None
            self.session_id = None
            self.record_execution = True

        async def execute_notebook_code(self, *, code: str, restart: bool = False):
            _ = (code, restart)
            call_count["value"] += 1
            seq = call_count["value"]
            if seq == 1:
                return {
                    "notebook_outputs": [
                        {"output_type": "stream", "name": "stdout", "text": "ok\n"}
                    ],
                    "stdout_text": "ok\n",
                    "error_output": None,
                }

            return {
                "notebook_outputs": [
                    {
                        "output_type": "error",
                        "name": "ValueError",
                        "text": "ValueError: boom",
                        "traceback": ["ValueError: boom"],
                    }
                ],
                "stdout_text": "",
                "error_output": "ValueError: boom",
            }

    monkeypatch.setattr(
        notebook_runtime_module,
        "LocalIPythonBox",
        FakeLocalIPythonBox,
    )

    tokens = _set_context(workspace, session_root, "session-demo")
    try:
        result = await RunNotebook().invoke(**RunNotebookParams(
                notebook_path="notebooks/demo.ipynb",
                scope="all",
                stop_on_error=True,
            ).model_dump())
    finally:
        _reset_context(tokens)

    assert not result.is_error
    payload = json.loads(result.output)
    assert payload["status"] == "partial_success"
    assert payload["stopped_on_error"] is True
    assert payload["executed_code_cell_count"] == 2

    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    assert notebook["cells"][0]["outputs"][0]["text"] == "ok\n"
    assert notebook["cells"][1]["outputs"][0]["output_type"] == "error"
    assert notebook["cells"][1]["outputs"][0]["text"] == "ValueError: boom"
    assert notebook["cells"][2]["outputs"] == []


@pytest.mark.asyncio
async def test_run_notebook_persists_structured_outputs_without_returning_base64(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    session_root = tmp_path / "session"
    notebook_path = workspace / "notebooks" / "demo.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    session_root.mkdir(parents=True, exist_ok=True)
    notebook_path.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "id": "cell-code-1",
                        "cell_type": "code",
                        "source": "print(1)",
                        "metadata": {},
                        "outputs": [],
                        "execution_count": None,
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    class FakeLocalIPythonBox:
        def __init__(self):
            self.workspace = None
            self.session_id = None
            self.record_execution = True

        async def execute_notebook_code(self, *, code: str, restart: bool = False):
            _ = (code, restart)
            return {
                "notebook_outputs": [
                    {
                        "output_type": "display_data",
                        "data": {"image/png": "ZmFrZQ==", "text/plain": "plot"},
                        "metadata": {},
                    }
                ],
                "stdout_text": "plot",
                "error_output": None,
            }

    monkeypatch.setattr(
        notebook_runtime_module,
        "LocalIPythonBox",
        FakeLocalIPythonBox,
    )

    tokens = _set_context(workspace, session_root, "session-demo")
    try:
        result = await RunNotebook().invoke(**RunNotebookParams(
                notebook_path="notebooks/demo.ipynb",
                scope="all",
            ).model_dump())
    finally:
        _reset_context(tokens)

    assert not result.is_error
    payload = json.loads(result.output)
    assert "ZmFrZQ==" not in result.output
    assert payload["cells"][0]["output_summaries"][0]["has_binary_payload"] is True

    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    assert notebook["cells"][0]["execution_count"] == 1
    assert notebook["cells"][0]["outputs"][0]["data"]["image/png"] == "ZmFrZQ=="

    records = SessionExecutionJournal(session_root, "session-demo").list_records(limit=1)
    assert records[0].origin.tool_name == "RunNotebook"
    assert records[0].origin.target_path == "notebooks/demo.ipynb"


@pytest.mark.asyncio
async def test_run_notebook_respects_existing_notebook_session_lock(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    session_root = tmp_path / "session"
    workspace.mkdir(parents=True, exist_ok=True)
    session_root.mkdir(parents=True, exist_ok=True)

    lock = get_notebook_session_lock("default_user", "session-busy")
    await lock.acquire()
    tokens = _set_context(workspace, session_root, "session-busy")
    try:
        result = await RunNotebook().invoke(**RunNotebookParams(
                notebook_path="notebooks/missing.ipynb",
                scope="all",
            ).model_dump())
    finally:
        _reset_context(tokens)
        lock.release()

    assert result.is_error
    assert result.brief == "notebook busy"
