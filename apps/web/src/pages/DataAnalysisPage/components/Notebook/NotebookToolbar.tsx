import {
  FileCode2,
  Loader2,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Sparkles,
  Square,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { NotebookStorageScope } from "@/types/notebook";
import { CanvasActionMenu } from "@/pages/DataAnalysisPage/components/AnalysisWorkspaceLayout/components/CanvasActionMenu";

export const NOTEBOOK_INSPECTOR_TABS = [
  "outline",
  "variables",
  "artifacts",
  "runs",
  "diff",
] as const;

export type NotebookInspectorTab =
  | "search"
  | (typeof NOTEBOOK_INSPECTOR_TABS)[number];

export function getInspectorTabLabel(tab: NotebookInspectorTab): string {
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

interface NotebookToolbarProps {
  title: string;
  stateDescription: string;
  resolvedFrom: NotebookStorageScope;
  canForkToSession: boolean;
  showPromoteToWorkspace: boolean;
  isDirty: boolean;
  kernelActive: boolean;
  inspectorTab: NotebookInspectorTab | null;
  runtimeAction: "interrupt" | "restart" | "stop" | null;
  isSaving: boolean;
  disableForkToSession: boolean;
  disablePromoteToWorkspace: boolean;
  disableReload: boolean;
  disableInterrupt: boolean;
  disableRestartKernel: boolean;
  disableStopKernel: boolean;
  disableRestartAndRunAll: boolean;
  disableRunAll: boolean;
  disableClearAllOutputs: boolean;
  disableSave: boolean;
  editLockReason?: string | null;
  externalUpdateDetected?: boolean;
  error?: string | null;
  onClose: () => void;
  closeLabel?: string;
  onSplitRight?: () => void;
  onSplitDown?: () => void;
  onForkToSession: () => void;
  onPromoteToWorkspace: () => void;
  onReload: () => void;
  onOpenInspector: (tab: NotebookInspectorTab) => void;
  onInterrupt: () => void;
  onRestartKernel: () => void;
  onStopKernel: () => void;
  onRestartAndRunAll: () => void;
  onRunAll: () => void;
  onClearAllOutputs: () => void;
  onSave: () => void;
}

export function NotebookToolbar({
  title,
  stateDescription,
  resolvedFrom,
  canForkToSession,
  showPromoteToWorkspace,
  isDirty,
  kernelActive,
  inspectorTab,
  runtimeAction,
  isSaving,
  disableForkToSession,
  disablePromoteToWorkspace,
  disableReload,
  disableInterrupt,
  disableRestartKernel,
  disableStopKernel,
  disableRestartAndRunAll,
  disableRunAll,
  disableClearAllOutputs,
  disableSave,
  editLockReason,
  externalUpdateDetected = false,
  error,
  onClose,
  closeLabel = "返回对话",
  onSplitRight,
  onSplitDown,
  onForkToSession,
  onPromoteToWorkspace,
  onReload,
  onOpenInspector,
  onInterrupt,
  onRestartKernel,
  onStopKernel,
  onRestartAndRunAll,
  onRunAll,
  onClearAllOutputs,
  onSave,
}: NotebookToolbarProps) {
  return (
    <div className="border-b border-border bg-background/95 px-5 py-4 backdrop-blur">
      {/* Top row: back button + title + status badges */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <FileCode2 className="h-3.5 w-3.5" />
              Notebook Workbench
            </div>
            <div className="mt-1 truncate text-base font-semibold text-foreground">
              {title}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {stateDescription}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={resolvedFrom === "session" ? "default" : "secondary"}>
            {resolvedFrom === "session" ? "当前会话私有" : "工作区共享"}
          </Badge>
          {isDirty ? <Badge variant="outline">未保存</Badge> : null}
          {kernelActive ? <Badge variant="outline">Kernel 活跃</Badge> : null}
          <CanvasActionMenu
            onClose={onClose}
            closeLabel={closeLabel}
            onSplitRight={onSplitRight}
            onSplitDown={onSplitDown}
          />
        </div>
      </div>

      {/* Action buttons row */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {/* File ops */}
        <Button
          type="button"
          size="sm"
          onClick={onSave}
          disabled={disableSave}
        >
          {isSaving ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <Save className="mr-1.5 h-3.5 w-3.5" />
          )}
          保存
        </Button>
        {showPromoteToWorkspace ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onPromoteToWorkspace}
            disabled={disablePromoteToWorkspace}
          >
            发布到工作区
          </Button>
        ) : null}
        {canForkToSession ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onForkToSession}
            disabled={disableForkToSession}
          >
            <Sparkles className="mr-1.5 h-3.5 w-3.5" />
            复制到当前会话
          </Button>
        ) : null}
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onReload}
          disabled={disableReload}
        >
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          重新加载
        </Button>

        <div className="mx-1 h-5 w-px bg-border" />

        {/* Run ops */}
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onRunAll}
          disabled={disableRunAll}
        >
          <Play className="mr-1.5 h-3.5 w-3.5" />
          运行整本
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onRestartAndRunAll}
          disabled={disableRestartAndRunAll}
        >
          <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
          重建环境并运行
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onClearAllOutputs}
          disabled={disableClearAllOutputs}
        >
          清空全部输出
        </Button>

        <div className="mx-1 h-5 w-px bg-border" />

        {/* Kernel ops */}
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onInterrupt}
          disabled={disableInterrupt}
        >
          {runtimeAction === "interrupt" ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : null}
          中断
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onRestartKernel}
          disabled={disableRestartKernel}
        >
          {runtimeAction === "restart" ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
          )}
          重启 Kernel
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onStopKernel}
          disabled={disableStopKernel}
        >
          {runtimeAction === "stop" ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <Square className="mr-1.5 h-3.5 w-3.5" />
          )}
          停止 Kernel
        </Button>

        <div className="mx-1 h-5 w-px bg-border" />

        {/* Inspector tabs */}
        <Button
          type="button"
          variant={inspectorTab === "search" ? "default" : "outline"}
          size="sm"
          onClick={() => onOpenInspector("search")}
        >
          <Search className="mr-1.5 h-3.5 w-3.5" />
          搜索
        </Button>
        {NOTEBOOK_INSPECTOR_TABS.map((tab) => (
          <Button
            key={tab}
            type="button"
            variant={inspectorTab === tab ? "default" : "outline"}
            size="sm"
            onClick={() => onOpenInspector(tab)}
          >
            {getInspectorTabLabel(tab)}
          </Button>
        ))}
      </div>

      {editLockReason ? (
        <div className="mt-3 rounded-xl border border-warning/20 bg-warning-container px-3 py-2 text-xs text-warning">
          {editLockReason}
        </div>
      ) : null}
      {externalUpdateDetected ? (
        <div className="mt-3 flex items-center justify-between gap-3 rounded-xl border border-info/20 bg-info-container px-3 py-2 text-xs text-tertiary">
          <span>
            检测到当前 notebook 在外部被更新。请重新加载确认最新内容。
          </span>
          <Button type="button" variant="outline" size="sm" onClick={onReload}>
            重新加载
          </Button>
        </div>
      ) : null}
      {error ? (
        <div className="mt-3 rounded-xl border border-error/20 bg-error-container px-3 py-2 text-xs text-error">
          {error}
        </div>
      ) : null}
    </div>
  );
}

interface NotebookAddCellStripProps {
  onAddCodeCell: () => void;
  onAddMarkdownCell: () => void;
  onAddRawCell: () => void;
  disableAddCodeCell?: boolean;
  disableAddMarkdownCell?: boolean;
  disableAddRawCell?: boolean;
}

export function NotebookAddCellStrip({
  onAddCodeCell,
  onAddMarkdownCell,
  onAddRawCell,
  disableAddCodeCell = false,
  disableAddMarkdownCell = false,
  disableAddRawCell = false,
}: NotebookAddCellStripProps) {
  return (
    <div className="flex items-center justify-center gap-3 rounded-2xl border border-dashed border-border px-4 py-4">
      <Button
        type="button"
        variant="outline"
        onClick={onAddCodeCell}
        disabled={disableAddCodeCell}
      >
        <Plus className="mr-1.5 h-3.5 w-3.5" />
        新增 Code Cell
      </Button>
      <Button
        type="button"
        variant="outline"
        onClick={onAddMarkdownCell}
        disabled={disableAddMarkdownCell}
      >
        <Plus className="mr-1.5 h-3.5 w-3.5" />
        新增 Markdown Cell
      </Button>
      <Button
        type="button"
        variant="outline"
        onClick={onAddRawCell}
        disabled={disableAddRawCell}
      >
        <Plus className="mr-1.5 h-3.5 w-3.5" />
        新增 Raw Cell
      </Button>
    </div>
  );
}
