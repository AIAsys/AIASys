"""Notebook workbench API.

This module re-exports all notebook endpoints and utilities from sub-modules
to keep the unified namespace.
"""

from __future__ import annotations

from fastapi import APIRouter

# Re-export shared imports from files.py so tests can monkeypatch them

# Re-export endpoints

# Re-export utilities so tests and other consumers can still access them
# from app.api.routes.notebooks directly.

# Re-export other imports used by tests


router = APIRouter(prefix="/notebooks", tags=["notebooks"])

# Include sub-routers
from . import notebooks_cells, notebooks_core, notebooks_execution

router.include_router(notebooks_execution.router)
router.include_router(notebooks_core.router)
router.include_router(notebooks_cells.router)
