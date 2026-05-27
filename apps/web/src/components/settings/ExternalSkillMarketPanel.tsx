import { useEffect, useMemo, useRef, useState } from "react";
import {
  CloudDownload,
  Download,
  ExternalLink,
  Loader2,
  Search,
  Star,
  User,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useExternalSkillMarket } from "@/hooks/useExternalSkillMarket";

interface ExternalSkillMarketPanelProps {
  workspaceId?: string | null;
  installedSkillNames?: string[];
  onInstalled?: () => void;
}

type SortOption = "recommended" | "downloads" | "stars";

const SORT_OPTIONS: Array<{
  value: SortOption;
  label: string;
}> = [
  { value: "recommended", label: "推荐" },
  { value: "downloads", label: "下载量" },
  { value: "stars", label: "收藏量" },
];

export function ExternalSkillMarketPanel({
  workspaceId,
  installedSkillNames = [],
  onInstalled,
}: ExternalSkillMarketPanelProps) {
  const {
    sources,
    selectedSourceId,
    setSelectedSourceId,
    items,
    availableCategories,
    totalCount,
    hasMoreItems,
    loadingSources,
    loadingItems,
    loadingMoreItems,
    loadingDetail,
    installingItemId,
    error,
    detail,
    loadDetail,
    refreshItems,
    loadNextPage,
    searchQuery,
    setSearchQuery,
    selectedCategory,
    setSelectedCategory,
    sortBy,
    setSortBy,
    installItem,
  } = useExternalSkillMarket();
  const [detailOpen, setDetailOpen] = useState(false);
  const [installMessage, setInstallMessage] = useState<string | null>(null);
  const [installMessageTone, setInstallMessageTone] = useState<
    "success" | "error"
  >("success");
  const listRef = useRef<HTMLDivElement | null>(null);

  const installedSet = useMemo(
    () => new Set(installedSkillNames),
    [installedSkillNames],
  );
  useEffect(() => {
    const container = listRef.current;
    if (!container) return;
    const handleScroll = () => {
      const remaining =
        container.scrollHeight - container.scrollTop - container.clientHeight;
      if (remaining <= 240) {
        void loadNextPage();
      }
    };
    container.addEventListener("scroll", handleScroll);
    handleScroll();
    return () => {
      container.removeEventListener("scroll", handleScroll);
    };
  }, [items.length, loadNextPage, selectedSourceId, selectedCategory, sortBy]);

  const openDetail = async (itemId: string) => {
    if (!selectedSourceId) return;
    setInstallMessage(null);
    setInstallMessageTone("success");
    setDetailOpen(true);
    await loadDetail(selectedSourceId, itemId);
  };

  const handleInstall = async (itemId: string) => {
    if (!workspaceId || !selectedSourceId) return;
    setInstallMessage(null);
    setInstallMessageTone("success");
    const success = await installItem({
      workspaceId,
      sourceId: selectedSourceId,
      itemId,
    });
    if (!success) {
      setInstallMessageTone("error");
      setInstallMessage("安装失败，可能是工作区已存在同名技能或外部源不可用。");
      return;
    }
    setInstallMessageTone("success");
    setInstallMessage("已安装到当前工作区。");
    onInstalled?.();
    await refreshItems();
    if (selectedSourceId) {
      await loadDetail(selectedSourceId, itemId);
    }
  };

  return (
    <div className="flex h-full flex-col gap-3 overflow-hidden">
      {/* Toolbar */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          {loadingSources ? (
            <>
              <Skeleton className="h-7 w-20 rounded-full" />
              <Skeleton className="h-7 w-20 rounded-full" />
            </>
          ) : (
            sources.map((source) => {
              const active = source.source_id === selectedSourceId;
              return (
                <button
                  key={source.source_id}
                  type="button"
                  onClick={() => setSelectedSourceId(source.source_id)}
                  className={`rounded-full border px-3 py-1 text-[11px] transition-colors ${
                    active
                      ? "border-tertiary/30 bg-tertiary-container text-on-tertiary-container"
                      : "border-border bg-card text-muted-foreground hover:bg-accent"
                  }`}
                >
                  {source.display_name}
                </button>
              );
            })
          )}
          <div className="flex-1" />
          <span className="text-[11px] text-muted-foreground">
            {items.length} / {totalCount}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <div className="relative flex-1 max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="搜索技能名称或分类"
              className="pl-9 h-8 text-xs"
            />
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 text-xs"
            onClick={() => void refreshItems()}
          >
            刷新
          </Button>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => setSelectedCategory(null)}
            className={`rounded-full border px-2.5 py-0.5 text-[11px] transition-colors ${
              selectedCategory === null
                ? "border-tertiary/30 bg-tertiary-container text-on-tertiary-container"
                : "border-border bg-card text-muted-foreground hover:bg-accent"
            }`}
          >
            全部
          </button>
          {availableCategories.map((category) => (
            <button
              key={category}
              type="button"
              onClick={() => setSelectedCategory(category)}
              className={`rounded-full border px-2.5 py-0.5 text-[11px] transition-colors ${
                selectedCategory === category
                  ? "border-tertiary/30 bg-tertiary-container text-on-tertiary-container"
                  : "border-border bg-card text-muted-foreground hover:bg-accent"
              }`}
            >
              {category}
            </button>
          ))}
          <div className="mx-1 h-3 w-px bg-border" />
          {SORT_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setSortBy(option.value)}
              className={`rounded-full border px-2.5 py-0.5 text-[11px] transition-colors ${
                sortBy === option.value
                  ? "border-tertiary/30 bg-tertiary-container text-on-tertiary-container"
                  : "border-border bg-card text-muted-foreground hover:bg-accent"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {error ? (
        <div className="rounded-xl border border-dashed border-border bg-muted/40 p-4 text-sm text-muted-foreground">
          {error.message}
        </div>
      ) : null}

      {/* List */}
      <div ref={listRef} className="flex-1 overflow-y-auto min-h-0">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {loadingItems ? (
            <>
              <Skeleton className="h-48 rounded-xl" />
              <Skeleton className="h-48 rounded-xl" />
              <Skeleton className="h-48 rounded-xl" />
            </>
          ) : items.length > 0 ? (
            items.map((item) => {
              const installed = installedSet.has(item.slug);
              const installing = installingItemId === item.item_id;

              return (
                <article
                  key={`${item.source_id}-${item.item_id}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => void openDetail(item.item_id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      void openDetail(item.item_id);
                    }
                  }}
                  className="flex cursor-pointer flex-col rounded-xl border border-border bg-muted/50 p-4 transition-colors hover:border-tertiary/30 hover:bg-card"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-semibold text-foreground">
                        {item.display_name}
                      </div>
                      <div className="mt-0.5 text-[11px] text-muted-foreground">
                        {item.slug}
                        {item.version ? ` · v${item.version}` : ""}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      {item.homepage_url ? (
                        <a
                          href={item.homepage_url}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(event) => event.stopPropagation()}
                          className="rounded-full border border-border p-1.5 text-muted-foreground transition-colors hover:bg-accent"
                          title="查看来源"
                        >
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      ) : null}
                      <Button
                        type="button"
                        variant={installed ? "secondary" : "accent"}
                        size="sm"
                        className="h-8 text-xs"
                        onClick={(event) => {
                          event.stopPropagation();
                          void openDetail(item.item_id);
                        }}
                      >
                        {installing ? (
                          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                        ) : null}
                        {installed ? "查看详情" : "预览安装"}
                      </Button>
                    </div>
                  </div>

                  <p className="mt-2 line-clamp-3 h-[3.75rem] text-xs leading-5 text-muted-foreground">
                    {item.summary || item.description || "暂无简介"}
                  </p>

                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {item.categories.slice(0, 3).map((category) => (
                      <Badge key={`${item.slug}-${category}`} variant="outline" className="text-[10px]">
                        {category}
                      </Badge>
                    ))}
                  </div>

                  <div className="mt-2 flex flex-wrap gap-1.5 text-[11px] text-muted-foreground">
                    {item.owner_name ? (
                      <span className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5">
                        <User className="h-3 w-3" />
                        {item.owner_name}
                      </span>
                    ) : null}
                    {typeof item.installs === "number" ? (
                      <span className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5">
                        <CloudDownload className="h-3 w-3" />
                        {item.installs}
                      </span>
                    ) : null}
                    {typeof item.downloads === "number" ? (
                      <span className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5">
                        <Download className="h-3 w-3" />
                        {item.downloads}
                      </span>
                    ) : null}
                    {typeof item.stars === "number" ? (
                      <span className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5">
                        <Star className="h-3 w-3" />
                        {item.stars}
                      </span>
                    ) : null}
                  </div>
                </article>
              );
            })
          ) : (
            <div className="col-span-full rounded-xl border border-dashed border-border bg-muted/40 p-4 text-center text-sm text-muted-foreground">
              当前筛选条件下没有找到可展示的外部技能。
            </div>
          )}
        </div>

        {loadingMoreItems ? (
          <div className="flex items-center justify-center py-3 text-xs text-muted-foreground">
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            正在加载更多...
          </div>
        ) : hasMoreItems ? null : items.length > 0 ? (
          <div className="py-2 text-center text-[11px] text-muted-foreground">
            已加载全部
          </div>
        ) : null}
      </div>

      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="h-[90vh] max-h-[90vh] max-w-2xl overflow-hidden flex flex-col gap-0 bg-background">
          <DialogHeader className="shrink-0">
            <DialogTitle>
              {detail?.item.display_name || "外部技能详情"}
            </DialogTitle>
            <DialogDescription>
              {detail?.item.slug}
              {detail?.item.version ? ` · v${detail.item.version}` : ""}
            </DialogDescription>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto min-h-0 pr-1 space-y-4">
            {loadingDetail ? (
              <div className="space-y-3 py-2">
                <Skeleton className="h-6 w-1/2 rounded-xl" />
                <Skeleton className="h-28 rounded-xl" />
                <Skeleton className="h-48 rounded-xl" />
              </div>
            ) : detail ? (
              <>
                <div className="rounded-xl border border-border bg-muted/50 p-4">
                  <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_200px]">
                    <div>
                      {detail.item.description_zh ? (
                        <div className="text-sm leading-6 text-foreground mb-2">
                          {detail.item.description_zh}
                        </div>
                      ) : null}
                      <div className="text-sm leading-6 text-muted-foreground">
                        {detail.item.description ||
                          detail.item.summary ||
                          "暂无说明"}
                      </div>
                      {detail.item.owner_name ? (
                        <div className="mt-2 flex items-center gap-2 text-[11px] text-muted-foreground">
                          <span className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5">
                            <User className="h-3 w-3" />
                            {detail.item.owner_name}
                          </span>
                          {detail.item.source ? (
                            <span className="rounded-full border border-border px-2 py-0.5">
                              {detail.item.source}
                            </span>
                          ) : null}
                        </div>
                      ) : null}
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {detail.item.categories.map((category) => (
                          <Badge
                            key={`${detail.item.slug}-detail-${category}`}
                            variant="outline"
                            className="text-[10px]"
                          >
                            {category}
                          </Badge>
                        ))}
                      </div>
                    </div>

                    <div className="rounded-xl border border-border bg-card p-4">
                      <div className="text-xs text-muted-foreground">状态</div>
                      <div className="mt-1 text-sm font-medium text-foreground">
                        {installedSet.has(detail.item.slug)
                          ? "已安装"
                          : workspaceId
                            ? "可安装"
                            : "请先打开工作区"}
                      </div>
                      <Button
                        type="button"
                        variant="accent"
                        size="sm"
                        className="mt-3 w-full h-8 text-xs"
                        disabled={
                          !workspaceId ||
                          !selectedSourceId ||
                          !detail.can_install ||
                          installingItemId === detail.item.item_id ||
                          installedSet.has(detail.item.slug)
                        }
                        onClick={() => void handleInstall(detail.item.item_id)}
                      >
                        {installingItemId === detail.item.item_id ? (
                          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                        ) : null}
                        {installedSet.has(detail.item.slug)
                          ? "已安装"
                          : workspaceId
                            ? "安装到当前工作区"
                            : "先打开工作区"}
                      </Button>
                    </div>
                  </div>
                </div>

                {detail.readme_excerpt ? (
                  <section>
                    <div className="text-sm font-medium text-foreground">入口文档</div>
                    <div className="mt-1 text-[11px] text-muted-foreground">
                      {detail.entry_relative_path || "SKILL.md"}
                    </div>
                    <pre className="mt-2 max-h-[35vh] overflow-auto rounded-xl border border-border bg-muted/50 p-3 text-xs leading-5 text-foreground">
                      {detail.readme_excerpt}
                    </pre>
                  </section>
                ) : null}

                {installMessage ? (
                  <div
                    className={`rounded-xl border px-4 py-3 text-sm ${
                      installMessageTone === "success"
                        ? "border-success/20 bg-success-container text-on-success-container"
                        : "border-destructive/30 bg-destructive/10 text-destructive"
                    }`}
                  >
                    {installMessage}
                  </div>
                ) : null}

                {detail.install_disabled_reason ? (
                  <div className="rounded-xl border border-dashed border-border bg-muted/40 p-4 text-sm text-muted-foreground">
                    {detail.install_disabled_reason}
                  </div>
                ) : null}

              </>
            ) : (
              <div className="rounded-xl border border-dashed border-border bg-muted/40 p-4 text-sm text-muted-foreground">
                当前无法加载这个外部技能的详情。
              </div>
            )}
          </div>
          <div className="shrink-0 flex items-center justify-end gap-2 pt-4 border-t border-border">
            {detail?.item.homepage_url ? (
              <Button variant="outline" size="sm" className="h-8 text-xs" asChild>
                <a
                  href={detail.item.homepage_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  <ExternalLink className="mr-1.5 h-3.5 w-3.5" />
                  查看来源
                </a>
              </Button>
            ) : null}
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8 text-xs"
              onClick={() => setDetailOpen(false)}
            >
              关闭
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
