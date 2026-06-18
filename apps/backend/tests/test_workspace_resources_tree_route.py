from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from app.api.routes import workspaces_resources_files as files_route_module
from app.api.routes import workspaces_resources_tree as tree_route_module
from app.core import config as config_module
from app.models.user import UserInfo
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _find_node(nodes: list[dict], path: str) -> dict:
    for node in nodes:
        if node["path"] == path:
            return node
        found = _find_node(node.get("children") or [], path)
        if found:
            return found
    return {}


def _write_resource_metadata_db(path: Path, metadata: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE _aiasys_metadata (key TEXT PRIMARY KEY, value TEXT)")
        conn.executemany(
            "INSERT INTO _aiasys_metadata (key, value) VALUES (?, ?)",
            [(key, str(value)) for key, value in metadata.items()],
        )
        conn.commit()
    finally:
        conn.close()


def _patch_workspace_registry_service(
    monkeypatch: pytest.MonkeyPatch,
    service: WorkspaceRegistryService,
) -> None:
    monkeypatch.setattr(
        tree_route_module,
        "get_workspace_registry_service",
        lambda: service,
    )


def test_workspace_resources_tree_returns_file_assets_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = WorkspaceRegistryService(
        tmp_path,
        session_manager=SessionManager(tmp_path),
    )
    service.create_workspace(
        user_id="local_default",
        workspace_id="workspace-1",
        title="资源树任务",
        initial_conversation_title="当前会话",
    )
    _patch_workspace_registry_service(monkeypatch, service)
    workspace_root = service.get_workspace_root("local_default", "workspace-1")

    # 在工作区不同目录下创建带 metadata 的 .db 文件
    _write_resource_metadata_db(
        workspace_root / "knowledge/product-docs.knowledge.db",
        {
            "resource_type": "knowledge",
            "id": "kb-product-docs",
            "document_count": 3,
            "renderer_hint": "knowledge_base_preview",
        },
    )
    _write_resource_metadata_db(
        workspace_root / "graphs/project.graph.db",
        {
            "resource_type": "graph",
            "id": "kg-project",
            "entity_count": 3,
            "relation_count": 2,
            "renderer_hint": "knowledge_graph_preview",
        },
    )
    _write_resource_metadata_db(
        workspace_root / "databases/workspace.sqlite.db",
        {
            "resource_type": "database",
            "id": "workspace-sqlite",
            "handle": "workspace-sqlite",
            "readonly": "false",
            "renderer_hint": "database_preview",
        },
    )
    # 不带 resource_type 的 .db 文件也应被包含
    _write_resource_metadata_db(
        workspace_root / "raw/data.duckdb",
        {
            "id": "raw-data",
        },
    )
    (workspace_root / "docs").mkdir(parents=True, exist_ok=True)
    (workspace_root / "docs" / "note.md").write_text("# note", encoding="utf-8")
    response = asyncio.run(
        tree_route_module.get_workspace_resources_tree(
            "workspace-1",
            current_user=_build_user(),
        )
    )

    nodes = response.model_dump()["nodes"]

    # 验证目录结构保持原始路径，不再被重定向到虚拟目录
    knowledge_dir = _find_node(nodes, "knowledge")
    assert knowledge_dir["node_type"] == "directory"
    knowledge_asset = _find_node(nodes, "knowledge/product-docs.knowledge.db")
    assert knowledge_asset["node_type"] == "resource"
    assert knowledge_asset["resource_type"] == "knowledge"
    assert knowledge_asset["meta"]["id"] == "kb-product-docs"
    assert knowledge_asset["meta"]["resource_type"] == "knowledge"
    assert knowledge_asset["meta"]["renderer_hint"] == "knowledge_base_preview"

    graphs_dir = _find_node(nodes, "graphs")
    assert graphs_dir["node_type"] == "directory"
    graph_asset = _find_node(nodes, "graphs/project.graph.db")
    assert graph_asset["node_type"] == "resource"
    assert graph_asset["resource_type"] == "graph"
    assert graph_asset["meta"]["id"] == "kg-project"
    assert graph_asset["meta"]["resource_type"] == "graph"

    databases_dir = _find_node(nodes, "databases")
    assert databases_dir["node_type"] == "directory"
    db_asset = _find_node(nodes, "databases/workspace.sqlite.db")
    assert db_asset["node_type"] == "resource"
    assert db_asset["resource_type"] == "database"
    assert db_asset["meta"]["id"] == "workspace-sqlite"
    assert db_asset["meta"]["resource_type"] == "database"

    raw_dir = _find_node(nodes, "raw")
    assert raw_dir["node_type"] == "directory"
    raw_asset = _find_node(nodes, "raw/data.duckdb")
    assert raw_asset["node_type"] == "resource"
    assert raw_asset["resource_type"] is None
    assert raw_asset["meta"]["id"] == "raw-data"

    docs_dir = _find_node(nodes, "docs")
    assert docs_dir["node_type"] == "directory"
    assert docs_dir["absolute_path"] == str((workspace_root / "docs").absolute())
    docs_asset = _find_node(nodes, "docs/note.md")
    assert docs_asset["node_type"] == "resource"
    assert docs_asset["absolute_path"] == str((workspace_root / "docs/note.md").absolute())
    assert docs_asset["resource_type"] is None
    assert docs_asset["meta"]["relative_path"] == "docs/note.md"

    # 验证不再混入系统资源
    assert _find_node(nodes, "knowledge/kb_1") == {}
    assert _find_node(nodes, "databases/builtin_db") == {}
    assert _find_node(nodes, "databases/dbc_1") == {}
    assert _find_node(nodes, "graphs/kg_1") == {}


def test_workspace_resources_tree_shows_dot_dirs_but_skips_internal_dirs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = WorkspaceRegistryService(
        tmp_path,
        session_manager=SessionManager(tmp_path),
    )
    service.create_workspace(
        user_id="local_default",
        workspace_id="workspace-2",
        title="点目录测试",
    )
    _patch_workspace_registry_service(monkeypatch, service)
    workspace_root = service.get_workspace_root("local_default", "workspace-2")

    # 正常目录下的文件
    _write_resource_metadata_db(
        workspace_root / "visible/file.db",
        {"id": "visible-file"},
    )
    # 普通点目录应像 VSCode 文件树一样出现。
    _write_resource_metadata_db(
        workspace_root / ".hidden/hidden.db",
        {"id": "hidden-file"},
    )
    (workspace_root / ".vscode/settings.json").parent.mkdir(parents=True, exist_ok=True)
    (workspace_root / ".vscode/settings.json").write_text("{}", encoding="utf-8")
    (workspace_root / ".aiasys/session/internal.db").parent.mkdir(parents=True, exist_ok=True)
    (workspace_root / ".aiasys/session/internal.db").write_bytes(b"internal")
    (workspace_root / "metadata.json").write_text("{}", encoding="utf-8")
    response = asyncio.run(
        tree_route_module.get_workspace_resources_tree(
            "workspace-2",
            current_user=_build_user(),
        )
    )

    nodes = response.model_dump()["nodes"]

    assert _find_node(nodes, "visible/file.db") != {}
    assert _find_node(nodes, ".hidden/hidden.db") != {}
    assert _find_node(nodes, ".hidden") != {}
    assert _find_node(nodes, ".vscode/settings.json") != {}
    assert _find_node(nodes, ".aiasys/session/internal.db") == {}
    assert _find_node(nodes, ".aiasys/session") == {}
    assert _find_node(nodes, "metadata.json") == {}


def test_global_workspace_tree_exposes_user_default_memory_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = WorkspaceRegistryService(
        tmp_path,
        session_manager=SessionManager(tmp_path),
    )
    service.create_workspace(
        user_id="local_default",
        workspace_id="workspace-global-memory",
        title="全局记忆入口测试",
    )
    _patch_workspace_registry_service(monkeypatch, service)
    monkeypatch.setattr(config_module, "WORKSPACE_DIR", tmp_path)

    response = asyncio.run(
        files_route_module.get_global_workspace_resources_tree(
            "workspace-global-memory",
            current_user=_build_user(),
        )
    )

    nodes = response.model_dump()["nodes"]
    assert _find_node(nodes, ".aiasys/.memory/MEMORY.md")["node_type"] == "resource"
    assert _find_node(nodes, ".aiasys/.memory/memory_summary.md")["node_type"] == "resource"
    assert _find_node(nodes, ".aiasys/.memory/raw_memories.md")["node_type"] == "resource"
    assert _find_node(nodes, ".aiasys/.memory/state.db") == {}
    assert _find_node(nodes, ".aiasys/.memory/MEMORY.snapshots.json") == {}


def test_workspace_resources_tree_preserves_empty_folder_markers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = WorkspaceRegistryService(
        tmp_path,
        session_manager=SessionManager(tmp_path),
    )
    service.create_workspace(
        user_id="local_default",
        workspace_id="workspace-3",
        title="空目录测试",
    )
    _patch_workspace_registry_service(monkeypatch, service)
    workspace_root = service.get_workspace_root("local_default", "workspace-3")
    marker_path = workspace_root / "reports/2026/__aiasys_folder__.md"
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text("", encoding="utf-8")
    response = asyncio.run(
        tree_route_module.get_workspace_resources_tree(
            "workspace-3",
            current_user=_build_user(),
        )
    )

    nodes = response.model_dump()["nodes"]

    reports_dir = _find_node(nodes, "reports")
    assert reports_dir["node_type"] == "directory"
    assert reports_dir["absolute_path"] == str((workspace_root / "reports").absolute())
    year_dir = _find_node(nodes, "reports/2026")
    assert year_dir["node_type"] == "directory"
    assert year_dir["absolute_path"] == str((workspace_root / "reports/2026").absolute())
    assert _find_node(nodes, "reports/2026/__aiasys_folder__.md") == {}


def test_workspace_resources_tree_shows_env_and_collapses_heavy_dependency_dirs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = WorkspaceRegistryService(
        tmp_path,
        session_manager=SessionManager(tmp_path),
    )
    service.create_workspace(
        user_id="local_default",
        workspace_id="workspace-heavy",
        title="重目录测试",
    )
    _patch_workspace_registry_service(monkeypatch, service)
    workspace_root = service.get_workspace_root("local_default", "workspace-heavy")
    env_dir = workspace_root / ".env"
    venv_dir = env_dir / ".uv-runtime"
    site_packages_dir = venv_dir / "lib/python3.12/site-packages"
    site_packages_dir.mkdir(parents=True, exist_ok=True)
    (venv_dir / "bin").mkdir(parents=True, exist_ok=True)
    (venv_dir / "bin" / "python").write_text("#!/usr/bin/env python\n", encoding="utf-8")
    (venv_dir / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
    (site_packages_dir / "heavy_pkg.py").write_text("x = 1\n", encoding="utf-8")
    (env_dir / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (env_dir / "environments.json").write_text(
        (
            "{"
            '"envs": ['
            "{"
            '"env_id": "workspace-default",'
            '"kind": "uv",'
            '"display_name": "Workspace UV",'
            f'"material_path": "{env_dir.as_posix()}",'
            f'"python_executable": "{(venv_dir / "bin" / "python").as_posix()}",'
            '"metadata": {"manager": "uv"}'
            "}"
            "]"
            "}"
        ),
        encoding="utf-8",
    )
    node_modules = workspace_root / "app/node_modules"
    (node_modules / "react").mkdir(parents=True, exist_ok=True)
    (node_modules / "react/index.js").write_text("module.exports = {}\n", encoding="utf-8")
    (workspace_root / "app/package.json").write_text("{}", encoding="utf-8")
    (workspace_root / "notes.md").write_text("visible", encoding="utf-8")
    response = asyncio.run(
        tree_route_module.get_workspace_resources_tree(
            "workspace-heavy",
            current_user=_build_user(),
        )
    )

    nodes = response.model_dump()["nodes"]

    env_node = _find_node(nodes, ".env")
    assert env_node["node_type"] == "directory"
    assert env_node["meta"]["directory_kind"] == "runtime_material"

    venv_node = _find_node(nodes, ".env/.uv-runtime")
    assert venv_node["node_type"] == "directory"
    assert venv_node["meta"]["directory_kind"] == "python_venv"
    assert venv_node["meta"]["heavy"] is True
    assert venv_node["meta"]["children_truncated"] is True
    assert venv_node["children"] == []
    assert _find_node(nodes, ".env/.uv-runtime/lib/python3.12/site-packages/heavy_pkg.py") == {}

    node_modules_node = _find_node(nodes, "app/node_modules")
    assert node_modules_node["node_type"] == "directory"
    assert node_modules_node["meta"]["directory_kind"] == "node_dependency"
    assert node_modules_node["meta"]["children_truncated"] is True
    assert node_modules_node["children"] == []
    assert _find_node(nodes, "app/node_modules/react/index.js") == {}

    assert _find_node(nodes, ".env/pyproject.toml")["node_type"] == "resource"
    assert _find_node(nodes, "app/package.json")["node_type"] == "resource"
    assert _find_node(nodes, "notes.md")["node_type"] == "resource"


def test_workspace_resources_tree_children_pages_heavy_directory(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    node_modules = workspace_root / "node_modules"
    for index in range(3):
        package_dir = node_modules / f"pkg-{index}"
        package_dir.mkdir(parents=True, exist_ok=True)
        (package_dir / "index.js").write_text("", encoding="utf-8")

    response = tree_route_module._scan_workspace_directory_children(
        workspace_root,
        "node_modules",
        limit=2,
        offset=0,
    )
    payload = response.model_dump()

    assert payload["path"] == "node_modules"
    assert payload["total"] == 3
    assert payload["has_more"] is True
    assert payload["next_offset"] == 2
    assert [node["path"] for node in payload["nodes"]] == [
        "node_modules/pkg-0",
        "node_modules/pkg-1",
    ]
    assert payload["nodes"][0]["node_type"] == "directory"


def test_workspace_resources_tree_recognizes_windows_style_python_venv(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    venv_dir = workspace_root / "runtime" / "custom-env"
    scripts_dir = venv_dir / "Scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "python.exe").write_text("", encoding="utf-8")
    (venv_dir / "pyvenv.cfg").write_text("home = C:/Python312\n", encoding="utf-8")
    (venv_dir / "Lib/site-packages").mkdir(parents=True)
    (venv_dir / "Lib/site-packages/pkg.py").write_text("x = 1\n", encoding="utf-8")

    nodes = tree_route_module._scan_workspace_file_assets(workspace_root)
    payload = [node.model_dump() for node in nodes]

    venv_node = _find_node(payload, "runtime/custom-env")
    assert venv_node["node_type"] == "directory"
    assert venv_node["meta"]["directory_kind"] == "python_venv"
    assert venv_node["meta"]["heavy"] is True
    assert venv_node["children"] == []
    assert _find_node(payload, "runtime/custom-env/Lib/site-packages/pkg.py") == {}


def test_workspace_resources_tree_children_counts_visible_items_only(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    env_dir = workspace_root / ".env"
    env_dir.mkdir(parents=True)
    (env_dir / "environments.json").write_text("{}", encoding="utf-8")
    (env_dir / "__aiasys_folder__.md").write_text("", encoding="utf-8")
    (env_dir / "visible.txt").write_text("ok", encoding="utf-8")
    (env_dir / ".aiasys" / "session").mkdir(parents=True)
    (env_dir / ".aiasys/session/internal.txt").write_text("hidden", encoding="utf-8")

    response = tree_route_module._scan_workspace_directory_children(
        workspace_root,
        ".env",
        limit=10,
        offset=0,
    )
    payload = response.model_dump()

    assert payload["total"] == 2
    assert payload["has_more"] is False
    assert [node["path"] for node in payload["nodes"]] == [
        ".env/environments.json",
        ".env/visible.txt",
    ]
