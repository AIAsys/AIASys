import { useEffect, useRef, useState } from "react";
import { FileCode2, Loader2, PanelRightClose, PanelRightOpen, Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

import { NotebookCellCard } from "../Notebook/NotebookCellCard";
import {
  NotebookInspectorTabButtons,
  getNotebookInspectorTabLabel,
} from "../Notebook/NotebookInspectorPanel";
import { NotebookAddCellStrip, NotebookToolbar } from "../Notebook/NotebookToolbar";
import { useNotebookDocument } from "../Notebook/hooks/useNotebookDocument";
import { useNotebookInspector } from "../Notebook/hooks/useNotebookInspector";
import { DiffInspector } from "../Notebook/inspectors/DiffInspector";
import { OutlineInspector } from "../Notebook/inspectors/OutlineInspector";
import { RunsInspector } from "../Notebook/inspectors/RunsInspector";
import { VariablesInspector } from "../Notebook/inspectors/VariablesInspector";
import type {
  NotebookWorkbenchCanvasProps,
  UseNotebookInspectorResult,
} from "../Notebook/types";

type NotebookSearchResults = UseNotebookInspectorResult["searchResults"];
type NotebookArtifacts = UseNotebookInspectorResult["artifacts"];
type ActiveNotebookInspectorTab = NonNullable<
  UseNotebookInspectorResult["inspectorTab"]
>;

function SearchInspectorContent({
  searchQuery,
  inspectorLoading,
  searchResults,
  onSearchQueryChange,
  onSearch,
  onSelectCell,
}: {
  searchQuery: string;
  inspectorLoading: boolean;
  searchResults: NotebookSearchResults;
  onSearchQueryChange: (value: string) => void;
  onSearch: () => void;
  onSelectCell: (cellId: string) => void;
}) {
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={searchQuery}
          onChange={(event) => onSearchQueryChange(event.target.value)}
          placeholder="搜索 cell 内容"
          className="max-w-sm"
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              onSearch();
            }
          }}
        />
        <Button
          type="button"
          size="sm"
          onClick={onSearch}
          disabled={inspectorLoading}
        >
          {inspectorLoading ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <Search className="mr-1.5 h-3.5 w-3.5" />
          )}
          搜索
        </Button>
      </div>
      <div className="space-y-2">
        {searchResults.length > 0 ? (
          searchResults.map((match) => (
            <button
              key={`${match.cell_id}-${match.cell_index}`}
              type="button"
              className="w-full rounded-xl border border-border px-3 py-3 text-left transition-colors hover:border-primary/40 hover:bg-muted/30"
              onClick={() => onSelectCell(match.cell_id)}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm font-medium text-foreground">
                  Cell {match.cell_index + 1}
                </div>
                <Badge variant="secondary">{match.cell_type}</Badge>
              </div>
              <div className="mt-2 text-xs text-muted-foreground">
                {match.snippet || match.source_preview}
              </div>
            </button>
          ))
        ) : (
          <div className="rounded-xl border border-dashed border-border/60 px-3 py-4 text-xs text-muted-foreground">
            输入关键词后可定位 notebook 中的目标 cell。
          </div>
        )}
      </div>
    </>
  );
}

function ArtifactsInspectorContent({
  artifacts,
}: {
  artifacts: NotebookArtifacts;
}) {
  if (artifacts.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border/60 px-3 py-4 text-xs text-muted-foreground">
        当前 notebook 还没有产物记录。
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {artifacts.map((artifact) => (
        <div
          key={artifact.artifact_id}
          className="rounded-xl border border-border px-3 py-3"
        >
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-medium text-foreground">
              {artifact.display_name}
            </div>
            <Badge variant="outline">{artifact.artifact_kind}</Badge>
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {artifact.mime_type || "artifact"}
            {artifact.cell_index != null ? ` · Cell ${artifact.cell_index + 1}` : ""}
            {artifact.relative_path ? ` · ${artifact.relative_path}` : ""}
          </div>
        </div>
      ))}
    </div>
  );
}

function NotebookInspectorContent({
  activeTab,
  inspectorLoading,
  inspectorError,
  searchQuery,
  searchResults,
  outlineItems,
  variables,
  artifacts,
  executionRecords,
  diffChanges,
  diffMetadataChanged,
  onSearchQueryChange,
  onSearch,
  onSelectCell,
}: {
  activeTab: ActiveNotebookInspectorTab;
  inspectorLoading: boolean;
  inspectorError: string | null;
  searchQuery: string;
  searchResults: NotebookSearchResults;
  outlineItems: UseNotebookInspectorResult["outlineItems"];
  variables: UseNotebookInspectorResult["variables"];
  artifacts: NotebookArtifacts;
  executionRecords: UseNotebookInspectorResult["executionRecords"];
  diffChanges: UseNotebookInspectorResult["diffChanges"];
  diffMetadataChanged: boolean;
  onSearchQueryChange: (value: string) => void;
  onSearch: () => void;
  onSelectCell: (cellId: string) => void;
}) {
  return (
    <>
      {activeTab === "search" ? (
        <SearchInspectorContent
          searchQuery={searchQuery}
          inspectorLoading={inspectorLoading}
          searchResults={searchResults}
          onSearchQueryChange={onSearchQueryChange}
          onSearch={onSearch}
          onSelectCell={onSelectCell}
        />
      ) : null}
      {inspectorError ? (
        <div className="rounded-xl border border-error/20 bg-error-container px-3 py-2 text-xs text-error">
          {inspectorError}
        </div>
      ) : null}
      {inspectorLoading && activeTab !== "search" ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          正在读取 {getNotebookInspectorTabLabel(activeTab)}...
        </div>
      ) : null}
      {activeTab === "outline" ? (
        <OutlineInspector items={outlineItems} onSelectCell={onSelectCell} />
      ) : null}
      {activeTab === "variables" ? (
        <VariablesInspector variables={variables} />
      ) : null}
      {activeTab === "artifacts" ? (
        <ArtifactsInspectorContent artifacts={artifacts} />
      ) : null}
      {activeTab === "runs" ? (
        <RunsInspector executionRecords={executionRecords} />
      ) : null}
      {activeTab === "diff" ? (
        <DiffInspector
          changes={diffChanges}
          metadataChanged={diffMetadataChanged}
          onSelectCell={onSelectCell}
        />
      ) : null}
    </>
  );
}

export function NotebookWorkbenchCanvas({
  file,
  sessionId,
  workspaceFiles,
  onClose,
  closeLabel,
  onSplitRight,
  onSplitDown,
  onRefreshWorkspace,
  onRefreshSessionStatus,
}: NotebookWorkbenchCanvasProps) {
  const [markdownPreviewCellId, setMarkdownPreviewCellId] = useState<string | null>(null);
  const [focusedCellId, setFocusedCellId] = useState<string | null>(null);

  const cellRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const {
    draftDocument,
    workbenchSnapshot,
    isLoading,
    isSaving,
    isRunning,
    runningCellId,
    error,
    externalUpdateDetected,
    isDirty,
    runtimeState,
    runtimeAction,
    inspectorRefreshVersion,
    loadDocument,
    saveDocument: handleSave,
    runNotebook: handleRun,
    restartAndRunAll: handleRestartAndRunAll,
    clearOutputs: handleClearOutputs,
    forkToSession: handleForkToSession,
    promoteToWorkspace,
    controlRuntime: handleRuntimeControl,
    updateCell,
    insertCell,
    moveCell,
    deleteCell,
  } = useNotebookDocument({
    file,
    sessionId,
    workspaceFiles,
    onRefreshWorkspace,
    onRefreshSessionStatus,
  });

  const {
    inspectorTab,
    inspectorLoading,
    inspectorError,
    searchQuery,
    setSearchQuery,
    searchResults,
    outlineItems,
    variables,
    artifacts,
    executionRecords,
    diffChanges,
    diffMetadataChanged,
    toggleInspectorTab: handleOpenInspector,
    closeInspector,
    handleSearch,
  } = useNotebookInspector({
    sessionId,
    notebookPath: draftDocument?.notebook_path,
    lastExecutionRecordId: draftDocument?.state.last_execution_record_id,
    refreshVersion: inspectorRefreshVersion,
  });

  useEffect(() => {
    if (!focusedCellId) {
      return;
    }
    const timer = window.setTimeout(() => setFocusedCellId(null), 1800);
    return () => window.clearTimeout(timer);
  }, [focusedCellId]);

  const scrollToCell = (cellId: string) => {
    setFocusedCellId(cellId);
    cellRefs.current[cellId]?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
  };

  const [showPromoteDialog, setShowPromoteDialog] = useState(false);

  const handlePromoteToWorkspace = () => {
    setShowPromoteDialog(true);
  };

  const confirmPromoteToWorkspace = async () => {
    setShowPromoteDialog(false);
    await promoteToWorkspace();
  };

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
        正在加载 notebook...
      </div>
    );
  }

  if (!draftDocument) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center text-muted-foreground">
        <FileCode2 className="h-10 w-10 opacity-40" />
        <div className="text-sm">当前 notebook 无法打开。</div>
        {error ? <div className="text-xs text-error">{error}</div> : null}
      </div>
    );
  }

  const runtimeSummary = runtimeState?.runtime_summary ?? draftDocument.state.runtime_summary;
  const kernelActive = runtimeState?.kernel_active ?? Boolean(runtimeSummary.kernel_active);
  const canInterrupt = runtimeState?.can_interrupt ?? kernelActive;
  const canStop = runtimeState?.can_stop ?? kernelActive;
  const stateDescription = [
    draftDocument.state.resolved_from === "workspace"
      ? "当前打开的是工作区共享副本"
      : "当前打开的是会话私有副本",
    draftDocument.state.will_create_session_copy
      ? "保存后会自动在当前会话生成私有副本"
      : null,
    runtimeSummary.status_label ? `执行环境：${runtimeSummary.status_label}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const lastCellIndex = draftDocument.cells.length - 1;
  const activeInspectorTab: ActiveNotebookInspectorTab | null = inspectorTab;
  const workbenchSummary = workbenchSnapshot?.summary;

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-background">
      <NotebookToolbar
        title={draftDocument.title || file.name}
        stateDescription={stateDescription}
        resolvedFrom={draftDocument.state.resolved_from}
        canForkToSession={draftDocument.state.can_fork_to_session}
        showPromoteToWorkspace={draftDocument.state.resolved_from === "session"}
        isDirty={isDirty}
        kernelActive={kernelActive}
        inspectorTab={inspectorTab}
        runtimeAction={runtimeAction}
        isSaving={isSaving}
        disableForkToSession={isSaving || isRunning}
        disablePromoteToWorkspace={isSaving || isRunning || runtimeAction !== null}
        disableReload={isLoading || isSaving || isRunning}
        disableInterrupt={runtimeAction !== null || (!isRunning && !canInterrupt)}
        disableRestartKernel={runtimeAction !== null || isSaving}
        disableStopKernel={runtimeAction !== null || !canStop}
        disableRestartAndRunAll={isSaving || isRunning || runtimeAction !== null}
        disableRunAll={isSaving || isRunning || runtimeAction !== null}
        disableClearAllOutputs={isSaving || isRunning || runtimeAction !== null}
        disableSave={!isDirty || isSaving || isRunning || runtimeAction !== null}
        editLockReason={draftDocument.state.edit_lock_reason}
        externalUpdateDetected={externalUpdateDetected}
        error={error}
        onClose={onClose}
        closeLabel={closeLabel}
        onSplitRight={onSplitRight}
        onSplitDown={onSplitDown}
        onForkToSession={() => {
          void handleForkToSession();
        }}
        onPromoteToWorkspace={() => {
          void handlePromoteToWorkspace();
        }}
        onReload={() => {
          void loadDocument();
        }}
        onOpenInspector={handleOpenInspector}
        onInterrupt={() => {
          void handleRuntimeControl("interrupt");
        }}
        onRestartKernel={() => {
          void handleRuntimeControl("restart");
        }}
        onStopKernel={() => {
          void handleRuntimeControl("stop");
        }}
        onRestartAndRunAll={() => {
          void handleRestartAndRunAll();
        }}
        onRunAll={() => {
          void handleRun("all");
        }}
        onClearAllOutputs={() => {
          void handleClearOutputs();
        }}
        onSave={() => {
          void handleSave();
        }}
      />

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden px-6 py-6 xl:flex-row">
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <div className="mx-auto flex min-h-0 flex-1 w-full max-w-5xl flex-col gap-4 overflow-y-auto pr-1 pb-12">
            <div className="flex items-start gap-3">
              <div className="grid flex-1 gap-3 rounded-2xl border border-border bg-card px-4 py-3 shadow-sm sm:grid-cols-4">
              <div>
                <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  单元
                </div>
                <div className="mt-1 text-lg font-semibold text-foreground">
                  {workbenchSummary?.total_cell_count ?? draftDocument.cells.length}
                </div>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  已运行
                </div>
                <div className="mt-1 text-lg font-semibold text-foreground">
                  {workbenchSummary?.executed_code_cell_count ?? 0}
                </div>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  变量
                </div>
                <div className="mt-1 text-lg font-semibold text-foreground">
                  {workbenchSummary?.variable_count ?? variables.length}
                </div>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  产物
                </div>
                <div className="mt-1 text-lg font-semibold text-foreground">
                  {workbenchSummary?.artifact_count ?? artifacts.length}
                </div>
              </div>
            </div>
            {activeInspectorTab === null ? (
                <button
                  type="button"
                  onClick={() => handleOpenInspector("variables")}
                  className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-border bg-card text-muted-foreground shadow-sm transition-colors hover:bg-muted hover:text-foreground"
                  title="展开右侧面板"
                >
                  <PanelRightOpen className="h-4 w-4" />
                </button>
              ) : null}
            </div>

            {draftDocument.cells.map((cell, index) => (
              <NotebookCellCard
                key={cell.cell_id}
                cell={cell}
                cellIndex={index}
                isFocused={focusedCellId === cell.cell_id}
                isMarkdownPreview={markdownPreviewCellId === cell.cell_id}
                isRunning={isRunning && runningCellId === cell.cell_id}
                disableRunCell={isSaving || isRunning}
                containerRef={(node) => {
                  cellRefs.current[cell.cell_id] = node;
                }}
                onChangeCellType={(cellId, nextType) =>
                  updateCell(cellId, {
                    cell_type: nextType,
                    outputs: nextType === "code" ? cell.outputs : [],
                    output_summaries: nextType === "code" ? cell.output_summaries : [],
                  })
                }
                onChangeSource={(cellId, source) => updateCell(cellId, { source })}
                onToggleMarkdownPreview={(cellId) =>
                  setMarkdownPreviewCellId((prev) => (prev === cellId ? null : cellId))
                }
                onRunCell={(cellId) => {
                  void handleRun("cell", cellId);
                }}
                onInsertCell={insertCell}
                onMoveCell={moveCell}
                onClearOutputs={(cellId) => {
                  void handleClearOutputs(cellId);
                }}
                onDeleteCell={deleteCell}
              />
            ))}

            <NotebookAddCellStrip
              onAddCodeCell={() => insertCell(lastCellIndex, "after", "code")}
              onAddMarkdownCell={() => insertCell(lastCellIndex, "after", "markdown")}
              onAddRawCell={() => insertCell(lastCellIndex, "after", "raw")}
            />
          </div>
        </div>

        {activeInspectorTab !== null ? (
          <aside className="flex min-h-0 w-full shrink-0 flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-sm xl:w-[340px]">
            <div className="border-b border-border/60 px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-foreground">
                    {getNotebookInspectorTabLabel(activeInspectorTab)}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    当前 Notebook 的大纲、变量、运行和产物
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={kernelActive ? "default" : "outline"}>
                    {kernelActive ? "Kernel 活跃" : "Kernel 未启动"}
                  </Badge>
                  <button
                    type="button"
                    onClick={() => closeInspector()}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                    title="收起面板"
                  >
                    <PanelRightClose className="h-4 w-4" />
                  </button>
                </div>
              </div>
              <NotebookInspectorTabButtons
                activeTab={activeInspectorTab}
                onTabToggle={handleOpenInspector}
                className="mt-3"
              />
            </div>
          {workbenchSnapshot?.issues.length ? (
            <div className="border-b border-border/60 bg-warning-container px-4 py-2 text-xs text-warning">
              {workbenchSnapshot.issues[0].detail}
            </div>
          ) : null}
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
            <NotebookInspectorContent
              activeTab={activeInspectorTab}
              inspectorLoading={inspectorLoading}
              inspectorError={inspectorError}
              searchQuery={searchQuery}
              searchResults={searchResults}
              outlineItems={outlineItems}
              variables={variables}
              artifacts={artifacts}
              executionRecords={executionRecords}
              diffChanges={diffChanges}
              diffMetadataChanged={diffMetadataChanged}
              onSearchQueryChange={setSearchQuery}
              onSearch={() => {
                void handleSearch();
              }}
              onSelectCell={scrollToCell}
            />
            </div>
          </aside>
        ) : null}
      </div>

      <AlertDialog open={showPromoteDialog} onOpenChange={setShowPromoteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认发布</AlertDialogTitle>
            <AlertDialogDescription>
              这会覆盖工作区共享基线版本。是否继续发布当前会话副本？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={() => void confirmPromoteToWorkspace()}>
              确认
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
