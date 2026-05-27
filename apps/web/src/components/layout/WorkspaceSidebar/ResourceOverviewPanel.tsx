/**
 * ResourceOverviewPanel — 工作区资源概览面板。
 *
 * 从 WorkspaceContextPanel.tsx 提取，显示知识库、知识图谱和数据库连接的状态卡片。
 */

import { Database, LibraryBig, Network } from "lucide-react";
import { RuntimeDatabaseConsole } from "@/components/database/RuntimeDatabaseConsole";
import type { WorkspaceOverviewResourceBucket } from "@/types/workspace";
import {
  CenterCanvasHero,
  LocalResourceCard,
  ResourceMetricCard,
  SummaryChip,
  WorkspaceResourceMountCard,
} from "./WorkspaceSummaryCards";

interface ResourceOverviewPanelProps {
  workspaceId: string | null;
  isLoading: boolean;
  knowledgeBaseCount: number;
  knowledgeGraphCount: number;
  databaseCount: number;
  sessionId?: string;
  knowledgeBaseNames: string[];
  knowledgeGraphItem: WorkspaceOverviewResourceBucket | null;
  databaseItem: WorkspaceOverviewResourceBucket | null;
  onOpenKnowledgeBase?: () => void;
  onOpenKnowledgeGraph?: () => void;
  onManageResources?: () => void;
  onManageDatabases?: () => void;
}

function getKnowledgeGraphItems(
  bucket: WorkspaceOverviewResourceBucket | null,
): Array<{ id: string; label: string }> {
  const rawGraphs = bucket?.metadata?.available_graphs;
  if (Array.isArray(rawGraphs)) {
    return rawGraphs
      .map((item) => {
        if (!item || typeof item !== "object") {
          return null;
        }
        const record = item as { id?: unknown; name?: unknown };
        const id = String(record.id || "").trim();
        if (!id) {
          return null;
        }
        const name = String(record.name || "").trim();
        return {
          id,
          label: name || id,
        };
      })
      .filter((item): item is { id: string; label: string } => Boolean(item));
  }

  return (
    (bucket?.metadata?.available_graph_ids as string[] | undefined) || []
  )
    .filter(Boolean)
    .map((id) => ({ id, label: id }));
}

export function ResourceOverviewPanel({
  workspaceId,
  isLoading,
  knowledgeBaseCount,
  knowledgeGraphCount,
  databaseCount,
  sessionId,
  knowledgeBaseNames,
  knowledgeGraphItem,
  databaseItem,
  onOpenKnowledgeBase,
  onOpenKnowledgeGraph,
  onManageResources,
  onManageDatabases,
}: ResourceOverviewPanelProps) {
  return (
    <div className="min-h-0 h-full overflow-y-auto overscroll-contain px-6 pb-8 pt-4">
      <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-5">
        <CenterCanvasHero
          eyebrow="工作区资源"
          title="资源"
          description="数据库、知识库、知识图谱和文件统一收口。这里看资源本体、默认可见数据源、当前会话可查询范围和可使用状态。"
          badge={
            <SummaryChip className="border-tertiary/20 bg-tertiary-container text-on-tertiary-container">
              {workspaceId ? "当前工作区" : "未绑定工作区"}
            </SummaryChip>
          }
        />

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <ResourceMetricCard
            label="知识库"
            value={isLoading ? "..." : knowledgeBaseCount}
            hint="已创建的知识库数量。"
          />
          <ResourceMetricCard
            label="知识图谱"
            value={isLoading ? "..." : knowledgeGraphCount}
            hint="已创建的图谱数量。"
          />
          <ResourceMetricCard
            label="数据库"
            value={isLoading ? "..." : databaseCount}
            hint="已配置的数据库连接。"
          />
        </div>

        <RuntimeDatabaseConsole sessionId={sessionId} />

        <div className="grid gap-4">
          <LocalResourceCard
            testId="sidebar-workspace-resource-knowledge-base"
            title="知识库"
            count={knowledgeBaseCount}
            items={knowledgeBaseNames.map((id) => ({
              id,
              label: id,
            }))}
            icon={<LibraryBig className="h-4 w-4 text-info" />}
            actionLabel={onOpenKnowledgeBase ? "打开知识库" : undefined}
            onAction={onOpenKnowledgeBase}
            createLabel={onManageResources ? "管理" : undefined}
            onCreate={onManageResources}
          />
          <LocalResourceCard
            testId="sidebar-workspace-resource-knowledge-graph"
            title="知识图谱"
            count={knowledgeGraphCount}
            items={getKnowledgeGraphItems(knowledgeGraphItem)}
            icon={<Network className="h-4 w-4 text-success" />}
            actionLabel={onOpenKnowledgeGraph ? "打开图谱" : undefined}
            onAction={onOpenKnowledgeGraph}
            createLabel={onManageResources ? "管理" : undefined}
            onCreate={onManageResources}
          />
          <WorkspaceResourceMountCard
            title="外部数据库"
            description="外部数据库连接需要配置并测试通过后，才能在本页 SQL 控制台中查询。"
            icon={<Database className="h-4 w-4 text-tertiary" />}
            bucket={databaseItem}
            secondaryActionLabel={onManageDatabases ? "管理数据库连接" : undefined}
            onSecondaryAction={onManageDatabases}
          />
        </div>
      </div>
    </div>
  );
}
