"""
GraphRAG 服务 - 对外暴露的接口
使用系统 llm_config.json 配置
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from app.document_extraction import get_document_extraction_service

from .core import SQLiteGraphStore
from .core.community_detection import CommunityDetector, CommunityReporter
from .core.entity_extractor import EntityExtractor
from .core.entity_resolution import EntityResolver
from .llm_adapter import create_llm_client_from_config
from .utils.locks import get_lock_manager


class GraphRAGService:
    """
    GraphRAG 服务

    系统级知识图谱，自动从 llm_config.json 读取 LLM 配置
    """

    def __init__(
        self,
        kb_id: str = "system",
        llm_client=None,
        enable_resolution: bool = True,
        enable_communities: bool = True,
        auto_init_llm: bool = True,
        user_id: Optional[str] = None,
        graph_store=None,
    ):
        """
        初始化 GraphRAG 服务

        Args:
            kb_id: 知识库 ID
            llm_client: LLM 客户端（可选，不传则自动从 llm_config.json 初始化）
            enable_resolution: 是否启用实体消歧
            enable_communities: 是否启用社区发现
            auto_init_llm: 是否自动从系统配置初始化 LLM
            user_id: 用户 ID（用于读取用户特定的配置）
            graph_store: 外部传入的图存储实例（可选）
        """
        self.kb_id = kb_id
        self.user_id = user_id

        # 初始化存储
        if graph_store is not None:
            self.graph_store = graph_store
        else:
            raise ValueError("graph_store is required for GraphRAGService")

        # 初始化 LLM 客户端
        self.llm_client = llm_client
        self._auto_init_llm = auto_init_llm

        # 初始化抽取器（懒加载）
        self.extractor: Optional[EntityExtractor] = None
        self.resolver: Optional[EntityResolver] = None
        self.community_detector: Optional[CommunityDetector] = None
        self.community_reporter: Optional[CommunityReporter] = None
        self._enable_communities = enable_communities
        self._enable_resolution = enable_resolution
        self._lock_manager = None

        # 社区缓存
        self._communities: Optional[Dict[int, Dict[str, Any]]] = None
        self._llm_initialized = False

    def _get_lock_manager(self):
        """按需初始化锁管理器，避免只读接口首屏被 Redis 探测阻塞。"""
        if self._lock_manager is None:
            self._lock_manager = get_lock_manager()
        return self._lock_manager

    def _get_community_detector(self) -> Optional[CommunityDetector]:
        """按需初始化社区检测器，避免总览页首屏加载 graspologic。"""
        if not self._enable_communities:
            return None
        if self.community_detector is None:
            self.community_detector = CommunityDetector()
        return self.community_detector

    async def _init_llm(self):
        """懒加载初始化 LLM 客户端（从 llm_config.json）"""
        if self._llm_initialized:
            return

        if self.llm_client is None and self._auto_init_llm:
            # 从系统配置创建 LLM 客户端
            # 自动读取用户默认层模型配置
            self.llm_client = await create_llm_client_from_config(user_id=self.user_id)

        # 如果成功获取 LLM 客户端，初始化相关组件
        if self.llm_client:
            self.extractor = EntityExtractor(self.llm_client)
            self.resolver = EntityResolver(self.llm_client)
            self.community_reporter = CommunityReporter(self.llm_client)

        self._llm_initialized = True

    def _ensure_llm(self):
        """确保 LLM 已初始化（同步检查）"""
        if not self._llm_initialized:
            raise RuntimeError(
                "LLM client not initialized. " "Please call await service._init_llm() first."
            )
        if self.extractor is None:
            raise RuntimeError(
                "LLM client not available. "
                "Please configure LLM provider in system settings (Settings > LLM Config). "
                "Ensure at least one enabled non-coding text model is available for GraphRAG."
            )

    async def add_document(
        self,
        content: str,
        doc_id: Optional[str] = None,
        resolve_entities: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        添加文档并构建知识图谱

        Args:
            content: 文档内容
            doc_id: 文档ID（可选）
            resolve_entities: 是否执行实体消歧，None 表示使用服务级默认设置

        Returns:
            构建结果统计
        """
        # 应用服务级默认
        if resolve_entities is None:
            resolve_entities = self._enable_resolution

        # 确保 LLM 已初始化
        await self._init_llm()
        self._ensure_llm()

        if not doc_id:
            import hashlib

            doc_id = hashlib.md5(content.encode()).hexdigest()[:12]

        # 获取分布式锁
        async with self._get_lock_manager().lock(f"add_doc:{doc_id}", timeout=300):
            # 抽取实体和关系
            result = await self.extractor.extract(content, doc_id)

            entities = result.entities
            relations = result.relations

            # 实体消歧
            merge_map = {}
            if resolve_entities and self.resolver and len(entities) > 1:
                merge_map = await self.resolver.resolve(entities)
                if merge_map:
                    entities = self.resolver.merge_entities(entities, merge_map)
                    # 更新关系中的实体名称
                    for rel in relations:
                        if rel.source_entity in merge_map:
                            rel.source_entity = merge_map[rel.source_entity]
                        if rel.target_entity in merge_map:
                            rel.target_entity = merge_map[rel.target_entity]

            # 添加到图谱
            await self.graph_store.add_subgraph(
                doc_id=doc_id, entities=entities, relations=relations
            )

            # 清空社区缓存（图已改变）
            self._communities = None

            return {
                "doc_id": doc_id,
                "entity_count": len(entities),
                "relation_count": len(relations),
                "token_count": result.token_count,
                "merged_entities": len(merge_map) if resolve_entities and self.resolver else 0,
            }

    async def add_document_from_file(
        self,
        *,
        filename: str,
        file_bytes: bytes,
        extraction_mode: Optional[str] = None,
        doc_id: Optional[str] = None,
        resolve_entities: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """通过共享文件提取模块导入文档，再执行图谱构建。"""
        safe_filename = Path(filename or "uploaded.txt").name
        if not safe_filename:
            raise ValueError("文件名不能为空")
        if not file_bytes:
            raise ValueError("上传文件为空")

        extraction = get_document_extraction_service().extract(
            Path(safe_filename),
            file_bytes,
            mode=extraction_mode,
        )

        result = await self.add_document(
            content=extraction.text,
            doc_id=doc_id,
            resolve_entities=resolve_entities,
        )
        result.update(
            {
                "filename": safe_filename,
                "file_type": extraction.file_type,
                "extraction_mode": extraction.mode_used.value,
                "requested_mode": extraction.requested_mode.value,
                "warnings": extraction.warnings,
                "text_length": len(extraction.text),
            }
        )
        return result

    async def query(
        self, question: str, top_k: int = 5, depth: int = 1, use_communities: bool = False
    ) -> Dict[str, Any]:
        """查询知识图谱"""
        # 搜索实体
        entities = self.graph_store.search_entities(question)

        if not entities:
            return {
                "question": question,
                "entities": [],
                "context": "",
                "subgraph_stats": {"nodes": 0, "edges": 0},
                "subgraph": self.graph_store.serialize_graph(
                    self.graph_store.get_subgraph([], depth=depth), source="query"
                ),
                "communities": [] if use_communities else None,
            }

        # 取前 top_k 个实体
        top_entities = entities[:top_k]
        entity_names = [e["name"] for e in top_entities]

        # 获取子图
        subgraph = self.graph_store.get_subgraph(entity_names, depth=depth)
        communities = (
            self._get_or_detect_communities()
            if use_communities and self._get_community_detector()
            else {}
        )
        level_zero_communities = communities.get(0, {})

        # 构建上下文
        context = self._build_context(subgraph)

        result = {
            "question": question,
            "entities": top_entities,
            "context": context,
            "subgraph_stats": {
                "nodes": subgraph.number_of_nodes(),
                "edges": subgraph.number_of_edges(),
            },
            "subgraph": self.graph_store.serialize_graph(
                subgraph, communities=level_zero_communities, source="query"
            ),
        }

        # 添加社区信息
        if use_communities and self._get_community_detector():
            entity_communities = self._find_entity_communities(entity_names)
            result["communities"] = entity_communities
        else:
            result["communities"] = None

        return result

    def _build_context(self, subgraph) -> str:
        """从子图构建文本上下文"""
        context_parts = []

        # 添加实体信息
        context_parts.append("=== 相关实体 ===")
        for node, data in subgraph.nodes(data=True):
            entity_type = data.get("entity_type", "unknown")
            description = data.get("description", "")
            context_parts.append(f"【{entity_type}】{node}: {description}")

        # 添加关系信息
        if subgraph.number_of_edges() > 0:
            context_parts.append("\n=== 实体关系 ===")
            for u, v, data in subgraph.edges(data=True):
                description = data.get("description", "")
                strength = data.get("strength", 5)
                context_parts.append(f"{u} -> {v}: {description} (强度: {strength})")

        return "\n".join(context_parts)

    def _get_or_detect_communities(self) -> Dict[int, Dict[str, Any]]:
        """获取或检测社区"""
        detector = self._get_community_detector()
        if self._communities is None and detector:
            self._communities = detector.detect(self.graph_store.get_graph())
        return self._communities or {}

    def _find_entity_communities(
        self, entity_names: List[str], level: int = 0
    ) -> List[Dict[str, Any]]:
        """查找实体所属的社区"""
        communities = self._get_or_detect_communities()
        if level not in communities:
            return []

        entity_set = set(entity_names)
        result = []

        for community_id, data in communities[level].items():
            community_nodes = set(data.get("nodes", []))
            overlap = entity_set & community_nodes
            if overlap:
                result.append(
                    {
                        "community_id": community_id,
                        "overlap_entities": list(overlap),
                        "size": len(community_nodes),
                        "nodes": list(community_nodes),
                    }
                )

        return result

    async def build_community_reports(self, level: int = 0) -> Dict[str, str]:
        """为所有社区生成报告（需要 LLM）"""
        # 确保 LLM 已初始化
        await self._init_llm()

        detector = self._get_community_detector()
        if not detector or not self.community_reporter:
            return {}

        communities = self._get_or_detect_communities()
        if level not in communities:
            return {}

        # 生成社区摘要
        summaries = detector.generate_community_summary(
            self.graph_store.get_graph(), communities[level]
        )

        # 生成报告
        reports = {}
        for summary in summaries:
            report = await self.community_reporter.generate_report(
                self.graph_store.get_graph(), summary
            )
            reports[summary["community_id"]] = report

        return reports

    def get_statistics(self) -> Dict[str, Any]:
        """获取图谱统计信息"""
        stats = self.graph_store.get_statistics()

        # 统计接口保持轻量，只返回已经缓存的社区信息，避免首屏被社区检测阻塞。
        if self._enable_communities and self._communities:
            stats["communities"] = {level: len(comms) for level, comms in self._communities.items()}

        return stats

    def get_entity(self, name: str) -> Optional[Dict[str, Any]]:
        """获取实体详情"""
        return self.graph_store.get_entity(name)

    def update_entity(
        self,
        entity_id: str,
        name: Optional[str] = None,
        entity_type: Optional[str] = None,
        description: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """更新实体信息"""
        result = self.graph_store.update_entity(
            entity_id=entity_id,
            name=name,
            entity_type=entity_type,
            description=description,
            properties=properties,
        )
        if result:
            # 图已改变，清空缓存
            self._communities = None
        return result

    def create_entity(
        self,
        name: str,
        entity_type: str = "concept",
        description: str = "",
        properties: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """创建手工实体节点。"""
        result = self.graph_store.create_entity(
            name=name,
            entity_type=entity_type,
            description=description,
            properties=properties,
        )
        self._communities = None
        return result

    def create_relation(
        self,
        source_entity_id: str,
        target_entity_id: str,
        relation_type: str = "related_to",
        description: str = "",
        strength: float = 1.0,
        properties: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """创建手工实体关系。"""
        result = self.graph_store.create_relation(
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            relation_type=relation_type,
            description=description,
            strength=strength,
            properties=properties,
        )
        self._communities = None
        return result

    def delete_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """删除实体节点和所有关联关系。"""
        result = self.graph_store.delete_entity(entity_id)
        if result:
            self._communities = None
        return result

    def get_all_entities(
        self, entity_type: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取所有实体"""
        entities = self.graph_store.get_all_entities()

        if entity_type:
            entities = [e for e in entities if e.get("entity_type") == entity_type]

        return entities[:limit]

    def search(self, query: str, entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """搜索实体"""
        return self.graph_store.search_entities(query, entity_type)

    def get_communities(self, level: int = 0) -> List[Dict[str, Any]]:
        """获取社区列表"""
        detector = self._get_community_detector()
        if not detector:
            return []

        communities = self._get_or_detect_communities()
        if level not in communities:
            return []

        return detector.generate_community_summary(self.graph_store.get_graph(), communities[level])

    def get_visualization(
        self,
        limit: int = 180,
        community_level: int = 0,
        include_communities: bool = False,
    ) -> Dict[str, Any]:
        """获取供前端图可视化使用的图数据。"""
        graph, truncated = self.graph_store.get_visualization_graph(limit=limit)
        communities = (
            self._get_or_detect_communities()
            if include_communities and self._get_community_detector()
            else {}
        )
        community_data = communities.get(community_level, {})
        result = self.graph_store.serialize_graph(
            graph,
            communities=community_data,
            source="overview",
            truncated=truncated,
            total_nodes=self.graph_store.get_graph().number_of_nodes(),
            total_edges=self.graph_store.get_graph().number_of_edges(),
        )
        result["layout_positions"] = self.graph_store.get_layout_positions()
        return result

    def save_layout_positions(self, positions: Dict[str, Any]) -> None:
        """保存前端布局位置。"""
        self.graph_store.save_layout_positions(positions)

    def get_layout_positions(self) -> Optional[Dict[str, Any]]:
        """读取持久化的布局位置。"""
        return self.graph_store.get_layout_positions()

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        stats = self.graph_store.get_statistics()

        # 检查 LLM 状态
        await self._init_llm()
        llm_status = "available" if self.extractor else "not_configured"

        return {
            "status": "healthy",
            "entities": stats["entity_count"],
            "relations": stats["relation_count"],
            "llm_status": llm_status,
            "kb_id": self.kb_id,
        }
