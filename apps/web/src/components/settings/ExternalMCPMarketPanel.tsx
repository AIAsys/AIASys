import { useEffect, useState } from "react";
import {
  ExternalLink,
  Loader2,
  PackagePlus,
  Search,
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
import { useExternalMCPMarket } from "@/hooks/useExternalMCPMarket";

interface ExternalMCPMarketPanelProps {
  onImported?: () => void;
}

export function ExternalMCPMarketPanel({
  onImported,
}: ExternalMCPMarketPanelProps) {
  const {
    sources,
    selectedSourceId,
    setSelectedSourceId,
    items,
    loadedCount,
    hasMore,
    loadingSources,
    loadingItems,
    loadingMore,
    loadingDetail,
    importingItemId,
    error,
    detail,
    loadDetail,
    refreshItems,
    loadMore,
    searchQuery,
    setSearchQuery,
    importItem,
  } = useExternalMCPMarket();
  const [detailOpen, setDetailOpen] = useState(false);
  const [envValues, setEnvValues] = useState<Record<string, string>>({});
  const [installMessage, setInstallMessage] = useState<string | null>(null);
  const [installMessageTone, setInstallMessageTone] = useState<
    "success" | "error"
  >("success");
  const [dialogItemId, setDialogItemId] = useState<string | null>(null);
  const [importedItemIds, setImportedItemIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!detail) return;
    setEnvValues(
      Object.fromEntries(
        detail.env_fields.map((field) => [
          field.name,
          field.default_value || "",
        ]),
      ),
    );
  }, [detail]);

  const openDetail = async (itemId: string) => {
    if (!selectedSourceId) return;
    setInstallMessage(null);
    setInstallMessageTone("success");
    setDialogItemId(itemId);
    setDetailOpen(true);
    await loadDetail(selectedSourceId, itemId);
  };

  const handleImport = async () => {
    if (!selectedSourceId || !detail) return;
    if (importingItemId || importedItemIds.has(detail.item.item_id)) return;
    setInstallMessage(null);
    setInstallMessageTone("success");
    const missingRequiredFields = detail.env_fields
      .filter(
        (field) => field.required && !(envValues[field.name] || "").trim(),
      )
      .map((field) => field.name);
    if (missingRequiredFields.length > 0) {
      setInstallMessageTone("error");
      setInstallMessage(`请填写必填变量：${missingRequiredFields.join("，")}`);
      return;
    }
    const success = await importItem({
      sourceId: selectedSourceId,
      itemId: detail.item.item_id,
      envOverrides: envValues,
      enabled: true,
    });
    if (!success) {
      setInstallMessageTone("error");
      setInstallMessage("添加失败，请检查变量填写和导入模板后重试。");
      return;
    }
    setImportedItemIds((previous) =>
      new Set(previous).add(detail.item.item_id),
    );
    setInstallMessage("已添加到我的默认，工作区会按继承规则生效。");
    setInstallMessageTone("success");
    onImported?.();
    await refreshItems();
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
            {loadedCount} 条
          </span>
        </div>

        <div className="flex items-center gap-2">
          <div className="relative flex-1 max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="搜索连接器名称或作者"
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
      </div>

      {error ? (
        <div className="rounded-xl border border-dashed border-border bg-muted/40 p-4 text-sm text-muted-foreground">
          {error.message}
        </div>
      ) : null}

      {/* List */}
      <div className="flex-1 overflow-y-auto min-h-0">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {loadingItems && loadedCount === 0 ? (
            <>
              <Skeleton className="h-44 rounded-xl" />
              <Skeleton className="h-44 rounded-xl" />
              <Skeleton className="h-44 rounded-xl" />
            </>
          ) : items.length > 0 ? (
            items.map((item) => (
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
                className="group flex cursor-pointer flex-col rounded-xl border border-border bg-muted/50 p-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-tertiary/30 hover:bg-card"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="line-clamp-2 min-h-[2rem] text-sm font-semibold leading-5 text-foreground">
                      {item.display_name}
                    </div>
                    <div className="mt-0.5 text-[11px] text-muted-foreground">
                      {item.publisher || "未标注作者"}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    {item.source_id === "modelscope" ? (
                      <a
                        href={`https://www.modelscope.cn/mcp/servers/${item.item_id}`}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(event) => event.stopPropagation()}
                        className="rounded-full border border-border p-1.5 text-muted-foreground transition-colors hover:bg-accent"
                        title="打开来源页面"
                      >
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    ) : null}
                    {item.is_hosted ? (
                      <Badge variant="secondary" className="text-[10px] shrink-0">Hosted</Badge>
                    ) : null}
                    <Button
                      type="button"
                      variant="accent"
                      size="sm"
                      className="h-8 text-xs"
                      onClick={(event) => {
                        event.stopPropagation();
                        void openDetail(item.item_id);
                      }}
                      disabled={loadingDetail && dialogItemId === item.item_id}
                    >
                      {loadingDetail && dialogItemId === item.item_id ? (
                        <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <PackagePlus className="mr-1.5 h-3.5 w-3.5" />
                      )}
                      预览安装
                    </Button>
                  </div>
                </div>

                <p className="mt-2 line-clamp-3 h-[3.75rem] text-xs leading-5 text-muted-foreground">
                  {item.description || "暂无简介"}
                </p>

                <div className="mt-2 flex flex-wrap gap-1.5">
                  {item.categories.slice(0, 2).map((category) => (
                    <Badge
                      key={`${item.item_id}-${category}`}
                      variant="outline"
                      className="text-[10px]"
                    >
                      {category}
                    </Badge>
                  ))}
                </div>
              </article>
            ))
          ) : (
            <div className="col-span-full rounded-xl border border-dashed border-border bg-muted/40 p-4 text-center text-sm text-muted-foreground">
              当前没有可展示的外部连接器。
            </div>
          )}
        </div>

        {loadedCount > 0 ? (
          <div className="mt-3 flex items-center justify-between gap-3">
            <div className="text-[11px] text-muted-foreground">
              已加载 {loadedCount} 条
            </div>
            {hasMore ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-8 text-xs"
                onClick={() => void loadMore()}
                disabled={loadingItems || loadingMore}
              >
                {loadingMore ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : null}
                加载更多
              </Button>
            ) : (
              <div className="text-[11px] text-muted-foreground">已加载全部</div>
            )}
          </div>
        ) : null}
      </div>

      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="h-[90vh] max-h-[90vh] max-w-2xl overflow-hidden flex flex-col gap-0 bg-background">
          <DialogHeader className="shrink-0">
            <DialogTitle>
              {detail?.item.display_name || "外部连接器详情"}
            </DialogTitle>
            <DialogDescription>
              查看导入模板并决定是否添加到我的默认
            </DialogDescription>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto min-h-0 pr-1 space-y-4">
            {loadingDetail ? (
              <div className="space-y-3 py-4">
                <Skeleton className="h-24 rounded-xl" />
                <Skeleton className="h-48 rounded-xl" />
              </div>
            ) : detail ? (
              <div className="min-w-0 space-y-4">
                <div className="rounded-xl border border-border bg-muted/50 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className="text-[10px]">
                      {detail.source.display_name}
                    </Badge>
                    {detail.item.publisher ? (
                      <Badge variant="outline" className="text-[10px]">{detail.item.publisher}</Badge>
                    ) : null}
                    {detail.item.is_hosted ? (
                      <Badge variant="secondary" className="text-[10px]">支持托管</Badge>
                    ) : null}
                  </div>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">
                    {detail.item.description || "暂无简介"}
                  </p>
                </div>

                <div className="rounded-xl border border-border bg-card p-4 space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-xs text-muted-foreground">操作</div>
                      <div className="mt-0.5 text-sm font-medium text-foreground">
                        {detail.can_import ? "可添加到我的默认" : "当前不可添加"}
                      </div>
                    </div>
                    <Button
                      type="button"
                      variant="accent"
                      size="sm"
                      className="h-8 text-xs"
                      onClick={() => void handleImport()}
                      disabled={
                        !detail.can_import ||
                        importingItemId === detail.item.item_id ||
                        importedItemIds.has(detail.item.item_id)
                      }
                    >
                      {importingItemId === detail.item.item_id ? (
                        <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <PackagePlus className="mr-1.5 h-3.5 w-3.5" />
                      )}
                      {importedItemIds.has(detail.item.item_id)
                        ? "已导入"
                        : importingItemId === detail.item.item_id
                          ? "导入中..."
                          : "添加到我的默认"}
                    </Button>
                  </div>

                  {installMessage ? (
                    <div
                      className={`rounded-lg border px-3 py-2 text-xs ${
                        installMessageTone === "success"
                          ? "border-success/20 bg-success-container text-on-success-container"
                          : "border-warning/20 bg-warning-container text-on-warning-container"
                      }`}
                    >
                      {installMessage}
                    </div>
                  ) : null}
                </div>

                {detail.template_previews.length > 0 ? (
                  <section className="space-y-2">
                    <div className="text-sm font-medium text-foreground">导入模板</div>
                    <div className="space-y-2">
                      {detail.template_previews.map((template) => (
                        <div
                          key={`${detail.item.item_id}-${template.server_key}`}
                          className="min-w-0 rounded-xl border border-border bg-card p-3"
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <div className="text-sm font-medium text-foreground">
                              {template.import_name}
                            </div>
                            <Badge variant="outline" className="text-[10px]">
                              {template.transport_type}
                            </Badge>
                          </div>
                          <div className="mt-1 break-all text-[11px] text-muted-foreground">
                            {template.target || "模板未提供连接目标"}
                          </div>
                          <div className="mt-2 flex min-w-0 flex-wrap gap-2 text-[11px] text-muted-foreground">
                            {template.args.length > 0 ? (
                              <span className="break-all">
                                args: {template.args.join(" ")}
                              </span>
                            ) : null}
                            {template.env_keys.length > 0 ? (
                              <span className="break-all">
                                env: {template.env_keys.join(", ")}
                              </span>
                            ) : null}
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>
                ) : (
                  <div className="rounded-xl border border-dashed border-border bg-muted/40 p-4 text-sm text-muted-foreground">
                    {detail.import_disabled_reason || "当前没有可导入模板。"}
                  </div>
                )}

                {detail.env_fields.length > 0 ? (
                  <section className="space-y-2">
                    <div className="text-sm font-medium text-foreground">环境变量</div>
                    <div className="grid gap-2 md:grid-cols-2">
                      {detail.env_fields.map((field) => (
                        <label
                          key={`${detail.item.item_id}-${field.name}`}
                          className="rounded-xl border border-border bg-card p-3"
                        >
                          <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                            {field.name}
                            {field.required ? (
                              <Badge variant="secondary" className="text-[10px]">必填</Badge>
                            ) : null}
                          </div>
                          <div className="mt-0.5 text-[11px] text-muted-foreground">
                            {field.description || "未提供说明"}
                          </div>
                          <Input
                            className="mt-2 h-9"
                            value={envValues[field.name] || ""}
                            onChange={(event) =>
                              setEnvValues((previous) => ({
                                ...previous,
                                [field.name]: event.target.value,
                              }))
                            }
                            placeholder={`填写 ${field.name}`}
                          />
                        </label>
                      ))}
                    </div>
                  </section>
                ) : null}

                {detail.readme_excerpt ? (
                  <section className="space-y-2">
                    <div className="text-sm font-medium text-foreground">说明摘录</div>
                    <div className="max-h-48 overflow-auto rounded-xl border border-border bg-muted/50 p-3 text-xs leading-5 text-muted-foreground">
                      <pre className="max-w-full whitespace-pre-wrap break-words font-mono">
                        {detail.readme_excerpt}
                      </pre>
                    </div>
                  </section>
                ) : null}

              </div>
            ) : (
              <div className="rounded-xl border border-dashed border-border bg-muted/40 p-4 text-sm text-muted-foreground">
                当前无法读取该外部连接器详情。
              </div>
            )}
          </div>

          {detail && !loadingDetail && (
            <div className="shrink-0 flex items-center justify-end gap-2 pt-4 border-t border-border">
              {detail.source.source_id === "modelscope" ? (
                <Button type="button" variant="outline" size="sm" className="h-8 text-xs" asChild>
                  <a
                    href={`https://www.modelscope.cn/mcp/servers/${detail.item.item_id}`}
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
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
