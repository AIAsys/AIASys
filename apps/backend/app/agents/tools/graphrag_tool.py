"""
GraphRAG 工具集

允许 Agent 搜索当前任务已挂载知识图谱中的实体，查看实体详情，
查询实体关系，生成社区报告，并把工作区文件导入知识图谱。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.graphrag import GraphRAGService
from app.graphrag.core import SQLiteGraphStore
from app.services.history import (
    current_global_workspace,
    current_user_id,
    current_workspace,
)
from app.services.task_resource_context import (
    resolve_mounted_knowledge_graph_ids,
)

# 当前 capability catalog 和系统预设使用本模块路径注册知识图谱工具。
from .graphrag_models import (  # noqa: F401
    CommunityReportParams,
    CreateGraphEntityParams,
    CreateGraphRelationParams,
    CreateKnowledgeGraphParams,
    DeleteGraphEntityParams,
    DeleteKnowledgeGraphParams,
    EntityRelationsParams,
    GraphEntityDetailParams,
    GraphEntitySearchParams,
    GraphRelationDirection,
    GraphUploadExtractionMode,
    ListKnowledgeGraphsParams,
    UpdateGraphEntityParams,
    UploadDocumentsToGraphParams,
)
from .graphrag_relations import QueryEntityRelations  # noqa: F401
from .graphrag_upload import UploadDocumentsToGraph  # noqa: F401

logger = logging.getLogger(__name__)

_GRAPH_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


def _resolve_graph_workspace_root(scope: str) -> Path:
    """根据 scope 解析图谱 .db 文件所在工作区根目录。"""
    if scope == "global":
        global_ws = current_global_workspace.get()
        if global_ws is None:
            raise ValueError("当前上下文未设置全局工作区，无法创建到全局工作区")
        return Path(global_ws).resolve()
    workspace = current_workspace.get()
    if workspace is None:
        raise ValueError("当前上下文未设置工作区，无法创建知识图谱")
    return Path(workspace).resolve()


def _find_graph_db_path(user_id: str, graph_id: str) -> Path | None:
    """在 workspace 和 global 两个位置查找图谱 .db 文件。"""
    workspace = current_workspace.get()
    global_ws = current_global_workspace.get()
    return SQLiteGraphStore.find_db_path(
        user_id,
        graph_id,
        workspace_root=Path(workspace).resolve() if workspace else None,
        global_workspace_root=Path(global_ws).resolve() if global_ws else None,
    )


_graphrag_services: dict[tuple[str, str], GraphRAGService] = {}
_MAX_CACHED_SERVICES = 16


def _resolve_current_user_id_for_graph_tools() -> str:
    user_id = current_user_id.get()
    if user_id:
        return user_id

    workspace = current_workspace.get()
    if workspace:
        parts = Path(workspace).resolve().parts
        for index, part in enumerate(parts):
            if part == "workspaces" and index + 1 < len(parts):
                return parts[index + 1]

    return "local_default"


def get_graphrag_service_for_tools(
    graph_id: str = "system",
    *,
    auto_init_llm: bool = False,
) -> GraphRAGService:
    user_id = _resolve_current_user_id_for_graph_tools()
    cache_key = (user_id, graph_id)
    service = _graphrag_services.get(cache_key)
    if service is None:
        if len(_graphrag_services) >= _MAX_CACHED_SERVICES:
            oldest = next(iter(_graphrag_services))
            logger.warning(
                "GraphRAG 服务缓存已满(%d)，淘汰最旧条目: %s", _MAX_CACHED_SERVICES, oldest
            )
            _graphrag_services.pop(oldest, None)
        db_path = _find_graph_db_path(user_id, graph_id)
        if db_path is None:
            raise ValueError(f"知识图谱不存在: {graph_id}")
        store = SQLiteGraphStore(user_id=user_id, kg_id=graph_id, db_path=db_path)
        service = GraphRAGService(
            kb_id=graph_id,
            auto_init_llm=auto_init_llm,
            user_id=user_id if auto_init_llm else None,
            graph_store=store,
        )
        _graphrag_services[cache_key] = service
    else:
        # LRU：将访问条目移到末尾
        _graphrag_services.pop(cache_key, None)
        _graphrag_services[cache_key] = service
        if auto_init_llm and not service._auto_init_llm:
            service._auto_init_llm = True
            if service.user_id is None:
                service.user_id = user_id
            if service.llm_client is None and service.extractor is None:
                service._llm_initialized = False
    return service


def reset_graphrag_service_for_tools() -> None:
    _graphrag_services.clear()


def _normalize_graph_id(graph_id: str) -> str:
    normalized = str(graph_id or "").strip()
    if not normalized:
        raise ValueError("知识图谱 ID 不能为空")
    if normalized in {".", ".."} or not _GRAPH_ID_PATTERN.fullmatch(normalized):
        raise ValueError("知识图谱 ID 只能包含字母、数字、下划线、中划线和点号")
    return normalized


def _resolve_target_graph_ids(graph_id: str | None = None) -> list[str]:
    normalized_graph_id = str(graph_id or "").strip()
    if normalized_graph_id:
        return [normalized_graph_id]

    mounted_graph_ids = resolve_mounted_knowledge_graph_ids()
    if mounted_graph_ids:
        return mounted_graph_ids

    return ["system"]


def _format_metadata(metadata: Dict[str, Any]) -> list[str]:
    if not metadata:
        return []

    lines: list[str] = ["元数据："]
    for key in sorted(metadata.keys()):
        value = metadata[key]
        if isinstance(value, (list, tuple)):
            rendered = ", ".join(str(item) for item in value[:5])
            if len(value) > 5:
                rendered += " ..."
        else:
            rendered = str(value)
        lines.append(f"- {key}: {rendered}")
    return lines


def _format_entity(entity: dict[str, Any]) -> list[str]:
    lines = [
        f"实体: {entity.get('name')}",
        f"ID: {entity.get('entity_id')}",
        f"类型: {entity.get('entity_type') or 'unknown'}",
        f"描述: {(entity.get('description') or '').strip() or '无描述'}",
    ]
    metadata = entity.get("properties") or {}
    lines.extend(_format_metadata(metadata))
    return lines


class CreateKnowledgeGraph(AiasysTool):
    """
    创建知识图谱。

    适用场景：
    - 用户希望新建一个图谱来承接后续文档构图
    - 用户已经给出图谱 ID 或名称，需要为后续 UploadDocumentsToGraph 准备目标
    """

    name: str = "CreateKnowledgeGraph"
    description: str = """
创建知识图谱。

默认创建在当前工作区 .aiasys/graphs/ 下，scope=global 时创建到全局工作区。
创建后返回 graph_id，后续可以用 UploadDocumentsToGraph 构图，或用实体/关系工具手工维护。

参数：
- graph_id: 知识图谱 ID，只能包含字母、数字、下划线、中划线和点号。
- name: 可选，展示名称。
- description: 可选，图谱说明。
- scope: 可选，创建位置，workspace（默认，当前工作区）或 global（全局工作区）。
- overwrite: 可选，目标图谱已存在时是否覆盖。默认 false。
"""
    params: type[BaseModel] = CreateKnowledgeGraphParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del ctx
        params = CreateKnowledgeGraphParams.model_validate(kwargs)
        try:
            graph_id = _normalize_graph_id(params.graph_id)
            user_id = _resolve_current_user_id_for_graph_tools()
            workspace_root = _resolve_graph_workspace_root(params.scope)
            graph_path = SQLiteGraphStore._db_path_for(workspace_root, graph_id)
            existed = graph_path.exists()
            if existed and not params.overwrite:
                return ToolResult(
                    content=(
                        f"知识图谱已存在：{graph_id}。" "如需覆盖，请显式传入 overwrite=true。"
                    ),
                    is_error=True,
                )
            if existed and params.overwrite:
                graph_path.unlink()
                _graphrag_services.pop((user_id, graph_id), None)

            store = SQLiteGraphStore(user_id=user_id, kg_id=graph_id, db_path=graph_path)
            graph_name = (params.name or graph_id).strip() or graph_id
            graph_description = (params.description or "").strip()
            store.set_metadata("name", graph_name)
            store.set_metadata("description", graph_description)
            stats = store.get_statistics()
            scope_label = "全局工作区" if params.scope == "global" else "当前工作区"
            return ToolResult(
                content="\n".join(
                    [
                        f"知识图谱创建成功：{graph_name}",
                        f"ID: {graph_id}",
                        f"位置: {scope_label}",
                        f"描述: {graph_description or '无'}",
                        f"实体数: {stats.get('entity_count', 0)}",
                        f"关系数: {stats.get('relation_count', 0)}",
                    ]
                ),
                artifacts=[
                    {
                        "knowledge_graph": {
                            "id": graph_id,
                            "name": graph_name,
                            "description": graph_description,
                            "scope": params.scope,
                            "entity_count": stats.get("entity_count", 0),
                            "relation_count": stats.get("relation_count", 0),
                        }
                    }
                ],
            )
        except Exception as exc:
            logger.error("创建知识图谱失败: %s", exc, exc_info=True)
            return ToolResult(content=f"创建知识图谱失败: {exc}", is_error=True)


class DeleteKnowledgeGraph(AiasysTool):
    """删除知识图谱。"""

    name: str = "DeleteKnowledgeGraph"
    description: str = """
删除知识图谱。

当用户明确要求删除某个知识图谱时使用。如果用户只给出图谱名称，先调用 ListKnowledgeGraphs 获取 ID 并向用户确认。

参数：
- graph_id: 要删除的知识图谱 ID。
"""
    params: type[BaseModel] = DeleteKnowledgeGraphParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del ctx
        params = DeleteKnowledgeGraphParams.model_validate(kwargs)
        try:
            graph_id = _normalize_graph_id(params.graph_id)
            user_id = _resolve_current_user_id_for_graph_tools()
            graph_path = _find_graph_db_path(user_id, graph_id)
            if graph_path is None:
                return ToolResult(content=f"知识图谱不存在：{graph_id}", is_error=True)
            graph_path.unlink()
            _graphrag_services.pop((user_id, graph_id), None)
            return ToolResult(
                content=f"知识图谱已删除：{graph_id}",
                artifacts=[{"knowledge_graph_id": graph_id, "deleted": True}],
            )
        except Exception as exc:
            logger.error("删除知识图谱失败: %s", exc, exc_info=True)
            return ToolResult(content=f"删除知识图谱失败: {exc}", is_error=True)


class CreateGraphEntity(AiasysTool):
    """在知识图谱中创建实体。"""

    name: str = "CreateGraphEntity"
    description: str = """
在指定知识图谱中创建实体节点。

通常先调用 ListKnowledgeGraphs 获取 base_id，再创建实体。

参数：
- base_id: 知识图谱 ID。
- name: 实体名称。
- entity_type: 实体类型，默认 concept。
- description: 可选，实体说明。
- properties: 可选，实体附加属性 JSON 对象。
"""
    params: type[BaseModel] = CreateGraphEntityParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del ctx
        params = CreateGraphEntityParams.model_validate(kwargs)
        try:
            service = get_graphrag_service_for_tools(_normalize_graph_id(params.base_id))
            created = service.create_entity(
                name=params.name,
                entity_type=params.entity_type,
                description=params.description or "",
                properties=params.properties,
            )
            return ToolResult(
                content="\n".join(
                    [f"知识图谱 {params.base_id} 已创建实体：", "", *_format_entity(created)]
                ),
                artifacts=[
                    {
                        "knowledge_graph_id": params.base_id,
                        "entity": created,
                    }
                ],
            )
        except Exception as exc:
            logger.error("创建知识图谱实体失败: %s", exc, exc_info=True)
            return ToolResult(content=f"创建知识图谱实体失败: {exc}", is_error=True)


class UpdateGraphEntity(AiasysTool):
    """更新知识图谱实体。"""

    name: str = "UpdateGraphEntity"
    description: str = """
更新指定知识图谱中的实体。

entity_id 可以传实体 ID，也可以传实体名称。只传需要修改的字段。
properties 一旦传入会替换原 properties。

参数：
- base_id: 知识图谱 ID。
- entity_id: 实体 ID 或实体名称。
- name / entity_type / description / properties: 要更新的字段。
"""
    params: type[BaseModel] = UpdateGraphEntityParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del ctx
        params = UpdateGraphEntityParams.model_validate(kwargs)
        try:
            service = get_graphrag_service_for_tools(_normalize_graph_id(params.base_id))
            current_entity = service.get_entity(params.entity_id)
            if not current_entity:
                return ToolResult(
                    content=f"知识图谱 {params.base_id} 中未找到实体：{params.entity_id}",
                    is_error=True,
                )
            updated = service.update_entity(
                entity_id=str(current_entity["entity_id"]),
                name=params.name,
                entity_type=params.entity_type,
                description=params.description,
                properties=params.properties,
            )
            if not updated:
                return ToolResult(
                    content=f"知识图谱 {params.base_id} 中未找到实体：{params.entity_id}",
                    is_error=True,
                )
            return ToolResult(
                content="\n".join(
                    [f"知识图谱 {params.base_id} 已更新实体：", "", *_format_entity(updated)]
                ),
                artifacts=[
                    {
                        "knowledge_graph_id": params.base_id,
                        "entity": updated,
                    }
                ],
            )
        except Exception as exc:
            logger.error("更新知识图谱实体失败: %s", exc, exc_info=True)
            return ToolResult(content=f"更新知识图谱实体失败: {exc}", is_error=True)


class DeleteGraphEntity(AiasysTool):
    """删除知识图谱实体和相关关系。"""

    name: str = "DeleteGraphEntity"
    description: str = """
删除指定知识图谱中的实体，并同步删除连接到该实体的关系。

entity_id 可以传实体 ID，也可以传实体名称。如果用户只给出模糊名称，先用 SearchKnowledgeGraphEntities 确认。

参数：
- base_id: 知识图谱 ID。
- entity_id: 实体 ID 或实体名称。
"""
    params: type[BaseModel] = DeleteGraphEntityParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del ctx
        params = DeleteGraphEntityParams.model_validate(kwargs)
        try:
            service = get_graphrag_service_for_tools(_normalize_graph_id(params.base_id))
            deleted = service.delete_entity(params.entity_id)
            if not deleted:
                return ToolResult(
                    content=f"知识图谱 {params.base_id} 中未找到实体：{params.entity_id}",
                    is_error=True,
                )
            return ToolResult(
                content="\n".join(
                    [
                        f"知识图谱 {params.base_id} 已删除实体：{deleted.get('name')}",
                        f"ID: {deleted.get('entity_id')}",
                        f"同步删除关系数: {deleted.get('deleted_relations', 0)}",
                    ]
                ),
                artifacts=[
                    {
                        "knowledge_graph_id": params.base_id,
                        "deleted_entity": deleted,
                    }
                ],
            )
        except Exception as exc:
            logger.error("删除知识图谱实体失败: %s", exc, exc_info=True)
            return ToolResult(content=f"删除知识图谱实体失败: {exc}", is_error=True)


class CreateGraphRelation(AiasysTool):
    """在知识图谱中创建两个实体之间的关系。"""

    name: str = "CreateGraphRelation"
    description: str = """
在指定知识图谱中创建两个实体之间的关系。

source_entity_id 和 target_entity_id 可以传实体 ID，也可以传实体名称。
关系创建前会校验两个实体存在，且不会创建完全相同的重复关系。

参数：
- base_id: 知识图谱 ID。
- source_entity_id: 源实体 ID 或实体名称。
- target_entity_id: 目标实体 ID 或实体名称。
- relation_type: 关系类型，默认 related_to。
- description: 可选，关系说明。
- strength: 可选，关系强度，默认 1.0。
- properties: 可选，关系附加属性 JSON 对象。
"""
    params: type[BaseModel] = CreateGraphRelationParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del ctx
        params = CreateGraphRelationParams.model_validate(kwargs)
        try:
            service = get_graphrag_service_for_tools(_normalize_graph_id(params.base_id))
            relation = service.create_relation(
                source_entity_id=params.source_entity_id,
                target_entity_id=params.target_entity_id,
                relation_type=params.relation_type,
                description=params.description or "",
                strength=params.strength,
                properties=params.properties,
            )
            lines = [
                f"知识图谱 {params.base_id} 已创建关系：",
                f"ID: {relation.get('relation_id')}",
                f"源实体: {relation.get('source_name')} ({relation.get('source')})",
                f"目标实体: {relation.get('target_name')} ({relation.get('target')})",
                f"类型: {relation.get('relation_type')}",
                f"强度: {relation.get('strength')}",
                f"描述: {(relation.get('description') or '').strip() or '无描述'}",
            ]
            lines.extend(_format_metadata(relation.get("properties") or {}))
            return ToolResult(
                content="\n".join(lines),
                artifacts=[
                    {
                        "knowledge_graph_id": params.base_id,
                        "relation": relation,
                    }
                ],
            )
        except Exception as exc:
            logger.error("创建知识图谱关系失败: %s", exc, exc_info=True)
            return ToolResult(content=f"创建知识图谱关系失败: {exc}", is_error=True)


def _format_community_summary(summary: dict[str, Any]) -> list[str]:
    entity_types = summary.get("entity_types") or {}
    key_entities = summary.get("key_entities") or []
    lines = [
        f"社区: {summary.get('community_id')}",
        f"规模: {summary.get('size', 0)} 个实体",
        f"权重: {summary.get('weight', 0)}",
    ]
    if entity_types:
        rendered_types = "，".join(f"{key}: {value}" for key, value in entity_types.items())
        lines.append(f"实体类型: {rendered_types}")
    if key_entities:
        lines.append(f"关键实体: {'，'.join(str(item) for item in key_entities[:10])}")
    return lines


class SearchKnowledgeGraphEntities(AiasysTool):
    """
    搜索当前任务知识图谱中的实体。

    适用场景：
    - 用户提到某个名词、设备、组织、概念，想确认图谱中是否存在
    - 想先浏览图谱命中的实体，再决定进一步分析哪个实体
    - 需要按实体类型筛选搜索结果
    """

    name: str = "SearchKnowledgeGraphEntities"
    description: str = """
搜索当前任务知识图谱中的实体。

适合在以下场景使用：
- 用户提到某个术语、设备、组织、概念，想确认图谱里是否存在相关实体
- 需要先用关键词粗搜，再进一步查看具体实体详情
- 想按 entity_type 过滤特定类别的实体

如果用户提到了具体的知识图谱名称但没有提供 ID，先调用 ListKnowledgeGraphs 获取图谱 ID，再将 graph_id 传入本工具进行查询。

参数：
- query: 搜索关键词
- entity_type: 可选实体类型过滤
- graph_id: 可选，显式指定某一个知识图谱 ID。当用户想查询特定图谱时使用。
- limit: 返回结果上限
"""
    params: type[BaseModel] = GraphEntitySearchParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = GraphEntitySearchParams.model_validate(kwargs)
        try:
            graph_ids = _resolve_target_graph_ids(params.graph_id)
            results: list[dict[str, Any]] = []
            seen: set[tuple[str, str]] = set()
            for graph_id in graph_ids:
                service = get_graphrag_service_for_tools(graph_id)
                graph_results = service.search(
                    query=params.query,
                    entity_type=params.entity_type,
                )
                for entity in graph_results:
                    entity_name = str(entity.get("name") or "").strip()
                    dedupe_key = (graph_id, entity_name)
                    if not entity_name or dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    results.append({**entity, "graph_id": graph_id})
            results = results[: params.limit]

            if not results:
                return ToolResult(
                    content=(
                        f'当前任务知识图谱中未找到与"{params.query}"相关的实体。'
                        "可以尝试换一个关键词，或去掉 entity_type 过滤。"
                    )
                )

            lines = [f"找到 {len(results)} 个相关实体：", ""]
            for index, entity in enumerate(results, 1):
                name = entity.get("name", "")
                entity_type = entity.get("entity_type", "unknown")
                description = (entity.get("description") or "无描述").strip()
                graph_id = entity.get("graph_id", "system")
                lines.append(f"[{index}] {name}")
                lines.append(f"  图谱: {graph_id}")
                lines.append(f"  类型: {entity_type}")
                lines.append(
                    f"  描述: {description[:300]}{'...' if len(description) > 300 else ''}"
                )
                lines.append("")

            lines.append("如需查看某个实体的完整详情，请继续调用 GetKnowledgeGraphEntityDetail。")
            return ToolResult(content="\n".join(lines))

        except Exception as exc:
            logger.error("知识图谱实体搜索失败: %s", exc, exc_info=True)
            return ToolResult(
                content=f"知识图谱实体搜索失败: {exc}",
                is_error=True,
            )


class GetKnowledgeGraphEntityDetail(AiasysTool):
    """
    查看知识图谱中单个实体的详情。

    适用场景：
    - 已经通过搜索拿到实体名称，需要查看描述和元数据
    - 想确认某个实体的标准化名称、实体类型和附加属性
    """

    name: str = "GetKnowledgeGraphEntityDetail"
    description: str = """
获取当前任务知识图谱中某个实体的详情。

通常先调用 SearchKnowledgeGraphEntities 找到候选实体，再把其中的 entity_name 传给本工具。

参数：
- entity_name: 实体名称
- graph_id: 可选，显式指定图谱 ID
"""
    params: type[BaseModel] = GraphEntityDetailParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = GraphEntityDetailParams.model_validate(kwargs)
        try:
            graph_ids = _resolve_target_graph_ids(params.graph_id)
            matched_entities: list[tuple[str, dict[str, Any]]] = []
            for graph_id in graph_ids:
                service = get_graphrag_service_for_tools(graph_id)
                entity = service.get_entity(params.entity_name)
                if entity:
                    matched_entities.append((graph_id, entity))

            if not matched_entities:
                return ToolResult(content=f'当前任务知识图谱中未找到实体"{params.entity_name}"。')

            lines: list[str] = []
            for graph_id, entity in matched_entities:
                metadata = entity.get("metadata") or {}
                lines.extend(
                    [
                        f"图谱: {graph_id}",
                        f"实体: {entity.get('name', params.entity_name)}",
                        f"类型: {entity.get('entity_type', 'unknown')}",
                        f"描述: {(entity.get('description') or '无描述').strip()}",
                    ]
                )
                lines.extend(_format_metadata(metadata))
                lines.append("")

            return ToolResult(content="\n".join(lines).strip())

        except Exception as exc:
            logger.error("获取知识图谱实体详情失败: %s", exc, exc_info=True)
            return ToolResult(
                content=f"获取知识图谱实体详情失败: {exc}",
                is_error=True,
            )


class GetCommunityReport(AiasysTool):
    """
    生成并查看知识图谱社区报告。

    适用场景：
    - 用户想了解图谱有哪些社区结构
    - 需要解释某个社区的主题、关键实体和内部关系
    - 需要把结构化社区摘要转换成可读分析报告
    """

    name: str = "GetCommunityReport"
    description: str = """
生成并查看指定知识图谱的社区报告。

社区报告依赖 GraphRAG LLM 配置。若用户只想看社区结构摘要，返回内容也会包含社区规模、权重、实体类型和关键实体。

参数：
- base_id: 知识图谱 ID
- community_id: 可选，指定社区 ID；不填则返回当前层级所有社区报告
- level: 可选，社区层级，默认 0
"""
    params: type[BaseModel] = CommunityReportParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del ctx
        params = CommunityReportParams.model_validate(kwargs)
        try:
            base_id = params.base_id.strip()
            if not base_id:
                return ToolResult(content="base_id 不能为空。", is_error=True)

            service = get_graphrag_service_for_tools(base_id, auto_init_llm=True)
            summaries = service.get_communities(level=params.level)
            summary_by_id = {str(summary.get("community_id")): summary for summary in summaries}

            selected_ids: list[str]
            if params.community_id:
                normalized_community_id = params.community_id.strip()
                if not normalized_community_id:
                    return ToolResult(content="community_id 不能为空。", is_error=True)
                selected_ids = [normalized_community_id]
            else:
                selected_ids = list(summary_by_id.keys())

            if not selected_ids:
                return ToolResult(
                    content=(
                        f"知识图谱 {base_id} 的 level={params.level} 暂无社区。"
                        "请先构建图谱，或换一个社区层级。"
                    )
                )

            raw_reports = await service.build_community_reports(level=params.level)
            reports = {str(key): value for key, value in raw_reports.items()}

            lines = [
                f"图谱: {base_id}",
                f"社区层级: {params.level}",
                f"报告数量: {len(selected_ids)}",
                "",
            ]
            missing_ids: list[str] = []
            for community_id in selected_ids:
                summary = summary_by_id.get(community_id)
                report = reports.get(community_id)
                if not summary and report is None:
                    missing_ids.append(community_id)
                    continue

                lines.append(f"## 社区 {community_id}")
                if summary:
                    lines.extend(_format_community_summary(summary))
                if report:
                    lines.extend(["", "报告:", str(report).strip()])
                else:
                    lines.extend(
                        [
                            "",
                            "报告: 当前未生成该社区的 LLM 报告；上方为社区结构摘要。",
                        ]
                    )
                lines.append("")

            if missing_ids:
                lines.append(f"未找到社区: {', '.join(missing_ids)}")

            return ToolResult(content="\n".join(lines).strip())

        except RuntimeError as exc:
            logger.error("生成知识图谱社区报告失败: %s", exc, exc_info=True)
            return ToolResult(
                content=("生成知识图谱社区报告失败: " f"{exc}"),
                is_error=True,
            )
        except Exception as exc:
            logger.error("获取知识图谱社区报告失败: %s", exc, exc_info=True)
            return ToolResult(
                content=f"获取知识图谱社区报告失败: {exc}",
                is_error=True,
            )


class ListKnowledgeGraphs(AiasysTool):
    """
    列出知识图谱工具 - 获取当前用户可用的知识图谱列表

    当需要查看用户有哪些知识图谱、获取图谱ID时使用此工具。

    使用场景：
    - 用户想查询知识图谱但不知道图谱ID
    - 需要展示用户所有的知识图谱供选择
    - 查看知识图谱的基本信息（实体数、关系数、文档数）
    """

    name: str = "ListKnowledgeGraphs"
    description: str = """
列出知识图谱。

默认优先列出当前任务已挂载的知识图谱；如果没有挂载，或显式指定 scope=all，再列出当前用户的全部知识图谱。

返回结果包含每个图谱的：
- id: 知识图谱唯一标识（查询时需要用到）
- entity_count: 实体数量
- relation_count: 关系数量
- document_count: 文档数量

使用示例：
用户问："我想查询我的知识图谱"
→ 先调用 ListKnowledgeGraphs 获取列表
→ 展示给用户选择
→ 用户选择后使用 SearchKnowledgeGraphEntities 查询具体内容
"""
    params: type[BaseModel] = ListKnowledgeGraphsParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = ListKnowledgeGraphsParams.model_validate(kwargs)
        try:
            mounted_graph_ids = resolve_mounted_knowledge_graph_ids() or []

            if params.scope.lower() == "mounted" and mounted_graph_ids:
                candidate_ids = mounted_graph_ids
                resolved_scope = "mounted"
            else:
                all_graphs = SQLiteGraphStore.list_graphs(
                    _resolve_current_user_id_for_graph_tools()
                )
                candidate_ids = [g["kg_id"] for g in all_graphs]
                resolved_scope = "all"

            if not candidate_ids:
                return ToolResult(
                    content="您还没有创建知识图谱。可以通过知识图谱管理页面创建一个。"
                )

            lines = [f"找到 {len(candidate_ids)} 个知识图谱：", ""]
            if resolved_scope == "mounted":
                lines.append("列出范围：当前任务已挂载知识图谱")
                lines.append("")
            else:
                lines.append("列出范围：用户全部知识图谱")
                lines.append("")

            for index, graph_id in enumerate(candidate_ids, 1):
                service = get_graphrag_service_for_tools(graph_id)
                stats = service.get_statistics()
                entity_count = stats.get("entity_count", 0)
                relation_count = stats.get("relation_count", 0)
                doc_count = stats.get("document_count", 0)
                marker = ""
                lines.extend(
                    [
                        f"[{index}] {graph_id}{marker}",
                        f"    实体数: {entity_count}",
                        f"    关系数: {relation_count}",
                        f"    文档数: {doc_count}",
                        "",
                    ]
                )

            return ToolResult(content="\n".join(lines))

        except Exception as exc:
            logger.error("列出知识图谱失败: %s", exc, exc_info=True)
            return ToolResult(
                content=f"列出知识图谱失败: {exc}",
                is_error=True,
            )
