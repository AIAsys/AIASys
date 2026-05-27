import {
  Bot,
  Database,
  FolderOpen,
  GitBranch,
  Globe,
  Puzzle,
  Radio,
  Search,
  Settings,
  Terminal,
  ScrollText,
  Zap,
} from "lucide-react";
import type { ActivityBarItem } from "../ActivityBar";

export type ActivityPanelView =
  | "artifacts"
  | "search"
  | "resources"
  | "database"
  | "monitor"
  | "subagents"
  | "auto-tasks"
  | "env"
  | "terminal"
  | "capabilities"
  | "agent-config"
  | "file-changes"
;

export interface ViewButton {
  id: ActivityPanelView;
  label: string;
  icon: React.ReactNode;
}

export function getViewButtons(
  layoutMode: "sidebar" | "center",
): ViewButton[] {
  return [
    {
      id: "artifacts",
      label: "当前工作区",
      icon: <FolderOpen className="h-4 w-4 text-warning" />,
    },
    {
      id: "resources",
      label: "全局工作区",
      icon: <Globe className="h-4 w-4 text-tertiary" />,
    },
    ...(layoutMode === "center"
      ? []
      : [
          { id: "monitor" as const, label: "监控任务", icon: <Radio className="h-4 w-4 text-warning" /> },
          { id: "terminal" as const, label: "终端", icon: <Terminal className="h-4 w-4 text-info" /> },
          { id: "auto-tasks" as const, label: "自动化任务", icon: <Zap className="h-4 w-4 text-info" /> },
          { id: "subagents" as const, label: "专家协作节点", icon: <Bot className="h-4 w-4 text-success" /> },
          { id: "env" as const, label: "环境变量", icon: <ScrollText className="h-4 w-4 text-info" /> },
          { id: "capabilities" as const, label: "能力管理", icon: <Puzzle className="h-4 w-4 text-tertiary" /> },
          { id: "agent-config" as const, label: "工作区设置", icon: <Settings className="h-4 w-4 text-muted-foreground" /> },
          { id: "file-changes" as const, label: "文件变更", icon: <GitBranch className="h-4 w-4 text-info" /> },
        ]),
  ];
}

export function getDefaultActivityItems(): Array<ActivityBarItem<ActivityPanelView>> {
  return [
    { id: "artifacts", label: "当前工作区", icon: <FolderOpen className="h-4 w-4" /> },
    { id: "resources", label: "全局工作区", icon: <Globe className="h-4 w-4" /> },
    { id: "database", label: "数据查询", icon: <Database className="h-4 w-4" /> },
    { id: "search", label: "文件搜索", icon: <Search className="h-4 w-4" /> },
    { id: "monitor", label: "监控任务", icon: <Radio className="h-4 w-4" /> },
    { id: "terminal", label: "终端", icon: <Terminal className="h-4 w-4" /> },
    { id: "auto-tasks", label: "自动化任务", icon: <Zap className="h-4 w-4" /> },
    { id: "subagents", label: "专家协作节点", icon: <Bot className="h-4 w-4" /> },
    { id: "env", label: "环境变量", icon: <ScrollText className="h-4 w-4" /> },
    { id: "capabilities", label: "能力管理", icon: <Puzzle className="h-4 w-4" /> },
    { id: "agent-config", label: "工作区设置", icon: <Settings className="h-4 w-4" /> },
    { id: "file-changes", label: "文件变更", icon: <GitBranch className="h-4 w-4" /> },
  ];
}

export function applyOrder(
  items: Array<ActivityBarItem<ActivityPanelView>>,
  order: string[] | undefined,
): Array<ActivityBarItem<ActivityPanelView>> {
  if (!order || order.length !== items.length) return items;
  const itemMap = new Map<string, ActivityBarItem<ActivityPanelView>>(
    items.map((i) => [i.id as string, i]),
  );
  const reordered = order
    .map((id) => itemMap.get(id))
    .filter((i): i is ActivityBarItem<ActivityPanelView> => Boolean(i));
  return reordered.length === items.length ? reordered : items;
}

export function isActivityPanelView(view: string): view is ActivityPanelView {
  return (
    view === "artifacts" ||
    view === "search" ||
    view === "resources" ||
    view === "database" ||
    view === "monitor" ||
    view === "subagents" ||
    view === "auto-tasks" ||

    view === "env" ||
    view === "terminal" ||
    view === "capabilities" ||
    view === "agent-config" ||
    view === "file-changes"
  );
}
