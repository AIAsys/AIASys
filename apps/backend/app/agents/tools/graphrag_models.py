"""
GraphRAG 工具 — Pydantic 参数模型与类型别名

从 graphrag_tool.py 拆分，包含所有 Tool 的 params 模型和 Literal 类型。
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

GraphRelationDirection = Literal["both", "outgoing", "incoming"]
GraphUploadExtractionMode = Literal["basic", "enhanced", "docling"]


class GraphEntitySearchParams(BaseModel):
    """知识图谱实体搜索参数"""

    query: str = Field(description="要搜索的实体关键词或短语", min_length=1)
    entity_type: Optional[str] = Field(
        default=None,
        description="可选的实体类型过滤，例如 person、organization、technology",
    )
    graph_id: Optional[str] = Field(
        default=None,
        description="可选。显式指定某一个知识图谱 ID；默认使用当前任务主图谱/挂载图谱",
    )
    limit: int = Field(
        default=8,
        ge=1,
        le=20,
        description="返回的实体数量上限，默认 8，最多 20",
    )


class GraphEntityDetailParams(BaseModel):
    """知识图谱实体详情参数"""

    entity_name: str = Field(
        description="实体名称，通常来自 SearchKnowledgeGraphEntities 的搜索结果"
    )
    graph_id: Optional[str] = Field(
        default=None,
        description="可选。显式指定图谱 ID；默认先查当前任务主图谱，再查其他已挂载图谱",
    )


class EntityRelationsParams(BaseModel):
    """知识图谱实体关系查询参数"""

    base_id: str = Field(description="知识图谱 ID，通常来自 ListKnowledgeGraphs 的 id")
    entity_name: str = Field(description="实体名称或实体 ID，通常来自实体搜索/实体详情结果")
    relation_type: Optional[str] = Field(
        default=None,
        description="可选。按关系类型或关系描述过滤，例如 depends_on、uses、影响",
    )
    direction: GraphRelationDirection = Field(
        default="both",
        description="关系方向。both 查询双向，outgoing 查询从该实体发出的关系，incoming 查询指向该实体的关系",
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="返回关系数量上限，默认 20，最多 100",
    )


class CommunityReportParams(BaseModel):
    """知识图谱社区报告参数"""

    base_id: str = Field(description="知识图谱 ID，通常来自 ListKnowledgeGraphs 的 id")
    community_id: Optional[str] = Field(
        default=None,
        description="可选。只返回指定社区 ID 的报告；不填则返回当前层级所有社区报告",
    )
    level: int = Field(
        default=0,
        ge=0,
        description="社区层级，默认 0，对齐 GraphRAG 社区报告 API 的 level 参数",
    )


class ListKnowledgeGraphsParams(BaseModel):
    """列出知识图谱参数"""

    scope: str = Field(
        default="mounted",
        description='默认只列出当前任务已挂载的知识图谱；如需查看全部可切换为 "all"',
    )


class CreateKnowledgeGraphParams(BaseModel):
    """创建知识图谱参数"""

    graph_id: str = Field(
        description="知识图谱 ID，只能包含字母、数字、下划线、中划线和点号",
        min_length=1,
        max_length=120,
    )
    name: Optional[str] = Field(
        default=None,
        description="可选。知识图谱展示名称；不填则使用 graph_id",
        max_length=200,
    )
    description: Optional[str] = Field(
        default=None,
        description="可选。知识图谱说明",
        max_length=1000,
    )
    scope: Literal["workspace", "global"] = Field(
        default="workspace",
        description="创建位置：workspace（当前工作区）或 global（全局工作区），默认 workspace",
    )
    overwrite: bool = Field(
        default=False,
        description="目标图谱已存在时是否覆盖。默认 false，避免误删已有图谱",
    )


class DeleteKnowledgeGraphParams(BaseModel):
    """删除知识图谱参数"""

    graph_id: str = Field(description="要删除的知识图谱 ID", min_length=1)


class CreateGraphEntityParams(BaseModel):
    """创建知识图谱实体参数"""

    base_id: str = Field(description="知识图谱 ID，通常来自 ListKnowledgeGraphs 的 id")
    name: str = Field(description="实体名称", min_length=1, max_length=300)
    entity_type: str = Field(
        default="concept",
        description="实体类型，例如 concept、person、organization、technology",
        max_length=120,
    )
    description: Optional[str] = Field(
        default="",
        description="实体说明",
        max_length=4000,
    )
    properties: dict[str, object] = Field(
        default_factory=dict,
        description="实体附加属性，必须是 JSON 对象",
    )


class UpdateGraphEntityParams(BaseModel):
    """更新知识图谱实体参数"""

    base_id: str = Field(description="知识图谱 ID，通常来自 ListKnowledgeGraphs 的 id")
    entity_id: str = Field(description="实体 ID 或实体名称", min_length=1)
    name: Optional[str] = Field(default=None, description="新的实体名称", max_length=300)
    entity_type: Optional[str] = Field(default=None, description="新的实体类型", max_length=120)
    description: Optional[str] = Field(default=None, description="新的实体说明", max_length=4000)
    properties: Optional[dict[str, object]] = Field(
        default=None,
        description="新的实体附加属性；传入后会替换原 properties",
    )


class DeleteGraphEntityParams(BaseModel):
    """删除知识图谱实体参数"""

    base_id: str = Field(description="知识图谱 ID，通常来自 ListKnowledgeGraphs 的 id")
    entity_id: str = Field(description="实体 ID 或实体名称", min_length=1)


class CreateGraphRelationParams(BaseModel):
    """创建知识图谱关系参数"""

    base_id: str = Field(description="知识图谱 ID，通常来自 ListKnowledgeGraphs 的 id")
    source_entity_id: str = Field(description="源实体 ID 或实体名称", min_length=1)
    target_entity_id: str = Field(description="目标实体 ID 或实体名称", min_length=1)
    relation_type: str = Field(
        default="related_to",
        description="关系类型，例如 depends_on、uses、supports、related_to",
        max_length=160,
    )
    description: Optional[str] = Field(
        default="",
        description="关系说明",
        max_length=4000,
    )
    strength: float = Field(
        default=1.0,
        description="关系强度，默认 1.0",
        ge=0,
    )
    properties: dict[str, object] = Field(
        default_factory=dict,
        description="关系附加属性，必须是 JSON 对象",
    )


class UploadDocumentsToGraphParams(BaseModel):
    """上传工作区文档到知识图谱参数"""

    base_id: str = Field(description="知识图谱 ID，通常来自 ListKnowledgeGraphs 的 id")
    files: list[str] = Field(
        description=(
            "要导入的文件路径列表。支持相对路径、/workspace/... 和 /global/...。"
            "文件会先读取，再按 GraphRAG 文档上传逻辑抽取文本并构建图谱。"
        ),
        min_length=1,
    )
    doc_id_prefix: Optional[str] = Field(
        default=None,
        description="可选。给批量导入生成 doc_id 前缀；不填则由 GraphRAG 根据内容生成",
    )
    resolve_entities: bool = Field(
        default=True,
        description="是否执行实体消歧，默认 true",
    )
    extraction_mode: Optional[GraphUploadExtractionMode] = Field(
        default=None,
        description="可选文档解析模式：basic、enhanced、docling。不填时使用系统默认模式。",
    )
