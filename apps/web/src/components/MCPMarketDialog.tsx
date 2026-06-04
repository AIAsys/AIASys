import { useState } from "react";
import { ServerCog, Store } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { SettingsMCPMarketPanel } from "@/components/settings/SettingsMCPMarketPanel";
import { cn } from "@/lib/utils";

type MCPMarketTabId = "builtin" | "external";

interface MCPMarketDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const TABS: Array<{
  id: MCPMarketTabId;
  label: string;
  description: string;
  icon: typeof ServerCog;
}> = [
  {
    id: "builtin",
    label: "连接器仓库",
    description: "系统预装和用户添加的连接器",
    icon: ServerCog,
  },
  {
    id: "external",
    label: "外部连接器市场",
    description: "从外部来源导入连接器",
    icon: Store,
  },
];

export function MCPMarketDialog({
  open,
  onOpenChange,
}: MCPMarketDialogProps) {
  const [activeTab, setActiveTab] = useState<MCPMarketTabId>("builtin");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-6xl h-[86vh] overflow-hidden p-0 gap-0 flex flex-col bg-background">
        <DialogHeader className="px-6 pt-5 pb-0">
          <DialogTitle>连接器管理</DialogTitle>
          <DialogDescription>
            管理已添加连接器或从外部市场导入
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
              <SettingsMCPMarketPanel
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
