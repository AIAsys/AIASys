import type { ReactNode } from "react";
import { Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type NotebookInspectorTab =
  | "search"
  | "outline"
  | "variables"
  | "artifacts"
  | "runs"
  | "diff";

type NotebookDataInspectorTab = Exclude<NotebookInspectorTab, "search">;

const NOTEBOOK_DATA_INSPECTOR_TABS: NotebookDataInspectorTab[] = [
  "outline",
  "variables",
  "artifacts",
  "runs",
  "diff",
];

export function getNotebookInspectorTabLabel(tab: NotebookInspectorTab): string {
  switch (tab) {
    case "search":
      return "搜索";
    case "outline":
      return "Outline";
    case "variables":
      return "变量";
    case "artifacts":
      return "产物";
    case "runs":
      return "运行记录";
    case "diff":
      return "版本差异";
    default:
      return tab;
  }
}

interface NotebookInspectorTabButtonsProps {
  activeTab: NotebookInspectorTab | null;
  onTabToggle: (tab: NotebookInspectorTab) => void;
  className?: string;
}

export function NotebookInspectorTabButtons({
  activeTab,
  onTabToggle,
  className,
}: NotebookInspectorTabButtonsProps) {
  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <Button
        type="button"
        variant={activeTab === "search" ? "default" : "outline"}
        size="sm"
        onClick={() => onTabToggle("search")}
      >
        <Search className="mr-1.5 h-3.5 w-3.5" />
        搜索
      </Button>
      {NOTEBOOK_DATA_INSPECTOR_TABS.map((tab) => (
        <Button
          key={tab}
          type="button"
          variant={activeTab === tab ? "default" : "outline"}
          size="sm"
          onClick={() => onTabToggle(tab)}
        >
          {getNotebookInspectorTabLabel(tab)}
        </Button>
      ))}
    </div>
  );
}

interface NotebookInspectorPanelProps {
  activeTab: NotebookInspectorTab;
  onClose: () => void;
  children: ReactNode;
  className?: string;
}

export function NotebookInspectorPanel({
  activeTab,
  onClose,
  children,
  className,
}: NotebookInspectorPanelProps) {
  return (
    <div className={cn("rounded-2xl border border-border/80 bg-card shadow-sm", className)}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/60 px-4 py-3">
        <div>
          <div className="text-sm font-semibold text-foreground">
            {getNotebookInspectorTabLabel(activeTab)}
          </div>
          <div className="text-xs text-muted-foreground">
            围绕当前 notebook 的定位、观测和版本协作能力
          </div>
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          关闭
        </Button>
      </div>
      <div className="space-y-3 px-4 py-4">{children}</div>
    </div>
  );
}
