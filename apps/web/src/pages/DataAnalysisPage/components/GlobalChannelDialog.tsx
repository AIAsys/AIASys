import { useState, useEffect, useMemo } from "react";
import { Wifi } from "lucide-react";

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ChannelSessionPanel } from "./AnalysisWorkspaceLayout/ChannelSessionPanel";
import { useChannelSessionDock } from "./AnalysisWorkspaceLayout/hooks/useChannelSessionDock";
import type { TaskWorkspaceSummary } from "../types";

interface GlobalChannelDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentSessionId?: string | null;
  workspaces: TaskWorkspaceSummary[];
}

export function GlobalChannelDialog({
  open,
  onOpenChange,
  currentSessionId,
  workspaces,
}: GlobalChannelDialogProps) {
  const allSessions = useMemo(() => {
    return workspaces.flatMap((w) => w.conversations || []);
  }, [workspaces]);

  const validDefaultSessionId =
    currentSessionId && allSessions.some((c) => c.session_id === currentSessionId)
      ? currentSessionId
      : undefined;

  const [selectedSessionId, setSelectedSessionId] = useState(validDefaultSessionId ?? "");

  useEffect(() => {
    if (open && validDefaultSessionId && !selectedSessionId) {
      setSelectedSessionId(validDefaultSessionId);
    }
  }, [open, validDefaultSessionId, selectedSessionId]);

  const availableSessionGroups = useMemo(() => {
    return workspaces.map((w) => ({
      workspace_id: w.workspace_id,
      workspace_title: w.title || w.workspace_id,
      sessions: (w.conversations || []).map((c) => ({
        session_id: c.session_id,
        title: c.title,
      })),
    }));
  }, [workspaces]);

  const channelDock = useChannelSessionDock({
    sessionId: selectedSessionId || undefined,
    enabled: open,
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[min(85vh,800px)] overflow-hidden flex flex-col p-0">
        <DialogHeader className="px-6 pt-6 pb-2 pr-12 shrink-0">
          <DialogDescription className="sr-only">
            管理通信渠道连接资产，包括微信、飞书等平台的绑定与配置。
          </DialogDescription>
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <DialogTitle className="flex items-center gap-2">
                <Wifi className="h-5 w-5 text-primary" />
                频道管理
              </DialogTitle>
              <p className="text-xs text-muted-foreground mt-1">
                管理通信渠道（微信 / 飞书 / 钉钉）的频道资产，以及会话与频道的绑定设置。
              </p>
            </div>

          </div>
        </DialogHeader>

        <div className="flex-1 min-h-0 overflow-y-auto px-6 pb-6">
          <ChannelSessionPanel
            sessionId={selectedSessionId || undefined}
            availableSessionGroups={availableSessionGroups}
            allSessions={allSessions}
            onSelectSession={setSelectedSessionId}
            platforms={channelDock.platforms}
            channels={channelDock.channels}
            binding={channelDock.binding}
            qrLogin={channelDock.qrLogin}
            isLoading={channelDock.isLoading}
            isMutating={channelDock.isMutating}
            isQrLoginStarting={channelDock.isQrLoginStarting}
            isQrLoginPolling={channelDock.isQrLoginPolling}
            error={channelDock.error}
            notice={channelDock.notice}
            onReload={channelDock.reload}
            onCreateChannel={channelDock.handleCreateChannel}
            onDeleteChannel={channelDock.handleDeleteChannel}
            onUpdateChannelEnabled={channelDock.handleUpdateChannelEnabled}
            onSaveBinding={channelDock.handleSaveBinding}
            onClearBinding={channelDock.handleClearBinding}
            onStartLink={channelDock.handleStartLink}
            onStopLink={channelDock.handleStopLink}
            onStartQrLogin={channelDock.handleStartQrLogin}
            onPollQrLogin={channelDock.handlePollQrLogin}
            onClearQrLogin={channelDock.handleClearQrLogin}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}
