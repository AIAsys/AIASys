"""
GraphRAG 工具 — 实体关系查询

从 graphrag_tool.py 拆分，包含 QueryEntityRelations。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult

from .graphrag_models import EntityRelationsParams

logger = logging.getLogger(__name__)


class QueryEntityRelations(AiasysTool):
    """
    查询知识图谱中某个实体的直接关系。

    适用场景：
    - 用户想知道某个实体和其他实体有什么联系
    - 需要按关系类型筛选实体的一跳关系
    - 已经通过实体搜索拿到实体名称，需要继续分析网络结构
    """

    name: str = "QueryEntityRelations"
    description: str = """
查询指定知识图谱中某个实体的直接关系。

通常先调用 ListKnowledgeGraphs 获取 base_id，再调用 SearchKnowledgeGraphEntities 找到 entity_name。

参数：
- base_id: 知识图谱 ID
- entity_name: 实体名称或实体 ID
- relation_type: 可选，按关系类型或关系描述过滤
- direction: 可选，both / outgoing / incoming
- limit: 可选，返回关系数量上限

返回结果包含关系两端实体、关系类型、关系描述、强度和来源文档 ID。
"""
    params: type[BaseModel] = EntityRelationsParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del ctx
        params = EntityRelationsParams.model_validate(kwargs)
        try:
            base_id = params.base_id.strip()
            if not base_id:
                return ToolResult(content="base_id 不能为空。", is_error=True)

            from .graphrag_tool import get_graphrag_service_for_tools

            service = get_graphrag_service_for_tools(base_id)
            entity, relations = await service.graph_store.get_entity_relations(
                entity_name=params.entity_name.strip(),
                relation_type=params.relation_type,
                direction=params.direction,
                limit=params.limit,
            )

            if entity is None:
                return ToolResult(
                    content=f"知识图谱 {base_id} 中未找到实体“{params.entity_name}”。"
                )

            if not relations:
                relation_hint = (
                    f"、relation_type={params.relation_type}" if params.relation_type else ""
                )
                return ToolResult(
                    content=(
                        f"知识图谱 {base_id} 中未找到实体“{entity['name']}”"
                        f"匹配 direction={params.direction}{relation_hint} 的直接关系。"
                    )
                )

            lines = [
                f"图谱: {base_id}",
                f"实体: {entity['name']} ({entity.get('entity_type') or 'unknown'})",
                f"找到 {len(relations)} 条直接关系：",
                "",
            ]
            for index, relation in enumerate(relations, 1):
                source = relation.get("source") or ""
                target = relation.get("target") or ""
                relation_type = relation.get("relation_type") or "unknown"
                description = (relation.get("description") or "").strip()
                strength = relation.get("strength")
                source_doc_id = relation.get("source_doc_id") or ""
                lines.extend(
                    [
                        f"[{index}] {source} -> {target}",
                        f"  类型: {relation_type}",
                        f"  方向: {relation.get('direction') or params.direction}",
                        f"  强度: {strength}",
                        f"  描述: {description or '无描述'}",
                    ]
                )
                if source_doc_id:
                    lines.append(f"  来源文档: {source_doc_id}")
                lines.append("")

            return ToolResult(content="\n".join(lines).strip())

        except Exception as exc:
            logger.error("查询知识图谱实体关系失败: %s", exc, exc_info=True)
            return ToolResult(
                content=f"查询知识图谱实体关系失败: {exc}",
                is_error=True,
            )
