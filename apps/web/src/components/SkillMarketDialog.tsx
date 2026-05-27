import { useState } from "react";
import { ServerCog, Store } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { SettingsSkillMarketPanel } from "@/components/settings/SettingsSkillMarketPanel";
import { cn } from "@/lib/utils";

type SkillMarketTabId = "builtin" | "external";

interface SkillMarketDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspaceId?: string | null;
}

const TABS: Array<{
  id: SkillMarketTabId;
  label: string;
  description: string;
  icon: typeof ServerCog;
}> = [
  {
    id: "builtin",
    label: "技能仓库",
    description: "系统内置和已导入的技能",
    icon: ServerCog,
  },
  {
    id: "external",
    label: "外部技能市场",
    description: "从外部来源安装技能",
    icon: Store,
  },
];

export function SkillMarketDialog({
  open,
  onOpenChange,
  workspaceId,
}: SkillMarketDialogProps) {
  const [activeTab, setActiveTab] = useState<SkillMarketTabId>("builtin");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-6xl h-[86vh] overflow-hidden p-0 gap-0 flex flex-col bg-background">
        <DialogHeader className="px-6 pt-5 pb-0">
          <DialogTitle>技能管理</DialogTitle>
          <DialogDescription>
            管理已安装技能、导入自定义技能包或浏览外部市场
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 px-6 py-4">
          <div className="grid h-full min-h-0 grid-cols-[236px_minmax(0,1fr)] overflow-hidden rounded-2xl border border-border bg-card">
            {/* 左侧导航栏 */}
            <aside className="border-r border-border bg-muted/20 p-3">
              <div className="space-y-1">
                {TABS.map((tab) => {
                  const active = tab.id === activeTab;
                  const Icon = tab.icon;
                  return (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => setActiveTab(tab.id)}
                      className={cn(
                        "flex w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left transition-colors",
                        active
                          ? "bg-background text-foreground shadow-sm"
                          : "text-muted-foreground hover:bg-background/70 hover:text-foreground",
                      )}
                    >
                      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
                      <span className="min-w-0">
                        <span className="block text-sm font-medium">
                          {tab.label}
                        </span>
                        <span className="mt-0.5 block text-xs leading-4 text-muted-foreground">
                          {tab.description}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </aside>

            {/* 右侧内容区 */}
            <div className="min-h-0 overflow-hidden p-5">
              <SettingsSkillMarketPanel
                workspaceId={workspaceId}
                activeTab={activeTab}
                onActiveTabChange={setActiveTab}
                hideTabBar
              />
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
