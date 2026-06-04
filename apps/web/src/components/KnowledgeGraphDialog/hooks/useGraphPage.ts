import {
  useState,
  useEffect,
  useCallback,
  useDeferredValue,
  useMemo,
  useRef,
} from "react";
import { createGraphragApi } from "@/lib/api/graphrag";
import type {
  GraphHealth,
  GraphStatistics,
  GraphLlmStatus,
  GraphCommunitySummary,
  GraphVisualizationResponse,
  GraphQueryResponse,
  GraphEntity,
  AddGraphDocumentResponse,
  UploadGraphDocumentResponse,
  GraphExtractionMode,
} from "@/types/graphrag";
import type { LayoutMode } from "../lib/graphConfig";

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

export function useGraphPage(
  workspaceId?: string | null,
  graphId?: string | null,
) {
  const graphragApi = useMemo(
    () => createGraphragApi({ workspaceId, graphId }),
    [graphId, workspaceId],
  );

  // 核心数据状态
  const [health, setHealth] = useState<GraphHealth | null>(null);
  const [stats, setStats] = useState<GraphStatistics | null>(null);
  const [llmStatus, setLlmStatus] = useState<GraphLlmStatus | null>(null);
  const [communities, setCommunities] = useState<GraphCommunitySummary[]>([]);
  const [overviewGraph, setOverviewGraph] = useState<GraphVisualizationResponse | null>(null);

  // 加载状态
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isLoadingOverviewGraph, setIsLoadingOverviewGraph] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);

  // 文本构图状态
  const [documentText, setDocumentText] = useState("");
  const [documentId, setDocumentId] = useState("");
  const [resolveEntities, setResolveEntities] = useState(true);
  const [isSubmittingDocument, setIsSubmittingDocument] = useState(false);
  const [documentError, setDocumentError] = useState<string | null>(null);
  const [documentResult, setDocumentResult] = useState<AddGraphDocumentResponse | null>(null);

  // 文件上传状态
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadDocumentId, setUploadDocumentId] = useState("");
  const [uploadExtractionMode, setUploadExtractionMode] = useState<GraphExtractionMode>("enhanced");
  const [uploadResolveEntities, setUploadResolveEntities] = useState(true);
  const [isUploadingDocument, setIsUploadingDocument] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadResult, setUploadResult] = useState<UploadGraphDocumentResponse | null>(null);

  // 查询状态
  const [question, setQuestion] = useState("");
  const [queryTopK, setQueryTopK] = useState("5");
  const [queryDepth, setQueryDepth] = useState("1");
  const [useCommunities, setUseCommunities] = useState(false);
  const [isQuerying, setIsQuerying] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [queryResult, setQueryResult] = useState<GraphQueryResponse | null>(null);

  // UI 状态
  const [activeView, setActiveView] = useState<"overview" | "query">("overview");
  const [workspaceTab, setWorkspaceTab] = useState<"overview" | "build" | "query">("overview");
  const [buildTab, setBuildTab] = useState<"upload" | "text" | "results">("upload");
  const [inspectorTab, setInspectorTab] = useState<"search" | "details">("search");
  const layoutMode: LayoutMode = "force";
  const [searchQuery, setSearchQuery] = useState("");
  const deferredSearchQuery = useDeferredValue(searchQuery);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEntity, setSelectedEntity] = useState<GraphEntity | null>(null);
  const [isLoadingEntity, setIsLoadingEntity] = useState(false);
  const [entityError, setEntityError] = useState<string | null>(null);
  const dashboardRequestIdRef = useRef(0);

  const totalCommunities =
    communities.length ||
    Object.values(stats?.communities || {}).reduce((sum, count) => sum + count, 0);

  // 加载仪表板数据
  const loadDashboard = useCallback(async (options?: { silent?: boolean; refreshHeavyData?: boolean }) => {
    const requestId = dashboardRequestIdRef.current + 1;
    dashboardRequestIdRef.current = requestId;
    const silent = options?.silent ?? false;
    const refreshHeavyData = options?.refreshHeavyData ?? false;

    if (silent) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }

    if (refreshHeavyData) {
      setOverviewGraph(null);
      setCommunities([]);
      setLlmStatus(null);
    }

    setPageError(null);

    try {
      const [nextHealth, nextStats] = await Promise.all([
        graphragApi.getHealth(),
        graphragApi.getStatistics(),
      ]);
      if (dashboardRequestIdRef.current !== requestId) {
        return;
      }
      setHealth(nextHealth);
      setStats(nextStats);
    } catch (error) {
      if (dashboardRequestIdRef.current !== requestId) {
        return;
      }
      setPageError(getErrorMessage(error, "加载 GraphRAG 图谱概览失败"));
    } finally {
      if (dashboardRequestIdRef.current === requestId) {
        if (silent) {
          setIsRefreshing(false);
        } else {
          setIsLoading(false);
        }
      }
    }
  }, [graphragApi]);

  // 初始加载
  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  // 加载 LLM 状态
  useEffect(() => {
    if (llmStatus) return;

    let cancelled = false;
    const timer = window.setTimeout(() => {
      void graphragApi
        .getLlmStatus()
        .then((nextLlmStatus) => {
          if (!cancelled) setLlmStatus(nextLlmStatus);
        })
        .catch(() => {
          if (!cancelled) setLlmStatus(null);
        });
    }, 0);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [graphragApi, llmStatus]);

  // 加载社区数据
  useEffect(() => {
    if (communities.length > 0 || !overviewGraph?.nodes.length || workspaceTab !== "overview") {
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(() => {
      void graphragApi
        .listCommunities(0)
        .then((nextCommunities) => {
          if (!cancelled) setCommunities(nextCommunities);
        })
        .catch(() => {
          if (!cancelled) setCommunities([]);
        });
    }, 0);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [communities.length, graphragApi, overviewGraph, workspaceTab]);

  // 加载概览图
  useEffect(() => {
    if (activeView === "query" || workspaceTab !== "overview" || overviewGraph) {
      return;
    }

    let cancelled = false;
    setIsLoadingOverviewGraph(true);

    const timer = window.setTimeout(() => {
      void graphragApi
        .getVisualization(120, 0, false)
        .then((nextOverviewGraph) => {
          if (!cancelled) setOverviewGraph(nextOverviewGraph);
        })
        .catch((error) => {
          if (!cancelled) {
            setPageError((current) =>
              current || getErrorMessage(error, "加载图谱可视化数据失败"),
            );
          }
        })
        .finally(() => {
          if (!cancelled) setIsLoadingOverviewGraph(false);
        });
    }, 0);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      setIsLoadingOverviewGraph(false);
    };
  }, [activeView, graphragApi, overviewGraph, workspaceTab]);

  const activeGraph =
    activeView === "query" && queryResult?.subgraph ? queryResult.subgraph : overviewGraph;

  // 节点选择处理
  const handleSelectNode = useCallback((nodeId: string | null) => {
    setSelectedNodeId(nodeId);
    if (nodeId) {
      setInspectorTab("details");
    }
  }, []);

  // 当活动图变化时，选择第一个节点
  useEffect(() => {
    if (!activeGraph?.nodes.length) {
      setSelectedNodeId(null);
      return;
    }

    const hasSelected = selectedNodeId
      ? activeGraph.nodes.some((node) => node.id === selectedNodeId)
      : false;

    if (!hasSelected) {
      setSelectedNodeId(activeGraph.nodes[0].id);
    }
  }, [activeGraph, selectedNodeId]);

  // 加载选中实体详情
  useEffect(() => {
    if (!selectedNodeId || inspectorTab !== "details") {
      setSelectedEntity(null);
      setEntityError(null);
      setIsLoadingEntity(false);
      return;
    }

    let cancelled = false;
    const entityId = selectedNodeId;

    async function loadSelectedEntity() {
      setIsLoadingEntity(true);
      setEntityError(null);

      try {
        const entity = await graphragApi.getEntity(entityId);
        if (!cancelled) setSelectedEntity(entity);
      } catch (error) {
        if (!cancelled) {
          setSelectedEntity(null);
          setEntityError(getErrorMessage(error, "加载实体详情失败"));
        }
      } finally {
        if (!cancelled) setIsLoadingEntity(false);
      }
    }

    void loadSelectedEntity();

    return () => {
      cancelled = true;
    };
  }, [graphragApi, inspectorTab, selectedNodeId]);

  // 打开构图工作台
  const openBuildWorkspace = useCallback((nextBuildTab: "upload" | "text" | "results") => {
    setWorkspaceTab("build");
    setBuildTab(nextBuildTab);
  }, []);

  // 文本构图提交
  const handleAddDocument = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!documentText.trim()) {
      setDocumentError("请输入要构图的文档内容");
      return;
    }

    setIsSubmittingDocument(true);
    setDocumentError(null);

    try {
      const result = await graphragApi.addDocument({
        content: documentText.trim(),
        doc_id: documentId.trim() || undefined,
        resolve_entities: resolveEntities,
      });
      setDocumentResult(result);
      setDocumentId(result.doc_id);
      await loadDashboard({ silent: true, refreshHeavyData: true });
      setWorkspaceTab("build");
      setBuildTab("results");
      setActiveView("overview");
    } catch (error) {
      setDocumentError(getErrorMessage(error, "文档构图失败"));
    } finally {
      setIsSubmittingDocument(false);
    }
  };

  // 文件上传提交
  const handleUploadDocument = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile) {
      setUploadError("请选择一个待构图文件");
      return;
    }

    setIsUploadingDocument(true);
    setUploadError(null);

    try {
      const result = await graphragApi.uploadDocument(uploadFile, {
        doc_id: uploadDocumentId.trim() || undefined,
        resolve_entities: uploadResolveEntities,
        extraction_mode: uploadExtractionMode,
      });
      setUploadResult(result);
      setUploadDocumentId(result.doc_id);
      await loadDashboard({ silent: true, refreshHeavyData: true });
      setWorkspaceTab("build");
      setBuildTab("results");
      setActiveView("overview");
    } catch (error) {
      setUploadError(getErrorMessage(error, "文件构图失败"));
    } finally {
      setIsUploadingDocument(false);
    }
  };

  // 图谱查询
  const handleQuery = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) {
      setQueryError("请输入查询问题");
      return;
    }

    setIsQuerying(true);
    setQueryError(null);
    setWorkspaceTab("query");

    try {
      const result = await graphragApi.query({
        question: question.trim(),
        top_k: Number.parseInt(queryTopK, 10) || 5,
        depth: Number.parseInt(queryDepth, 10) || 1,
        use_communities: useCommunities,
      });
      setQueryResult(result);

      if (result.subgraph?.nodes.length) {
        setActiveView("query");
        setSelectedNodeId(result.subgraph.nodes[0].id);
      } else {
        setActiveView("overview");
      }
    } catch (error) {
      setQueryError(getErrorMessage(error, "图谱查询失败"));
    } finally {
      setIsQuerying(false);
    }
  };

  return {
    // 数据
    health,
    stats,
    llmStatus,
    communities,
    overviewGraph,
    activeGraph,
    totalCommunities,
    
    // 加载状态
    isLoading,
    isRefreshing,
    isLoadingOverviewGraph,
    pageError,
    
    // 文本构图
    documentText,
    setDocumentText,
    documentId,
    setDocumentId,
    resolveEntities,
    setResolveEntities,
    isSubmittingDocument,
    documentError,
    documentResult,
    
    // 文件上传
    uploadFile,
    setUploadFile,
    uploadDocumentId,
    setUploadDocumentId,
    uploadExtractionMode,
    setUploadExtractionMode,
    uploadResolveEntities,
    setUploadResolveEntities,
    isUploadingDocument,
    uploadError,
    uploadResult,
    
    // 查询
    question,
    setQuestion,
    queryTopK,
    setQueryTopK,
    queryDepth,
    setQueryDepth,
    useCommunities,
    setUseCommunities,
    isQuerying,
    queryError,
    queryResult,
    
    // UI 状态
    activeView,
    setActiveView,
    workspaceTab,
    setWorkspaceTab,
    buildTab,
    setBuildTab,
    inspectorTab,
    setInspectorTab,
    layoutMode,
    searchQuery,
    setSearchQuery,
    deferredSearchQuery,
    selectedNodeId,
    selectedEntity,
    isLoadingEntity,
    entityError,
    
    // 动作
    loadDashboard,
    handleSelectNode,
    openBuildWorkspace,
    handleAddDocument,
    handleUploadDocument,
    handleQuery,
  };
}
