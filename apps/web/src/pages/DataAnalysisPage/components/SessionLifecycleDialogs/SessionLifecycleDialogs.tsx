import { useEffect, useRef } from "react";
import { ChevronDown } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { SessionRecordsDialogTab } from "../../types";
import { buildConversationHistoryBatches, buildExecutionRecordSegments } from "./builders";
import { formatExecutionShortTime } from "./formatters";
import { ConversationHistoryRows, ExecutionRecordRows } from "./rows";
import type { SessionLifecycleDialogsProps } from "./types";

export function SessionLifecycleDialogs({
  isExecutionRecordsDialogOpen,
  onExecutionRecordsDialogOpenChange,
  recordsDialogTab,
  onRecordsDialogTabChange,
  highlightedExecutionSequence,
  isLoadingExecutionRecords,
  conversationHistoryMessages,
  conversationHistoryArchivedBatches,
  executionRecords,
  executionMaintenanceMarkers,
  executionRecordsSummary,
  effectiveSessionStatus,
}: SessionLifecycleDialogsProps) {
  const conversationBatches = buildConversationHistoryBatches(
    conversationHistoryMessages,
    conversationHistoryArchivedBatches,
  );
  const currentConversationBatch = conversationBatches[0];
  const historicalConversationBatches = conversationBatches.filter(
    (batch) => !batch.isCurrent && batch.messages.length > 0,
  );
  const showConversationHistoricalNotice =
    (currentConversationBatch?.messages.length ?? 0) === 0 &&
    historicalConversationBatches.length > 0;

  const executionSegments = buildExecutionRecordSegments(
    executionRecords,
    executionMaintenanceMarkers,
  );
  const currentExecutionSegment = executionSegments[0];
  const historicalExecutionSegments = executionSegments.filter(
    (segment) => !segment.isCurrent && segment.records.length > 0,
  );
  const latestHistoricalMarker = historicalExecutionSegments[0]?.marker;
  const showHistoricalNotice =
    !!latestHistoricalMarker && (currentExecutionSegment?.records.length ?? 0) === 0;
  const conversationScrollRef = useRef<HTMLDivElement | null>(null);
  const executionScrollRef = useRef<HTMLDivElement | null>(null);

  function focusActiveScrollRegion() {
    const target =
      recordsDialogTab === "execution"
        ? executionScrollRef.current
        : conversationScrollRef.current;
    target?.focus({ preventScroll: true });
  }

  useEffect(() => {
    if (!isExecutionRecordsDialogOpen) {
      return;
    }

    const frameId = window.requestAnimationFrame(() => {
      focusActiveScrollRegion();
    });

    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [isExecutionRecordsDialogOpen, recordsDialogTab]);

  return (
    <>
      <Dialog
        open={isExecutionRecordsDialogOpen}
        onOpenChange={onExecutionRecordsDialogOpenChange}
      >
        <DialogContent
          className="grid h-[80vh] max-h-[80vh] sm:max-w-4xl grid-rows-[auto_minmax(0,1fr)] overflow-hidden p-0"
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            window.requestAnimationFrame(() => {
              focusActiveScrollRegion();
            });
          }}
        >
          <DialogHeader className="px-6 pb-0 pt-6 pr-12">
            <DialogTitle>会话记录</DialogTitle>
            <DialogDescription>
              查看当前会话保留的对话上下文与代码执行轨迹。新建空会话或维护后，较早批次会按时间折叠保留。
            </DialogDescription>
          </DialogHeader>

          <Tabs
            value={recordsDialogTab}
            onValueChange={(value) =>
              onRecordsDialogTabChange(value as SessionRecordsDialogTab)
            }
            className="mt-0 flex min-h-0 flex-1 flex-col px-6 pb-6"
          >
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="conversation">
                对话上下文
                <span className="ml-2 text-[11px] text-muted-foreground">
                  {conversationHistoryMessages.length +
                    historicalConversationBatches.reduce(
                      (total, batch) => total + batch.messages.length,
                      0,
                    )}
                </span>
              </TabsTrigger>

              <TabsTrigger value="execution">
                代码执行
                <span className="ml-2 text-[11px] text-muted-foreground">
                  {executionRecordsSummary?.execution_record_count ??
                    effectiveSessionStatus?.execution_record_count ??
                    0}
                </span>
              </TabsTrigger>
            </TabsList>

            <TabsContent
              value="conversation"
              className="mt-3 flex min-h-0 flex-1 flex-col overflow-hidden"
            >
              <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span>当前会话与较早会话按维护批次分离展示</span>
                <span>新建空会话不会删除较早记录</span>
              </div>
              <div
                ref={conversationScrollRef}
                tabIndex={0}
                aria-label="会话记录对话上下文滚动区"
                className="min-h-0 flex-1 overflow-y-auto overscroll-contain rounded-lg border border-border/60 focus:outline-none focus:ring-1 focus:ring-border/60"
              >
                {isLoadingExecutionRecords ? (
                  <div className="px-4 py-8 text-sm text-muted-foreground">
                    正在加载对话记录...
                  </div>
                ) : (currentConversationBatch?.messages.length ?? 0) === 0 &&
                  historicalConversationBatches.length === 0 ? (
                  <div className="px-4 py-8 text-sm text-muted-foreground">
                    当前会话还没有可展示的对话记录。
                  </div>
                ) : (
                  <div className="divide-y divide-border/60">
                    {showConversationHistoricalNotice ? (
                      <div className="px-4 py-3 text-xs text-muted-foreground">
                        当前正在查看新的空会话。以下为较早阶段保留的对话记录。
                      </div>
                    ) : null}

                    {(currentConversationBatch?.messages.length ?? 0) > 0 ? (
                      <ConversationHistoryRows messages={currentConversationBatch.messages} />
                    ) : null}

                    {historicalConversationBatches.map((batch) => (
                      <Collapsible key={batch.id} defaultOpen={false}>
                        <CollapsibleTrigger asChild>
                          <button
                            type="button"
                            className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/40"
                          >
                            <div>
                              <div className="text-sm font-medium text-foreground">
                                {formatExecutionShortTime(batch.occurredAt)} {batch.label}
                              </div>
                              <div className="mt-1 text-xs text-muted-foreground">
                                {batch.messages.length} 条较早对话记录 · {batch.description}
                              </div>
                            </div>
                            <ChevronDown className="h-4 w-4 text-muted-foreground" />
                          </button>
                        </CollapsibleTrigger>
                        <CollapsibleContent>
                          <ConversationHistoryRows messages={batch.messages} />
                        </CollapsibleContent>
                      </Collapsible>
                    ))}
                  </div>
                )}
              </div>
            </TabsContent>

            <TabsContent
              value="execution"
              className="mt-3 flex min-h-0 flex-1 flex-col overflow-hidden"
            >
              <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span>
                  执行次数:{" "}
                  {executionRecordsSummary?.execution_record_count ??
                    effectiveSessionStatus?.execution_record_count ??
                    0}
                </span>
                <span>当前会话与代码执行记录分离管理</span>
              </div>
              <div
                ref={executionScrollRef}
                tabIndex={0}
                aria-label="会话记录代码执行滚动区"
                className="min-h-0 flex-1 overflow-y-auto overscroll-contain rounded-lg border border-border/60 focus:outline-none focus:ring-1 focus:ring-border/60"
              >
                {isLoadingExecutionRecords ? (
                  <div className="px-4 py-8 text-sm text-muted-foreground">
                    正在加载执行记录...
                  </div>
                ) : executionRecords.length === 0 ? (
                  <div className="px-4 py-8 text-sm text-muted-foreground">
                    当前会话还没有代码执行记录。
                  </div>
                ) : (
                  <div className="divide-y divide-border/60">
                    {showHistoricalNotice ? (
                      <div className="px-4 py-3 text-xs text-muted-foreground">
                        {formatExecutionShortTime(latestHistoricalMarker.occurred_at)}{" "}
                        {latestHistoricalMarker.label}。以下为较早执行记录。
                      </div>
                    ) : null}

                    {(currentExecutionSegment?.records.length ?? 0) > 0 ? (
                      <ExecutionRecordRows
                        records={currentExecutionSegment.records}
                        highlightedExecutionSequence={highlightedExecutionSequence}
                      />
                    ) : null}

                    {historicalExecutionSegments.map((segment) => (
                      <Collapsible key={segment.id} defaultOpen={false}>
                        <CollapsibleTrigger asChild>
                          <button
                            type="button"
                            className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/40"
                          >
                            <div>
                              <div className="text-sm font-medium text-foreground">
                                {formatExecutionShortTime(segment.marker?.occurred_at)}{" "}
                                {segment.marker?.label}
                              </div>
                              <div className="mt-1 text-xs text-muted-foreground">
                                {segment.records.length} 条较早执行记录
                                {segment.marker?.description
                                  ? ` · ${segment.marker.description}`
                                  : ""}
                              </div>
                            </div>
                            <ChevronDown className="h-4 w-4 text-muted-foreground" />
                          </button>
                        </CollapsibleTrigger>
                        <CollapsibleContent>
                          <ExecutionRecordRows
                            records={segment.records}
                            highlightedExecutionSequence={highlightedExecutionSequence}
                          />
                        </CollapsibleContent>
                      </Collapsible>
                    ))}
                  </div>
                )}
              </div>
            </TabsContent>
          </Tabs>
        </DialogContent>
      </Dialog>
    </>
  );
}
