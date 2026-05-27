import json
import logging
from pathlib import Path

from app.models.workspace import WorkspaceResourceVerificationResponse

logger = logging.getLogger(__name__)

_RESOURCE_VERIFICATION_CACHE_RELATIVE_PATH = ".aiasys/resource-verification/latest.json"


def _get_resource_verification_cache_path(workspace_dir: Path) -> Path:
    return workspace_dir / _RESOURCE_VERIFICATION_CACHE_RELATIVE_PATH


def _read_resource_verification_cache(
    workspace_dir: Path,
) -> WorkspaceResourceVerificationResponse | None:
    cache_path = _get_resource_verification_cache_path(workspace_dir)
    if not cache_path.exists():
        return None
    try:
        cached = WorkspaceResourceVerificationResponse.model_validate(
            json.loads(cache_path.read_text(encoding="utf-8"))
        )
        cached.verification_source = "cache"
        cached.cache_hit = True
        return cached
    except Exception as exc:
        logger.warning("读取资源验活缓存失败: path=%s error=%s", cache_path, exc)
        return None


def _write_resource_verification_cache(
    workspace_dir: Path,
    response: WorkspaceResourceVerificationResponse,
) -> None:
    cache_path = _get_resource_verification_cache_path(workspace_dir)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(response.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
