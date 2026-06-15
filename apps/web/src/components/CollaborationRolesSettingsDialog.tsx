import { useState } from "react";
import {
  PackageSearch,
  ServerCog,
} from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { RolesManagerPanel } from "@/components/RolesManagerPanel";
import { cn } from "@/lib/utils";

type CollaborationRolesScopeTab = "experts" | "market";

interface CollaborationRolesSettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspaceId?: string | null;
}

const TABS: Array<{
  id: CollaborationRolesScopeTab;
  label: string;
  description: string;
  icon: typeof ServerCog;
}> = [
  {
    id: "experts",
    label: "我的协作专家",
    description: "已安装到可选集合的协作专家",
    icon: ServerCog,
  },
  {
    id: "market",
    label: "外部协作专家市场",
    description: "AIASys 系统内置协作专家",
    icon: PackageSearch,
  },
];

export function CollaborationRolesSettingsDialog({
  open,
  onOpenChange,
  workspaceId: _workspaceId,
}: CollaborationRolesSettingsDialogProps) {
  const [scopeTab, setScopeTab] =
    useState<CollaborationRolesScopeTab>("experts");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-6xl h-[86vh] overflow-hidden p-0 gap-0 flex flex-col bg-background"
        data-testid="collaboration-roles-settings-dialog"
      >
        <DialogHeader className="px-6 pt-5 pb-0">
          <DialogTitle>协作专家管理</DialogTitle>
          <DialogDescription>
            创建和管理自定义协作专家，或浏览系统内置专家
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 px-6 py-4">
          <div className="grid h-full min-h-0 grid-cols-[236px_minmax(0,1fr)] overflow-hidden rounded-2xl border border-border bg-card">
            {/* 左侧导航栏 */}
            <aside className="border-r border-border bg-muted/20 p-3">
              <div className="space-y-1">
                {TABS.map((tab) => {
                  const active = tab.id === scopeTab;
                  const Icon = tab.icon;
                  return (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => setScopeTab(tab.id)}
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
              {scopeTab === "experts" ? (
                <RolesManagerPanel
                  scope="global"
                  mode="manage"
                  title="我的协作专家"
                  description="管理已安装到可选集合的协作专家。系统专家可移出，自定义专家可编辑或删除。"
                />
              ) : null}
              {scopeTab === "market" ? (
                <div className="flex h-full flex-col gap-3">
                  {/* 来源标识 */}
                  <div className="flex items-center gap-2">
                    <span className="rounded-full border border-tertiary/30 bg-tertiary-container px-3 py-1 text-[11px] text-on-tertiary-container">
                      AIASys
                    </span>
                    <span className="text-[11px] text-muted-foreground">
                      系统内置协作专家
                    </span>
                  </div>
                  <div className="flex-1 min-h-0">
                    <RolesManagerPanel
                      scope="global"
                      mode="market"
                      roleFilter={(role) => role.source === "system"}
                      hideCreateButton
                      title="外部协作专家市场"
                      description="安装后进入可选集合，默认启用需单独设置。"
                    />
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
