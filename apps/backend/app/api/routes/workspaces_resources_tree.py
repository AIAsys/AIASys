import fnmatch
import json
import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import require_auth
from app.models.user import UserInfo
from app.services.runtime_environment import resolve_workspace_runtime_dir
from app.services.workspace_registry import get_workspace_registry_service

logger = logging.getLogger(__name__)

router = APIRouter()

# 文件可见性配置文件名
FILE_VISIBILITY_CONFIG = "file-visibility.json"

# 默认隐藏规则（配置文件不存在时使用）
_DEFAULT_HIDDEN_PATTERNS = [
    "**/.aiasys",
    ".aiasys/file-history",
    ".aiasys/file-history/**",
    ".aiasys/.memory/*.lock",
    ".aiasys/.memory/state.db",
    ".aiasys/.memory/*.snapshots.json",
    ".aiasys/session",
    ".aiasys/session/**",
    "**/__aiasys_folder__.md",
    "*-shm",
    "**/*-shm",
    "*-wal",
    "**/*-wal",
    "*-journal",
    "**/*-journal",
]

# 工作区根目录下的内部文件（不应显示在文件树中）
_INTERNAL_ROOT_FILES = {
    ".cleanup_marker",
    "metadata.json",
    "history.json",
    "file_snapshots.json",
}

# 已知的资源型复合后缀（按长度降序，优先匹配更长的）
_RESOURCE_SUFFIXES = (".graph.db", ".table.db", ".kb.db", ".db", ".sqlite", ".sqlite3", ".duckdb")
DirectoryKind = Literal[
    "normal",
    "runtime_material",
    "python_venv",
    "python_dependency",
    "node_dependency",
]
HEAVY_DIRECTORY_DEFAULT_LIMIT = 50
HEAVY_NODE_DIRECTORY_NAMES = {"node_modules", ".pnpm"}
PYTHON_DEPENDENCY_DIR_NAMES = {"site-packages", "dist-packages"}


def _load_file_visibility_rules(workspace_root: Path) -> list[str]:
    """从工作区 .aiasys/file-visibility.json 读取隐藏规则。

    返回 pattern 列表，匹配任一 pattern 的路径将被隐藏。
    文件不存在或解析失败时返回默认规则。
    """
    config_path = workspace_root / ".aiasys" / FILE_VISIBILITY_CONFIG
    if not config_path.is_file():
        return list(_DEFAULT_HIDDEN_PATTERNS)
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("文件可见性配置解析失败: %s，使用默认规则", config_path)
        return list(_DEFAULT_HIDDEN_PATTERNS)
    if not isinstance(data, dict):
        return list(_DEFAULT_HIDDEN_PATTERNS)
    return [k for k, v in data.items() if v is True]


def _is_hidden_by_config(relative_path: str, patterns: list[str]) -> bool:
    """判断路径是否匹配任一隐藏 pattern。"""
    for pattern in patterns:
        if fnmatch.fnmatch(relative_path, pattern):
            return True
    return False


def _extract_resource_id(file_path: Path) -> str:
    """从资源文件名提取 ID，正确处理 .graph.db / .table.db 等复合后缀。"""
    name = file_path.name
    lower_name = name.lower()
    for suffix in _RESOURCE_SUFFIXES:
        if lower_name.endswith(suffix):
            return name[: -len(suffix)]
    return file_path.stem


class ResourceTreeNode(BaseModel):
    """工作区文件树节点"""

    name: str
    path: str
    absolute_path: str | None = None
    node_type: str  # "directory" | "resource"
    resource_type: str | None = None  # "knowledge" | "database" | "graph"
    meta: dict = Field(default_factory=dict)
    children: list["ResourceTreeNode"] = Field(default_factory=list)


class WorkspaceResourcesTreeResponse(BaseModel):
    """工作区文件树响应"""

    nodes: list[ResourceTreeNode]


class WorkspaceDirectoryChildrenResponse(BaseModel):
    """工作区目录一级子项响应"""

    path: str
    nodes: list[ResourceTreeNode]
    total: int
    limit: int
    offset: int
    has_more: bool
    next_offset: int | None = None


def _normalize_path_key(path: Path) -> str:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path.absolute()
    return str(resolved)


def _is_hidden_path(relative_path: str, patterns: list[str]) -> bool:
    """判断路径是否应该被隐藏。"""
    parts = Path(relative_path).parts
    if not parts:
        return True
    # 工作区根目录下的内部文件
    if len(parts) == 1 and parts[0] in _INTERNAL_ROOT_FILES:
        return True
    return _is_hidden_by_config(relative_path, patterns)


def _python_bin_candidates_for_venv(venv_dir: Path) -> tuple[Path, ...]:
    return (
        venv_dir / "bin" / "python",
        venv_dir / "bin" / "python3",
        venv_dir / "Scripts" / "python.exe",
    )


def _looks_like_python_venv(path: Path) -> bool:
    if not path.is_dir():
        return False
    if not (path / "pyvenv.cfg").is_file():
        return False
    return any(candidate.exists() for candidate in _python_bin_candidates_for_venv(path))


def _venv_dir_from_python_executable(path: Path) -> Path | None:
    parts = path.parts
    if len(parts) < 2:
        return None
    parent_name = path.parent.name.lower()
    if parent_name in {"bin", "scripts"}:
        return path.parent.parent
    return None


def _read_runtime_path_sets(workspace_root: Path) -> tuple[set[str], set[str]]:
    """读取运行环境登记路径，返回材料目录和虚拟环境目录集合。"""
    runtime_material_dirs: set[str] = set()
    python_venv_dirs: set[str] = set()
    registry_path = resolve_workspace_runtime_dir(workspace_root) / "environments.json"
    if not registry_path.exists():
        return runtime_material_dirs, python_venv_dirs

    try:
        import json

        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        return runtime_material_dirs, python_venv_dirs

    envs = payload.get("envs") if isinstance(payload, dict) else None
    if not isinstance(envs, list):
        return runtime_material_dirs, python_venv_dirs

    for item in envs:
        if not isinstance(item, dict):
            continue
        material_path = str(item.get("material_path") or "").strip()
        if material_path:
            runtime_material_dirs.add(_normalize_path_key(Path(material_path)))

        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        project_environment_path = str(metadata.get("project_environment_path") or "").strip()
        if project_environment_path:
            python_venv_dirs.add(_normalize_path_key(Path(project_environment_path)))

        python_executable = str(item.get("python_executable") or "").strip()
        if python_executable:
            venv_dir = _venv_dir_from_python_executable(Path(python_executable))
            if venv_dir is not None:
                python_venv_dirs.add(_normalize_path_key(venv_dir))

    return runtime_material_dirs, python_venv_dirs


def _classify_directory(
    path: Path,
    *,
    runtime_material_dirs: set[str],
    python_venv_dirs: set[str],
    known_venv_ancestors: set[str],
) -> DirectoryKind:
    path_key = _normalize_path_key(path)
    if path_key in runtime_material_dirs:
        return "runtime_material"
    if path_key in python_venv_dirs or _looks_like_python_venv(path):
        return "python_venv"
    if path.name in HEAVY_NODE_DIRECTORY_NAMES:
        return "node_dependency"
    if path.name in PYTHON_DEPENDENCY_DIR_NAMES and any(
        path_key.startswith(venv_key + "/") or path_key.startswith(venv_key + "\\")
        for venv_key in known_venv_ancestors
    ):
        return "python_dependency"
    return "normal"


def _collect_venv_ancestor_keys(path: Path, workspace_root: Path) -> set[str]:
    venv_dirs: set[str] = set()
    current = path
    while True:
        if _looks_like_python_venv(current):
            venv_dirs.add(_normalize_path_key(current))
        if current == workspace_root or current.parent == current:
            break
        current = current.parent
    return venv_dirs


def _is_heavy_directory_kind(kind: DirectoryKind) -> bool:
    return kind in {"python_venv", "python_dependency", "node_dependency"}


def _make_directory_node(
    *,
    path: Path,
    relative_path: str,
    kind: DirectoryKind,
    children: list[ResourceTreeNode] | None = None,
) -> ResourceTreeNode:
    meta: dict[str, object] = {
        "directory_kind": kind,
        "source": "workspace_directory",
        "relative_path": relative_path,
    }
    if _is_heavy_directory_kind(kind):
        meta.update(
            {
                "heavy": True,
                "children_truncated": True,
                "preview_limit": HEAVY_DIRECTORY_DEFAULT_LIMIT,
            }
        )
    elif kind == "runtime_material":
        meta["runtime_material"] = True

    return ResourceTreeNode(
        name=path.name,
        path=relative_path,
        absolute_path=str(path.absolute()),
        node_type="directory",
        meta=meta,
        children=children or [],
    )


def _build_file_tree(
    file_nodes: list[ResourceTreeNode],
    explicit_dir_paths: set[str] | None = None,
    root_path=None,
    directory_kinds: dict[str, DirectoryKind] | None = None,
) -> list[ResourceTreeNode]:
    """根据文件相对路径构建真实目录树。"""
    dir_paths: set[str] = set(explicit_dir_paths or set())
    for node in file_nodes:
        parts = node.path.split("/")
        for i in range(1, len(parts)):
            dir_paths.add("/".join(parts[:i]))

    if not dir_paths and not file_nodes:
        return []

    dir_nodes: dict[str, ResourceTreeNode] = {}
    for dir_path in sorted(dir_paths):
        name = dir_path.split("/")[-1]
        directory_path = root_path / dir_path if root_path else Path(dir_path)
        kind: DirectoryKind = (directory_kinds or {}).get(dir_path, "normal")
        dir_nodes[dir_path] = ResourceTreeNode(
            name=name,
            path=dir_path,
            absolute_path=str(directory_path.absolute()) if root_path else None,
            node_type="directory",
            meta={
                "directory_kind": kind,
                "source": "workspace_directory",
                "relative_path": dir_path,
                **(
                    {
                        "runtime_material": True,
                    }
                    if kind == "runtime_material"
                    else {}
                ),
                **(
                    {
                        "heavy": True,
                        "children_truncated": True,
                        "preview_limit": HEAVY_DIRECTORY_DEFAULT_LIMIT,
                    }
                    if _is_heavy_directory_kind(kind)
                    else {}
                ),
            },
            children=[],
        )

    root_nodes: list[ResourceTreeNode] = []
    for dir_path, dir_node in sorted(dir_nodes.items(), key=lambda x: x[0]):
        parent_path = "/".join(dir_path.split("/")[:-1]) if "/" in dir_path else ""
        if parent_path and parent_path in dir_nodes:
            dir_nodes[parent_path].children.append(dir_node)
        else:
            root_nodes.append(dir_node)

    for node in file_nodes:
        parent_path = "/".join(node.path.split("/")[:-1]) if "/" in node.path else ""
        if parent_path and parent_path in dir_nodes:
            dir_nodes[parent_path].children.append(node)
        else:
            root_nodes.append(node)

    def sort_children(nodes: list[ResourceTreeNode]) -> None:
        nodes.sort(key=lambda n: (0 if n.node_type == "directory" else 1, n.path))
        for node in nodes:
            if node.node_type == "directory":
                sort_children(node.children)

    sort_children(root_nodes)
    return root_nodes


def _scan_workspace_file_assets(
    workspace_root,
    workspace_id: str | None = None,
    logical_prefix: str = "/workspace",
    source: str = "workspace_asset",
    include_heavy_children: bool = False,
) -> list[ResourceTreeNode]:
    """扫描工作区目录下的文件资产，保持原始路径，不再混入系统资源。"""
    from app.api.routes.files_utils import (
        RESOURCE_DB_EXTENSIONS,
        RESOURCE_METADATA_TOP_LEVEL_KEYS,
        _read_sqlite_resource_metadata,
    )

    workspace_path = workspace_root
    if not workspace_path.exists():
        return []

    patterns = _load_file_visibility_rules(workspace_path)
    file_nodes: list[ResourceTreeNode] = []
    explicit_dir_paths: set[str] = set()
    directory_kinds: dict[str, DirectoryKind] = {}
    runtime_material_dirs, registered_venv_dirs = _read_runtime_path_sets(workspace_path)
    known_venv_dirs: set[str] = set(registered_venv_dirs)
    pending_dirs = [workspace_path]
    while pending_dirs:
        current_dir = pending_dirs.pop()
        try:
            entries = sorted(current_dir.iterdir(), key=lambda item: item.name)
        except OSError:
            continue

        for entry in entries:
            if entry.is_symlink():
                continue
            try:
                rel_parts = entry.relative_to(workspace_path).parts
            except ValueError:
                continue
            if not rel_parts:
                continue
            relative_path = entry.relative_to(workspace_path).as_posix()
            if _is_hidden_path(relative_path, patterns):
                continue

            if entry.is_dir():
                known_venv_dirs.update(_collect_venv_ancestor_keys(entry.parent, workspace_path))
                dir_kind = _classify_directory(
                    entry,
                    runtime_material_dirs=runtime_material_dirs,
                    python_venv_dirs=registered_venv_dirs,
                    known_venv_ancestors=known_venv_dirs,
                )
                directory_kinds[relative_path] = dir_kind
                explicit_dir_paths.add(relative_path)
                if dir_kind == "python_venv":
                    known_venv_dirs.add(_normalize_path_key(entry))
                if include_heavy_children or not _is_heavy_directory_kind(dir_kind):
                    pending_dirs.append(entry)
                continue

            if not entry.is_file():
                continue

            file_path = entry
            rel_parts = file_path.relative_to(workspace_path).parts
            relative_path = file_path.relative_to(workspace_path).as_posix()
            metadata = (
                _read_sqlite_resource_metadata(file_path)
                if file_path.suffix.lower() in RESOURCE_DB_EXTENSIONS
                else {}
            )

            resource_meta: dict[str, object] = {}
            nested_meta = metadata.get("meta")
            if isinstance(nested_meta, dict):
                resource_meta = dict(nested_meta)
            for key, value in metadata.items():
                if key in RESOURCE_METADATA_TOP_LEVEL_KEYS or key == "meta":
                    continue
                resource_meta[key] = value
            resource_meta.setdefault("id", metadata.get("id") or _extract_resource_id(file_path))
            normalized_prefix = logical_prefix.rstrip("/") or "/workspace"
            resource_meta.setdefault("db_path", f"{normalized_prefix}/{relative_path}")
            resource_meta.setdefault("source", source)
            resource_meta.setdefault("relative_path", relative_path)
            if workspace_id:
                resource_meta.setdefault("workspace_id", workspace_id)

            for hint_key in ("resource_type", "renderer_hint", "preview_kind", "schema_kind"):
                if metadata.get(hint_key):
                    resource_meta[hint_key] = metadata.get(hint_key)

            file_nodes.append(
                ResourceTreeNode(
                    name=file_path.name,
                    path=relative_path,
                    absolute_path=str(file_path.absolute()),
                    node_type="resource",
                    resource_type=(
                        metadata.get("resource_type") if metadata.get("resource_type") else None
                    ),
                    meta=resource_meta,
                )
            )

    return _build_file_tree(
        file_nodes,
        explicit_dir_paths,
        root_path=workspace_path,
        directory_kinds=directory_kinds,
    )


def _scan_workspace_directory_children(
    workspace_root: Path,
    directory_path: str,
    *,
    workspace_id: str | None = None,
    logical_prefix: str = "/workspace",
    source: str = "workspace_asset",
    limit: int = HEAVY_DIRECTORY_DEFAULT_LIMIT,
    offset: int = 0,
) -> WorkspaceDirectoryChildrenResponse:
    from app.api.routes.files_utils import (
        RESOURCE_DB_EXTENSIONS,
        RESOURCE_METADATA_TOP_LEVEL_KEYS,
        _ensure_path_within_root,
        _normalize_relative_path,
        _read_sqlite_resource_metadata,
    )

    normalized_path = _normalize_relative_path(directory_path)
    target_dir = _ensure_path_within_root(workspace_root, normalized_path)
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=404, detail="目录不存在")

    runtime_material_dirs, registered_venv_dirs = _read_runtime_path_sets(workspace_root)
    known_venv_dirs = set(registered_venv_dirs)
    known_venv_dirs.update(_collect_venv_ancestor_keys(target_dir, workspace_root))
    if _looks_like_python_venv(target_dir):
        known_venv_dirs.add(_normalize_path_key(target_dir))

    patterns = _load_file_visibility_rules(workspace_root)
    nodes: list[ResourceTreeNode] = []

    def is_visible_directory_child(item: Path) -> bool:
        try:
            rel_parts = item.relative_to(workspace_root).parts
        except ValueError:
            return False
        if not rel_parts:
            return False
        relative_path = item.relative_to(workspace_root).as_posix()
        if _is_hidden_path(relative_path, patterns):
            return False
        return True

    try:
        entries = [
            item
            for item in sorted(target_dir.iterdir(), key=lambda value: value.name)
            if not item.is_symlink() and is_visible_directory_child(item)
        ]
    except OSError:
        entries = []

    visible_entries = entries[offset : offset + limit]
    for item in visible_entries:
        relative_path = item.relative_to(workspace_root).as_posix()
        if item.is_dir():
            known_venv_dirs.update(_collect_venv_ancestor_keys(item.parent, workspace_root))
            kind = _classify_directory(
                item,
                runtime_material_dirs=runtime_material_dirs,
                python_venv_dirs=registered_venv_dirs,
                known_venv_ancestors=known_venv_dirs,
            )
            nodes.append(
                _make_directory_node(
                    path=item,
                    relative_path=relative_path,
                    kind=kind,
                )
            )
            continue
        if not item.is_file():
            continue
        metadata = (
            _read_sqlite_resource_metadata(item)
            if item.suffix.lower() in RESOURCE_DB_EXTENSIONS
            else {}
        )
        resource_meta: dict[str, object] = {}
        nested_meta = metadata.get("meta")
        if isinstance(nested_meta, dict):
            resource_meta = dict(nested_meta)
        for key, value in metadata.items():
            if key in RESOURCE_METADATA_TOP_LEVEL_KEYS or key == "meta":
                continue
            resource_meta[key] = value
        resource_meta.setdefault("id", metadata.get("id") or _extract_resource_id(item))
        normalized_prefix = logical_prefix.rstrip("/") or "/workspace"
        resource_meta.setdefault("db_path", f"{normalized_prefix}/{relative_path}")
        resource_meta.setdefault("source", source)
        resource_meta.setdefault("relative_path", relative_path)
        if workspace_id:
            resource_meta.setdefault("workspace_id", workspace_id)
        nodes.append(
            ResourceTreeNode(
                name=item.name,
                path=relative_path,
                absolute_path=str(item.absolute()),
                node_type="resource",
                resource_type=(
                    metadata.get("resource_type") if metadata.get("resource_type") else None
                ),
                meta=resource_meta,
            )
        )

    next_offset = offset + limit if offset + limit < len(entries) else None
    return WorkspaceDirectoryChildrenResponse(
        path=normalized_path.as_posix(),
        nodes=nodes,
        total=len(entries),
        limit=limit,
        offset=offset,
        has_more=next_offset is not None,
        next_offset=next_offset,
    )


@router.get(
    "/{workspace_id}/resources/tree",
    response_model=WorkspaceResourcesTreeResponse,
)
async def get_workspace_resources_tree(
    workspace_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """获取工作区的文件资产树。"""
    service = get_workspace_registry_service()
    try:
        service.get_workspace(
            current_user.user_id,
            workspace_id,
            include_conversations=False,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    nodes = _scan_workspace_file_assets(workspace_root, workspace_id=workspace_id)
    return WorkspaceResourcesTreeResponse(nodes=nodes)


@router.get(
    "/{workspace_id}/resources/tree/children/{directory_path:path}",
    response_model=WorkspaceDirectoryChildrenResponse,
)
async def get_workspace_resources_tree_children(
    workspace_id: str,
    directory_path: str,
    limit: int = Query(HEAVY_DIRECTORY_DEFAULT_LIMIT, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: UserInfo = Depends(require_auth()),
):
    """按需获取工作区目录的一级子项。"""
    service = get_workspace_registry_service()
    try:
        service.get_workspace(
            current_user.user_id,
            workspace_id,
            include_conversations=False,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    return _scan_workspace_directory_children(
        workspace_root,
        directory_path,
        workspace_id=workspace_id,
        limit=limit,
        offset=offset,
    )
