import { GlobalChannelDialog } from "../../GlobalChannelDialog";
import type { TaskWorkspaceSummary } from "../../../types";

interface WorkspaceGlobalDialogsProps {
  isChannelOpen: boolean;
  onChannelOpenChange: (open: boolean) => void;
  currentSessionId?: string | null;
  workspaces: TaskWorkspaceSummary[];
}

export function WorkspaceGlobalDialogs({
  isChannelOpen,
  onChannelOpenChange,
  currentSessionId,
  workspaces,
}: WorkspaceGlobalDialogsProps) {
  return (
    <>
      <GlobalChannelDialog
        open={isChannelOpen}
        onOpenChange={onChannelOpenChange}
        currentSessionId={currentSessionId}
        workspaces={workspaces}
      />
    </>
  );
}
