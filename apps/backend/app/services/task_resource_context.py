from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Sequence

from app.core.config import (
    GLOBAL_RESOURCE_SCAN_LIMIT,
    RESOURCE_PROMPT_ITEM_LIMIT,
    WORKSPACE_DIR,
    get_user_global_workspace_dir,
)
from app.knowledge import get_sqlite_kb_service
from app.services.connector import DatabaseConnectorService
from app.services.history import (
    current_global_workspace,
    current_session_id,
    current_user_id,
    current_workspace,
)
from app.services.session.config_projection import (
    read_workspace_database_mount_data,
)

logger = logging.getLogger(__name__)


def _resolve_workspace_dir(workspace_dir: Path | str | None = None) -> Path | None:
    if workspace_dir is not None:
        return Path(workspace_dir)

    context_workspace = current_workspace.get()
    if context_workspace is None:
        return None
    return Path(context_workspace)


def _resolve_user_id(user_id: str | None = None) -> str | None:
    if user_id:
        return user_id
    return current_user_id.get()


def _resolve_session_id(session_id: str | None = None) -> str | None:
    if session_id:
        return session_id
    return current_session_id.get()


def _resolve_global_workspace_dir(global_workspace_dir: Path | str | None = None) -> Path | None:
    if global_workspace_dir is not None:
        return Path(global_workspace_dir)

    context_global = current_global_workspace.get()
    if context_global is None:
        return None
    return Path(context_global)


def resolve_global_workspace_resources(
    *,
    user_id: str | None = None,
    global_workspace_dir: Path | str | None = None,
) -> list[dict[str, Any]]:
    """扫描全局工作区目录，返回文件资源列表。"""
    resolved_user_id = _resolve_user_id(user_id)
    resolved_global = _resolve_global_workspace_dir(global_workspace_dir)

    if resolved_global is None and resolved_user_id:
        resolved_global = get_user_global_workspace_dir(resolved_user_id)

    if resolved_global is None or not resolved_global.exists():
        return []

    try:
        resources: list[dict[str, Any]] = []
        for file_path in sorted(resolved_global.rglob("*")):
            if not file_path.is_file():
                continue
            if any(part.startswith(".") for part in file_path.relative_to(resolved_global).parts):
                continue
            relative_path = file_path.relative_to(resolved_global).as_posix()
            resources.append(
                {
                    "relative_path": relative_path,
                    "display_path": f"/global/{relative_path}",
                    "size_bytes": file_path.stat().st_size,
                }
            )
            if len(resources) >= GLOBAL_RESOURCE_SCAN_LIMIT:
                logger.info(
                    "全局工作区资源超过扫描上限 %d，已截断。",
                    GLOBAL_RESOURCE_SCAN_LIMIT,
                )
                break
        return resources
    except Exception as exc:
        logger.warning("扫描全局工作区资源失败: %s", exc)
        return []


def _normalize_attached_file_path(raw_path: str) -> str:
    normalized = str(raw_path or "").strip().replace("\\", "/")
    if not normalized:
        return ""
    if normalized.startswith("/workspace/") or normalized.startswith("/global/"):
        return normalized
    return f"/workspace/{normalized.lstrip('/')}"


def resolve_mounted_knowledge_base_ids(
    *,
    user_id: str | None = None,
    workspace_dir: Path | str | None = None,
) -> list[str]:
    """返回用户名下全部知识库 ID（知识库已取消挂载，改为 AI 自行发现）。"""
    resolved_user_id = _resolve_user_id(user_id)
    if not resolved_user_id:
        return []

    try:
        visible_knowledge_bases = get_sqlite_kb_service().list_knowledge_bases(resolved_user_id)
    except Exception as exc:
        logger.warning("列出用户知识库失败: %s", exc)
        return []

    return [str(kb.id) for kb in visible_knowledge_bases if getattr(kb, "id", None)]


def resolve_mounted_knowledge_graph_ids(
    *,
    user_id: str | None = None,
    workspace_dir: Path | str | None = None,
) -> list[str]:
    """返回全部知识图谱 ID（扫描文件系统发现，覆盖 workspace 和 global 两个位置）。"""
    resolved_user_id = _resolve_user_id(user_id)
    if not resolved_user_id:
        return []

    resolved_workspace = _resolve_workspace_dir(workspace_dir)
    workspace_dirs = [resolved_workspace] if resolved_workspace else None

    try:
        from app.graphrag.core import SQLiteGraphStore

        db_files = SQLiteGraphStore._scan_graph_dirs(
            resolved_user_id,
            workspace_dirs=workspace_dirs,
        )
        return sorted(db_file.stem for db_file in db_files)
    except Exception as exc:
        logger.warning("扫描知识图谱目录失败: %s", exc)
        return []


def resolve_workspace_database_mount_ids(
    *,
    workspace_dir: Path | str | None = None,
) -> list[str]:
    resolved_workspace = _resolve_workspace_dir(workspace_dir)
    if resolved_workspace is None:
        return []

    mount_data = read_workspace_database_mount_data(resolved_workspace)
    raw_ids = mount_data.get("connector_ids", [])
    if not isinstance(raw_ids, list):
        return []
    return [str(item).strip() for item in raw_ids if str(item).strip()]


def resolve_workspace_database_mount_summaries(
    *,
    user_id: str | None = None,
    workspace_dir: Path | str | None = None,
) -> list[dict[str, Any]]:
    resolved_user_id = _resolve_user_id(user_id)
    mounted_ids = resolve_workspace_database_mount_ids(workspace_dir=workspace_dir)
    if not resolved_user_id or not mounted_ids:
        return []

    try:
        visible_connectors = DatabaseConnectorService(WORKSPACE_DIR).list_connectors(
            resolved_user_id
        )
    except Exception as exc:
        logger.warning("读取当前任务工作区数据库挂载失败: %s", exc)
        return [
            {"connector_id": connector_id, "name": connector_id, "db_type": None}
            for connector_id in mounted_ids
        ]

    visible_by_id = {
        str(item.connector_id): item
        for item in visible_connectors
        if getattr(item, "connector_id", None)
    }
    summaries: list[dict[str, Any]] = []
    for connector_id in mounted_ids:
        matched = visible_by_id.get(connector_id)
        if matched is None:
            summaries.append({"connector_id": connector_id, "name": connector_id, "db_type": None})
            continue
        summaries.append(
            {
                "connector_id": connector_id,
                "name": getattr(matched, "name", connector_id) or connector_id,
                "db_type": getattr(matched, "db_type", None),
            }
        )
    return summaries


def resolve_current_session_database_resource_summaries(
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    workspace_id: str | None = None,
) -> list[dict[str, Any]]:
    """返回当前会话/工作区可见的数据库连接器摘要。"""
    resolved_user_id = _resolve_user_id(user_id)
    if not resolved_user_id:
        return []

    try:
        connectors = DatabaseConnectorService(WORKSPACE_DIR).list_connectors(
            resolved_user_id,
            workspace_id=workspace_id,
        )
    except Exception as exc:
        logger.warning("读取数据库连接器列表失败: %s", exc)
        return []

    summaries: list[dict[str, Any]] = []
    for conn in connectors:
        summaries.append(
            {
                "connector_id": str(getattr(conn, "connector_id", "") or "").strip(),
                "handle": f"connector:{getattr(conn, 'connector_id', '')}",
                "name": str(getattr(conn, "name", "") or "").strip()
                or str(getattr(conn, "connector_id", "") or "").strip(),
                "db_type": getattr(conn, "db_type", None),
                "readonly": bool(getattr(conn, "readonly", True)),
            }
        )
    return summaries


def resolve_mounted_knowledge_base_summaries(
    *,
    user_id: str | None = None,
    workspace_dir: Path | str | None = None,
) -> list[dict[str, Any]]:
    resolved_user_id = _resolve_user_id(user_id)
    mounted_ids = resolve_mounted_knowledge_base_ids(
        user_id=resolved_user_id, workspace_dir=workspace_dir
    )
    if not resolved_user_id or not mounted_ids:
        return []

    try:
        visible_knowledge_bases = get_sqlite_kb_service().list_knowledge_bases(resolved_user_id)
    except Exception as exc:
        logger.warning("读取用户知识库失败: %s", exc)
        return [{"id": kb_id, "name": kb_id, "document_count": None} for kb_id in mounted_ids]

    visible_by_id = {
        str(item.id): item for item in visible_knowledge_bases if getattr(item, "id", None)
    }
    summaries: list[dict[str, Any]] = []
    for kb_id in mounted_ids:
        matched = visible_by_id.get(kb_id)
        if matched is None:
            summaries.append({"id": kb_id, "name": kb_id, "document_count": None})
            continue
        summaries.append(
            {
                "id": kb_id,
                "name": getattr(matched, "name", kb_id) or kb_id,
                "document_count": getattr(matched, "document_count", None),
            }
        )
    return summaries


def build_task_resource_context(
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    workspace_dir: Path | str | None = None,
    attached_files: Sequence[str] | None = None,
) -> dict[str, Any]:
    resolved_workspace = _resolve_workspace_dir(workspace_dir)
    mounted_knowledge_bases = resolve_mounted_knowledge_base_summaries(
        user_id=user_id,
        workspace_dir=resolved_workspace,
    )
    mounted_knowledge_graph_ids = resolve_mounted_knowledge_graph_ids(
        user_id=user_id,
        workspace_dir=resolved_workspace,
    )
    workspace_database_mounts = resolve_workspace_database_mount_summaries(
        user_id=user_id,
        workspace_dir=resolved_workspace,
    )
    workspace_id = resolved_workspace.name if resolved_workspace else None
    current_session_database_resources = resolve_current_session_database_resource_summaries(
        user_id=user_id,
        session_id=session_id,
        workspace_id=workspace_id,
    )
    normalized_attached_files = [
        normalized
        for normalized in (_normalize_attached_file_path(item) for item in (attached_files or []))
        if normalized
    ]
    resolved_global_workspace = _resolve_global_workspace_dir()
    if resolved_global_workspace is None and user_id:
        resolved_global_workspace = get_user_global_workspace_dir(user_id)
    global_workspace_resources = resolve_global_workspace_resources(
        user_id=user_id,
        global_workspace_dir=resolved_global_workspace,
    )
    direct_reference_objects: set[str] = set()
    for item in current_session_database_resources:
        handle = str(item.get("handle") or "").strip()
        if handle:
            direct_reference_objects.add(f"db_handle:{handle}")
    for item in workspace_database_mounts:
        connector_id = str(item.get("connector_id") or "").strip()
        if connector_id:
            direct_reference_objects.add(f"connector:{connector_id}")
    for item in mounted_knowledge_bases:
        kb_id = str(item.get("id") or "").strip()
        if kb_id:
            direct_reference_objects.add(f"kb:{kb_id}")
    for graph_id in mounted_knowledge_graph_ids:
        normalized_graph_id = str(graph_id).strip()
        if normalized_graph_id:
            direct_reference_objects.add(f"kg:{normalized_graph_id}")
    for attached_file in normalized_attached_files:
        normalized_file = str(attached_file).strip()
        if normalized_file:
            direct_reference_objects.add(f"file:{normalized_file}")
    for global_resource in global_workspace_resources:
        display_path = str(global_resource.get("display_path") or "").strip()
        if display_path:
            direct_reference_objects.add(f"file:{display_path}")

    workspace_mount_summary = {
        "database_mount_count": len(workspace_database_mounts),
        "knowledge_base_mount_count": len(mounted_knowledge_bases),
        "knowledge_graph_mount_count": len(mounted_knowledge_graph_ids),
    }

    current_session_resource_summary = {
        "database_handle_count": len(current_session_database_resources),
        "attachment_count": len(normalized_attached_files),
    }

    return {
        "workspace_dir": str(resolved_workspace) if resolved_workspace else None,
        "global_workspace_dir": (
            str(resolved_global_workspace) if resolved_global_workspace else None
        ),
        "workspace_database_mounts": workspace_database_mounts,
        "mounted_knowledge_bases": mounted_knowledge_bases,
        "mounted_knowledge_graph_ids": mounted_knowledge_graph_ids,
        "current_session_database_resources": current_session_database_resources,
        "attached_files": normalized_attached_files,
        "global_workspace_resources": global_workspace_resources,
        "workspace_mount_summary": workspace_mount_summary,
        "current_session_resource_summary": current_session_resource_summary,
        "global_workspace_resource_count": len(global_workspace_resources),
        "direct_reference_object_count": len(direct_reference_objects),
    }


def format_task_resource_context_for_prompt(resource_context: dict[str, Any] | None) -> str:
    if not resource_context:
        return ""

    lines: list[str] = []
    workspace_database_mounts = resource_context.get("workspace_database_mounts", []) or []
    mounted_knowledge_bases = resource_context.get("mounted_knowledge_bases", []) or []
    mounted_knowledge_graph_ids = resource_context.get("mounted_knowledge_graph_ids", []) or []
    current_session_database_resources = (
        resource_context.get("current_session_database_resources", []) or []
    )
    attached_files = resource_context.get("attached_files", []) or []
    workspace_mount_summary = resource_context.get("workspace_mount_summary", {}) or {}
    current_session_resource_summary = (
        resource_context.get("current_session_resource_summary", {}) or {}
    )
    global_workspace_resources = resource_context.get("global_workspace_resources", []) or []
    global_workspace_resource_count = int(
        resource_context.get("global_workspace_resource_count") or 0
    )
    direct_reference_object_count = int(resource_context.get("direct_reference_object_count") or 0)

    if workspace_mount_summary:
        database_mount_count = int(workspace_mount_summary.get("database_mount_count") or 0)
        knowledge_base_mount_count = int(
            workspace_mount_summary.get("knowledge_base_mount_count") or 0
        )
        knowledge_graph_mount_count = int(
            workspace_mount_summary.get("knowledge_graph_mount_count") or 0
        )
        mount_summary_text = (
            f"- 工作区挂载摘要：数据库 {database_mount_count} 个、"
            f"知识库 {knowledge_base_mount_count} 个、"
            f"知识图谱 {knowledge_graph_mount_count} 个"
        )
        lines.append(mount_summary_text)

    if current_session_resource_summary:
        database_handle_count = int(
            current_session_resource_summary.get("database_handle_count") or 0
        )
        attachment_count = int(current_session_resource_summary.get("attachment_count") or 0)
        lines.append(
            f"- 当前会话资源摘要：数据库句柄 {database_handle_count} 个、"
            f"当前轮附件 {attachment_count} 个"
        )

    if global_workspace_resources:
        rendered_globals = []
        for item in global_workspace_resources[:RESOURCE_PROMPT_ITEM_LIMIT]:
            display_path = str(item.get("display_path") or "").strip()
            if display_path:
                rendered_globals.append(display_path)
        lines.append(f"- 全局工作区资源：共 {global_workspace_resource_count} 个文件")
        if rendered_globals:
            lines.append("  " + "；".join(rendered_globals))
        if global_workspace_resource_count > RESOURCE_PROMPT_ITEM_LIMIT:
            lines.append(f"  ... 等共 {global_workspace_resource_count} 个文件")
            lines.append("  文件较多，如需定位特定文件，请用 Shell 或文件工具按路径搜索。")
        lines.append("  全局资源跨所有工作区共享，使用 /global/... 路径引用。")
    else:
        lines.append("- 全局工作区资源：暂无")

    lines.append(f"- 可直接引用资源对象数：{direct_reference_object_count}")

    if workspace_database_mounts:
        rendered_connectors = []
        for item in workspace_database_mounts[:RESOURCE_PROMPT_ITEM_LIMIT]:
            name = str(item.get("name") or item.get("connector_id") or "unknown").strip()
            connector_id = str(item.get("connector_id") or "").strip()
            db_type = str(item.get("db_type") or "").strip()
            if db_type:
                rendered_connectors.append(f"{name}({connector_id}, {db_type})")
            else:
                rendered_connectors.append(f"{name}({connector_id})")
        lines.append(
            f"- 当前任务工作区挂载了 {len(workspace_database_mounts)} 个数据库连接："
            + "；".join(rendered_connectors)
        )

    if mounted_knowledge_bases:
        rendered_items = []
        for item in mounted_knowledge_bases[:RESOURCE_PROMPT_ITEM_LIMIT]:
            name = str(item.get("name") or item.get("id") or "unknown").strip()
            kb_id = str(item.get("id") or "").strip()
            document_count = item.get("document_count")
            if isinstance(document_count, int):
                rendered_items.append(f"{name}({kb_id}, {document_count} 篇文档)")
            else:
                rendered_items.append(f"{name}({kb_id})")
        lines.append(
            f"- 当前用户共有 {len(mounted_knowledge_bases)} 个知识库可用："
            + "；".join(rendered_items)
        )
        lines.append("- 根据对话内容选择最合适的知识库进行检索。")

    if mounted_knowledge_graph_ids:
        rendered_graphs = "、".join(mounted_knowledge_graph_ids[:RESOURCE_PROMPT_ITEM_LIMIT])
        lines.append(
            f"- 当前用户共有 {len(mounted_knowledge_graph_ids)} 个知识图谱可用：{rendered_graphs}"
        )
        lines.append("- 若问题需要实体关系或概念网络，自行判断查询哪个知识图谱。")

    if current_session_database_resources:
        rendered_session_handles = []
        for item in current_session_database_resources[:RESOURCE_PROMPT_ITEM_LIMIT]:
            name = str(item.get("name") or item.get("connector_id") or "unknown").strip()
            handle = str(item.get("handle") or "").strip()
            db_type = str(item.get("db_type") or "").strip()
            if handle and db_type:
                rendered_session_handles.append(f"{name}[{handle}, {db_type}]")
            elif handle:
                rendered_session_handles.append(f"{name}[{handle}]")
            else:
                rendered_session_handles.append(name)
        lines.append(
            f"- 当前会话已挂载 {len(current_session_database_resources)} 个数据库资源："
            + "；".join(rendered_session_handles)
        )
        lines.append("- 查询数据库时优先使用这些已挂载句柄，不要猜测不存在的 handle。")

    if attached_files:
        rendered_attachments = "、".join(attached_files[:RESOURCE_PROMPT_ITEM_LIMIT])
        lines.append("- 当前轮附件：" + rendered_attachments)
        if len(attached_files) > RESOURCE_PROMPT_ITEM_LIMIT:
            lines.append(f"  ... 等共 {len(attached_files)} 个附件")
        lines.append("- 如果用户问题明显围绕这些附件，优先查看这些文件，不要先查知识图谱。")

    return "\n".join(lines)
