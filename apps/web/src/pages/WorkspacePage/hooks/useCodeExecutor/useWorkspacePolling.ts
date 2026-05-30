import { useEffect, useRef } from "react";
import type { UploadedFile } from "@/hooks/useAgentFileUpload";
import type { WorkspaceFile } from "@/types/task";
import { refreshWorkspaceFiles } from "./workspaceFiles";

interface WorkspacePollingOptions {
  isRunning: boolean;
  reloadWorkspaceFiles: (
    workspaceId?: string,
    options?: { force?: boolean },
  ) => Promise<UploadedFile[]>;
  updateWorkspaceFilesForSession: (
    sessionId: string,
    files: WorkspaceFile[],
  ) => void;
  workspaceFiles?: WorkspaceFile[];
  sessionId?: string;
  workspaceId?: string | null;
  intervalMs?: number;
}

export function useWorkspacePolling({
  isRunning,
  reloadWorkspaceFiles,
  updateWorkspaceFilesForSession,
  workspaceFiles,
  sessionId,
  workspaceId,
  intervalMs = 5000,
}: WorkspacePollingOptions) {
  const workspaceFilesRef = useRef(workspaceFiles);

  useEffect(() => {
    workspaceFilesRef.current = workspaceFiles;
  }, [workspaceFiles]);

  useEffect(() => {
    if (!sessionId || !workspaceId || !isRunning) {
      return;
    }

    let interval: ReturnType<typeof setInterval> | null = null;
    let inFlight = false;
    let cancelled = false;

    const tick = async () => {
      if (inFlight || cancelled) {
        return;
      }

      inFlight = true;
      try {
        await refreshWorkspaceFiles(
          reloadWorkspaceFiles,
          updateWorkspaceFilesForSession,
          sessionId,
          workspaceId,
          workspaceFilesRef.current,
        );
      } finally {
        inFlight = false;
      }
    };

    // 立即执行一次，然后按间隔轮询
    void tick();
    interval = setInterval(() => {
      void tick();
    }, intervalMs);

    return () => {
      cancelled = true;
      if (interval) {
        clearInterval(interval);
      }
    };
  }, [
    intervalMs,
    isRunning,
    reloadWorkspaceFiles,
    updateWorkspaceFilesForSession,
    sessionId,
    workspaceId,
  ]);
}
