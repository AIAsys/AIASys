"""Notebook workbench API.

This module re-exports all notebook endpoints and utilities from sub-modules
to keep the unified namespace.
"""

from __future__ import annotations

from fastapi import APIRouter

# Re-export shared imports from files.py so tests can monkeypatch them
# Re-export endpoints
from .notebooks_cells import (  # noqa: E402, F401
    clear_notebook_outputs,
    delete_notebook_cell,
    get_notebook_outline,
    insert_notebook_cell,
    move_notebook_cell,
    search_notebook_cells,
    update_notebook_cell,
)
from .notebooks_core import (  # noqa: E402, F401
    create_notebook,
    diff_notebook_scope_versions,
    fork_notebook_to_session,
    get_notebook_document,
    get_notebook_state,
    list_notebooks,
    promote_notebook_to_workspace,
    save_notebook_document,
)
from .notebooks_execution import (  # noqa: E402, F401
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

# Re-export other imports used by tests


router = APIRouter(prefix="/notebooks", tags=["notebooks"])

# Include sub-routers
from . import notebooks_cells, notebooks_core, notebooks_execution

router.include_router(notebooks_execution.router)
router.include_router(notebooks_core.router)
router.include_router(notebooks_cells.router)
