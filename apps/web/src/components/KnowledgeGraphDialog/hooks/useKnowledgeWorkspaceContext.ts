import { useCallback, useEffect, useState } from "react";
import {
  getWorkspaceDatabaseMounts,
  getTaskWorkspace,
  getWorkspaceKnowledgeBaseMounts,
  updateWorkspaceDatabaseMounts,
} from "@/lib/api/workspaces";
import type {
  WorkspaceDatabaseMountSummary,
  WorkspaceKnowledgeBaseMountSummary,
} from "@/types/workspace";

interface WorkspaceContextOptions {
  enabled?: boolean;
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

export function useWorkspaceDatabaseContext(
  workspaceId?: string | null,
  options: WorkspaceContextOptions = {},
) {
  const enabled = options.enabled ?? true;
  const [workspaceTitle, setWorkspaceTitle] = useState<string | null>(null);
  const [mounts, setMounts] =
    useState<WorkspaceDatabaseMountSummary | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const refresh = useCallback(async () => {
    if (!enabled || !workspaceId) {
      setWorkspaceTitle(null);
      setMounts(null);
      setError(null);
      setIsSaving(false);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const [workspace, databaseMounts] = await Promise.all([
        getTaskWorkspace(workspaceId),
        getWorkspaceDatabaseMounts(workspaceId),
      ]);
      setWorkspaceTitle(workspace.title || workspace.workspace_id);
      setMounts(databaseMounts);
    } catch (error) {
      setError(getErrorMessage(error, "加载工作区数据库上下文失败"));
    } finally {
      setIsLoading(false);
    }
  }, [enabled, workspaceId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const setMounted = useCallback(
    async (connectorId: string, checked: boolean) => {
      if (!workspaceId || !mounts) {
        return null;
      }

      const nextIds = checked
        ? Array.from(new Set([...mounts.connector_ids, connectorId]))
        : mounts.connector_ids.filter((id) => id !== connectorId);

      setIsSaving(true);
      setError(null);

      try {
        const nextMounts = await updateWorkspaceDatabaseMounts(
          workspaceId,
          nextIds,
        );
        setMounts(nextMounts);
        return nextMounts;
      } catch (error) {
        setError(getErrorMessage(error, "更新工作区数据库挂载失败"));
        return null;
      } finally {
        setIsSaving(false);
      }
    },
    [mounts, workspaceId],
  );

  return {
    workspaceTitle,
    mounts,
    isLoading,
    error,
    isSaving,
    refresh,
    setMounted,
  };
}

export function useWorkspaceKnowledgeBaseContext(
  workspaceId?: string | null,
  options: WorkspaceContextOptions = {},
) {
  const enabled = options.enabled ?? true;
  const [workspaceTitle, setWorkspaceTitle] = useState<string | null>(null);
  const [mounts, setMounts] =
    useState<WorkspaceKnowledgeBaseMountSummary | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!enabled || !workspaceId) {
      setWorkspaceTitle(null);
      setMounts(null);
      setError(null);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const [workspace, knowledgeBaseMounts] = await Promise.all([
        getTaskWorkspace(workspaceId),
        getWorkspaceKnowledgeBaseMounts(workspaceId),
      ]);
      setWorkspaceTitle(workspace.title || workspace.workspace_id);
      setMounts(knowledgeBaseMounts);
    } catch (error) {
      setError(getErrorMessage(error, "加载工作区知识库上下文失败"));
    } finally {
      setIsLoading(false);
    }
  }, [enabled, workspaceId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return {
    workspaceTitle,
    mounts,
    isLoading,
    error,
    refresh,
  };
}
