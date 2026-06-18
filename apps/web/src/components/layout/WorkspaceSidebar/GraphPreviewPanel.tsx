import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  CircleAlert,
  Database,
  Trash2,
  Eye,
  Link2,
  Loader2,
  MessageSquareQuote,
  Network,
  Pencil,
  Plus,
  Save,
  Search,
  Settings,
  Upload,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { createGraphragApi } from "@/lib/api/graphrag";
import { SqlQueryPanel } from "@/components/database/SqlQueryPanel";
import type {
  GraphQueryResponse,
  GraphRawQueryResponse,
  GraphStatistics,
  GraphTableInfo,
  GraphEntity,
  GraphVisualizationEdge,
  GraphVisualizationNode,
  GraphVisualizationResponse,
} from "@/types/graphrag";
import { getText } from "./ResourcePreviewShared";
import { CanvasActionMenu } from "@/components/workspace/CanvasActionMenu";

const LazyPixiExplorer = lazy(() =>
  import("@/components/KnowledgeGraphDialog/PixiExplorer").then((module) => ({
    default: module.PixiExplorer,
  })),
);

type GraphTab = "visualize" | "query" | "settings" | "data";
type InspectorMode = "create" | "connect" | "details" | "empty";

function getGraphEntityId(entity: GraphEntity) {
  return entity.entity_id || entity.name;
}

const EMPTY_VISUALIZATION: GraphVisualizationResponse = {
  source: "overview",
  nodes: [],
  edges: [],
  truncated: false,
  total_nodes: 0,
  total_edges: 0,
};

interface GraphResourceNode {
  name: string;
  path: string;
  meta?: Record<string, unknown>;
}

interface GraphPreviewPanelProps {
  node: GraphResourceNode;
  sessionId?: string | null;
  onClose?: () => void;
  closeLabel?: string;
  onSplitRight?: () => void;
  onSplitDown?: () => void;
}

export function GraphPreviewPanel({
  node,
  sessionId: _sessionId,
  onClose,
  closeLabel = "返回文件资产",
  onSplitRight,
  onSplitDown,
}: GraphPreviewPanelProps) {
  const [activeTab, setActiveTab] = useState<GraphTab>("visualize");
  const [question, setQuestion] = useState("");
  const [queryResult, setQueryResult] = useState<GraphQueryResponse | null>(null);
  const [isQuerying, setIsQuerying] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [visualization, setVisualization] =
    useState<GraphVisualizationResponse | null>(null);
  const [isLoadingVisualization, setIsLoadingVisualization] = useState(false);
  const [visualizationError, setVisualizationError] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  // 探索历史（旅行地图导航）
  const [explorationHistory, setExplorationHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);

  // 节点编辑状态
  const [isEditingNode, setIsEditingNode] = useState(false);
  const [editNodeName, setEditNodeName] = useState("");
  const [editNodeType, setEditNodeType] = useState("");
  const [editNodeDescription, setEditNodeDescription] = useState("");
  const [editNodeProperties, setEditNodeProperties] = useState<Record<string, string>>({});
  const [isSavingNode, setIsSavingNode] = useState(false);
  const [nodeSaveError, setNodeSaveError] = useState<string | null>(null);
  const [isCreatingNode, setIsCreatingNode] = useState(false);
  const [newNodeName, setNewNodeName] = useState("");
  const [newNodeType, setNewNodeType] = useState("concept");
  const [newNodeDescription, setNewNodeDescription] = useState("");
  const [isSavingNewNode, setIsSavingNewNode] = useState(false);
  const [newNodeError, setNewNodeError] = useState<string | null>(null);
  const [isConnectingNode, setIsConnectingNode] = useState(false);
  const [connectTargetNodeId, setConnectTargetNodeId] = useState("");
  const [connectTargetSearch, setConnectTargetSearch] = useState("");
  const [connectRelationType, setConnectRelationType] = useState("related_to");
  const [connectDescription, setConnectDescription] = useState("");
  const [relationCandidates, setRelationCandidates] = useState<GraphEntity[]>([]);
  const [isSearchingRelationTarget, setIsSearchingRelationTarget] = useState(false);
  const [isSavingRelation, setIsSavingRelation] = useState(false);
  const [relationSaveError, setRelationSaveError] = useState<string | null>(null);
  const [isDeleteNodeDialogOpen, setIsDeleteNodeDialogOpen] = useState(false);
  const [isDeletingNode, setIsDeletingNode] = useState(false);
  const [deleteNodeError, setDeleteNodeError] = useState<string | null>(null);

  // 设置 Tab 状态
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // 原始数据 Tab 状态
  const [graphTables, setGraphTables] = useState<GraphTableInfo[]>([]);
  const [loadingGraphTables, setLoadingGraphTables] = useState(false);
  const [rawSql, setRawSql] = useState('SELECT * FROM "entities" LIMIT 100;');
  const [rawQueryLimit, setRawQueryLimit] = useState("100");
  const [rawRunning, setRawRunning] = useState(false);
  const [rawError, setRawError] = useState<string | null>(null);
  const [rawResult, setRawResult] = useState<GraphRawQueryResponse | null>(null);
  const [graphStats, setGraphStats] = useState<GraphStatistics | null>(null);
  const [loadingStats, setLoadingStats] = useState(false);

  const kgId = useMemo(() => {
    const fromMeta = getText(node.meta?.id);
    if (fromMeta) {
      return fromMeta;
    }
    const pathParts = node.path.split("/").filter(Boolean);
    return pathParts[pathParts.length - 1] ?? "";
  }, [node.meta, node.path]);

  const dbPath = getText(node.meta?.db_path);
  const hasDataView = Boolean(dbPath);

  const selectedGraphNode = useMemo<GraphVisualizationNode | null>(() => {
    if (!selectedNodeId || !visualization) {
      return null;
    }
    return visualization.nodes.find((item) => item.id === selectedNodeId) ?? null;
  }, [selectedNodeId, visualization]);
  const entityCount = getText(node.meta?.entity_count);
  const visualizationNodeCount = visualization?.nodes.length ?? 0;
  const visualizationEdgeCount = visualization?.edges.length ?? 0;
  const selectedNodeRelations = useMemo(() => {
    if (!selectedGraphNode || !visualization) {
      return [];
    }
    return visualization.edges.filter(
      (edge) => edge.source === selectedGraphNode.id || edge.target === selectedGraphNode.id,
    );
  }, [selectedGraphNode, visualization]);
  const connectTargetCandidates = useMemo(() => {
    if (!selectedGraphNode) {
      return [];
    }
    const query = connectTargetSearch.trim().toLowerCase();
    const byId = new Map<string, GraphEntity>();
    const addCandidate = (entity: GraphEntity) => {
      const id = getGraphEntityId(entity);
      if (!id || id === selectedGraphNode.id) {
        return;
      }
      byId.set(id, entity);
    };
    for (const item of relationCandidates) {
      addCandidate(item);
    }
    for (const item of visualization?.nodes ?? []) {
      const candidate: GraphEntity = {
        entity_id: item.id,
        name: item.name,
        entity_type: item.entity_type,
        description: item.description,
        properties: item.properties,
      };
      if (!query) {
        addCandidate(candidate);
        continue;
      }
      const haystack = [
        item.name,
        item.entity_type,
        item.description ?? "",
        Object.values(item.properties || {}).join(" "),
      ]
        .join(" ")
        .toLowerCase();
      if (haystack.includes(query)) {
        addCandidate(candidate);
      }
    }
    return Array.from(byId.values()).slice(0, 8);
  }, [connectTargetSearch, relationCandidates, selectedGraphNode, visualization]);
  const selectedConnectTarget = useMemo(
    () => {
      const candidate = connectTargetCandidates.find(
        (item) => getGraphEntityId(item) === connectTargetNodeId,
      );
      if (candidate) {
        return candidate;
      }
      const relationCandidate = relationCandidates.find(
        (item) => getGraphEntityId(item) === connectTargetNodeId,
      );
      if (relationCandidate) {
        return relationCandidate;
      }
      const visualNode = visualization?.nodes.find(
        (item) => item.id === connectTargetNodeId,
      );
      if (!visualNode) {
        return null;
      }
      return {
        entity_id: visualNode.id,
        name: visualNode.name,
        entity_type: visualNode.entity_type,
        description: visualNode.description,
        properties: visualNode.properties,
      };
    },
    [connectTargetCandidates, connectTargetNodeId, relationCandidates, visualization],
  );
  const inspectorMode: InspectorMode = isCreatingNode
    ? "create"
    : isConnectingNode
      ? "connect"
    : selectedGraphNode
      ? "details"
      : "empty";

  const handleLoadStats = useCallback(async () => {
    if (!kgId) return;
    setLoadingStats(true);
    try {
      const graphApi = createGraphragApi({
        workspaceId: getText(node.meta?.workspace_id) || undefined,
        graphId: kgId,
        dbPath: dbPath || undefined,
      });
      const stats = await graphApi.getStatistics();
      setGraphStats(stats);
    } catch {
      setGraphStats(null);
    } finally {
      setLoadingStats(false);
    }
  }, [kgId, node.meta?.workspace_id, dbPath]);

  const handleLoadVisualization = useCallback(async () => {
    if (!kgId || isLoadingVisualization) {
      return;
    }

    setIsLoadingVisualization(true);
    setVisualizationError(null);
    try {
      const graphApi = createGraphragApi({
        workspaceId: getText(node.meta?.workspace_id) || undefined,
        graphId: kgId,
        dbPath: dbPath || undefined,
      });
      const response = await graphApi.getVisualization(120, 0, false);
      setVisualization(response);
      setSelectedNodeId(null);
    } catch (error) {
      setVisualization(null);
      setVisualizationError(
        error instanceof Error ? error.message : "加载图谱可视化失败",
      );
    } finally {
      setIsLoadingVisualization(false);
    }
  }, [isLoadingVisualization, kgId, node.meta?.workspace_id, dbPath]);

  const handleSaveNode = useCallback(async () => {
    if (!selectedGraphNode || !kgId || isSavingNode) {
      return;
    }

    setIsSavingNode(true);
    setNodeSaveError(null);
    try {
      const graphApi = createGraphragApi({
        workspaceId: getText(node.meta?.workspace_id) || undefined,
        graphId: kgId,
        dbPath: dbPath || undefined,
      });
      const updated = await graphApi.updateEntity(selectedGraphNode.id, {
        name: editNodeName.trim() || undefined,
        entity_type: editNodeType.trim() || undefined,
        description: editNodeDescription.trim() || undefined,
        properties: Object.keys(editNodeProperties).length > 0 ? editNodeProperties : undefined,
      });
      // 乐观更新本地 visualization 数据
      setVisualization((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          nodes: prev.nodes.map((n) =>
            n.id === selectedGraphNode.id
              ? {
                  ...n,
                  name: updated.name,
                  entity_type: updated.entity_type,
                  description: updated.description,
                  properties: updated.properties || {},
                }
              : n,
          ),
        };
      });
      setIsEditingNode(false);
    } catch (error) {
      setNodeSaveError(
        error instanceof Error ? error.message : "保存失败",
      );
    } finally {
      setIsSavingNode(false);
    }
  }, [
    selectedGraphNode,
    kgId,
    isSavingNode,
    editNodeName,
    editNodeType,
    editNodeDescription,
    editNodeProperties,
    node.meta?.workspace_id,
    dbPath,
  ]);

  const handleStartCreateNode = useCallback(() => {
    setNewNodeName("");
    setNewNodeType("concept");
    setNewNodeDescription("");
    setNewNodeError(null);
    setNodeSaveError(null);
    setSelectedNodeId(null);
    setVisualization((current) => current ?? EMPTY_VISUALIZATION);
    setVisualizationError(null);
    setIsCreatingNode(true);
    setIsConnectingNode(false);
    setIsEditingNode(false);
  }, []);

  const handleSelectVisualizationNode = useCallback((nodeId: string | null) => {
    setSelectedNodeId(nodeId);
    if (nodeId) {
      setIsCreatingNode(false);
      setNewNodeError(null);
      setIsConnectingNode(false);
      setRelationSaveError(null);
      // 记录探索历史（旅行地图路径）
      setExplorationHistory((prev) => {
        const truncated = prev.slice(0, historyIndex + 1);
        if (truncated[truncated.length - 1] === nodeId) {
          return truncated;
        }
        return [...truncated, nodeId];
      });
      setHistoryIndex((prev) => prev + 1);
    }
  }, [historyIndex]);

  // 旅行地图导航：跳转到指定节点并记录历史
  const handleNavigateToNode = useCallback((nodeId: string) => {
    setSelectedNodeId(nodeId);
    setIsCreatingNode(false);
    setIsConnectingNode(false);
    setIsEditingNode(false);
    setNewNodeError(null);
    setRelationSaveError(null);
    setExplorationHistory((prev) => {
      // 截断当前索引之后的历史，再追加新节点
      const truncated = prev.slice(0, historyIndex + 1);
      if (truncated[truncated.length - 1] === nodeId) {
        return truncated;
      }
      return [...truncated, nodeId];
    });
    setHistoryIndex((prev) => prev + 1);
  }, [historyIndex]);

  const handleHistoryBack = useCallback(() => {
    if (historyIndex <= 0) return;
    const newIndex = historyIndex - 1;
    setHistoryIndex(newIndex);
    const targetId = explorationHistory[newIndex];
    if (targetId) {
      setSelectedNodeId(targetId);
      setIsCreatingNode(false);
      setIsConnectingNode(false);
      setIsEditingNode(false);
    }
  }, [explorationHistory, historyIndex]);

  const handleHistoryForward = useCallback(() => {
    if (historyIndex >= explorationHistory.length - 1) return;
    const newIndex = historyIndex + 1;
    setHistoryIndex(newIndex);
    const targetId = explorationHistory[newIndex];
    if (targetId) {
      setSelectedNodeId(targetId);
      setIsCreatingNode(false);
      setIsConnectingNode(false);
      setIsEditingNode(false);
    }
  }, [explorationHistory, historyIndex]);

  // 查询结果实体 → 跳转到可视化 Tab 并选中节点
  const handleJumpToEntityFromQuery = useCallback((entityName: string) => {
    if (!visualization) return;
    const matched = visualization.nodes.find(
      (n) => n.name === entityName || n.id === entityName,
    );
    if (matched) {
      setActiveTab("visualize");
      handleNavigateToNode(matched.id);
    }
  }, [visualization, handleNavigateToNode]);

  const handleStartConnectNode = useCallback(() => {
    if (!selectedGraphNode) {
      return;
    }
    setConnectTargetNodeId("");
    setConnectTargetSearch("");
    setConnectRelationType("related_to");
    setConnectDescription("");
    setRelationCandidates([]);
    setRelationSaveError(null);
    setIsEditingNode(false);
    setIsCreatingNode(false);
    setIsConnectingNode(true);
  }, [selectedGraphNode]);

  const handleCreateNode = useCallback(async () => {
    const name = newNodeName.trim();
    if (!kgId || isSavingNewNode) {
      return;
    }
    if (!name) {
      setNewNodeError("节点名称不能为空");
      return;
    }

    setIsSavingNewNode(true);
    setNewNodeError(null);
    try {
      const graphApi = createGraphragApi({
        workspaceId: getText(node.meta?.workspace_id) || undefined,
        graphId: kgId,
        dbPath: dbPath || undefined,
      });
      const created = await graphApi.createEntity({
        name,
        entity_type: newNodeType.trim() || "concept",
        description: newNodeDescription.trim() || undefined,
      });
      const nodeId = created.entity_id || created.name;
      const nextNode: GraphVisualizationNode = {
        id: nodeId,
        name: created.name,
        entity_type: created.entity_type || "concept",
        description: created.description || "",
        degree: 0,
        community_ids: [],
        primary_community: null,
        properties: created.properties || {},
      };
      setVisualization((prev) => {
        if (!prev) {
          return {
            source: "overview",
            nodes: [nextNode],
            edges: [],
            truncated: false,
            total_nodes: 1,
            total_edges: 0,
          };
        }
        return {
          ...prev,
          nodes: [...prev.nodes, nextNode],
          total_nodes: prev.total_nodes + 1,
        };
      });
      setSelectedNodeId(nodeId);
      setIsCreatingNode(false);
      setIsConnectingNode(false);
      setNewNodeName("");
      setNewNodeType("concept");
      setNewNodeDescription("");
      void handleLoadStats();
    } catch (error) {
      setNewNodeError(error instanceof Error ? error.message : "新建节点失败");
    } finally {
      setIsSavingNewNode(false);
    }
  }, [
    handleLoadStats,
    isSavingNewNode,
    kgId,
    newNodeDescription,
    newNodeName,
    newNodeType,
    node.meta?.workspace_id,
    dbPath,
  ]);

  const handleCreateRelation = useCallback(async () => {
    if (!selectedGraphNode || !kgId || isSavingRelation) {
      return;
    }
    const targetId = connectTargetNodeId.trim();
    if (!targetId) {
      setRelationSaveError("请选择目标节点");
      return;
    }
    const relationType = connectRelationType.trim() || "related_to";

    setIsSavingRelation(true);
    setRelationSaveError(null);
    try {
      const graphApi = createGraphragApi({
        workspaceId: getText(node.meta?.workspace_id) || undefined,
        graphId: kgId,
        dbPath: dbPath || undefined,
      });
      const created = await graphApi.createRelation({
        source_entity_id: selectedGraphNode.id,
        target_entity_id: targetId,
        relation_type: relationType,
        description: connectDescription.trim() || undefined,
      });
      const nextEdge: GraphVisualizationEdge = {
        id: created.relation_id,
        source: created.source,
        target: created.target,
        relation_type: created.relation_type,
        description: created.description || created.relation_type,
        strength: created.strength,
        metadata: created.properties || {},
      };
      setVisualization((prev) => {
        if (!prev) return prev;
        const hasTargetNode = prev.nodes.some((item) => item.id === nextEdge.target);
        const nextNodes = hasTargetNode
          ? prev.nodes
          : [
              ...prev.nodes,
              {
                id: nextEdge.target,
                name: created.target_name,
                entity_type: selectedConnectTarget?.entity_type || "unknown",
                description: selectedConnectTarget?.description || "",
                degree: 0,
                community_ids: [],
                primary_community: null,
                properties: selectedConnectTarget?.properties || {},
              },
            ];
        return {
          ...prev,
          edges: [...prev.edges, nextEdge],
          nodes: nextNodes.map((item) =>
            item.id === nextEdge.source || item.id === nextEdge.target
              ? { ...item, degree: item.degree + 1 }
              : item,
          ),
          total_nodes: hasTargetNode ? prev.total_nodes : prev.total_nodes + 1,
          total_edges: prev.total_edges + 1,
        };
      });
      setIsConnectingNode(false);
      setConnectTargetNodeId("");
      setConnectTargetSearch("");
      setConnectRelationType("related_to");
      setConnectDescription("");
      setRelationCandidates([]);
      void handleLoadStats();
    } catch (error) {
      setRelationSaveError(
        error instanceof Error ? error.message : "创建关系失败",
      );
    } finally {
      setIsSavingRelation(false);
    }
  }, [
    connectDescription,
    connectRelationType,
    connectTargetNodeId,
    handleLoadStats,
    isSavingRelation,
    kgId,
    node.meta?.workspace_id,
    selectedGraphNode,
    selectedConnectTarget,
    dbPath,
  ]);

  const handleDeleteSelectedNode = useCallback(async () => {
    if (!selectedGraphNode || !kgId || isDeletingNode) {
      return;
    }

    const deletedNodeId = selectedGraphNode.id;
    setIsDeletingNode(true);
    setDeleteNodeError(null);
    try {
      const graphApi = createGraphragApi({
        workspaceId: getText(node.meta?.workspace_id) || undefined,
        graphId: kgId,
        dbPath: dbPath || undefined,
      });
      await graphApi.deleteEntity(deletedNodeId);
      setVisualization((prev) => {
        if (!prev) return prev;
        const removedEdges = prev.edges.filter(
          (edge) => edge.source === deletedNodeId || edge.target === deletedNodeId,
        );
        const removedEdgeCount = removedEdges.length;
        const nextEdges = prev.edges.filter(
          (edge) => edge.source !== deletedNodeId && edge.target !== deletedNodeId,
        );
        return {
          ...prev,
          nodes: prev.nodes
            .filter((item) => item.id !== deletedNodeId)
            .map((item) => {
              const lostDegree = removedEdges.filter(
                (edge) => edge.source === item.id || edge.target === item.id,
              ).length;
              return lostDegree > 0
                ? { ...item, degree: Math.max(0, item.degree - lostDegree) }
                : item;
            }),
          edges: nextEdges,
          total_nodes: Math.max(0, prev.total_nodes - 1),
          total_edges: Math.max(0, prev.total_edges - removedEdgeCount),
        };
      });
      setSelectedNodeId(null);
      setIsEditingNode(false);
      setIsConnectingNode(false);
      setIsDeleteNodeDialogOpen(false);
      void handleLoadStats();
    } catch (error) {
      setDeleteNodeError(error instanceof Error ? error.message : "删除节点失败");
    } finally {
      setIsDeletingNode(false);
    }
  }, [
    handleLoadStats,
    isDeletingNode,
    kgId,
    node.meta?.workspace_id,
    selectedGraphNode,
    dbPath,
  ]);

  useEffect(() => {
    if (!isConnectingNode || !kgId || !selectedGraphNode) {
      return;
    }
    const query = connectTargetSearch.trim();
    if (!query) {
      setRelationCandidates([]);
      setIsSearchingRelationTarget(false);
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(() => {
      setIsSearchingRelationTarget(true);
      const graphApi = createGraphragApi({
        workspaceId: getText(node.meta?.workspace_id) || undefined,
        graphId: kgId,
        dbPath: dbPath || undefined,
      });
      graphApi
        .searchEntities(query)
        .then((response) => {
          if (cancelled) return;
          setRelationCandidates(
            response.results.filter(
              (item) => getGraphEntityId(item) !== selectedGraphNode.id,
            ),
          );
        })
        .catch(() => {
          if (cancelled) return;
          setRelationCandidates([]);
        })
        .finally(() => {
          if (!cancelled) setIsSearchingRelationTarget(false);
        });
    }, 220);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [
    connectTargetSearch,
    isConnectingNode,
    kgId,
    node.meta?.workspace_id,
    selectedGraphNode,
    dbPath,
  ]);

  // 可视化 Tab 自动加载
  useEffect(() => {
    if (activeTab === "visualize" && !visualization && !isLoadingVisualization) {
      void handleLoadVisualization();
    }
  }, [activeTab, handleLoadVisualization, isLoadingVisualization, visualization]);

  // 设置 Tab 加载统计
  useEffect(() => {
    if (activeTab === "settings" && kgId) {
      void handleLoadStats();
    }
  }, [activeTab, kgId, handleLoadStats]);

  // 原始数据 Tab：加载表列表
  useEffect(() => {
    if (activeTab !== "data" || !kgId) {
      return;
    }

    let cancelled = false;

    async function loadTables() {
      setLoadingGraphTables(true);
      setRawError(null);
      try {
        const graphApi = createGraphragApi({
          workspaceId: getText(node.meta?.workspace_id) || undefined,
          graphId: kgId,
          dbPath: dbPath || undefined,
        });
        const tables = await graphApi.getTables();
        if (cancelled) return;
        setGraphTables(tables);
      } catch (err) {
        if (cancelled) return;
        setRawError(err instanceof Error ? err.message : "加载表列表失败");
      } finally {
        if (!cancelled) setLoadingGraphTables(false);
      }
    }

    void loadTables();

    return () => {
      cancelled = true;
    };
  }, [activeTab, kgId, node.meta?.workspace_id, dbPath]);

  const handleRunRawQuery = useCallback(async () => {
    if (!kgId || !rawSql.trim() || rawRunning) {
      return;
    }

    setRawRunning(true);
    setRawError(null);
    setRawResult(null);
    try {
      const graphApi = createGraphragApi({
        workspaceId: getText(node.meta?.workspace_id) || undefined,
        graphId: kgId,
        dbPath: dbPath || undefined,
      });
      const response = await graphApi.executeRawQuery(rawSql.trim());
      setRawResult(response);
    } catch (err) {
      setRawError(err instanceof Error ? err.message : "查询失败");
    } finally {
      setRawRunning(false);
    }
  }, [kgId, rawSql, rawRunning, node.meta?.workspace_id, dbPath]);

  const handleQuery = useCallback(async () => {
    const trimmed = question.trim();
    if (!kgId || !trimmed || isQuerying) {
      return;
    }

    setIsQuerying(true);
    setQueryError(null);
    try {
      const graphApi = createGraphragApi({
        workspaceId: getText(node.meta?.workspace_id) || undefined,
        graphId: kgId,
        dbPath: dbPath || undefined,
      });
      const response = await graphApi.query({
        question: trimmed,
        top_k: 5,
        depth: 1,
      });
      setQueryResult(response);
    } catch (error) {
      setQueryResult(null);
      setQueryError(error instanceof Error ? error.message : "查询失败");
    } finally {
      setIsQuerying(false);
    }
  }, [isQuerying, kgId, question, dbPath, node.meta?.workspace_id]);

  const handleUploadChange = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const selectedFiles = Array.from(event.target.files ?? []);
      if (!kgId || selectedFiles.length === 0 || isUploading) {
        return;
      }

      setIsUploading(true);
      setUploadError(null);
      setUploadMessage(null);
      try {
        const graphApi = createGraphragApi({
          workspaceId: getText(node.meta?.workspace_id) || undefined,
          graphId: kgId,
          dbPath: dbPath || undefined,
        });
        for (const file of selectedFiles) {
          await graphApi.uploadDocument(file);
        }
        setUploadMessage(
          selectedFiles.length === 1
            ? `已上传 ${selectedFiles[0].name}，实体和关系已抽取。`
            : `已上传 ${selectedFiles.length} 个文件，实体和关系已抽取。`,
        );
      } catch (error) {
        setUploadError(error instanceof Error ? error.message : "上传失败");
      } finally {
        setIsUploading(false);
        event.target.value = "";
      }
    },
    [isUploading, kgId, node.meta?.workspace_id, dbPath],
  );

  const tabs: { id: GraphTab; label: string; icon: React.ReactNode }[] = [
    { id: "visualize", label: "可视化", icon: <Eye className="h-3.5 w-3.5" /> },
    { id: "query", label: "查询", icon: <Search className="h-3.5 w-3.5" /> },
    { id: "settings", label: "设置", icon: <Settings className="h-3.5 w-3.5" /> },
  ];

  if (hasDataView) {
    tabs.push({ id: "data", label: "原始数据", icon: <Database className="h-3.5 w-3.5" /> });
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      <AlertDialog
        open={isDeleteNodeDialogOpen}
        onOpenChange={(open) => {
          if (isDeletingNode) {
            return;
          }
          setIsDeleteNodeDialogOpen(open);
          if (!open) {
            setDeleteNodeError(null);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除节点</AlertDialogTitle>
            <AlertDialogDescription>
              {selectedGraphNode
                ? `将删除“${selectedGraphNode.name}”，并删除所有连接到它的关系。此操作不能撤销。`
                : "将删除当前节点，并删除所有连接到它的关系。此操作不能撤销。"}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {deleteNodeError ? (
            <div className="rounded-md border border-error/20 bg-error-container px-3 py-2 text-xs text-error">
              {deleteNodeError}
            </div>
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeletingNode}>取消</AlertDialogCancel>
            <AlertDialogAction asChild>
              <Button
                type="button"
                variant="destructive"
                disabled={isDeletingNode || !selectedGraphNode}
                onClick={(event) => {
                  event.preventDefault();
                  void handleDeleteSelectedNode();
                }}
                data-testid="graph-preview-confirm-delete-node-button"
              >
                {isDeletingNode ? (
                  <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Trash2 className="mr-1 h-3.5 w-3.5" />
                )}
                删除节点
              </Button>
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <div className="border-b border-border px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Network className="h-4 w-4 shrink-0 text-tertiary" />
              <span className="truncate">{node.name}</span>
            </div>
            <div className="mt-1 text-xs leading-5 text-muted-foreground">
              知识图谱资产{entityCount ? ` · ${entityCount} 实体` : ""}
            </div>
          </div>
          {onClose ? (
            <CanvasActionMenu
              onClose={onClose}
              closeLabel={closeLabel}
              onSplitRight={onSplitRight}
              onSplitDown={onSplitDown}
            />
          ) : null}
        </div>

        <div className="mt-3 flex gap-1 rounded-lg border border-border bg-muted/40 p-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                activeTab === tab.id
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className={`min-h-0 flex-1 px-4 py-4 ${activeTab === "visualize" ? "overflow-hidden" : "overflow-y-auto"}`}>
        {/* 可视化 Tab */}
        {activeTab === "visualize" ? (
          <div className="flex h-full min-h-0 flex-col gap-3">
            {isLoadingVisualization ? (
              <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                加载图谱可视化...
              </div>
            ) : visualizationError ? (
              <div className="space-y-3">
                <div className="flex items-start gap-2 rounded-md border border-error/20 bg-error-container px-3 py-2 text-xs text-error">
                  <CircleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <span>{visualizationError}</span>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => void handleLoadVisualization()}
                >
                  重试
                </Button>
              </div>
            ) : visualization ? (
              <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] gap-3">
                <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-3 text-xs text-muted-foreground">
                      <Network className="h-3.5 w-3.5" />
                      力导向
                    </div>
                    <div className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-xs text-muted-foreground">
                      {visualizationNodeCount} 节点
                    </div>
                    <div className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-xs text-muted-foreground">
                      {visualizationEdgeCount} 关系
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => void handleLoadVisualization()}
                      disabled={isLoadingVisualization}
                    >
                      <Loader2
                        className={`mr-1.5 h-3 w-3 ${
                          isLoadingVisualization ? "animate-spin" : ""
                        }`}
                      />
                      刷新
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant={isCreatingNode ? "secondary" : "default"}
                      onClick={handleStartCreateNode}
                      disabled={!kgId || isSavingNewNode}
                      data-testid="graph-preview-create-node-button"
                    >
                      <Plus className="mr-1.5 h-3 w-3" />
                      新建节点
                    </Button>
                  </div>
                  <div className="min-w-[160px] flex-1">
                    <div className="relative">
                      <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
                      <Input
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="搜索节点..."
                        className="h-7 pl-7 text-[11px]"
                      />
                      {searchQuery && (
                        <button
                          type="button"
                          onClick={() => setSearchQuery("")}
                          className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      )}
                    </div>
                  </div>
                </div>

                <div className="min-h-0 overflow-hidden rounded-lg border border-border bg-card">
                  {visualization.nodes.length > 0 ? (
                    <Suspense
                      fallback={
                        <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          正在加载图引擎...
                        </div>
                      }
                    >
                      <LazyPixiExplorer
                        data={visualization}
                        selectedNodeId={selectedNodeId}
                        searchQuery={searchQuery}
                        layoutMode="force"
                        onSelectNode={handleSelectVisualizationNode}
                      />
                    </Suspense>
                  ) : (
                    <div className="flex h-full flex-col items-center justify-center gap-3 px-4 text-center text-sm text-muted-foreground">
                      <Network className="h-8 w-8 opacity-30" />
                      <div>当前图谱还没有可展示的节点。</div>
                      <div className="text-xs text-muted-foreground">
                        使用上方“新建节点”添加第一个实体。
                      </div>
                    </div>
                  )}
                </div>

                <div
                  className="min-h-[148px] max-h-[260px] overflow-y-auto rounded-lg border border-border bg-background px-3 py-3"
                  data-testid="graph-preview-node-inspector"
                >
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        {inspectorMode === "details" && historyIndex > 0 ? (
                          <button
                            type="button"
                            onClick={handleHistoryBack}
                            disabled={historyIndex <= 0}
                            className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-30 disabled:hover:bg-transparent"
                            title="返回上一个节点"
                            aria-label="返回上一个节点"
                          >
                            <ArrowLeft className="h-3 w-3" />
                          </button>
                        ) : null}
                        {inspectorMode === "details" && historyIndex < explorationHistory.length - 1 ? (
                          <button
                            type="button"
                            onClick={handleHistoryForward}
                            disabled={historyIndex >= explorationHistory.length - 1}
                            className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-30 disabled:hover:bg-transparent"
                            title="前进到下一个节点"
                            aria-label="前进到下一个节点"
                          >
                            <ArrowRight className="h-3 w-3" />
                          </button>
                        ) : null}
                        <span className="truncate text-xs font-medium text-foreground">
                          {inspectorMode === "create"
                            ? "新建节点"
                            : inspectorMode === "connect"
                              ? "连接节点"
                            : inspectorMode === "details"
                              ? "节点详情"
                              : "节点检查器"}
                        </span>
                      </div>
                      <div className="mt-0.5 text-[11px] leading-4 text-muted-foreground">
                        {inspectorMode === "create"
                          ? "输入名称后保存到当前知识图谱。"
                          : inspectorMode === "connect"
                            ? "从当前节点连到另一个已有节点。"
                          : inspectorMode === "details"
                            ? "查看和编辑当前选中的实体节点。"
                            : "点击画布节点查看详情，或使用上方按钮新建节点。"}
                      </div>
                    </div>
                    {inspectorMode === "details" && selectedGraphNode && !isEditingNode ? (
                      <div className="flex items-center gap-1">
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="h-7 px-2 text-[11px]"
                          onClick={handleStartConnectNode}
                          disabled={!kgId}
                          data-testid="graph-preview-connect-node-button"
                        >
                          <Link2 className="mr-1 h-3 w-3" />
                          连接节点
                        </Button>
                        <Button
                          type="button"
                          size="icon-sm"
                          variant="ghost"
                          onClick={() => {
                            setEditNodeName(selectedGraphNode.name);
                            setEditNodeType(selectedGraphNode.entity_type || "");
                            setEditNodeDescription(selectedGraphNode.description || "");
                            const props: Record<string, string> = {};
                            const rawProps = selectedGraphNode.properties;
                            if (rawProps && typeof rawProps === "object") {
                              for (const [k, v] of Object.entries(rawProps)) {
                                props[k] = typeof v === "string" ? v : String(v);
                              }
                            }
                            setEditNodeProperties(props);
                            setNodeSaveError(null);
                            setRelationSaveError(null);
                            setIsEditingNode(true);
                            setIsConnectingNode(false);
                          }}
                          title="编辑实体"
                          aria-label="编辑实体"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          type="button"
                          size="icon-sm"
                          variant="ghost"
                          className="text-destructive hover:text-destructive"
                          onClick={() => {
                            setDeleteNodeError(null);
                            setIsDeleteNodeDialogOpen(true);
                          }}
                          title="删除节点"
                          aria-label="删除节点"
                          disabled={isDeletingNode}
                          data-testid="graph-preview-delete-node-button"
                        >
                          {isDeletingNode ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Trash2 className="h-3.5 w-3.5" />
                          )}
                        </Button>
                      </div>
                    ) : null}
                  </div>

                  {isCreatingNode ? (
                    <div className="grid gap-2">
                      <div className="grid gap-1">
                        <label className="text-[11px] text-muted-foreground">名称</label>
                        <Input
                          value={newNodeName}
                          onChange={(event) => {
                            setNewNodeName(event.target.value);
                            setNewNodeError(null);
                          }}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") {
                              void handleCreateNode();
                            }
                          }}
                          placeholder="输入节点名称"
                          className="h-8 text-xs"
                          disabled={isSavingNewNode}
                          autoFocus
                        />
                      </div>
                      <div className="grid gap-1">
                        <label className="text-[11px] text-muted-foreground">类型</label>
                        <Input
                          value={newNodeType}
                          onChange={(event) => setNewNodeType(event.target.value)}
                          placeholder="concept"
                          className="h-8 text-xs"
                          disabled={isSavingNewNode}
                        />
                      </div>
                      <div className="grid gap-1">
                        <label className="text-[11px] text-muted-foreground">描述</label>
                        <Textarea
                          value={newNodeDescription}
                          onChange={(event) => setNewNodeDescription(event.target.value)}
                          placeholder="可选，补充这个节点的说明"
                          className="min-h-[64px] text-xs"
                          disabled={isSavingNewNode}
                        />
                      </div>
                      {newNodeError ? (
                        <div className="rounded-md border border-error/20 bg-error-container px-2 py-1.5 text-[11px] text-error">
                          {newNodeError}
                        </div>
                      ) : null}
                      <div className="flex gap-2 pt-1">
                        <Button
                          type="button"
                          size="sm"
                          className="h-7 text-xs"
                          onClick={() => void handleCreateNode()}
                          disabled={isSavingNewNode}
                        >
                          {isSavingNewNode ? (
                            <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                          ) : (
                            <Save className="mr-1 h-3 w-3" />
                          )}
                          保存
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="h-7 text-xs"
                          onClick={() => {
                            setIsCreatingNode(false);
                            setNewNodeError(null);
                          }}
                          disabled={isSavingNewNode}
                        >
                          取消
                        </Button>
                      </div>
                    </div>
                  ) : null}

                  {isConnectingNode && selectedGraphNode ? (
                    <div className="grid gap-2" data-testid="graph-preview-connect-node-form">
                      <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs">
                        <div className="text-[11px] text-muted-foreground">源节点</div>
                        <div className="mt-0.5 font-medium text-foreground">
                          {selectedGraphNode.name}
                        </div>
                      </div>
                      <div className="grid gap-1">
                        <label className="text-[11px] text-muted-foreground">搜索目标节点</label>
                        <div className="relative">
                          <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
                          <Input
                            value={connectTargetSearch}
                            onChange={(event) => {
                              setConnectTargetSearch(event.target.value);
                              setConnectTargetNodeId("");
                              setRelationSaveError(null);
                            }}
                            placeholder="输入节点名称、类型或描述"
                            className="h-8 pl-7 text-xs"
                            disabled={isSavingRelation}
                            data-testid="graph-preview-connect-target-search"
                          />
                          {isSearchingRelationTarget ? (
                            <Loader2 className="absolute right-2 top-1/2 h-3 w-3 -translate-y-1/2 animate-spin text-muted-foreground" />
                          ) : null}
                        </div>
                        <div
                          className="max-h-28 overflow-y-auto rounded-md border border-border bg-muted/20 p-1"
                          data-testid="graph-preview-connect-target-results"
                        >
                          {connectTargetCandidates.length > 0 ? (
                            connectTargetCandidates.map((item) => {
                              const id = getGraphEntityId(item);
                              const selected = id === connectTargetNodeId;
                              return (
                                <button
                                  key={id}
                                  type="button"
                                  className={`flex w-full min-w-0 items-center justify-between gap-2 rounded px-2 py-1.5 text-left text-xs transition-colors ${
                                    selected
                                      ? "bg-primary text-primary-foreground"
                                      : "text-foreground hover:bg-background"
                                  }`}
                                  onClick={() => {
                                    setConnectTargetNodeId(id);
                                    setConnectTargetSearch(item.name);
                                    setRelationSaveError(null);
                                  }}
                                  disabled={isSavingRelation}
                                >
                                  <span className="min-w-0 truncate">{item.name}</span>
                                  <span
                                    className={`shrink-0 text-[10px] ${
                                      selected
                                        ? "text-primary-foreground/80"
                                        : "text-muted-foreground"
                                    }`}
                                  >
                                    {item.entity_type || "unknown"}
                                  </span>
                                </button>
                              );
                            })
                          ) : (
                            <div className="px-2 py-1.5 text-[11px] text-muted-foreground">
                              {connectTargetSearch.trim()
                                ? "没有匹配节点"
                                : "输入关键词后选择目标节点。"}
                            </div>
                          )}
                        </div>
                        {selectedConnectTarget ? (
                          <div className="rounded-md border border-border bg-background px-2 py-1.5 text-[11px] text-muted-foreground">
                            已选择：
                            <span className="font-medium text-foreground">
                              {selectedConnectTarget.name}
                            </span>
                          </div>
                        ) : null}
                      </div>
                      <div className="grid gap-1">
                        <label className="text-[11px] text-muted-foreground">目标节点 ID</label>
                        <Input
                          value={connectTargetNodeId}
                          onChange={(event) => {
                            setConnectTargetNodeId(event.target.value.trim());
                            setRelationSaveError(null);
                          }}
                          placeholder="搜索选择后自动填入，也可粘贴节点 ID"
                          className="h-8 text-xs"
                          disabled={isSavingRelation}
                          data-testid="graph-preview-connect-target-id"
                        />
                      </div>
                      <div className="grid gap-1">
                        <label className="text-[11px] text-muted-foreground">关系类型</label>
                        <Input
                          value={connectRelationType}
                          onChange={(event) => setConnectRelationType(event.target.value)}
                          placeholder="related_to"
                          className="h-8 text-xs"
                          disabled={isSavingRelation}
                        />
                      </div>
                      <div className="grid gap-1">
                        <label className="text-[11px] text-muted-foreground">关系说明</label>
                        <Textarea
                          value={connectDescription}
                          onChange={(event) => setConnectDescription(event.target.value)}
                          placeholder="可选，补充这条关系的说明"
                          className="min-h-[56px] text-xs"
                          disabled={isSavingRelation}
                        />
                      </div>
                      {relationSaveError ? (
                        <div className="rounded-md border border-error/20 bg-error-container px-2 py-1.5 text-[11px] text-error">
                          {relationSaveError}
                        </div>
                      ) : null}
                      <div className="flex gap-2 pt-1">
                        <Button
                          type="button"
                          size="sm"
                          className="h-7 text-xs"
                          onClick={() => void handleCreateRelation()}
                          disabled={
                            isSavingRelation ||
                            !connectTargetNodeId
                          }
                        >
                          {isSavingRelation ? (
                            <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                          ) : (
                            <Link2 className="mr-1 h-3 w-3" />
                          )}
                          保存关系
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="h-7 text-xs"
                          onClick={() => {
                            setIsConnectingNode(false);
                            setRelationSaveError(null);
                          }}
                          disabled={isSavingRelation}
                        >
                          取消
                        </Button>
                      </div>
                    </div>
                  ) : null}

                  {!isCreatingNode && !isConnectingNode && selectedGraphNode ? (
                    <div>
                      {isEditingNode ? (
                        <div className="space-y-2">
                          <div>
                            <label className="text-[11px] text-muted-foreground">名称</label>
                            <Input
                              value={editNodeName}
                              onChange={(e) => setEditNodeName(e.target.value)}
                              className="mt-0.5 h-7 text-xs"
                              disabled={isSavingNode}
                            />
                          </div>
                          <div>
                            <label className="text-[11px] text-muted-foreground">类型</label>
                            <Input
                              value={editNodeType}
                              onChange={(e) => setEditNodeType(e.target.value)}
                              className="mt-0.5 h-7 text-xs"
                              disabled={isSavingNode}
                            />
                          </div>
                          <div>
                            <label className="text-[11px] text-muted-foreground">描述</label>
                            <Textarea
                              value={editNodeDescription}
                              onChange={(e) => setEditNodeDescription(e.target.value)}
                              className="mt-0.5 min-h-[60px] text-xs"
                              disabled={isSavingNode}
                            />
                          </div>
                          <div>
                            <label className="text-[11px] text-muted-foreground">扩展属性</label>
                            <div className="mt-1 space-y-1.5">
                              {Object.entries(editNodeProperties).length === 0 ? (
                                <div className="text-[11px] text-muted-foreground">暂无扩展属性</div>
                              ) : (
                                Object.entries(editNodeProperties).map(([key, value], index) => (
                                  <div key={index} className="flex gap-1.5">
                                    <Input
                                      value={key}
                                      onChange={(e) => {
                                        const newKey = e.target.value;
                                        setEditNodeProperties((prev) => {
                                          const entries = Object.entries(prev);
                                          entries[index] = [newKey, value];
                                          return Object.fromEntries(entries);
                                        });
                                      }}
                                      placeholder="属性名"
                                      className="h-7 text-xs"
                                      disabled={isSavingNode}
                                    />
                                    <Input
                                      value={value}
                                      onChange={(e) => {
                                        const newValue = e.target.value;
                                        setEditNodeProperties((prev) => ({
                                          ...prev,
                                          [key]: newValue,
                                        }));
                                      }}
                                      placeholder="属性值"
                                      className="h-7 text-xs"
                                      disabled={isSavingNode}
                                    />
                                    <Button
                                      type="button"
                                      size="sm"
                                      variant="ghost"
                                      className="h-7 w-7 shrink-0 p-0"
                                      onClick={() => {
                                        setEditNodeProperties((prev) => {
                                          const { [key]: _, ...rest } = prev;
                                          return rest;
                                        });
                                      }}
                                      disabled={isSavingNode}
                                    >
                                      <X className="h-3 w-3" />
                                    </Button>
                                  </div>
                                ))
                              )}
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                className="h-7 text-[11px]"
                                onClick={() => {
                                  setEditNodeProperties((prev) => ({
                                    ...prev,
                                    [""]: "",
                                  }));
                                }}
                                disabled={isSavingNode}
                              >
                                + 添加属性
                              </Button>
                            </div>
                          </div>
                          {nodeSaveError ? (
                            <div className="rounded-md border border-error/20 bg-error-container px-2 py-1.5 text-[11px] text-error">
                              {nodeSaveError}
                            </div>
                          ) : null}
                          <div className="flex gap-2 pt-1">
                            <Button
                              type="button"
                              size="sm"
                              className="h-7 text-xs"
                              onClick={() => void handleSaveNode()}
                              disabled={isSavingNode}
                            >
                              {isSavingNode ? (
                                <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                              ) : (
                                <Save className="mr-1 h-3 w-3" />
                              )}
                              保存
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              className="h-7 text-xs"
                              onClick={() => {
                                setIsEditingNode(false);
                                setNodeSaveError(null);
                              }}
                              disabled={isSavingNode}
                            >
                              取消
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <div>
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0 flex-1">
                              <div className="text-xs font-medium text-foreground">
                                {selectedGraphNode.name}
                              </div>
                              <div className="mt-1 text-xs text-muted-foreground">
                                {selectedGraphNode.entity_type || "unknown"}
                              </div>
                            </div>
                          </div>
                          {selectedGraphNode.description ? (
                            <p className="mt-2 line-clamp-4 text-xs leading-5 text-muted-foreground">
                              {selectedGraphNode.description}
                            </p>
                          ) : null}
                          {deleteNodeError ? (
                            <div className="mt-2 rounded-md border border-error/20 bg-error-container px-2 py-1.5 text-[11px] text-error">
                              {deleteNodeError}
                            </div>
                          ) : null}
                          <div className="mt-3 rounded-md border border-border bg-muted/20 px-3 py-2">
                            <div className="flex items-center justify-between gap-2">
                              <div className="text-[11px] text-muted-foreground">
                                关系
                              </div>
                              <div
                                className="text-[11px] font-medium text-foreground"
                                data-testid="graph-preview-selected-node-relation-count"
                              >
                                {selectedNodeRelations.length}
                              </div>
                            </div>
                            <div className="mt-1.5 grid gap-1">
                              {selectedNodeRelations.length > 0 ? (
                                selectedNodeRelations.slice(0, 4).map((edge) => {
                                  const peerId =
                                    edge.source === selectedGraphNode.id
                                      ? edge.target
                                      : edge.source;
                                  const peer = visualization?.nodes.find(
                                    (item) => item.id === peerId,
                                  );
                                  const direction =
                                    edge.source === selectedGraphNode.id ? "指向" : "来自";
                                  const canNavigate = Boolean(peer);
                                  return (
                                    <div
                                      key={edge.id}
                                      className="flex min-w-0 items-center gap-1.5 text-[11px]"
                                    >
                                      <Link2 className="h-3 w-3 shrink-0 text-muted-foreground" />
                                      <span className="shrink-0 text-muted-foreground">
                                        {direction}
                                      </span>
                                      {canNavigate ? (
                                        <button
                                          type="button"
                                          onClick={() => handleNavigateToNode(peerId)}
                                          className="min-w-0 truncate text-foreground underline-offset-2 transition-colors hover:text-primary hover:underline"
                                          title={`跳转到「${peer?.name ?? peerId}」`}
                                        >
                                          {peer?.name ?? peerId}
                                        </button>
                                      ) : (
                                        <span className="min-w-0 truncate text-muted-foreground">
                                          {peer?.name ?? peerId}
                                        </span>
                                      )}
                                      <span className="shrink-0 text-muted-foreground">
                                        {edge.relation_type || "related_to"}
                                      </span>
                                    </div>
                                  );
                                })
                              ) : (
                                <div className="text-[11px] text-muted-foreground">
                                  暂无关系，可以用“连接节点”添加。
                                </div>
                              )}
                            </div>
                          </div>
                          {selectedGraphNode.properties && Object.keys(selectedGraphNode.properties).length > 0 ? (
                            <div className="mt-2">
                              <div className="text-[11px] text-muted-foreground">扩展属性</div>
                              <div className="mt-1 grid gap-1">
                                {Object.entries(selectedGraphNode.properties).map(([key, value]) => (
                                  <div key={key} className="flex gap-1.5 text-xs">
                                    <span className="shrink-0 text-muted-foreground">{key}:</span>
                                    <span className="min-w-0 truncate text-foreground">
                                      {typeof value === "string" ? value : String(value)}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          ) : null}

                        </div>
                      )}
                    </div>
                  ) : null}

                  {!isCreatingNode && !selectedGraphNode ? (
                    <div className="grid gap-3 text-xs leading-5 text-muted-foreground sm:grid-cols-3">
                      <div className="rounded-md border border-border bg-muted/30 px-3 py-2">
                        <div className="font-medium text-foreground">{visualizationNodeCount}</div>
                        <div>节点</div>
                      </div>
                      <div className="rounded-md border border-border bg-muted/30 px-3 py-2">
                        <div className="font-medium text-foreground">{visualizationEdgeCount}</div>
                        <div>关系</div>
                      </div>
                      <div className="rounded-md border border-dashed border-border bg-muted/20 px-3 py-2">
                        <div className="font-medium text-foreground">开始探索</div>
                        <div className="mt-1">点击画布中的节点查看详情，点击关系节点可跳转探索。</div>
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>
            ) : (
              <div className="flex h-full min-h-0 flex-col items-center justify-center rounded-lg border border-dashed border-border bg-muted/20 px-4 text-center text-sm text-muted-foreground">
                <Network className="mb-3 h-8 w-8 opacity-30" />
                <p>暂无图谱数据</p>
                <p className="mt-1 text-xs">可以直接新建节点，或先刷新可视化数据。</p>
                <Button
                  type="button"
                  size="sm"
                  className="mt-4"
                  onClick={handleStartCreateNode}
                  disabled={!kgId || isSavingNewNode}
                >
                  <Plus className="mr-1.5 h-3.5 w-3.5" />
                  新建节点
                </Button>
              </div>
            )}
          </div>
        ) : null}

        {/* 查询 Tab */}
        {activeTab === "query" ? (
          <div className="space-y-4">
            <div>
              <div className="text-sm font-medium text-foreground">图谱查询</div>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                查询会在当前图谱中检索实体和关系上下文。
              </p>
            </div>

            <div className="flex gap-2">
              <Input
                value={question}
                onChange={(event) => {
                  setQuestion(event.target.value);
                  setQueryError(null);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    void handleQuery();
                  }
                }}
                placeholder="输入图谱问题..."
                disabled={!kgId || isQuerying}
              />
              <Button
                type="button"
                size="sm"
                onClick={() => void handleQuery()}
                disabled={!kgId || !question.trim() || isQuerying}
              >
                {isQuerying ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Search className="h-3.5 w-3.5" />
                )}
              </Button>
            </div>

            {queryError ? (
              <div className="flex items-start gap-2 rounded-md border border-error/20 bg-error-container px-3 py-2 text-xs text-error">
                <CircleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{queryError}</span>
              </div>
            ) : null}

            {queryResult ? (
              <div className="space-y-4">
                {/* 查询概览 */}
                <div className="flex items-center gap-2 rounded-md bg-muted/40 px-3 py-2">
                  <span className="text-[11px] text-muted-foreground">命中</span>
                  <span className="text-xs font-semibold text-foreground">
                    {queryResult.entities.length}
                  </span>
                  <span className="text-[11px] text-muted-foreground">个实体</span>
                </div>

                {/* 命中实体 */}
                {queryResult.entities.length > 0 ? (
                  <div className="space-y-2">
                    <div className="text-xs font-medium text-foreground">命中实体</div>
                    <div className="grid gap-2">
                      {queryResult.entities.map((entity, idx) => {
                        const inGraph = visualization?.nodes.some(
                          (n) => n.name === entity.name,
                        );
                        return (
                        <div
                          key={`${entity.entity_type}:${entity.name}:${idx}`}
                          className={`rounded-lg border border-border bg-background px-3 py-2.5 transition-all ${
                            inGraph
                              ? "cursor-pointer hover:shadow-sm hover:border-primary/30"
                              : "cursor-default"
                          }`}
                          onClick={inGraph ? () => handleJumpToEntityFromQuery(entity.name) : undefined}
                          title={inGraph ? "点击在可视化中定位此实体" : undefined}
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div className="flex min-w-0 items-center gap-2">
                              <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded bg-muted text-[10px] font-medium text-muted-foreground">
                                {idx + 1}
                              </span>
                              <span className="truncate text-xs font-medium text-foreground">
                                {entity.name}
                              </span>
                              {inGraph ? (
                                <Eye className="h-3 w-3 shrink-0 text-muted-foreground" />
                              ) : null}
                            </div>
                            <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                              {entity.entity_type}
                            </span>
                          </div>
                          {entity.description ? (
                            <p className="mt-1.5 line-clamp-3 text-xs leading-5 text-muted-foreground">
                              {entity.description}
                            </p>
                          ) : null}
                        </div>
                        );
                      })}
                    </div>
                  </div>
                ) : null}

                {/* 上下文 */}
                {queryResult.context ? (
                  <div className="rounded-lg border border-border bg-muted/20 px-3 py-3">
                    <div className="flex items-center gap-2 text-xs font-medium text-foreground">
                      <MessageSquareQuote className="h-3.5 w-3.5 text-muted-foreground" />
                      推理上下文
                    </div>
                    <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-muted-foreground">
                      {queryResult.context}
                    </p>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}

        {/* 设置 Tab */}
        {activeTab === "settings" ? (
          <div className="space-y-4">
            <div className="text-sm font-medium text-foreground">知识图谱设置</div>

            {/* 统计卡片 */}
            {loadingStats ? (
              <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />
                加载统计...
              </div>
            ) : graphStats ? (
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-lg border border-border bg-muted/20 px-3 py-2.5 text-center">
                  <div className="text-base font-semibold text-foreground">
                    {graphStats.entity_count ?? 0}
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-0.5">实体</div>
                </div>
                <div className="rounded-lg border border-border bg-muted/20 px-3 py-2.5 text-center">
                  <div className="text-base font-semibold text-foreground">
                    {graphStats.relation_count ?? 0}
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-0.5">关系</div>
                </div>
                <div className="rounded-lg border border-border bg-muted/20 px-3 py-2.5 text-center">
                  <div className="text-base font-semibold text-foreground">
                    {graphStats.entity_types?.length ?? 0}
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-0.5">实体类型</div>
                </div>
                <div className="rounded-lg border border-border bg-muted/20 px-3 py-2.5 text-center">
                  <div className="text-base font-semibold text-foreground">
                    {graphStats.communities ? Object.keys(graphStats.communities).length : 0}
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-0.5">社区</div>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-lg border border-border bg-muted/20 px-3 py-2.5 text-center">
                  <div className="text-base font-semibold text-foreground">{entityCount || 0}</div>
                  <div className="text-[11px] text-muted-foreground mt-0.5">实体</div>
                </div>
                <div className="rounded-lg border border-border bg-muted/20 px-3 py-2.5 text-center">
                  <div className="text-base font-semibold text-foreground">--</div>
                  <div className="text-[11px] text-muted-foreground mt-0.5">节点</div>
                </div>
              </div>
            )}

            <div className="grid gap-3 rounded-lg border border-border bg-muted/20 px-4 py-4">
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">图谱名称</span>
                <span className="font-medium text-foreground">{node.name}</span>
              </div>
              {dbPath ? (
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">数据路径</span>
                  <span className="font-medium text-foreground max-w-[180px] truncate" title={dbPath}>
                    {dbPath}
                  </span>
                </div>
              ) : null}
            </div>

            <div className="rounded-lg border border-border bg-background px-4 py-4">
              <div className="text-sm font-medium text-foreground">上传文档构建图谱</div>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                上传文档后会自动抽取实体和关系，构建知识图谱。支持 PDF、Markdown、TXT 等格式。
              </p>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="mt-3"
                onClick={() => uploadInputRef.current?.click()}
                disabled={!kgId || isUploading}
              >
                {isUploading ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Upload className="mr-1.5 h-3.5 w-3.5" />
                )}
                上传文档
              </Button>
              <input
                ref={uploadInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={handleUploadChange}
                aria-label="上传知识图谱文档"
              />
              {uploadMessage ? (
                <div className="mt-3 rounded-md border border-success/20 bg-success-container px-3 py-2 text-xs text-success">
                  {uploadMessage}
                </div>
              ) : null}
              {uploadError ? (
                <div className="mt-3 rounded-md border border-error/20 bg-error-container px-3 py-2 text-xs text-error">
                  {uploadError}
                </div>
              ) : null}
            </div>
          </div>
        ) : null}

        {/* 原始数据 Tab */}
        {activeTab === "data" && dbPath ? (
          <div className="flex h-full min-h-0 flex-col gap-3">
            {/* 表列表 */}
            {loadingGraphTables ? (
              <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />
                加载表结构...
              </div>
            ) : graphTables.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {graphTables.map((table) => (
                  <button
                    key={table.name}
                    type="button"
                    onClick={() =>
                      setRawSql(`SELECT * FROM "${table.name.replace(/"/g, "\"\"")}" LIMIT 100;`)
                    }
                    className="rounded-md border border-border bg-muted/40 px-2 py-1 text-[11px] text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                    title={`${table.name} (${table.columns.map((c) => c.name).join(", ")})`}
                  >
                    {table.name}
                  </button>
                ))}
              </div>
            ) : null}

            {/* SQL 编辑器 */}
            <div className="flex-shrink-0">
              <SqlQueryPanel
                sql={rawSql}
                onSqlChange={setRawSql}
                queryLimitInput={rawQueryLimit}
                onLimitChange={setRawQueryLimit}
                runningAction={rawRunning ? "query" : null}
                canExecute={false}
                disabled={!kgId || loadingGraphTables}
                error={rawError}
                onRunQuery={handleRunRawQuery}
                onRunExecute={() => {}}
              />
            </div>

            {/* 结果表格 */}
            <div className="min-h-0 flex-1 overflow-hidden flex flex-col">
              {rawResult ? (
                <>
                  <div className="min-h-0 flex-1 overflow-auto">
                    {rawResult.columns.length === 0 ? (
                      <div className="px-4 py-6 text-center text-[11px] text-muted-foreground">
                        查询已执行，但当前结果没有可展示的列。
                      </div>
                    ) : (
                      <div className="overflow-auto">
                        <table
                          className="w-full text-left text-[11px]"
                          style={{ tableLayout: "auto" }}
                        >
                          <thead className="sticky top-0 bg-muted/60">
                            <tr>
                              {rawResult.columns.map((column, colIdx) => (
                                <th
                                  key={`h-${colIdx}`}
                                  className="border-b border-border px-2 py-1.5 font-medium text-muted-foreground whitespace-nowrap"
                                >
                                  {column}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {rawResult.rows.map((row, index) => (
                              <tr
                                key={`${index}`}
                                className="border-b border-border/60 last:border-b-0"
                              >
                                {rawResult.columns.map((column, columnIndex) => {
                                  const value = row[column];
                                  const display =
                                    value === null || value === undefined
                                      ? "NULL"
                                      : typeof value === "string"
                                        ? value
                                        : typeof value === "number" || typeof value === "boolean"
                                          ? String(value)
                                          : JSON.stringify(value);
                                  return (
                                    <td
                                      key={`c${columnIndex}-r${index}`}
                                      className="px-2 py-1.5 align-top font-mono text-[10px] text-foreground max-w-[240px] truncate"
                                      title={display}
                                    >
                                      {display}
                                    </td>
                                  );
                                })}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                  <div className="flex-shrink-0 border-t border-border px-3 py-1.5 flex items-center gap-3 text-[11px] text-muted-foreground bg-muted/20">
                    <span className="flex items-center gap-1">
                      <span className="font-medium text-foreground">{rawResult.row_count}</span>
                      <span>行</span>
                    </span>
                  </div>
                </>
              ) : (
                <div className="flex h-full items-center justify-center px-6 text-center text-[12px] text-muted-foreground">
                  执行 SQL 后结果将显示在这里。
                </div>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
