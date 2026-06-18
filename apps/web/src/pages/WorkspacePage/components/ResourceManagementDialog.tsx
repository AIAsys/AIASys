import { useEffect, useMemo, useState } from "react";
import {
  LibraryBig,
  Network,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { KnowledgeBaseMarket } from "@/components/KnowledgeBaseMarket";
import {
  useWorkspaceKnowledgeBaseContext,
} from "@/pages/Knowledge/hooks/useKnowledgeWorkspaceContext";
import { GraphWorkbench } from "@/pages/Knowledge/GraphPage/components/GraphWorkbench";
import { CommunityAnalysisPanel } from "@/components/KnowledgeGraphDialog/CommunityAnalysisPanel";
import { EntityBrowserPanel } from "@/components/KnowledgeGraphDialog/EntityBrowserPanel";
import type {
  KnowledgeBaseDialogTab,
  KnowledgeGraphDialogTab,
  ResourceManagementSection,
} from "../hooks/useWorkspaceOverlayState";
import {
  KnowledgeDialogScaffold,
  type KnowledgeDialogNavItem,
} from "./KnowledgeDialogScaffold";

type WorkspaceKnowledgeBaseContextValue = ReturnType<
  typeof useWorkspaceKnowledgeBaseContext
>;

interface ResourceManagementDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultSection?: ResourceManagementSection;
  defaultKnowledgeBaseTab?: KnowledgeBaseDialogTab;
  defaultKnowledgeGraphTab?: KnowledgeGraphDialogTab;
}

const RESOURCE_NAV_ITEMS: Array<
  KnowledgeDialogNavItem<ResourceManagementSection>
> = [
  {
    id: "knowledge_base",
    label: "知识库",
    description: "知识库目录与管理",
    icon: LibraryBig,
  },
  {
    id: "knowledge_graph",
    label: "知识图谱",
    description: "图谱工作台与管理",
    icon: Network,
  },
];

function ResourceSectionHeader({
  icon: Icon,
  title,
  description,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
}) {
  return (
    <div className="flex items-center gap-3 border-b bg-muted/20 px-5 py-3">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
        <Icon className="h-4 w-4 text-primary" />
      </div>
      <div>
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
    </div>
  );
}

function KnowledgeBaseResourceSection({
  workspaceId,
  knowledgeBaseId,
  knowledgeBaseContext,
}: {
  workspaceId?: string | null;
  knowledgeBaseId?: string | null;
  knowledgeBaseContext: WorkspaceKnowledgeBaseContextValue;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <ResourceSectionHeader
        icon={LibraryBig}
        title="知识库目录"
        description={
          workspaceId
            ? `当前工作区：${knowledgeBaseContext.workspaceTitle || workspaceId}`
            : "当前以全局资源视角管理知识库，不限定到某个工作区。"
        }
      />
      <div className="min-h-0 flex-1 overflow-y-auto bg-muted/10">
        <KnowledgeBaseMarket
          mode="page"
          pageLayout="split"
          defaultKnowledgeBaseId={knowledgeBaseId || null}
          listTitle="知识库目录"
          listDescription="当前用户可见的知识库"
        />
      </div>
    </div>
  );
}

function KnowledgeGraphResourceSection({
  workspaceId,
  graphId,
  defaultTab,
}: {
  workspaceId?: string | null;
  graphId?: string | null;
  defaultTab: KnowledgeGraphDialogTab;
}) {
  const [selectedGraphId, setSelectedGraphId] = useState<string | null>(
    graphId || null,
  );
  const [activeTab, setActiveTab] =
    useState<KnowledgeGraphDialogTab>(defaultTab);

  useEffect(() => {
    setSelectedGraphId(graphId || null);
  }, [graphId]);

  useEffect(() => {
    setActiveTab(defaultTab);
  }, [defaultTab]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ResourceSectionHeader
        icon={Sparkles}
        title="图谱工作台"
        description={
          workspaceId
            ? selectedGraphId
              ? `当前工作区内正在查看图谱 ${selectedGraphId}。`
              : "当前工作区下还没有选中图谱。"
            : "当前以全局图谱视角浏览；如需按工作区限制，请从某个工作区内打开资源管理。"
        }
      />

      <div className="min-h-0 flex-1 overflow-y-auto bg-[radial-gradient(circle_at_top,_rgba(14,165,233,0.08),_transparent_38%),linear-gradient(180deg,#f8fafc_0%,#eef6ff_100%)] px-6 py-5">
        {activeTab === "workbench" ? (
          <GraphWorkbench
            key={`${workspaceId || "graph-dialog"}:${selectedGraphId || "default"}`}
            workspaceId={workspaceId}
            graphId={selectedGraphId}
            presentation="page"
          />
        ) : null}

        {activeTab === "entities" ? (
          <EntityBrowserPanel
            workspaceId={workspaceId}
            graphId={selectedGraphId}
            onOpenWorkbench={() => setActiveTab("workbench")}
          />
        ) : null}

        {activeTab === "communities" ? (
          <CommunityAnalysisPanel
            workspaceId={workspaceId}
            graphId={selectedGraphId}
            onOpenWorkbench={() => setActiveTab("workbench")}
          />
        ) : null}
      </div>
    </div>
  );
}

export function ResourceManagementDialog({
  open,
  onOpenChange,
  defaultSection = "knowledge_base",
  defaultKnowledgeGraphTab = "workbench",
}: ResourceManagementDialogProps) {
  const routeSearch =
    typeof window === "undefined" ? "" : window.location.search;
  const routeParams = useMemo(() => new URLSearchParams(routeSearch), [routeSearch]);
  const workspaceId = routeParams.get("workspace_id");
  const graphId = routeParams.get("graph_id");
  const knowledgeBaseId = routeParams.get("kb_id");
  const [activeSection, setActiveSection] =
    useState<ResourceManagementSection>(defaultSection);

  const knowledgeBaseContext = useWorkspaceKnowledgeBaseContext(workspaceId, {
    enabled: open && activeSection === "knowledge_base",
  });

  useEffect(() => {
    if (!open) {
      return;
    }
    setActiveSection(defaultSection);
  }, [defaultSection, open]);

  const sidebarSummary = useMemo(() => {
    if (activeSection === "knowledge_base") {
      if (!workspaceId) {
        return "当前以全局资源视角管理知识库，不限定到某个工作区。";
      }
      return `当前工作区：${knowledgeBaseContext.workspaceTitle || workspaceId} · 全部知识库可见`;
    }

    if (!workspaceId) {
      return "当前以全局图谱视角浏览知识图谱，不限定到某个工作区。";
    }
    return `当前工作区：${workspaceId} · 知识图谱`;
  }, [
    activeSection,
    knowledgeBaseContext.workspaceTitle,
    workspaceId,
  ]);

  return (
    <KnowledgeDialogScaffold
      open={open}
      onOpenChange={onOpenChange}
      title="资源管理"
      description="在分析页内统一管理知识库与知识图谱。"
      sidebarSummary={sidebarSummary}
      activeTab={activeSection}
      navItems={RESOURCE_NAV_ITEMS}
      onTabChange={setActiveSection}
      testIdPrefix="resource-management-dialog"
    >
      {activeSection === "knowledge_base" ? (
        <KnowledgeBaseResourceSection
          workspaceId={workspaceId}
          knowledgeBaseId={knowledgeBaseId}
          knowledgeBaseContext={knowledgeBaseContext}
        />
      ) : null}

      {activeSection === "knowledge_graph" ? (
        <KnowledgeGraphResourceSection
          workspaceId={workspaceId}
          graphId={graphId}
          defaultTab={defaultKnowledgeGraphTab}
        />
      ) : null}
    </KnowledgeDialogScaffold>
  );
}
