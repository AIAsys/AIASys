from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.api.routes import notebooks as notebook_route
from app.api.routes import notebooks_core as notebooks_core_mod
from app.api.routes import notebooks_execution as notebooks_execution_mod
from app.api.routes import notebooks_utils as notebooks_utils_mod
from app.models.notebook import (
    CreateNotebookRequest,
    InsertNotebookCellRequest,
    NotebookCellInput,
    NotebookPathRequest,
    NotebookPromoteRequest,
    NotebookSearchRequest,
    RunNotebookRequest,
    UpdateNotebookCellRequest,
)
from app.models.user import UserInfo
from app.services.history import SessionExecutionJournal
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _build_workspace_service(tmp_path: Path) -> WorkspaceRegistryService:
    return WorkspaceRegistryService(tmp_path, session_manager=SessionManager(tmp_path))


def _create_workspace(service: WorkspaceRegistryService):
    return service.create_workspace(
        user_id="local_default",
        workspace_id="task-notebook",
        title="Notebook Workbench",
        initial_conversation_id="branch-alpha",
        initial_conversation_title="Alpha",
    )


def _patch_notebook_roots(
    monkeypatch: pytest.MonkeyPatch,
    service: WorkspaceRegistryService,
) -> None:
    monkeypatch.setattr(
        notebooks_utils_mod,
        "_get_logical_workspace_root",
        lambda user_id, session_id: service.get_logical_workspace_root(user_id, session_id),
    )
    monkeypatch.setattr(
        notebooks_utils_mod,
        "_get_work_dir",
        lambda user_id, session_id: service.session_manager._get_session_dir(session_id, user_id),
    )


@pytest.mark.asyncio
async def test_get_notebook_document_prefers_workspace_copy_and_reports_session_overlay_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    monkeypatch.setattr(
        notebooks_utils_mod,
        "get_workspace_registry_service",
        lambda: service,
    )
    _patch_notebook_roots(monkeypatch, service)
    _create_workspace(service)

    workspace_root = service.get_logical_workspace_root("local_default", "branch-alpha")
    notebook_path = workspace_root / "research" / "notebooks" / "analysis.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    notebook_path.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "id": "cell-md",
                        "cell_type": "markdown",
                        "source": "# Shared Notebook",
                        "metadata": {},
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

    response = await notebook_route.get_notebook_document(
        "local_default",
        "branch-alpha",
        "research/notebooks/analysis.ipynb",
        current_user=_build_user(),
    )

    assert response.notebook_path == "research/notebooks/analysis.ipynb"
    assert response.state.resolved_from == "workspace"
    assert response.state.write_target_scope == "session"
    assert response.state.can_fork_to_session is True
    assert response.state.session_file_exists is False
    assert response.cells[0].cell_id == "cell-md"


@pytest.mark.asyncio
async def test_insert_and_update_notebook_cell_writes_branch_private_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    monkeypatch.setattr(
        notebooks_utils_mod,
        "get_workspace_registry_service",
        lambda: service,
    )
    _patch_notebook_roots(monkeypatch, service)
    _create_workspace(service)

    create_response = await notebook_route.create_notebook(
        "local_default",
        "branch-alpha",
        CreateNotebookRequest(
            notebook_path="research/notebooks/demo.ipynb",
            title="Demo Notebook",
        ),
        current_user=_build_user(),
    )
    assert create_response.state.storage_scope == "session"

    inserted = await notebook_route.insert_notebook_cell(
        "local_default",
        "branch-alpha",
        InsertNotebookCellRequest(
            notebook_path="research/notebooks/demo.ipynb",
            position="end",
            cell=NotebookCellInput(
                cell_type="code",
                source="print('hello')",
                cell_id="cell-code",
            ),
        ),
        current_user=_build_user(),
    )
    assert len(inserted.cells) == 2
    assert inserted.cells[1].cell_id == "cell-code"

    updated = await notebook_route.update_notebook_cell(
        "local_default",
        "branch-alpha",
        UpdateNotebookCellRequest(
            notebook_path="research/notebooks/demo.ipynb",
            cell_id="cell-code",
            source="print('updated')",
        ),
        current_user=_build_user(),
    )
    assert updated.cells[1].source == "print('updated')"

    session_root = service.session_manager._get_session_dir("branch-alpha", "local_default")
    session_notebook = session_root / "research" / "notebooks" / "demo.ipynb"
    assert session_notebook.exists()
    payload = json.loads(session_notebook.read_text(encoding="utf-8"))
    assert payload["cells"][1]["source"] == "print('updated')"


@pytest.mark.asyncio
async def test_run_notebook_persists_outputs_to_session_copy_and_execution_journal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    monkeypatch.setattr(
        notebooks_utils_mod,
        "get_workspace_registry_service",
        lambda: service,
    )
    _patch_notebook_roots(monkeypatch, service)
    _create_workspace(service)

    workspace_root = service.get_logical_workspace_root("local_default", "branch-alpha")
    notebook_path = workspace_root / "research" / "notebooks" / "run.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    notebook_path.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "id": "cell-code",
                        "cell_type": "code",
                        "source": "print('run')",
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
            self.record_execution = False

        async def execute_notebook_code(self, *, code: str, restart: bool = False):
            _ = (code, restart)
            return {
                "notebook_outputs": [
                    {
                        "output_type": "stream",
                        "name": "stdout",
                        "text": "run\n",
                    }
                ],
                "stdout_text": "run\n",
                "error_output": None,
            }

    monkeypatch.setattr(notebooks_execution_mod, "LocalIPythonBox", FakeLocalIPythonBox)

    response = await notebook_route.run_notebook(
        "local_default",
        "branch-alpha",
        RunNotebookRequest(
            notebook_path="research/notebooks/run.ipynb",
            scope="all",
        ),
        current_user=_build_user(),
    )

    assert response.status == "success"
    assert response.executed_code_cell_count == 1
    assert response.document.cells[0].outputs[0]["text"] == "run\n"
    assert response.document.state.resolved_from == "workspace"

    session_root = service.session_manager._get_session_dir("branch-alpha", "local_default")
    session_notebook = session_root / "research" / "notebooks" / "run.ipynb"
    assert session_notebook.exists()
    payload = json.loads(session_notebook.read_text(encoding="utf-8"))
    assert payload["cells"][0]["outputs"][0]["text"] == "run\n"
    assert payload["cells"][0]["execution_count"] == 1

    journal = SessionExecutionJournal(session_root, "branch-alpha")
    records = journal.list_records(limit=10)
    assert records[-1].origin.tool_name == "RunNotebook"
    assert records[-1].origin.target_path == "research/notebooks/run.ipynb"
    assert records[-1].status == "completed"


@pytest.mark.asyncio
async def test_search_and_outline_routes_return_cell_level_navigation_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    monkeypatch.setattr(notebooks_utils_mod, "get_workspace_registry_service", lambda: service)
    _patch_notebook_roots(monkeypatch, service)
    _create_workspace(service)

    workspace_root = service.get_logical_workspace_root("local_default", "branch-alpha")
    notebook_path = workspace_root / "research" / "notebooks" / "analysis.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    notebook_path.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "id": "cell-md",
                        "cell_type": "markdown",
                        "source": "# Overview\n\n## Findings",
                        "metadata": {},
                    },
                    {
                        "id": "cell-code",
                        "cell_type": "code",
                        "source": "print('needle value')",
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

    search_response = await notebook_route.search_notebook_cells(
        "local_default",
        "branch-alpha",
        NotebookSearchRequest(
            notebook_path="research/notebooks/analysis.ipynb",
            query="needle",
        ),
        current_user=_build_user(),
    )
    assert search_response.total_matches == 1
    assert search_response.matches[0].cell_id == "cell-code"
    assert "needle value" in search_response.matches[0].snippet

    outline_response = await notebook_route.get_notebook_outline(
        "local_default",
        "branch-alpha",
        notebook_path="research/notebooks/analysis.ipynb",
        current_user=_build_user(),
    )
    assert outline_response.total >= 2
    assert outline_response.items[0].item_type == "heading"
    assert outline_response.items[0].title == "Overview"


@pytest.mark.asyncio
async def test_execution_records_and_artifacts_routes_use_notebook_target_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    monkeypatch.setattr(notebooks_utils_mod, "get_workspace_registry_service", lambda: service)
    _patch_notebook_roots(monkeypatch, service)
    _create_workspace(service)

    workspace_root = service.get_logical_workspace_root("local_default", "branch-alpha")
    notebook_path = workspace_root / "research" / "notebooks" / "records.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    notebook_path.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "id": "cell-code",
                        "cell_type": "code",
                        "source": "print('records')",
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
            self.record_execution = False

        async def execute_notebook_code(self, *, code: str, restart: bool = False):
            _ = (code, restart)
            return {
                "notebook_outputs": [
                    {"output_type": "stream", "name": "stdout", "text": "records\n"},
                    {
                        "output_type": "display_data",
                        "data": {"image/png": "ZmFrZQ==", "text/plain": "plot"},
                        "metadata": {},
                    },
                ],
                "stdout_text": "records\n",
                "error_output": None,
            }

    monkeypatch.setattr(notebooks_execution_mod, "LocalIPythonBox", FakeLocalIPythonBox)

    await notebook_route.run_notebook(
        "local_default",
        "branch-alpha",
        RunNotebookRequest(
            notebook_path="research/notebooks/records.ipynb",
            scope="all",
        ),
        current_user=_build_user(),
    )

    records_response = await notebook_route.get_notebook_execution_records(
        "local_default",
        "branch-alpha",
        notebook_path="research/notebooks/records.ipynb",
        current_user=_build_user(),
    )
    assert records_response.total == 1
    assert records_response.records[0].source_cell_id == "cell-code"
    assert records_response.records[0].stdout_ref is not None

    artifacts_response = await notebook_route.get_notebook_artifacts(
        "local_default",
        "branch-alpha",
        notebook_path="research/notebooks/records.ipynb",
        current_user=_build_user(),
    )
    artifact_kinds = {artifact.artifact_kind for artifact in artifacts_response.artifacts}
    assert "stdout_log" in artifact_kinds
    assert "inline_output" in artifact_kinds


@pytest.mark.asyncio
async def test_workbench_snapshot_aggregates_document_runtime_variables_and_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    monkeypatch.setattr(notebooks_utils_mod, "get_workspace_registry_service", lambda: service)
    _patch_notebook_roots(monkeypatch, service)
    _create_workspace(service)

    workspace_root = service.get_logical_workspace_root("local_default", "branch-alpha")
    notebook_path = workspace_root / "notebooks" / "workbench.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    notebook_path.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "id": "cell-title",
                        "cell_type": "markdown",
                        "source": "# 回归验证 Notebook",
                        "metadata": {},
                    },
                    {
                        "id": "cell-code",
                        "cell_type": "code",
                        "source": "summary = {'rows': 3}",
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

    class FakeLocalIPythonBox:
        def __init__(self):
            self.workspace = None
            self.session_id = None
            self.record_execution = False

        async def execute_notebook_code(self, *, code: str, restart: bool = False):
            _ = (code, restart)
            return {
                "notebook_outputs": [
                    {
                        "output_type": "execute_result",
                        "data": {
                            "text/plain": "{'rows': 3}",
                            "text/html": "<table><tr><td>rows</td><td>3</td></tr></table>",
                        },
                        "metadata": {},
                    }
                ],
                "stdout_text": "{'rows': 3}",
                "error_output": None,
            }

        async def inspect_kernel_variables(self):
            return [
                {
                    "name": "summary",
                    "type_name": "dict",
                    "module_name": "builtins",
                    "size": 1,
                    "shape": None,
                    "preview": "{'rows': 3}",
                }
            ]

    monkeypatch.setattr(notebooks_execution_mod, "LocalIPythonBox", FakeLocalIPythonBox)

    await notebook_route.run_notebook(
        "local_default",
        "branch-alpha",
        RunNotebookRequest(
            notebook_path="notebooks/workbench.ipynb",
            scope="cell",
            cell_id="cell-code",
        ),
        current_user=_build_user(),
    )

    snapshot = await notebook_route.get_notebook_workbench_snapshot(
        "local_default",
        "branch-alpha",
        notebook_path="notebooks/workbench.ipynb",
        include_variables=True,
        records_limit=20,
        current_user=_build_user(),
    )

    assert snapshot.document.title == "回归验证 Notebook"
    assert snapshot.runtime_state.notebook_path == "notebooks/workbench.ipynb"
    assert snapshot.summary.total_cell_count == 2
    assert snapshot.summary.code_cell_count == 1
    assert snapshot.summary.executed_code_cell_count == 1
    assert snapshot.summary.variable_count == 1
    assert snapshot.summary.artifact_count >= 2
    assert snapshot.summary.latest_execution_status == "completed"
    assert snapshot.variables.variables[0].name == "summary"
    assert snapshot.outline.total >= 2
    assert snapshot.execution_records.total == 1
    assert snapshot.cell_statuses[1].status == "completed"
    assert snapshot.cell_statuses[1].latest_record_id is not None
    assert snapshot.cell_statuses[1].duration_ms is not None
    assert {artifact.artifact_kind for artifact in snapshot.artifacts.artifacts} >= {
        "inline_output",
        "stdout_log",
    }
    assert snapshot.issues == []


@pytest.mark.asyncio
async def test_diff_promote_and_variables_routes_cover_scope_and_runtime_helpers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    monkeypatch.setattr(notebooks_utils_mod, "get_workspace_registry_service", lambda: service)
    _patch_notebook_roots(monkeypatch, service)
    _create_workspace(service)

    workspace_root = service.get_logical_workspace_root("local_default", "branch-alpha")
    workspace_notebook = workspace_root / "research" / "notebooks" / "shared.ipynb"
    workspace_notebook.parent.mkdir(parents=True, exist_ok=True)
    workspace_notebook.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "id": "cell-shared",
                        "cell_type": "markdown",
                        "source": "# Shared",
                        "metadata": {},
                    }
                ],
                "metadata": {"tag": "workspace"},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    session_root = service.session_manager._get_session_dir("branch-alpha", "local_default")
    session_notebook = session_root / "research" / "notebooks" / "shared.ipynb"
    session_notebook.parent.mkdir(parents=True, exist_ok=True)
    session_notebook.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "id": "cell-shared",
                        "cell_type": "markdown",
                        "source": "# Shared Updated",
                        "metadata": {},
                    },
                    {
                        "id": "cell-private",
                        "cell_type": "code",
                        "source": "value = 42",
                        "metadata": {},
                        "outputs": [],
                        "execution_count": None,
                    },
                ],
                "metadata": {"tag": "session"},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    diff_response = await notebook_route.diff_notebook_scope_versions(
        "local_default",
        "branch-alpha",
        NotebookPathRequest(notebook_path="research/notebooks/shared.ipynb"),
        current_user=_build_user(),
    )
    assert diff_response.session_exists is True
    assert diff_response.workspace_exists is True
    assert diff_response.metadata_changed is True
    assert diff_response.total_changed_cells == 2

    class FakeLocalIPythonBox:
        def __init__(self):
            self.workspace = None
            self.session_id = None

        def _resolve_runtime_helper_env(self):
            return {}

        def _resolve_user_id(self):
            return "local_default"

        async def inspect_kernel_variables(self):
            return [
                {
                    "name": "df",
                    "type_name": "DataFrame",
                    "module_name": "pandas.core.frame",
                    "size": 12,
                    "shape": [3, 4],
                    "preview": "   a  b ...",
                }
            ]

        @classmethod
        async def restart_kernel(cls, session_id, notebook_path, user_id, *, cwd=None, helper_env=None):
            _ = (session_id, notebook_path, user_id, cwd, helper_env)
            return True

    monkeypatch.setattr(notebooks_execution_mod, "LocalIPythonBox", FakeLocalIPythonBox)

    variables_response = await notebook_route.get_notebook_variables(
        "local_default",
        "branch-alpha",
        notebook_path="research/notebooks/shared.ipynb",
        current_user=_build_user(),
    )
    assert variables_response.total == 1
    assert variables_response.variables[0].name == "df"

    runtime_response = await notebook_route.restart_notebook_runtime(
        "local_default",
        "branch-alpha",
        NotebookPathRequest(notebook_path="research/notebooks/shared.ipynb"),
        current_user=_build_user(),
    )
    assert runtime_response.action == "restart"
    assert runtime_response.status == "success"

    promote_response = await notebook_route.promote_notebook_to_workspace(
        "local_default",
        "branch-alpha",
        NotebookPromoteRequest(
            notebook_path="research/notebooks/shared.ipynb",
            overwrite=True,
        ),
        current_user=_build_user(),
    )
    assert promote_response.promoted_from_scope == "session"
    promoted_payload = json.loads(workspace_notebook.read_text(encoding="utf-8"))
    assert promoted_payload["metadata"]["tag"] == "session"
    assert promoted_payload["cells"][0]["source"] == "# Shared Updated"


@pytest.mark.asyncio
async def test_fork_notebook_to_session_creates_private_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    monkeypatch.setattr(
        notebooks_utils_mod,
        "get_workspace_registry_service",
        lambda: service,
    )
    _patch_notebook_roots(monkeypatch, service)
    _create_workspace(service)

    workspace_root = service.get_logical_workspace_root("local_default", "branch-alpha")
    notebook_path = workspace_root / "research" / "notebooks" / "shared.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    notebook_path.write_text("{}", encoding="utf-8")

    response = await notebook_route.fork_notebook_to_session(
        "local_default",
        "branch-alpha",
        NotebookPathRequest(notebook_path="research/notebooks/shared.ipynb"),
        current_user=_build_user(),
    )

    assert response.state.session_file_exists is True
    session_root = service.session_manager._get_session_dir("branch-alpha", "local_default")
    assert (session_root / "research" / "notebooks" / "shared.ipynb").exists()
