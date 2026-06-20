import { useState } from "react";
import {
  CloudDownload,
  FileText,
  Loader2,
  Puzzle,
  Search,
  Store,
  CheckCircle2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

import { useTemplateMarket } from "@/hooks/useTemplateMarket";
import { TEMPLATE_ICON_MAP } from "@/lib/templateIcons";
import { TemplatePreviewFileTree } from "@/components/NewWorkspaceDialog/TemplatePreviewFileTree";


export function TemplateMarketPanel() {
  const {
    items,
    availableCategories,
    searchQuery,
    setSearchQuery,
    selectedCategory,
    setSelectedCategory,
    loadingItems,
    installingItemId,
    detail,
    loadDetail,
    installItem,
    error,
  } = useTemplateMarket();

  const [detailOpen, setDetailOpen] = useState(false);

  const handleOpenDetail = async (itemId: string) => {
    setDetailOpen(true);
    await loadDetail(itemId);
  };

  const handleInstall = async (itemId: string) => {
    await installItem(itemId);
  };

  return (
    <div className="h-full flex flex-col">
      {/* 头部 */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-border">
        <div>
          <h3 className="text-sm font-semibold text-foreground">模板市场</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            浏览和安装系统内置工作区模板
          </p>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {error && (
          <div className="mb-4 rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-xs text-destructive">
            {error}
          </div>
        )}

        {/* 搜索 + 分类 */}
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="搜索模板..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-8 pl-8 text-xs"
            />
          </div>
          <div className="flex flex-wrap gap-1.5">
            <Badge
              variant={selectedCategory === "" ? "default" : "secondary"}
              className="cursor-pointer text-[10px]"
              onClick={() => setSelectedCategory("")}
            >
              全部
            </Badge>
            {availableCategories.map((cat) => (
              <Badge
                key={cat}
                variant={selectedCategory === cat ? "default" : "secondary"}
                className="cursor-pointer text-[10px]"
                onClick={() => setSelectedCategory(cat)}
              >
                {cat}
              </Badge>
            ))}
          </div>
        </div>

        {/* 模板卡片网格 */}
        {loadingItems ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {/* key={i} is safe — static skeleton array, never reorders */}
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-32 rounded-lg" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="flex h-40 flex-col items-center justify-center text-sm text-muted-foreground">
            <Store className="mb-2 h-8 w-8 opacity-40" />
            <p>暂无匹配的模板</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((item) => (
              <div
                key={item.item_id}
                className="group flex flex-col rounded-lg border border-border bg-background p-4 transition-shadow hover:shadow-sm"
              >
                <div className="flex items-start gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
                    {TEMPLATE_ICON_MAP[item.icon] ?? (
                      <Store className="h-5 w-5" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium text-foreground">
                        {item.name}
                      </span>
                      {item.official && (
                        <span className="shrink-0 rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary">
                          官方
                        </span>
                      )}
                      <span className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                        {item.category}
                      </span>
                    </div>
                    <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                      {item.description || "无描述"}
                    </p>
                  </div>
                </div>

                <div className="mt-3 flex items-center gap-3 text-[11px] text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <FileText className="h-3 w-3" />
                    {item.file_count} 个文件
                  </span>
                  {item.capability_count > 0 && (
                    <span className="flex items-center gap-1">
                      <Puzzle className="h-3 w-3" />
                      {item.capability_count} 项能力
                    </span>
                  )}
                </div>

                <div className="mt-3 flex items-center justify-end gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => handleOpenDetail(item.item_id)}
                  >
                    详情
                  </Button>
                  {item.is_installed ? (
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 text-xs"
                      disabled
                    >
                      <CheckCircle2 className="mr-1 h-3 w-3" />
                      已安装
                    </Button>
                  ) : (
                    <Button
                      variant="default"
                      size="sm"
                      className="h-7 text-xs"
                      onClick={() => handleInstall(item.item_id)}
                      disabled={installingItemId === item.item_id}
                    >
                      {installingItemId === item.item_id ? (
                        <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                      ) : (
                        <CloudDownload className="mr-1 h-3 w-3" />
                      )}
                      安装
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 详情 Dialog */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              {detail ? (
                <>
                  {TEMPLATE_ICON_MAP[detail.item.icon] ?? <Store className="h-5 w-5" />}
                  {detail.item.name}
                </>
              ) : (
                "模板详情"
              )}
            </DialogTitle>
            <DialogDescription className="text-xs">
              {detail?.item.description || "加载中..."}
            </DialogDescription>
          </DialogHeader>

          {detail && (
            <div className="space-y-4">
              {/* 基本信息 */}
              <div className="flex flex-wrap gap-2">
                {detail.item.official && (
                  <Badge variant="default" className="text-[10px]">
                    官方
                  </Badge>
                )}
                <Badge variant="secondary" className="text-[10px]">
                  {detail.item.category}
                </Badge>
                <Badge variant="outline" className="text-[10px]">
                  {detail.item.env_kind === "none"
                    ? "无环境"
                    : detail.item.env_kind === "uv"
                      ? "Python 环境"
                      : detail.item.env_kind}
                </Badge>
                <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                  <FileText className="h-3 w-3" />
                  {detail.item.file_count} 个文件
                </span>
                {detail.item.capability_count > 0 && (
                  <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                    <Puzzle className="h-3 w-3" />
                    {detail.item.capability_count} 项能力
                  </span>
                )}
              </div>

              {/* 文件预览 */}
              <div>
                <h4 className="mb-1.5 text-xs font-medium text-foreground">
                  预置文件
                </h4>
                {detail.files.length > 0 ? (
                  <div className="max-h-48 overflow-y-auto rounded-md border border-border">
                    <TemplatePreviewFileTree
                      files={detail.files.map((f) => ({
                        relative_path: f.relative_path,
                        content: f.content ?? "",
                        source_path: f.source_path,
                      }))}
                    />
                  </div>
                ) : (
                  <div className="py-4 text-center text-sm text-muted-foreground">
                    该模板不包含文件
                  </div>
                )}
              </div>

              {/* 推荐能力 */}
              {detail.recommended_capabilities.length > 0 && (
                <div>
                  <h4 className="mb-1.5 text-xs font-medium text-foreground">
                    推荐能力
                  </h4>
                  <div className="space-y-1">
                    {detail.recommended_capabilities.map((cap) => (
                      <div
                        key={cap.capability_id}
                        className="flex items-center gap-2 rounded-sm px-2 py-1 text-[11px]"
                      >
                        <Puzzle className="h-3 w-3 text-muted-foreground" />
                        <span className="text-foreground">{cap.capability_id}</span>
                        {cap.required && (
                          <Badge variant="outline" className="text-[9px]">
                            必需
                          </Badge>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 环境变量 */}
              {Object.keys(detail.env_vars).length > 0 && (
                <div>
                  <h4 className="mb-1.5 text-xs font-medium text-foreground">
                    环境变量
                  </h4>
                  <div className="space-y-1">
                    {Object.entries(detail.env_vars).map(([key, value]) => (
                      <div
                        key={key}
                        className="flex items-center gap-2 rounded-sm bg-muted/40 px-2 py-1 text-[11px]"
                      >
                        <span className="font-mono text-muted-foreground">{key}</span>
                        <span className="text-foreground">=</span>
                        <span className="font-mono text-muted-foreground">{value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 安装按钮 */}
              <div className="flex justify-end">
                {detail.item.is_installed ? (
                  <Button variant="outline" size="sm" disabled>
                    <CheckCircle2 className="mr-1 h-3 w-3" />
                    已安装
                  </Button>
                ) : (
                  <Button
                    variant="default"
                    size="sm"
                    onClick={() => handleInstall(detail.item.item_id)}
                    disabled={installingItemId === detail.item.item_id}
                  >
                    {installingItemId === detail.item.item_id ? (
                      <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                    ) : (
                      <CloudDownload className="mr-1 h-3 w-3" />
                    )}
                    安装到模板库
                  </Button>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
