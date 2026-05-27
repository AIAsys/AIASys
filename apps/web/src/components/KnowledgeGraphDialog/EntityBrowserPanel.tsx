import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Loader2, RefreshCw, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { createGraphragApi } from "@/lib/api/graphrag";
import type { GraphEntity } from "@/types/graphrag";
import {
  EmptyState,
  EntityTypeBadge,
  formatMetadataValue,
  getEntityTypeLabel,
  normalizeDisplayText,
  normalizeEntityType,
} from "@/pages/Knowledge/GraphPage/shared";

interface EntityBrowserPanelProps {
  workspaceId?: string | null;
  graphId?: string | null;
  onOpenWorkbench?: () => void;
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

export function EntityBrowserPanel({
  workspaceId = null,
  graphId = null,
  onOpenWorkbench,
}: EntityBrowserPanelProps) {
  const graphragApi = useMemo(
    () => createGraphragApi({ workspaceId, graphId }),
    [graphId, workspaceId],
  );
  const [entities, setEntities] = useState<GraphEntity[]>([]);
  const [entityTypes, setEntityTypes] = useState<string[]>([]);
  const [selectedType, setSelectedType] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const deferredSearchQuery = useDeferredValue(searchQuery.trim());

  const [selectedEntityName, setSelectedEntityName] = useState<string | null>(
    null,
  );
  const [selectedEntity, setSelectedEntity] = useState<GraphEntity | null>(
    null,
  );

  const [isLoadingEntities, setIsLoadingEntities] = useState(true);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  async function loadEntityTypes() {
    try {
      const stats = await graphragApi.getStatistics();
      const nextTypes = Array.from(
        new Set(stats.entity_types.map((type) => normalizeEntityType(type))),
      ).sort();
      setEntityTypes(nextTypes);
    } catch {
      setEntityTypes([]);
    }
  }

  async function loadEntities(silent = false) {
    if (silent) {
      setIsRefreshing(true);
    } else {
      setIsLoadingEntities(true);
    }
    setListError(null);

    try {
      const entityType = selectedType === "all" ? undefined : selectedType;
      const nextEntities = deferredSearchQuery
        ? (await graphragApi.searchEntities(deferredSearchQuery, entityType))
            .results
        : await graphragApi.listEntities(entityType, 100);
      setEntities(nextEntities);
    } catch (error) {
      setListError(getErrorMessage(error, "加载实体列表失败"));
    } finally {
      setIsLoadingEntities(false);
      setIsRefreshing(false);
    }
  }

  useEffect(() => {
    void loadEntityTypes();
  }, [graphragApi]);

  useEffect(() => {
    let cancelled = false;

    async function refreshEntities() {
      setIsLoadingEntities(true);
      setListError(null);

      try {
        const entityType = selectedType === "all" ? undefined : selectedType;
        const nextEntities = deferredSearchQuery
          ? (await graphragApi.searchEntities(deferredSearchQuery, entityType))
              .results
          : await graphragApi.listEntities(entityType, 100);

        if (!cancelled) {
          setEntities(nextEntities);
        }
      } catch (error) {
        if (!cancelled) {
          setListError(getErrorMessage(error, "加载实体列表失败"));
        }
      } finally {
        if (!cancelled) {
          setIsLoadingEntities(false);
        }
      }
    }

    void refreshEntities();

    return () => {
      cancelled = true;
    };
  }, [selectedType, deferredSearchQuery, graphragApi]);

  useEffect(() => {
    if (entities.length === 0) {
      setSelectedEntityName(null);
      setSelectedEntity(null);
      return;
    }

    const stillSelected = selectedEntityName
      ? entities.some((entity) => entity.name === selectedEntityName)
      : false;

    if (!stillSelected) {
      setSelectedEntityName(entities[0].name);
    }
  }, [entities, selectedEntityName]);

  useEffect(() => {
    let cancelled = false;

    async function loadSelectedEntity(name: string) {
      setIsLoadingDetail(true);
      setDetailError(null);

      try {
        const entity = await graphragApi.getEntity(name);
        if (!cancelled) {
          setSelectedEntity(entity);
        }
      } catch (error) {
        if (!cancelled) {
          setSelectedEntity(null);
          setDetailError(getErrorMessage(error, "加载实体详情失败"));
        }
      } finally {
        if (!cancelled) {
          setIsLoadingDetail(false);
        }
      }
    }

    if (selectedEntityName) {
      void loadSelectedEntity(selectedEntityName);
      return () => {
        cancelled = true;
      };
    }

    setSelectedEntity(null);
    setIsLoadingDetail(false);

    return () => {
      cancelled = true;
    };
  }, [graphragApi, selectedEntityName]);

  const metadataEntries = Object.entries(selectedEntity?.properties || {});
  const currentGraphLabel = graphId || "当前默认图谱";

  return (
    <div
      className="space-y-6"
      data-testid="knowledge-graph-dialog-panel-entities"
    >
      <Card className="border-border/90 bg-white/92 shadow-sm">
        <CardContent className="flex flex-col gap-4 p-5 xl:flex-row xl:items-center xl:justify-between">
          <div className="space-y-2">
            <div className="text-sm font-semibold text-foreground">实体浏览</div>
            <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
              这里直接浏览图谱里的实体节点与元数据，不显示工作区挂载关系。当前视图聚焦于单个图谱的搜索、筛查和详情核对。
            </p>
            <div className="inline-flex items-center rounded-full border border-border bg-muted px-3 py-1 text-xs text-muted-foreground">
              当前图谱: {currentGraphLabel}
            </div>
          </div>

          {onOpenWorkbench ? (
            <Button
              variant="outline"
              className="border-border bg-white"
              onClick={onOpenWorkbench}
            >
              切到图谱工作台
            </Button>
          ) : null}
        </CardContent>
      </Card>

      <Card className="border-border/90 shadow-sm">
        <CardContent className="flex flex-col gap-4 p-5 lg:flex-row lg:items-center lg:justify-between">
          <div className="grid flex-1 gap-4 md:grid-cols-[minmax(0,1fr)_220px]">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="搜索实体名称、别名或描述关键词"
                className="pl-10"
              />
            </div>

            <select
              value={selectedType}
              onChange={(event) => setSelectedType(event.target.value)}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm text-muted-foreground"
              aria-label="实体类型筛选"
            >
              <option value="all">全部类型</option>
              {entityTypes.map((type) => (
                <option key={type} value={type}>
                  {getEntityTypeLabel(type)}
                </option>
              ))}
            </select>
          </div>

          <Button
            variant="outline"
            className="gap-2"
            disabled={isRefreshing}
            onClick={() => {
              void loadEntityTypes();
              void loadEntities(true);
            }}
          >
            <RefreshCw
              className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`}
            />
            刷新
          </Button>
        </CardContent>
      </Card>

      {listError ? (
        <div className="flex items-start gap-3 rounded-2xl border border-warning/20 bg-warning-container p-4 text-sm text-warning">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>{listError}</div>
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <Card className="border-border/90 shadow-sm">
          <CardHeader>
            <CardTitle className="text-xl text-foreground">实体列表</CardTitle>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              当前结果最多显示 100 条，输入关键词后会自动切换到后端搜索接口。
            </p>
          </CardHeader>
          <CardContent>
            {isLoadingEntities ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                正在加载实体列表...
              </div>
            ) : entities.length > 0 ? (
              <div className="max-h-[720px] space-y-3 overflow-auto pr-1">
                {entities.map((entity) => {
                  const isSelected = entity.name === selectedEntityName;
                  return (
                    <button
                      key={`${entity.name}-${entity.entity_type}`}
                      type="button"
                      onClick={() => setSelectedEntityName(entity.name)}
                      className={`w-full rounded-2xl border p-4 text-left transition ${
                        isSelected
                          ? "border-info/20 bg-info-container shadow-sm"
                          : "border-border bg-white hover:border-border hover:bg-muted"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate text-base font-semibold text-foreground">
                            {normalizeDisplayText(entity.name)}
                          </div>
                          <div className="mt-2">
                            <EntityTypeBadge entityType={entity.entity_type} />
                          </div>
                        </div>
                        <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                          {Object.keys(entity.properties || {}).length} meta
                        </div>
                      </div>
                      <p className="mt-3 text-sm leading-6 text-muted-foreground">
                        {normalizeDisplayText(entity.description) ||
                          "当前实体没有描述信息。"}
                      </p>
                    </button>
                  );
                })}
              </div>
            ) : (
              <EmptyState
                title="没有找到匹配实体"
                description="可以更换关键词，或者先回到图谱工作台继续构入测试文档。"
              />
            )}
          </CardContent>
        </Card>

        <Card className="border-border/90 shadow-sm">
          <CardHeader>
            <CardTitle className="text-xl text-foreground">实体详情</CardTitle>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              详情从后端单实体接口实时拉取，用于确认描述和元数据是否稳定。
            </p>
          </CardHeader>
          <CardContent>
            {detailError ? (
              <div className="rounded-xl border border-error/20 bg-error-container px-4 py-3 text-sm text-error">
                {detailError}
              </div>
            ) : null}

            {isLoadingDetail ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                正在加载实体详情...
              </div>
            ) : selectedEntity ? (
              <div className="space-y-6">
                <div className="rounded-2xl border border-border bg-muted/80 p-5">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <h2 className="text-2xl font-semibold text-foreground">
                        {normalizeDisplayText(selectedEntity.name)}
                      </h2>
                      <div className="mt-3">
                        <EntityTypeBadge
                          entityType={selectedEntity.entity_type}
                        />
                      </div>
                    </div>
                    <div className="rounded-xl bg-white px-3 py-2 text-xs uppercase tracking-[0.18em] text-muted-foreground shadow-sm">
                      metadata {metadataEntries.length}
                    </div>
                  </div>
                  <p className="mt-4 text-sm leading-7 text-muted-foreground">
                    {normalizeDisplayText(selectedEntity.description) ||
                      "当前实体没有描述信息。"}
                  </p>
                </div>

                <div className="space-y-3">
                  <div className="text-sm font-medium text-muted-foreground">
                    元数据
                  </div>
                  {metadataEntries.length > 0 ? (
                    <div className="space-y-3">
                      {metadataEntries.map(([key, value]) => (
                        <div
                          key={key}
                          className="rounded-2xl border border-border bg-white p-4 shadow-sm"
                        >
                          <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                            {key}
                          </div>
                          <div className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-muted-foreground">
                            {formatMetadataValue(value)}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState
                      title="没有可展示的元数据"
                      description="当前实体结构里还没有额外元数据字段，这通常说明它来自最小抽取结果或占位节点。"
                    />
                  )}
                </div>
              </div>
            ) : (
              <EmptyState
                title="还没有选中实体"
                description="从左侧列表里点选一个实体，这里会展示名称、类型、描述和元数据。"
              />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
