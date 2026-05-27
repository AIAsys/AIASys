import {
  AlertTriangle,
  FileCog,
  MessageSquareQuote,
  Waypoints,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { BuildTab } from "./BuildTab";
import { MetricCards } from "./MetricCards";
import { OverviewTab } from "./OverviewTab";
import { QueryTab } from "./QueryTab";
import { useGraphPage } from "../hooks/useGraphPage";

interface GraphWorkbenchProps {
  workspaceId?: string | null;
  graphId?: string | null;
  presentation?: "page" | "dialog";
}

function DialogWorkbenchRail({
  workspaceTab,
  onWorkspaceTabChange,
  currentGraphId,
  activeGraph,
  totalCommunities,
}: {
  workspaceTab: "overview" | "build" | "query";
  onWorkspaceTabChange: (tab: "overview" | "build" | "query") => void;
  currentGraphId?: string;
  activeGraph: { nodes: Array<{ id: string }>; edges: Array<{ id: string }> } | null;
  totalCommunities: number;
}) {
  const items = [
    {
      id: "overview" as const,
      label: "图谱概览",
      description: "把画布和节点面板作为主工作区",
      icon: Waypoints,
    },
    {
      id: "build" as const,
      label: "构图工作台",
      description: "导入文档、文本构图、查看最近构图结果",
      icon: FileCog,
    },
    {
      id: "query" as const,
      label: "图谱问答",
      description: "围绕当前图谱提问，并把命中子图拉回主画布",
      icon: MessageSquareQuote,
    },
  ];
  return (
    <aside className="flex min-h-0 flex-col overflow-y-auto rounded-2xl border border-border/90 bg-white/92 p-4 shadow-sm">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge className="bg-foreground text-white">
            图谱 {currentGraphId || "--"}
          </Badge>
          <Badge variant="outline" className="border-border bg-muted text-muted-foreground">
            图探索
          </Badge>
        </div>

        <div>
          <div className="text-base font-semibold text-foreground">
            图谱工作台
          </div>
          <div className="mt-1 text-sm leading-6 text-muted-foreground">
            偏 Electron 的工作方式应该先固定左侧工作模式，再把右侧主区留给图画布、构图和问答操作。
          </div>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2">
        <div className="rounded-xl border border-border bg-muted/90 px-3 py-2.5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            节点
          </div>
          <div className="mt-1 text-lg font-semibold text-foreground">
            {activeGraph?.nodes.length ?? 0}
          </div>
        </div>
        <div className="rounded-xl border border-border bg-muted/90 px-3 py-2.5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            关系
          </div>
          <div className="mt-1 text-lg font-semibold text-foreground">
            {activeGraph?.edges.length ?? 0}
          </div>
        </div>
        <div className="rounded-xl border border-border bg-muted/90 px-3 py-2.5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            社区
          </div>
          <div className="mt-1 text-lg font-semibold text-foreground">
            {totalCommunities}
          </div>
        </div>
        <div className="rounded-xl border border-border bg-muted/90 px-3 py-2.5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            当前模式
          </div>
          <div className="mt-1 text-sm font-semibold text-foreground">
            {workspaceTab === "overview"
              ? "看图"
              : workspaceTab === "build"
                ? "构图"
                : "问答"}
          </div>
        </div>
      </div>

      <div className="mt-5 text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
        工作模式
      </div>
      <div className="mt-2 space-y-2">
        {items.map((item) => {
          const Icon = item.icon;
          const active = item.id === workspaceTab;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onWorkspaceTabChange(item.id)}
              className={cn(
                "w-full rounded-2xl border px-4 py-3 text-left transition-colors",
                active
                  ? "border-foreground bg-foreground text-white shadow-sm"
                  : "border-border bg-muted/70 text-foreground hover:border-border hover:bg-white",
              )}
            >
              <div className="flex items-center gap-2 text-sm font-medium">
                <Icon className={cn("h-4 w-4", active ? "text-white" : "text-muted-foreground")} />
                {item.label}
              </div>
              <div
                className={cn(
                  "mt-1 text-xs leading-5",
                  active ? "text-muted-foreground" : "text-muted-foreground",
                )}
              >
                {item.description}
              </div>
            </button>
          );
        })}
      </div>
      <div className="mt-4 rounded-2xl border border-border bg-muted/90 px-4 py-3">
        <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
          当前模式提示
        </div>
        <div className="mt-2 text-sm leading-6 text-muted-foreground">
          {workspaceTab === "overview"
            ? "先在这里看图和点节点，右侧节点面板承接细节。"
            : workspaceTab === "build"
              ? "构图完成后会回流到同一个图谱主区，不必离开当前弹窗。"
              : "问答命中的子图会直接回到图谱主区聚焦浏览。"}
        </div>
      </div>
    </aside>
  );
}

export function GraphWorkbench({
  workspaceId,
  graphId,
  presentation = "page",
}: GraphWorkbenchProps) {
  const isDialogPresentation = presentation === "dialog";
  const {
    health,
    stats,
    llmStatus,
    communities,
    activeGraph,
    totalCommunities,
    isLoading,
    isRefreshing,
    isLoadingOverviewGraph,
    pageError,
    documentText,
    setDocumentText,
    documentId,
    setDocumentId,
    resolveEntities,
    setResolveEntities,
    isSubmittingDocument,
    documentError,
    documentResult,
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
    activeView,
    setActiveView,
    workspaceTab,
    setWorkspaceTab,
    buildTab,
    setBuildTab,
    inspectorTab,
    setInspectorTab,
    layoutMode,
    deferredSearchQuery,
    setSearchQuery,
    selectedNodeId,
    selectedEntity,
    isLoadingEntity,
    entityError,
    loadDashboard,
    handleSelectNode,
    openBuildWorkspace,
    handleAddDocument,
    handleUploadDocument,
    handleQuery,
  } = useGraphPage(workspaceId, graphId);

  const selectedGraphNode =
    activeGraph?.nodes.find((node) => node.id === selectedNodeId) || null;

  if (isDialogPresentation) {
    return (
      <div className="grid h-full min-h-0 grid-cols-[268px_minmax(0,1fr)] gap-4">
        <DialogWorkbenchRail
          workspaceTab={workspaceTab}
          onWorkspaceTabChange={setWorkspaceTab}
          currentGraphId={health?.kb_id}
          activeGraph={activeGraph}
          totalCommunities={totalCommunities}
        />

        <div className="flex min-h-0 flex-col gap-4 overflow-hidden">
          {pageError ? (
            <div className="flex items-start gap-3 rounded-2xl border border-warning/20 bg-warning-container p-4 text-sm text-warning">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <div>{pageError}</div>
            </div>
          ) : null}

          {workspaceTab === "overview" ? (
            <div className="min-h-0 flex-1 overflow-y-auto pr-1">
              <OverviewTab
                activeGraph={activeGraph}
                activeView={activeView}
                selectedNodeId={selectedNodeId}
                searchQuery={deferredSearchQuery}
                layoutMode={layoutMode}
                isLoading={isLoading}
                isRefreshing={isRefreshing}
                isLoadingOverviewGraph={isLoadingOverviewGraph}
                selectedGraphNode={selectedGraphNode}
                selectedEntity={selectedEntity}
                isLoadingEntity={isLoadingEntity}
                entityError={entityError}
                inspectorTab={inspectorTab}
                onActiveViewChange={setActiveView}
                onRefresh={() =>
                  loadDashboard({ silent: true, refreshHeavyData: true })
                }
                onSelectNode={handleSelectNode}
                onInspectorTabChange={setInspectorTab}
                onSearchQueryChange={setSearchQuery}
                presentation="dialog"
              />
            </div>
          ) : workspaceTab === "build" ? (
            <div className="min-h-0 flex-1 overflow-y-auto pr-1">
              <BuildTab
                buildTab={buildTab}
                isRefreshing={isRefreshing}
                uploadFile={uploadFile}
                uploadDocumentId={uploadDocumentId}
                uploadExtractionMode={uploadExtractionMode}
                uploadResolveEntities={uploadResolveEntities}
                isUploadingDocument={isUploadingDocument}
                uploadError={uploadError}
                uploadResult={uploadResult}
                documentText={documentText}
                documentId={documentId}
                resolveEntities={resolveEntities}
                isSubmittingDocument={isSubmittingDocument}
                documentError={documentError}
                documentResult={documentResult}
                onBuildTabChange={setBuildTab}
                onRefresh={() =>
                  loadDashboard({ silent: true, refreshHeavyData: true })
                }
                onUploadFileChange={setUploadFile}
                onUploadIdChange={setUploadDocumentId}
                onUploadExtractionModeChange={setUploadExtractionMode}
                onUploadResolveEntitiesChange={setUploadResolveEntities}
                onUploadSubmit={handleUploadDocument}
                onTextChange={setDocumentText}
                onTextIdChange={setDocumentId}
                onTextResolveEntitiesChange={setResolveEntities}
                onTextSubmit={handleAddDocument}
                onOpenUpload={() => openBuildWorkspace("upload")}
                onOpenText={() => openBuildWorkspace("text")}
              />
            </div>
          ) : (
            <div className="min-h-0 flex-1 overflow-y-auto pr-1">
              <QueryTab
                question={question}
                queryTopK={queryTopK}
                queryDepth={queryDepth}
                useCommunities={useCommunities}
                isQuerying={isQuerying}
                queryError={queryError}
                queryResult={queryResult}
                onQuestionChange={setQuestion}
                onTopKChange={setQueryTopK}
                onDepthChange={setQueryDepth}
                onUseCommunitiesChange={setUseCommunities}
                onSubmit={handleQuery}
                onEntityClick={(entityName, hasSubgraph) => {
                  handleSelectNode(entityName);
                  if (hasSubgraph) {
                    setActiveView("query");
                    setWorkspaceTab("overview");
                  }
                }}
              />
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {pageError ? (
        <div className="flex items-start gap-3 rounded-2xl border border-warning/20 bg-warning-container p-4 text-sm text-warning">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>{pageError}</div>
        </div>
      ) : null}

      <MetricCards
        activeGraph={activeGraph}
        activeView={activeView}
        totalCommunities={totalCommunities}
        communitiesCount={communities.length}
        llmStatus={llmStatus}
        healthLlmStatus={health?.llm_status}
        statsLlmStatus={stats?.llm_status}
        currentGraphId={health?.kb_id}
      />

      <div className="space-y-4">
        <div
          className="rounded-3xl border border-border/90 bg-white/85 p-3 shadow-sm"
        >
          <div className="grid h-auto w-full grid-cols-3 rounded-2xl bg-muted p-1">
            {[
              ["overview", "图谱概览"],
              ["build", "构图工作台"],
              ["query", "图谱问答"],
            ].map(([value, label]) => {
              const active = workspaceTab === value;
              return (
                <button
                  key={value}
                  type="button"
                  onClick={() =>
                    setWorkspaceTab(value as "overview" | "build" | "query")
                  }
                  className={cn(
                    "rounded-xl py-2.5 text-sm font-medium transition-colors",
                    active
                      ? "bg-white text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>

        {workspaceTab === "overview" ? (
          <OverviewTab
            activeGraph={activeGraph}
            activeView={activeView}
            selectedNodeId={selectedNodeId}
            searchQuery={deferredSearchQuery}
            layoutMode={layoutMode}
            isLoading={isLoading}
            isRefreshing={isRefreshing}
            isLoadingOverviewGraph={isLoadingOverviewGraph}
            selectedGraphNode={selectedGraphNode}
            selectedEntity={selectedEntity}
            isLoadingEntity={isLoadingEntity}
            entityError={entityError}
            inspectorTab={inspectorTab}
            onActiveViewChange={setActiveView}
            onRefresh={() => loadDashboard({ silent: true, refreshHeavyData: true })}
            onSelectNode={handleSelectNode}
            onInspectorTabChange={setInspectorTab}
            onSearchQueryChange={setSearchQuery}
          />
        ) : null}

        {workspaceTab === "build" ? (
          <BuildTab
            buildTab={buildTab}
            isRefreshing={isRefreshing}
            uploadFile={uploadFile}
            uploadDocumentId={uploadDocumentId}
            uploadExtractionMode={uploadExtractionMode}
            uploadResolveEntities={uploadResolveEntities}
            isUploadingDocument={isUploadingDocument}
            uploadError={uploadError}
            uploadResult={uploadResult}
            documentText={documentText}
            documentId={documentId}
            resolveEntities={resolveEntities}
            isSubmittingDocument={isSubmittingDocument}
            documentError={documentError}
            documentResult={documentResult}
            onBuildTabChange={setBuildTab}
            onRefresh={() => loadDashboard({ silent: true, refreshHeavyData: true })}
            onUploadFileChange={setUploadFile}
            onUploadIdChange={setUploadDocumentId}
            onUploadExtractionModeChange={setUploadExtractionMode}
            onUploadResolveEntitiesChange={setUploadResolveEntities}
            onUploadSubmit={handleUploadDocument}
            onTextChange={setDocumentText}
            onTextIdChange={setDocumentId}
            onTextResolveEntitiesChange={setResolveEntities}
            onTextSubmit={handleAddDocument}
            onOpenUpload={() => openBuildWorkspace("upload")}
            onOpenText={() => openBuildWorkspace("text")}
          />
        ) : null}

        {workspaceTab === "query" ? (
          <QueryTab
            question={question}
            queryTopK={queryTopK}
            queryDepth={queryDepth}
            useCommunities={useCommunities}
            isQuerying={isQuerying}
            queryError={queryError}
            queryResult={queryResult}
            onQuestionChange={setQuestion}
            onTopKChange={setQueryTopK}
            onDepthChange={setQueryDepth}
            onUseCommunitiesChange={setUseCommunities}
            onSubmit={handleQuery}
            onEntityClick={(entityName, hasSubgraph) => {
              handleSelectNode(entityName);
              if (hasSubgraph) {
                setActiveView("query");
              }
            }}
          />
        ) : null}
      </div>
    </div>
  );
}
