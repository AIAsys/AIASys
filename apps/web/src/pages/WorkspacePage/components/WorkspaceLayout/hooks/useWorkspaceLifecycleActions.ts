import { useCallback, useState } from "react";
import {
  createWorkspaceConversation,
  deleteWorkspace,
  deleteAllWorkspaces,
  getTaskWorkspace,
} from "@/lib/api/workspaces";
import { createAndActivateWorkspaceConversation } from "../../../hooks/workspaceConversationTransition";
import { useFileUploadToast } from "@/components/file/FileUploadToast";
import type { TaskWorkspaceSummary } from "../../../types";
import type {
  WorkspaceLayoutProps,
  RuntimeControlsState,
} from "../types";

function navigateToHome() {
  const withAppNavigate = window as Window & {
    appNavigate?: (path: string, options?: { replace?: boolean }) => void;
  };
  if (withAppNavigate.appNavigate) {
    withAppNavigate.appNavigate("/", { replace: true });
  } else {
    window.location.replace("/");
  }
}

function getPreferredWorkspaceSessionId(
  workspace: TaskWorkspaceSummary | undefined,
): string | null {
  if (!workspace) {
    return null;
  }

  return (
    workspace.current_conversation?.session_id ||
    workspace.conversations?.[0]?.session_id ||
    null
  );
}

function findWorkspaceForSession(
  workspaces: TaskWorkspaceSummary[],
  sessionId: string,
): TaskWorkspaceSummary | undefined {
  return workspaces.find(
    (workspace) =>
      workspace.current_conversation?.session_id === sessionId ||
      Boolean(
        workspace.conversations?.some(
          (conversation) => conversation.session_id === sessionId,
        ),
      ),
  );
}

interface WorkspacePendingDeletion {
  workspaceId: string;
  title: string;
}

interface UseWorkspaceLifecycleActionsParams {
  apiBaseUrl: string;
  currentWorkspace?: TaskWorkspaceSummary;
  currentWorkspaceId?: string;
  executor: WorkspaceLayoutProps["executor"];
  leaveProjectWorkspace: () => void;
  loadWorkspaces: WorkspaceLayoutProps["loadWorkspaces"];
  navigateToWorkspaceConversation: (
    workspaceId: string,
    sessionId: string,
  ) => void;
  onDeleteSession: WorkspaceLayoutProps["onDeleteSession"];
  runtimeControls: RuntimeControlsState;
  workspaces: TaskWorkspaceSummary[];
}

interface UseWorkspaceLifecycleActionsReturn {
  deleteWorkspaceError: string | null;
  handleDeleteAllWorkspaces: () => void;
  handleDeleteConversation: (sessionId: string) => Promise<void>;
  handleDeleteSelectedWorkspaces: (ids: string[]) => void;
  handleDeleteWorkspace: (workspaceId: string) => void;
  handleForkConversation: (sourceConversationId: string) => void;
  handleNewSession: () => void;
  handleNewTask: () => void;
  handleRenameConversation: (sessionId: string, title: string) => Promise<void>;
  handleSessionSelect: (sessionId: string) => void;
  handleBulkDeleteDialogOpenChange: (open: boolean) => void;
  handleWorkspaceDeleteDialogOpenChange: (open: boolean) => void;
  handleWorkspaceSelect: (workspaceId: string) => void;
  bulkDeletePendingIds: string[] | null;
  isDeletingWorkspace: boolean;
  workspacePendingDeletion: WorkspacePendingDeletion | null;
  confirmDeleteAllWorkspaces: () => void;
  confirmDeleteWorkspace: () => void;
}

export function useWorkspaceLifecycleActions({
  apiBaseUrl,
  currentWorkspace,
  currentWorkspaceId,
  executor,
  leaveProjectWorkspace,
  loadWorkspaces,
  navigateToWorkspaceConversation,
  onDeleteSession,
  runtimeControls,
  workspaces,
}: UseWorkspaceLifecycleActionsParams): UseWorkspaceLifecycleActionsReturn {
  const { showError } = useFileUploadToast();
  const [workspacePendingDeletion, setWorkspacePendingDeletion] =
    useState<WorkspacePendingDeletion | null>(null);
  const [deleteWorkspaceError, setDeleteWorkspaceError] = useState<
    string | null
  >(null);
  const [isDeletingWorkspace, setIsDeletingWorkspace] = useState(false);
  const [bulkDeletePendingIds, setBulkDeletePendingIds] = useState<string[] | null>(null);

  const handleSessionSelect = useCallback(
    (sessionId: string) => {
      leaveProjectWorkspace();
      const targetWorkspace = findWorkspaceForSession(workspaces, sessionId);
      if (targetWorkspace?.workspace_id) {
        navigateToWorkspaceConversation(
          targetWorkspace.workspace_id,
          sessionId,
        );
        return;
      }
      void executor.handleSelectSession(sessionId);
    },
    [
      executor,
      leaveProjectWorkspace,
      navigateToWorkspaceConversation,
      workspaces,
    ],
  );

  const handleNewTask = useCallback(() => {
    runtimeControls.openNewWorkspaceDialog();
  }, [runtimeControls]);

  const handleNewSession = useCallback(() => {
    leaveProjectWorkspace();
    if (!currentWorkspaceId) {
      runtimeControls.openNewWorkspaceDialog();
      return;
    }

    void (async () => {
      try {
        await createAndActivateWorkspaceConversation({
          workspaceId: currentWorkspaceId,
          title: "新会话",
          loadWorkspaces,
          activatePreparedSession: executor.activatePreparedSession,
        });
      } catch (error) {
        console.error("Failed to create workspace conversation:", error);
      }
    })();
  }, [
    currentWorkspaceId,
    executor,
    leaveProjectWorkspace,
    loadWorkspaces,
    runtimeControls,
  ]);

  const handleWorkspaceSelect = useCallback(
    (workspaceId: string) => {
      const targetWorkspace = workspaces.find(
        (workspace) => workspace.workspace_id === workspaceId,
      );
      const targetSessionId = getPreferredWorkspaceSessionId(targetWorkspace);
      if (!targetSessionId) {
        return;
      }

      if (
        workspaceId === currentWorkspaceId &&
        targetWorkspace?.current_conversation?.session_id === executor.sessionId
      ) {
        return;
      }

      leaveProjectWorkspace();
      navigateToWorkspaceConversation(workspaceId, targetSessionId);
    },
    [
      currentWorkspaceId,
      executor.sessionId,
      leaveProjectWorkspace,
      navigateToWorkspaceConversation,
      workspaces,
    ],
  );

  const handleDeleteWorkspace = useCallback(
    (workspaceId: string) => {
      const targetWorkspace = workspaces.find(
        (workspace) => workspace.workspace_id === workspaceId,
      );
      if (!targetWorkspace) {
        return;
      }

      setDeleteWorkspaceError(null);
      setWorkspacePendingDeletion({
        workspaceId,
        title: targetWorkspace.title || "未命名工作区",
      });
    },
    [workspaces],
  );

  const handleWorkspaceDeleteDialogOpenChange = useCallback(
    (open: boolean) => {
      if (open || isDeletingWorkspace) {
        return;
      }

      setWorkspacePendingDeletion(null);
      setDeleteWorkspaceError(null);
    },
    [isDeletingWorkspace],
  );

  const handleDeleteAllWorkspaces = useCallback(() => {
    setDeleteWorkspaceError(null);
    setBulkDeletePendingIds(workspaces.map((w) => w.workspace_id));
  }, [workspaces]);

  const handleDeleteSelectedWorkspaces = useCallback((ids: string[]) => {
    setDeleteWorkspaceError(null);
    setBulkDeletePendingIds(ids);
  }, []);

  const handleBulkDeleteDialogOpenChange = useCallback(
    (open: boolean) => {
      if (open || isDeletingWorkspace) {
        return;
      }

      setBulkDeletePendingIds(null);
      setDeleteWorkspaceError(null);
    },
    [isDeletingWorkspace],
  );

  const confirmDeleteWorkspace = useCallback(() => {
    if (!workspacePendingDeletion) {
      return;
    }

    const { workspaceId } = workspacePendingDeletion;
    void (async () => {
      try {
        setIsDeletingWorkspace(true);
        setDeleteWorkspaceError(null);
        await deleteWorkspace(apiBaseUrl, workspaceId);
        setWorkspacePendingDeletion(null);

        // 清理被删除工作区下所有 session 的前端缓存
        const deletedWorkspace = workspaces.find(
          (w) => w.workspace_id === workspaceId,
        );
        const sessionIdsToClean: string[] = [];
        if (deletedWorkspace) {
          deletedWorkspace.conversations?.forEach((c) => {
            if (c.session_id) sessionIdsToClean.push(c.session_id);
          });
          if (deletedWorkspace.current_conversation?.session_id) {
            sessionIdsToClean.push(deletedWorkspace.current_conversation.session_id);
          }
        }
        [...new Set(sessionIdsToClean)].forEach((sid) => {
          executor.removeSessionFrontendState?.(sid);
        });

        const latestWorkspaces = (await loadWorkspaces()) as TaskWorkspaceSummary[];

        const deletedCurrentWorkspace = workspaceId === currentWorkspaceId;
        if (deletedCurrentWorkspace) {
          const remainingWorkspaces = latestWorkspaces.filter(
            (workspace) => workspace.workspace_id !== workspaceId,
          );
          const fallbackWorkspace = remainingWorkspaces[0];
          const fallbackSessionId =
            getPreferredWorkspaceSessionId(fallbackWorkspace);

          if (fallbackSessionId) {
            leaveProjectWorkspace();
            await executor.handleSelectSession(fallbackSessionId, {
              silent: true,
            });
          } else {
            navigateToHome();
          }
        }
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "删除工作区失败";
        console.error("Failed to delete workspace:", error);
        setDeleteWorkspaceError(message);
      } finally {
        setIsDeletingWorkspace(false);
      }
    })();
  }, [
    apiBaseUrl,
    currentWorkspaceId,
    executor,
    leaveProjectWorkspace,
    loadWorkspaces,
    workspacePendingDeletion,
    workspaces,
  ]);

  const confirmDeleteAllWorkspaces = useCallback(() => {
    const ids = bulkDeletePendingIds;
    if (!ids || ids.length === 0) {
      return;
    }

    void (async () => {
      try {
        setIsDeletingWorkspace(true);
        setDeleteWorkspaceError(null);
        const result = await deleteAllWorkspaces(apiBaseUrl, ids);
        setBulkDeletePendingIds(null);

        // 清理被删除工作区下所有 session 的前端缓存
        const allSessionIds: string[] = [];
        ids.forEach((wid) => {
          const w = workspaces.find((ws) => ws.workspace_id === wid);
          if (w) {
            w.conversations?.forEach((c) => {
              if (c.session_id) allSessionIds.push(c.session_id);
            });
            if (w.current_conversation?.session_id) {
              allSessionIds.push(w.current_conversation.session_id);
            }
          }
        });
        [...new Set(allSessionIds)].forEach((sid) => {
          executor.removeSessionFrontendState?.(sid);
        });

        await loadWorkspaces();

        if (result.failed > 0) {
          const summary = result.errors.slice(0, 3).join("；");
          setDeleteWorkspaceError(
            `已删除 ${result.deleted} 个工作区，${result.failed} 个失败${summary ? `：${summary}` : ""}`,
          );
          return;
        }

        navigateToHome();
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "批量删除工作区失败";
        console.error("Failed to delete workspaces:", error);
        setDeleteWorkspaceError(message);
      } finally {
        setIsDeletingWorkspace(false);
      }
    })();
  }, [apiBaseUrl, bulkDeletePendingIds, executor, loadWorkspaces, workspaces]);

  const handleForkConversation = useCallback(
    (sourceConversationId: string) => {
      if (!currentWorkspaceId) {
        return;
      }

      void (async () => {
        try {
          await createAndActivateWorkspaceConversation({
            workspaceId: currentWorkspaceId,
            title: "Fork 会话",
            branchedFromConversationId: sourceConversationId,
            loadWorkspaces,
            activatePreparedSession: executor.activatePreparedSession,
          });
        } catch (error) {
          console.error("Failed to fork workspace conversation:", error);
          showError("Fork 会话失败，请重试");
        }
      })();
    },
    [currentWorkspaceId, executor, loadWorkspaces],
  );

  const handleRenameConversation = useCallback(
    async (sessionId: string, title: string) => {
      await executor.updateSessionTitle(sessionId, title);
      await loadWorkspaces();
    },
    [executor, loadWorkspaces],
  );

  const handleDeleteConversation = useCallback(
    async (sessionId: string) => {
      const isDeletingActiveSession = sessionId === executor.sessionId;
      const workspaceIdBeforeDelete = isDeletingActiveSession
        ? currentWorkspaceId || null
        : null;

      await onDeleteSession(
        sessionId,
        isDeletingActiveSession ? { suppressActiveFallback: true } : undefined,
      );
      const latestWorkspaces = (await loadWorkspaces()) as TaskWorkspaceSummary[];

      if (isDeletingActiveSession && workspaceIdBeforeDelete) {
        try {
          const workspaceDetail = await getTaskWorkspace(
            workspaceIdBeforeDelete,
          );
          const replacementConversation =
            workspaceDetail.conversations?.find(
              (conversation) => conversation.session_id !== sessionId,
            ) ||
            workspaceDetail.current_conversation ||
            null;

          if (replacementConversation?.session_id) {
            navigateToWorkspaceConversation(
              workspaceIdBeforeDelete,
              replacementConversation.session_id,
            );
            return;
          }

          const createdConversation = await createWorkspaceConversation(
            workspaceIdBeforeDelete,
            {
              title: "新会话",
            },
          );
          // activatePreparedSession 内部已从当前 URL 读取 workspace_id 并正确导航，
          // 外层不再重复调用 navigateToWorkspaceConversation，消除双重导航。
          await executor.activatePreparedSession(createdConversation.session_id);
          return;
        } catch (error) {
          console.error(
            "Failed to restore workspace context after deleting active conversation:",
            error,
          );
        }
      }

      if (isDeletingActiveSession && !workspaceIdBeforeDelete) {
        const fallbackSessionId =
          currentWorkspace?.conversations?.find(
            (conversation) => conversation.session_id !== sessionId,
          )?.session_id ||
          latestWorkspaces
            .filter(
              (workspace) => workspace.workspace_id !== currentWorkspaceId,
            )
            .map((workspace) => getPreferredWorkspaceSessionId(workspace))
            .find(Boolean);

        if (fallbackSessionId) {
          leaveProjectWorkspace();
          const targetWorkspace = findWorkspaceForSession(
            latestWorkspaces,
            fallbackSessionId,
          );
          if (targetWorkspace?.workspace_id) {
            navigateToWorkspaceConversation(
              targetWorkspace.workspace_id,
              fallbackSessionId,
            );
          } else {
            await executor.handleSelectSession(fallbackSessionId);
          }
        } else {
          // 没有任何可回退会话时，创建新草稿并导航
          await executor.handleNewSession();
        }
      }
    },
    [
      currentWorkspace,
      currentWorkspaceId,
      executor,
      leaveProjectWorkspace,
      loadWorkspaces,
      navigateToWorkspaceConversation,
      onDeleteSession,
    ],
  );

  return {
    deleteWorkspaceError,
    handleDeleteAllWorkspaces,
    handleDeleteConversation,
    handleDeleteSelectedWorkspaces,
    handleDeleteWorkspace,
    handleForkConversation,
    handleNewSession,
    handleNewTask,
    handleRenameConversation,
    handleSessionSelect,
    handleBulkDeleteDialogOpenChange,
    handleWorkspaceDeleteDialogOpenChange,
    handleWorkspaceSelect,
    bulkDeletePendingIds,
    isDeletingWorkspace,
    workspacePendingDeletion,
    confirmDeleteAllWorkspaces,
    confirmDeleteWorkspace,
  };
}
