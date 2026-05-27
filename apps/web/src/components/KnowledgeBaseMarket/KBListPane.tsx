import { Clock, Database, Loader2, MoreVertical, Plus, Search, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { KnowledgeBase } from "@/types/knowledge";
import { formatDate, getStatusBadge } from "./utils";

interface KBListPaneProps {
  listTitle: string;
  listDescription: string;
  knowledgeBases: KnowledgeBase[];
  isLoadingList: boolean;
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
  filteredKBs: KnowledgeBase[];
  scopedKnowledgeBases: KnowledgeBase[];
  selectedKB: KnowledgeBase | null;
  onSelectKB: (kb: KnowledgeBase) => void;
  onDeleteKB: (id: string) => void;
  allowCreate: boolean;
  onCreate: () => void;
}

export function KBListPane({
  listTitle,
  listDescription,
  knowledgeBases,
  isLoadingList,
  searchQuery,
  onSearchQueryChange,
  filteredKBs,
  scopedKnowledgeBases,
  selectedKB,
  onSelectKB,
  onDeleteKB,
  allowCreate,
  onCreate,
}: KBListPaneProps) {
  return (
    <>
      <div className="border-b border-border/80 px-5 py-5">
        <div className="flex items-center gap-2 text-lg font-semibold text-foreground">
          <Database className="h-5 w-5 text-primary" />
          {listTitle}
        </div>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{listDescription}</p>
      </div>

      <div className="space-y-3 border-b border-border/80 bg-muted/70 px-5 py-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="搜索知识库..."
            className="pl-9"
            value={searchQuery}
            onChange={(e) => onSearchQueryChange(e.target.value)}
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {searchQuery ? (
            <Button variant="ghost" size="sm" onClick={() => onSearchQueryChange("")}>
              清除筛选
            </Button>
          ) : null}
          <div className="flex-1 text-xs text-muted-foreground">
            {filteredKBs.length} / {scopedKnowledgeBases.length} 个知识库
          </div>
          {allowCreate ? (
            <Button size="sm" onClick={onCreate} className="gap-2">
              <Plus className="h-4 w-4" />
              新建
            </Button>
          ) : null}
        </div>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-3 p-4">
          {isLoadingList && knowledgeBases.length === 0 ? (
            <div className="flex h-48 items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
            </div>
          ) : filteredKBs.length > 0 ? (
            filteredKBs.map((kb) => {
              const isSelected = selectedKB?.id === kb.id;
              return (
                <div
                  key={kb.id}
                  className={cn(
                    "group cursor-pointer rounded-2xl border p-4 transition-all",
                    isSelected
                      ? "border-info/20 bg-info-container/80 shadow-sm"
                      : "border-border bg-white hover:border-border hover:bg-muted",
                  )}
                  onClick={() => onSelectKB(kb)}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start gap-3">
                        <div
                          className={cn(
                            "flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border",
                            isSelected
                              ? "border-info/20 bg-white text-info"
                              : "border-border bg-muted text-muted-foreground",
                          )}
                        >
                          <Database className="h-5 w-5" />
                        </div>
                        <div className="min-w-0">
                          <div className="truncate text-sm font-semibold text-foreground">
                            {kb.name}
                          </div>
                          <div className="mt-1 text-xs text-muted-foreground">
                            {kb.document_count || 0} 个文档
                          </div>
                          <div
                            className={`mt-2 inline-flex rounded-full border px-2 py-0.5 text-[11px] ${getStatusBadge(kb).className}`}
                          >
                            {getStatusBadge(kb).label}
                          </div>
                        </div>
                      </div>
                      <p className="mt-3 line-clamp-2 text-sm leading-6 text-muted-foreground">
                        {kb.description || "暂无描述"}
                      </p>
                      <div className="mt-3 flex items-center gap-1 text-xs text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        {formatDate(kb.updated_at || kb.created_at)}
                      </div>
                    </div>

                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          className={cn(
                            "h-8 w-8",
                            isSelected ? "opacity-100" : "opacity-0 group-hover:opacity-100",
                          )}
                          onClick={(event) => event.stopPropagation()}
                        >
                          <MoreVertical className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem
                          className="text-destructive"
                          onClick={(event) => {
                            event.stopPropagation();
                            onDeleteKB(kb.id);
                          }}
                        >
                          <Trash2 className="mr-2 h-4 w-4" />
                          删除
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
              );
            })
          ) : (
            <div className="py-16 text-center">
              <Database className="mx-auto mb-4 h-12 w-12 text-muted-foreground/30" />
              <p className="text-sm text-muted-foreground">
                {searchQuery ? "没有找到匹配的知识库" : "暂无知识库"}
              </p>
              {!searchQuery && allowCreate ? (
                <Button variant="outline" className="mt-4" onClick={onCreate}>
                  <Plus className="mr-2 h-4 w-4" />
                  创建第一个知识库
                </Button>
              ) : null}
            </div>
          )}
        </div>
      </ScrollArea>
    </>
  );
}
