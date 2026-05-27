/**
 * SkillMarket - Skill 市场组件（技能仓库 + 我的默认 + 工作区启用模型）
 */
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { MarketSkill, SkillEntryResponse, SkillReadmeResponse } from "@/types/api";
import {
  FileArchive,
  KeyRound,
  Loader2,
  Package,
  Plus,
  Search,
  Sparkles,
  Upload,
} from "lucide-react";
import { MarkdownRenderer } from "@/components/chat/MarkdownRenderer";
import { useMemo, useRef, useState } from "react";
import { SkillCard } from "./SkillCard";

type SkillMarketTab = "all";

const TAB_TRIGGER_CLASS =
  "data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-tertiary data-[state=active]:text-tertiary data-[state=active]:shadow-none rounded-none h-full";

interface SkillMarketProps {
  workspaceId?: string | null;
  marketSkills: MarketSkill[];
  isLoading: boolean;
  onInstall: (skillName: string, version?: string) => Promise<boolean>;
  onUninstall: (skillName: string) => Promise<boolean>;
  onUpdate?: (skillName: string) => Promise<boolean>;
  onToggleGlobal?: (skillName: string, enabled: boolean) => Promise<boolean>;
  onImportArchive?: (file: File) => Promise<boolean>;
  onViewEntry?: (skillName: string) => Promise<SkillEntryResponse | null>;
  onViewReadme?: (skillName: string) => Promise<SkillReadmeResponse | null>;
  onRemoveStore?: (skillName: string) => Promise<boolean>;
}

export function SkillMarket({
  workspaceId,
  marketSkills,
  isLoading,
  onInstall,
  onUninstall,
  onUpdate,
  onToggleGlobal,
  onImportArchive,
  onViewEntry,
  onViewReadme,
  onRemoveStore,
}: SkillMarketProps) {
  const [processingSkill, setProcessingSkill] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState<SkillMarketTab>("all");
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewEntry, setPreviewEntry] = useState<SkillEntryResponse | null>(null);
  const [createGuideOpen, setCreateGuideOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const counts = useMemo(() => {
    return {
      all: marketSkills.length,
    };
  }, [marketSkills]);

  const filteredSkills = useMemo(() => {
    let result = marketSkills;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (s) =>
          s.name.toLowerCase().includes(q) ||
          s.description.toLowerCase().includes(q),
      );
    }
    return result;
  }, [marketSkills, searchQuery]);

  const handleInstall = async (skillName: string, version?: string) => {
    setProcessingSkill(skillName);
    const success = await onInstall(skillName, version);
    setProcessingSkill(null);
    return success;
  };

  const handleUninstall = async (skillName: string) => {
    setProcessingSkill(skillName);
    await onUninstall(skillName);
    setProcessingSkill(null);
  };

  const handleUpdate = async (skillName: string) => {
    if (!onUpdate) return;
    setProcessingSkill(skillName);
    await onUpdate(skillName);
    setProcessingSkill(null);
  };

  const handleToggleGlobal = async (skillName: string, enabled: boolean) => {
    if (!onToggleGlobal) return false;
    setProcessingSkill(skillName);
    const success = await onToggleGlobal(skillName, enabled);
    setProcessingSkill(null);
    return success;
  };

  const handleRemoveStore = async (skillName: string) => {
    if (!onRemoveStore) return;
    setProcessingSkill(skillName);
    await onRemoveStore(skillName);
    setProcessingSkill(null);
  };

  const handleImportClick = () => {
    fileInputRef.current?.click();
  };

  const handleFocusSearch = () => {
    searchInputRef.current?.focus();
    searchInputRef.current?.select();
  };

  const handleImportFileChange = async (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !onImportArchive) return;
    setProcessingSkill(`import:${file.name}`);
    await onImportArchive(file);
    setProcessingSkill(null);
  };

  const handleViewEntry = async (skillName: string) => {
    if (!onViewEntry) return;
    setPreviewOpen(true);
    setPreviewLoading(true);
    setPreviewError(null);
    setPreviewEntry(null);
    // 先尝试读取 README.md
    let readme: SkillReadmeResponse | null = null;
    if (onViewReadme) {
      readme = await onViewReadme(skillName);
    }
    if (readme?.found) {
      setPreviewEntry({
        name: skillName,
        display_name: skillName,
        description: "",
        entry_relative_path: "README.md",
        content: readme.content,
        env_fields: [],
      });
      setPreviewLoading(false);
      return;
    }
    // fallback 到 SKILL.md
    const entry = await onViewEntry(skillName);
    if (entry) {
      setPreviewEntry(entry);
    } else {
      setPreviewError("无法加载该技能的预览内容。");
    }
    setPreviewLoading(false);
  };

  const marketContent = (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center gap-3 border-b border-border px-5 py-3">
        <div className="relative max-w-sm min-w-[180px] flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            ref={searchInputRef}
            placeholder="搜索技能..."
            className="pl-9 h-9"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        {searchQuery && (
          <Button variant="ghost" size="sm" onClick={() => setSearchQuery("")}>
            清除
          </Button>
        )}
        <div className="flex-1" />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" className="h-9 gap-1 text-xs">
              <Plus className="h-3.5 w-3.5" />
              添加
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuItem onClick={handleFocusSearch}>
              <Search className="mr-2 h-4 w-4" />
              查找技能
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={handleImportClick}
              disabled={!onImportArchive}
            >
              <Upload className="mr-2 h-4 w-4" />
              上传技能包
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => setCreateGuideOpen(true)}>
              <Sparkles className="mr-2 h-4 w-4" />
              创建技能
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        {workspaceId && onImportArchive ? (
          <>
            <input
              ref={fileInputRef}
              type="file"
              accept=".zip"
              className="hidden"
              onChange={handleImportFileChange}
            />
            <Button
              variant="outline"
              size="sm"
              onClick={handleImportClick}
              className="h-9 gap-1 text-xs"
              disabled={isLoading}
            >
              <FileArchive className="h-3.5 w-3.5" />
              导入
            </Button>
          </>
        ) : null}
      </div>

      <Tabs
        value={activeTab}
        onValueChange={(v) => setActiveTab(v as SkillMarketTab)}
        className="flex-1 flex flex-col overflow-hidden"
      >
        <div className="overflow-x-auto border-b border-border bg-card px-5">
          <TabsList className="w-full justify-start gap-6 bg-transparent h-11 p-0 min-w-max">
            <TabsTrigger value="all" className={TAB_TRIGGER_CLASS}>
              技能仓库
              <Badge variant="secondary" className="ml-2">
                {counts.all}
              </Badge>
            </TabsTrigger>
          </TabsList>
        </div>

        <ScrollArea className="flex-1">
          <div className="p-5">
            {isLoading && marketSkills.length === 0 && (
              <div className="flex items-center justify-center h-48">
                <Loader2 className="w-8 h-8 animate-spin text-tertiary" />
                <span className="ml-3 text-muted-foreground">加载中...</span>
              </div>
            )}

            {filteredSkills.length > 0 && (
              <div
                className="grid auto-rows-fr gap-3"
                style={{ gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}
              >
                {filteredSkills.map((skill) => (
                  <SkillCard
                    key={skill.name}
                    skill={skill}
                    workspaceId={workspaceId}
                    processingSkill={processingSkill}
                    onInstall={handleInstall}
                    onUninstall={handleUninstall}
                    onUpdate={handleUpdate}
                    onToggleGlobal={handleToggleGlobal}
                    onViewEntry={handleViewEntry}
                    onRemoveStore={
                      activeTab === "all" && !skill.installed ? handleRemoveStore : undefined
                    }
                  />
                ))}
              </div>
            )}

            {!isLoading && filteredSkills.length === 0 && (
              <div className="py-16 text-center">
                <Package className="mx-auto mb-4 h-10 w-10 text-muted-foreground/30" />
                <p className="text-sm text-muted-foreground">
                  {searchQuery
                    ? "没有找到匹配的技能"
                    : "暂无可用技能"}
                </p>
              </div>
            )}
          </div>
        </ScrollArea>
      </Tabs>
    </div>
  );

  return (
    <>
      <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
        {marketContent}
      </div>

      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="flex flex-col h-[85vh] overflow-hidden p-0 max-w-3xl bg-background">
          <DialogHeader className="shrink-0 px-6 pt-6">
            <DialogTitle>
              {previewEntry?.display_name || previewEntry?.name || "技能预览"}
            </DialogTitle>
            <DialogDescription>
              {previewEntry ? previewEntry.entry_relative_path : "已启用技能的预览内容"}
            </DialogDescription>
          </DialogHeader>
          <div className="flex-1 min-h-0 overflow-y-auto px-6 py-4">
            {previewLoading ? (
              <div className="flex items-center justify-center py-10 text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                正在加载...
              </div>
            ) : previewError ? (
              <div className="rounded-xl border border-dashed border-border bg-muted/40 p-4 text-sm text-muted-foreground">
                {previewError}
              </div>
            ) : (
              <div className="space-y-4">
                {previewEntry?.env_fields && previewEntry.env_fields.length > 0 ? (
                  <section className="space-y-2">
                    <div className="text-sm font-medium text-foreground">环境变量配置</div>
                    <div className="grid gap-2 md:grid-cols-2">
                      {previewEntry.env_fields.map((field) => (
                        <div
                          key={field.name}
                          className="rounded-xl border border-border bg-card p-3"
                        >
                          <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                            <KeyRound className="h-3.5 w-3.5 text-warning" />
                            {field.name}
                            {field.required ? (
                              <Badge variant="secondary" className="text-[10px]">必填</Badge>
                            ) : null}
                          </div>
                          {field.description ? (
                            <div className="mt-0.5 text-[11px] text-muted-foreground">
                              {field.description}
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  </section>
                ) : null}
                {previewEntry?.entry_relative_path === "README.md" ? (
                  <div className="prose prose-sm max-w-none dark:prose-invert overflow-auto rounded-xl border border-border bg-muted/60 p-4 text-xs leading-6 text-foreground">
                    <MarkdownRenderer content={previewEntry?.content || ""} />
                  </div>
                ) : (
                  <pre className="overflow-auto rounded-xl border border-border bg-muted/60 p-4 text-xs leading-6 text-foreground">
                    {previewEntry?.content || "暂无内容"}
                  </pre>
                )}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={createGuideOpen} onOpenChange={setCreateGuideOpen}>
        <DialogContent className="flex flex-col h-auto max-h-[85vh] overflow-hidden p-0 max-w-md bg-background">
          <DialogHeader className="shrink-0 px-6 pt-6">
            <DialogTitle>创建技能</DialogTitle>
            <DialogDescription>
              当前版本不支持在线编写，请先本地整理后导入。
            </DialogDescription>
          </DialogHeader>
          <div className="flex-1 min-h-0 overflow-y-auto px-6 py-4 text-sm text-muted-foreground">
            <div className="rounded-xl border border-border bg-muted/60 p-3 space-y-2">
              <p>1. 在本地整理好技能包目录或 zip 包</p>
              <p>2. 通过"上传技能包"导入</p>
              <p>3. 导入后在当前工作区启用</p>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
