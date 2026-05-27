"""Notebook workbench API.

This module re-exports all notebook endpoints and utilities from sub-modules
to keep the unified namespace.
"""

from __future__ import annotations

from fastapi import APIRouter

# Re-export shared imports from files.py so tests can monkeypatch them
from .files import (
    _check_user_access,
    _get_logical_workspace_root,
    _get_notebook_edit_lock_reason,
    _get_work_dir,
    _is_runtime_busy_for_session,
    _iter_visible_workspace_files,
)
from .notebooks_cells import (
    clear_notebook_outputs,
    delete_notebook_cell,
    get_notebook_outline,
    insert_notebook_cell,
    move_notebook_cell,
    search_notebook_cells,
    update_notebook_cell,
)

# Re-export endpoints
from .notebooks_core import (
    create_notebook,
    diff_notebook_scope_versions,
    fork_notebook_to_session,
    get_notebook_document,
    get_notebook_state,
    list_notebooks,
    promote_notebook_to_workspace,
    save_notebook_document,
)
from .notebooks_execution import (
    get_notebook_artifacts,
    get_notebook_execution_records,
    get_notebook_runtime_state,
    get_notebook_variables,
    get_notebook_workbench_snapshot,
    interrupt_notebook_kernel,
    interrupt_notebook_runtime,
    list_notebook_kernels,
    restart_notebook_kernel,
    restart_notebook_runtime,
    run_notebook,
    stop_notebook_kernel,
    stop_notebook_runtime,
)

# Re-export utilities so tests and other consumers can still access them
# from app.api.routes.notebooks directly.
from .notebooks_utils import (
    _append_run_record,
    _bind_notebook_execution_context,
    _build_cell_response,
    _build_document_response,
    _build_error_notebook_output,
    _build_notebook_state,
    _build_run_result_cell,
    _build_runtime_state_response,
    _build_search_snippet,
    _collect_notebook_artifacts,
    _compare_cells,
    _derive_notebook_title,
    _list_notebook_execution_records,
    _load_notebook_for_targets,
    _load_session_runtime_data,
    _output_summaries,
    _resolve_move_index,
    _resolve_reference_index,
    _resolve_targets,
    _search_notebook_cells,
    _source_to_cell_input,
)

# Re-export other imports used by tests


router = APIRouter(prefix="/notebooks", tags=["notebooks"])

# Include sub-routers
from . import notebooks_cells, notebooks_core, notebooks_execution

router.include_router(notebooks_execution.router)
router.include_router(notebooks_core.router)
router.include_router(notebooks_cells.router)
