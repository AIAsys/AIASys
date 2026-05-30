import { useSessionLifecycleCompactAction } from "./useSessionLifecycleCompactAction";
import { useSessionLifecycleExecutionActions } from "./useSessionLifecycleExecutionActions";
import { useSessionLifecycleExportAction } from "./useSessionLifecycleExportAction";
import type { SessionLifecycleActionContext } from "./sessionLifecycleManagerActionTypes";

export function useSessionLifecycleManagerActions(
  context: SessionLifecycleActionContext,
) {
  const handleExportSession = useSessionLifecycleExportAction(context);
  const { handleViewExecutionRecords } =
    useSessionLifecycleExecutionActions(context);
  const { handleCompactConversation } =
    useSessionLifecycleCompactAction(context);

  return {
    handleExportSession,
    handleCompactConversation,
    handleViewExecutionRecords,
  };
}
