from fastapi import APIRouter

from .workspaces_resources_files import router as _files_router
from .workspaces_resources_mounts import router as _mounts_router
from .workspaces_resources_tree import router as _tree_router
from .workspaces_resources_verification import router as _verification_router

router = APIRouter(prefix="/workspaces", tags=["workspaces"])
router.include_router(_verification_router)
router.include_router(_mounts_router)
router.include_router(_tree_router)
router.include_router(_files_router)
