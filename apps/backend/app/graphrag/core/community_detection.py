"""
社区发现
使用 Leiden 算法检测图谱社区
"""

import logging
from typing import Any, Dict, List

import networkx as nx

logger = logging.getLogger(__name__)


class CommunityDetector:
    """社区检测器 - 使用 Leiden 算法"""

    SMALL_GRAPH_NODE_THRESHOLD = 24
    SMALL_GRAPH_EDGE_THRESHOLD = 32

    def __init__(self):
        self._graspologic_available = False
        self._graspologic_import_attempted = False
        self._hierarchical_leiden = None
        self._lcc = None

    def _ensure_graspologic(self):
        """仅在确实需要 Leiden 时才导入 graspologic。"""
        if self._graspologic_import_attempted:
            return

        self._graspologic_import_attempted = True
        try:
            from graspologic.partition import hierarchical_leiden
            from graspologic.utils import largest_connected_component

            self._hierarchical_leiden = hierarchical_leiden
            self._lcc = largest_connected_component
            self._graspologic_available = True
        except ImportError:
            logger.warning("graspologic not available, using simple community detection")

    def detect(
        self,
        graph: nx.Graph,
        max_cluster_size: int = 12,
        use_lcc: bool = True,
        seed: int = 0xDEADBEEF,
    ) -> Dict[int, Dict[str, Any]]:
        """
        检测社区

        Args:
            graph: NetworkX 图
            max_cluster_size: 最大社区大小
            use_lcc: 是否只使用最大连通分量
            seed: 随机种子

        Returns:
            Dict[level, Dict[community_id, {"nodes": [...], "weight": float}]]
        """
        node_count = graph.number_of_nodes()
        edge_count = graph.number_of_edges()

        # 对小图直接退回简单社区，避免 Leiden 在小样本上耗时不稳定，
        # 这类图对前端概览页更重要，首屏优先级高于复杂社区划分。
        if (
            node_count <= self.SMALL_GRAPH_NODE_THRESHOLD
            or edge_count <= self.SMALL_GRAPH_EDGE_THRESHOLD
        ):
            return self._detect_simple(graph)

        self._ensure_graspologic()
        if self._graspologic_available:
            return self._detect_leiden(graph, max_cluster_size, use_lcc, seed)
        else:
            return self._detect_simple(graph)

    def _detect_leiden(
        self, graph: nx.Graph, max_cluster_size: int, use_lcc: bool, seed: int
    ) -> Dict[int, Dict[str, Any]]:
        """使用 Leiden 算法检测社区"""
        if graph.number_of_nodes() == 0:
            return {}

        # 获取最大连通分量
        if use_lcc:
            graph = self._get_lcc(graph)

        # 运行 Leiden 算法
        community_mapping = self._hierarchical_leiden(
            graph, max_cluster_size=max_cluster_size, random_seed=seed
        )

        # 按层级组织结果
        level_communities: Dict[int, Dict[str, Any]] = {}

        for partition in community_mapping:
            level = partition.level
            node = partition.node
            cluster = str(partition.cluster)

            if level not in level_communities:
                level_communities[level] = {}

            if cluster not in level_communities[level]:
                level_communities[level][cluster] = {"nodes": [], "weight": 0.0}

            level_communities[level][cluster]["nodes"].append(node)

            # 计算社区权重（基于 PageRank）
            rank = graph.nodes[node].get("rank", 1.0)
            weight = graph.nodes[node].get("weight", 1.0)
            level_communities[level][cluster]["weight"] += rank * weight

        # 归一化权重
        for level in level_communities:
            communities = level_communities[level]
            total_weight = sum(c["weight"] for c in communities.values())
            if total_weight > 0:
                for c in communities.values():
                    c["weight"] /= total_weight

        return level_communities

    def _get_lcc(self, graph: nx.Graph) -> nx.Graph:
        """获取最大连通分量"""
        if graph.number_of_nodes() == 0:
            return graph

        # 获取所有连通分量
        components = list(nx.connected_components(graph))
        if not components:
            return graph

        # 找到最大连通分量
        largest = max(components, key=len)

        # 创建子图
        return graph.subgraph(largest).copy()

    def _detect_simple(self, graph: nx.Graph) -> Dict[int, Dict[str, Any]]:
        """
        简单的社区检测（基于连通分量）
        当 graspologic 不可用时使用
        """
        if graph.number_of_nodes() == 0:
            return {}

        # 使用连通分量作为社区
        communities = {}
        for i, component in enumerate(nx.connected_components(graph)):
            communities[str(i)] = {"nodes": list(component), "weight": 1.0}

        return {0: communities}

    def add_community_to_graph(
        self, graph: nx.Graph, communities: Dict[int, Dict[str, Any]], level: int = 0
    ):
        """
        将社区信息添加到图中

        Args:
            graph: NetworkX 图
            communities: 社区检测结果
            level: 使用哪个层级
        """
        if level not in communities:
            return

        # 为每个节点添加社区信息
        for community_id, data in communities[level].items():
            for node in data["nodes"]:
                if node in graph:
                    if "communities" not in graph.nodes[node]:
                        graph.nodes[node]["communities"] = []
                    graph.nodes[node]["communities"].append(community_id)

    def generate_community_summary(
        self, graph: nx.Graph, communities: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        生成社区摘要

        Returns:
            List of community summaries
        """
        summaries = []

        for community_id, data in communities.items():
            nodes = data["nodes"]

            # 获取社区中的实体类型分布
            entity_types = {}
            for node in nodes:
                if node in graph:
                    etype = graph.nodes[node].get("entity_type", "UNKNOWN")
                    entity_types[etype] = entity_types.get(etype, 0) + 1

            # 获取社区内的关键实体（度数最高的）
            subgraph = graph.subgraph(nodes)
            degrees = dict(subgraph.degree())
            key_entities = sorted(degrees.items(), key=lambda x: x[1], reverse=True)[:5]

            summaries.append(
                {
                    "community_id": community_id,
                    "size": len(nodes),
                    "weight": data.get("weight", 0),
                    "entity_types": entity_types,
                    "key_entities": [e[0] for e in key_entities],
                    "nodes": nodes,
                }
            )

        # 按权重排序
        summaries.sort(key=lambda x: x["weight"], reverse=True)
        return summaries


class CommunityReporter:
    """社区报告生成器"""

    def __init__(self, llm_client=None):
        self.llm = llm_client

    async def generate_report(self, graph: nx.Graph, community_summary: Dict[str, Any]) -> str:
        """
        使用 LLM 生成社区报告

        Args:
            graph: NetworkX 图
            community_summary: 社区摘要

        Returns:
            社区报告文本
        """
        if not self.llm:
            return self._generate_simple_report(graph, community_summary)

        # 构建提示
        nodes = community_summary["nodes"]
        entity_types = community_summary["entity_types"]

        # 获取社区内的关系
        subgraph = graph.subgraph(nodes)
        relations = []
        for u, v, data in subgraph.edges(data=True):
            desc = data.get("description", "")
            relations.append(f"- {u} -> {v}: {desc}")

        prompt = f"""You are an expert community analyst. Summarize the following community in the knowledge graph.

Community ID: {community_summary['community_id']}
Size: {community_summary['size']} entities
Entity Types: {entity_types}
Key Entities: {', '.join(community_summary['key_entities'])}

Relationships within this community:
{chr(10).join(relations[:20])}

Please provide a concise summary (2-3 sentences) describing:
1. What this community represents
2. The key relationships and dynamics
3. Any notable patterns or insights

Summary:"""

        try:
            report = await self.llm.chat(prompt)
            return report.strip()
        except Exception as e:
            logger.error("LLM report generation failed: %s", e)
            return self._generate_simple_report(graph, community_summary)

    def _generate_simple_report(self, graph: nx.Graph, community_summary: Dict[str, Any]) -> str:
        """生成简单报告（无 LLM 时）"""
        return (
            f"Community {community_summary['community_id']} contains "
            f"{community_summary['size']} entities of types "
            f"{list(community_summary['entity_types'].keys())}. "
            f"Key entities: {', '.join(community_summary['key_entities'])}."
        )

    async def generate_all_reports(
        self, graph: nx.Graph, communities: Dict[str, Any]
    ) -> Dict[str, str]:
        """为所有社区生成报告"""
        reports = {}
        for community_id, data in communities.items():
            report = await self.generate_report(graph, data)
            reports[community_id] = report
        return reports
