import { useCallback, useEffect, useMemo, useState } from "react";

import { useFileUploadToast } from "@/components/file/FileUploadToast";
import { apiRequest } from "@/lib/api/httpClient";
import { listKernelEnvs, type KernelEnvItem } from "@/lib/api/kernelEnvs";
import {
  createImportFolderStream,
  createTaskWorkspace,
  getWorkspaceRuntimeEnvironments,
  registerWorkspacePythonEnvironment,
} from "@/lib/api/workspaces";
import type { ExecutionResourceSelection } from "@/components/NewWorkspaceDialog";
import type { NewTaskStage, WorkspaceRuntimeEnvironment } from "@/types/workspace";
import { buildNewTaskLifecycleState } from "@/utils/newTaskLifecycleState";

import type {
  ActiveEnvironmentInfo,
  UseWorkspaceRuntimeControlsProps,
  UseWorkspaceRuntimeControlsReturn,
} from "./workspaceRuntimeControlsTypes";
import { emitWorkspaceListRefreshEvent } from "./workspaceListRefreshEvent";

export function useWorkspaceRuntimeControls({
  userId,
  workspace,
  sessionId,
  prepareNewSession,
  activatePreparedSession,
  refreshWorkspaceForSession,
  refreshSessionStatus,
}: UseWorkspaceRuntimeControlsProps): UseWorkspaceRuntimeControlsReturn {
  const { toasts, showSuccess, showError } = useFileUploadToast();
  const [showNewWorkspaceDialog, setShowNewWorkspaceDialog] = useState(false);
  const [showRestartRuntimeConfirmDialog, setShowRestartRuntimeConfirmDialog] =
    useState(false);
  const [newWorkspaceStage, setNewWorkspaceStage] =
    useState<NewTaskStage>("idle");
  const [newWorkspaceError, setNewWorkspaceError] = useState<string | null>(
    null,
  );
  const [importProgress, setImportProgress] = useState<number>(0);
  const [isRestartingRuntime, setIsRestartingRuntime] = useState(false);
  const [boundWorkspaceEnv, setBoundWorkspaceEnv] =
    useState<WorkspaceRuntimeEnvironment | null>(null);
  const [registeredPythonEnvs, setRegisteredPythonEnvs] = useState<KernelEnvItem[]>([]);
  const [isLoadingRegisteredPythonEnvs, setIsLoadingRegisteredPythonEnvs] =
    useState(false);
  const workspaceId = workspace?.workspace_id ?? null;
  const boundEnvId = workspace?.runtime_binding?.env_id ?? null;
  const sandboxMode = workspace?.runtime_binding?.sandbox_mode ?? null;

  useEffect(() => {
    if (!workspaceId || !boundEnvId || sandboxMode === "docker") {
      setBoundWorkspaceEnv(null);
      return;
    }

    let cancelled = false;
    void getWorkspaceRuntimeEnvironments(workspaceId, { inspect: true })
      .then((registry) => {
        if (cancelled) {
          return;
        }
        setBoundWorkspaceEnv(
          registry.envs.find((env) => env.env_id === boundEnvId) ?? null,
        );
      })
      .catch(() => {
        if (!cancelled) {
          setBoundWorkspaceEnv(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [boundEnvId, sandboxMode, workspaceId]);

  const activeEnv: ActiveEnvironmentInfo | null = useMemo(
    () => {
      if (sandboxMode === "docker" && boundEnvId) {
        return {
          id: boundEnvId,
          name: boundEnvId,
          image: "docker",
          sandbox_mode: "docker",
          is_default: false,
        };
      }

      if (boundWorkspaceEnv) {
        return {
          id: boundWorkspaceEnv.env_id,
          name: boundWorkspaceEnv.display_name || boundWorkspaceEnv.env_id,
          image: "uv",
          sandbox_mode: "local",
          is_default: false,
        };
      }

      if (boundEnvId) {
        return {
          id: boundEnvId,
          name: `${boundEnvId} (未找到)`,
          image: "uv",
          sandbox_mode: "local",
          is_default: false,
        };
      }

      return {
        id: "none",
        name: "无 Python 环境",
        image: "none",
        is_default: false,
      };
    },
    [boundEnvId, boundWorkspaceEnv, sandboxMode],
  );

  const isCreatingWorkspace =
    newWorkspaceStage !== "idle" && newWorkspaceStage !== "error";
  const isInitializingEnvironment = isCreatingWorkspace;
  const newWorkspaceLifecycleState = useMemo(
    () => buildNewTaskLifecycleState(newWorkspaceStage, newWorkspaceError, importProgress),
    [newWorkspaceError, newWorkspaceStage, importProgress],
  );

  const closeNewWorkspaceDialog = useCallback(() => {
    if (isCreatingWorkspace) {
      return;
    }
    setShowNewWorkspaceDialog(false);
    setNewWorkspaceStage("idle");
    setNewWorkspaceError(null);
    setImportProgress(0);
  }, [isCreatingWorkspace]);

  const openNewWorkspaceDialog = useCallback(() => {
    setNewWorkspaceError(null);
    setNewWorkspaceStage("idle");
    setImportProgress(0);
    setShowNewWorkspaceDialog(true);
  }, []);

  useEffect(() => {
    if (!showNewWorkspaceDialog) {
      return;
    }
    let cancelled = false;
    setIsLoadingRegisteredPythonEnvs(true);
    void listKernelEnvs()
      .then((data) => {
        if (!cancelled) {
          setRegisteredPythonEnvs(data.kernels ?? []);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRegisteredPythonEnvs([]);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingRegisteredPythonEnvs(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [showNewWorkspaceDialog]);

  const handleConfirmNewWorkspace = useCallback(
    async (
      title: string,
      description: string | undefined,
      resources: ExecutionResourceSelection,
      options: {
        templateId?: string;
        initialConversationTitle?: string;
        installCapabilities?: string[];
        templateFiles?: string[];
        sourceFolderPath?: string;
        tempUploadId?: string;
        importFiles?: string[];
      } = {},
    ) => {
      const {
        templateId,
        initialConversationTitle,
        installCapabilities,
        templateFiles,
        sourceFolderPath,
        tempUploadId,
        importFiles,
      } = options;

      try {
        const normalizedTitle = title.trim();
        if (!normalizedTitle) {
          throw new Error("任务名称不能为空");
        }

        setNewWorkspaceError(null);
        setImportProgress(0);
        setNewWorkspaceStage("preparing_session");
        const preparedSessionId = await prepareNewSession();

        const runtimeBinding = resources.dockerEnabled
          ? {
              sandbox_mode: "docker",
              env_id: null,
              resources: {
                python_env_id: null,
                node_env_id: null,
                docker_resource_id: "docker-default",
              },
            }
          : {
              sandbox_mode:
                resources.pythonEnabled || resources.nodeEnabled ? "local" : null,
              env_id: resources.pythonEnabled ? "workspace-default" : null,
              resources: {
                python_env_id: resources.pythonEnabled ? "workspace-default" : null,
                node_env_id: resources.nodeEnabled ? "node-default" : null,
                docker_resource_id: null,
              },
            };

        if (sourceFolderPath || tempUploadId) {
          // 文件夹导入：通过 SSE 流式创建
          const abortController = new AbortController();
          setNewWorkspaceStage("scanning_folder");

          await createImportFolderStream(
            {
              title: normalizedTitle,
              description,
              workspaceKind: "task",
              initialConversationId: preparedSessionId,
              initialConversationTitle: initialConversationTitle || "新对话",
              runtimeBinding,
              templateId,
              installCapabilities,
              templateFiles,
              sourceFolderPath,
              tempUploadId,
              importFiles,
            },
            {
              onEvent: (event) => {
                setImportProgress(event.progress);
                if (event.stage === "copying") {
                  setNewWorkspaceStage("copying_files");
                } else if (event.stage === "creating_workspace") {
                  setNewWorkspaceStage("import_creating_workspace");
                } else if (event.stage === "scanning") {
                  setNewWorkspaceStage("scanning_folder");
                }
              },
              onComplete: async (workspaceId, warnings) => {
                try {
                  if (
                    resources.pythonEnabled &&
                    resources.pythonSource.kind === "registered"
                  ) {
                    setNewWorkspaceStage("binding_environment");
                    await registerWorkspacePythonEnvironment(workspaceId, {
                      envId: `python-${resources.pythonSource.kernelName}`,
                      displayName: `Python (${resources.pythonSource.kernelName})`,
                      pythonExecutable: resources.pythonSource.pythonExecutable,
                      sourceKernelName: resources.pythonSource.kernelName,
                      activate: true,
                    });
                  }
                  emitWorkspaceListRefreshEvent();
                  await activatePreparedSession(preparedSessionId);
                  await refreshWorkspaceForSession(preparedSessionId, { force: true });
                  refreshSessionStatus();
                  setShowNewWorkspaceDialog(false);
                  setNewWorkspaceStage("idle");
                  setImportProgress(0);
                  showSuccess(
                    resources.dockerEnabled
                      ? "已创建新工作区并启用 Docker 沙盒"
                      : resources.pythonEnabled && resources.nodeEnabled
                        ? "已创建新工作区并启用 Python + Node.js"
                        : resources.pythonEnabled
                          ? "已创建新工作区并启用 Python"
                          : resources.nodeEnabled
                            ? "已创建新工作区并启用 Node.js"
                            : "已创建新工作区",
                  );
                  if (warnings && warnings.length > 0) {
                    for (const warning of warnings) {
                      showError(warning, 6000);
                    }
                  }
                } catch (completeError) {
                  const message = completeError instanceof Error ? completeError.message : "导入后初始化失败";
                  setNewWorkspaceError(message);
                  setNewWorkspaceStage("error");
                  showError(message);
                }
              },
              onError: (message) => {
                abortController.abort();
                setNewWorkspaceError(message);
                setNewWorkspaceStage("error");
                showError(message);
              },
            },
            abortController.signal,
          );
          return;
        }

        setNewWorkspaceStage("creating_workspace");
        const createdWorkspace = await createTaskWorkspace({
          title: normalizedTitle,
          description,
          workspaceKind: "task",
          initialConversationId: preparedSessionId,
          initialConversationTitle: initialConversationTitle || "新对话",
          runtimeBinding,
          templateId,
          installCapabilities,
          templateFiles,
        });
        if (
          resources.pythonEnabled &&
          resources.pythonSource.kind === "registered"
        ) {
          setNewWorkspaceStage("binding_environment");
          await registerWorkspacePythonEnvironment(createdWorkspace.workspace_id, {
            envId: `python-${resources.pythonSource.kernelName}`,
            displayName: `Python (${resources.pythonSource.kernelName})`,
            pythonExecutable: resources.pythonSource.pythonExecutable,
            sourceKernelName: resources.pythonSource.kernelName,
            activate: true,
          });
        }
        emitWorkspaceListRefreshEvent();

        await activatePreparedSession(preparedSessionId);
        await refreshWorkspaceForSession(preparedSessionId, { force: true });
        refreshSessionStatus();
        setShowNewWorkspaceDialog(false);
        setNewWorkspaceStage("idle");
        setImportProgress(0);
        showSuccess(
          resources.dockerEnabled
            ? "已创建新工作区并启用 Docker 沙盒"
            : resources.pythonEnabled && resources.nodeEnabled
              ? "已创建新工作区并启用 Python + Node.js"
              : resources.pythonEnabled
                ? "已创建新工作区并启用 Python"
                : resources.nodeEnabled
                  ? "已创建新工作区并启用 Node.js"
                  : "已创建新工作区",
        );
        // 提示模板能力安装失败
        if (createdWorkspace.warnings && createdWorkspace.warnings.length > 0) {
          for (const warning of createdWorkspace.warnings) {
            showError(warning, 6000);
          }
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : "新建工作区失败";
        setNewWorkspaceError(message);
        setNewWorkspaceStage("error");
        showError(message);
      }
    },
    [
      activatePreparedSession,
      prepareNewSession,
      refreshSessionStatus,
      refreshWorkspaceForSession,
      showError,
      showSuccess,
    ],
  );

  const openRestartRuntimeConfirmDialog = useCallback(() => {
    if (!sessionId) {
      showError("当前没有可重建的任务会话。");
      return;
    }
    setShowRestartRuntimeConfirmDialog(true);
  }, [sessionId, showError]);

  const closeRestartRuntimeConfirmDialog = useCallback(() => {
    if (!isRestartingRuntime) {
      setShowRestartRuntimeConfirmDialog(false);
    }
  }, [isRestartingRuntime]);

  const handleRestartRuntime = useCallback(async () => {
    if (!sessionId) {
      showError("当前没有可重建的任务会话。");
      return;
    }

    try {
      setIsRestartingRuntime(true);
      await apiRequest(`/api/sessions/${userId}/${sessionId}/rebuild-runtime`, {
        method: "POST",
      });
      await refreshWorkspaceForSession(sessionId, { force: true });
      refreshSessionStatus();
      showSuccess("已重置当前会话的 Python 运行环境；下一次代码执行会创建新的 notebook 内核");
    } catch (error) {
      const message = error instanceof Error ? error.message : "重置 Python 运行环境失败";
      showError(message);
    } finally {
      setIsRestartingRuntime(false);
      setShowRestartRuntimeConfirmDialog(false);
    }
  }, [
    refreshSessionStatus,
    refreshWorkspaceForSession,
    sessionId,
    showError,
    showSuccess,
    userId,
  ]);

  const confirmRestartRuntime = useCallback(async () => {
    await handleRestartRuntime();
  }, [handleRestartRuntime]);

  return {
    toasts,
    showNewWorkspaceDialog,
    showRestartRuntimeConfirmDialog,
    isRestartingRuntime,
    isCreatingWorkspace,
    isInitializingEnvironment,
    newWorkspaceStage,
    newWorkspaceLifecycleState,
    newWorkspaceError,
    activeEnv,
    registeredPythonEnvs,
    isLoadingRegisteredPythonEnvs,
    closeNewWorkspaceDialog,
    openNewWorkspaceDialog,
    handleConfirmNewWorkspace,
    openRestartRuntimeConfirmDialog,
    closeRestartRuntimeConfirmDialog,
    confirmRestartRuntime,
    handleRestartRuntime,
  };
}
