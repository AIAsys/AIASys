import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useFileUploadToast } from "@/components/file/FileUploadToast";
import { apiRequest } from "@/lib/api/httpClient";
import { listKernelEnvs, type KernelEnvItem } from "@/lib/api/kernelEnvs";
import {
  createImportFolderStream,
  createTaskWorkspace,
  getWorkspaceInitialization,
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
import { navigateToAnalysisSession } from "./useCodeExecutor/useSessionOrchestratorHelpers";

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
  const [newWorkspaceMessage, setNewWorkspaceMessage] = useState<string | undefined>(undefined);
  const [isRestartingRuntime, setIsRestartingRuntime] = useState(false);
  const [boundWorkspaceEnv, setBoundWorkspaceEnv] =
    useState<WorkspaceRuntimeEnvironment | null>(null);
  const [registeredPythonEnvs, setRegisteredPythonEnvs] = useState<KernelEnvItem[]>([]);
  const [isLoadingRegisteredPythonEnvs, setIsLoadingRegisteredPythonEnvs] =
    useState(false);
  const workspaceInitAbortControllerRef = useRef<AbortController | null>(null);
  const workspaceId = workspace?.workspace_id ?? null;
  const resources = workspace?.runtime_binding?.resources ?? null;
  const boundEnvId = resources?.python_env_id ?? null;
  const dockerResourceId = resources?.docker_resource_id ?? null;
  const isDockerMode = Boolean(dockerResourceId);

  useEffect(() => {
    if (!workspaceId || !boundEnvId || isDockerMode) {
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
  }, [boundEnvId, isDockerMode, workspaceId]);

  const activeEnv: ActiveEnvironmentInfo | null = useMemo(
    () => {
      if (isDockerMode && dockerResourceId) {
        return {
          id: dockerResourceId,
          name: dockerResourceId,
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
    [boundEnvId, boundWorkspaceEnv, dockerResourceId, isDockerMode],
  );

  const isCreatingWorkspace =
    newWorkspaceStage !== "idle" && newWorkspaceStage !== "error";
  const isInitializingEnvironment = isCreatingWorkspace;
  const newWorkspaceLifecycleState = useMemo(
    () => buildNewTaskLifecycleState(newWorkspaceStage, newWorkspaceError, importProgress, newWorkspaceMessage),
    [newWorkspaceError, newWorkspaceStage, importProgress, newWorkspaceMessage],
  );

  const closeNewWorkspaceDialog = useCallback(() => {
    if (isCreatingWorkspace) {
      return;
    }
    setShowNewWorkspaceDialog(false);
    setNewWorkspaceStage("idle");
    setNewWorkspaceError(null);
    setImportProgress(0);
    setNewWorkspaceMessage(undefined);
  }, [isCreatingWorkspace]);

  const openNewWorkspaceDialog = useCallback(() => {
    setNewWorkspaceError(null);
    setNewWorkspaceStage("idle");
    setImportProgress(0);
    setNewWorkspaceMessage(undefined);
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

  // 组件卸载或对话框关闭时，取消正在进行的创建/轮询流程
  useEffect(() => {
    return () => {
      workspaceInitAbortControllerRef.current?.abort();
      workspaceInitAbortControllerRef.current = null;
    };
  }, []);

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

      // 整个创建流程共享一个 AbortController，组件卸载或用户关闭对话框时可取消
      const abortController = new AbortController();
      workspaceInitAbortControllerRef.current = abortController;
      const sleepWithAbort = (ms: number) =>
        new Promise<void>((resolve, reject) => {
          const timer = window.setTimeout(resolve, ms);
          abortController.signal.addEventListener(
            "abort",
            () => {
              window.clearTimeout(timer);
              reject(new DOMException("新建工作区流程已取消", "AbortError"));
            },
            { once: true },
          );
        });

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
              resources: {
                python_env_id: null,
                node_env_id: null,
                docker_resource_id: "docker-default",
              },
            }
          : {
              resources: {
                python_env_id: resources.pythonEnabled ? "workspace-default" : null,
                node_env_id: resources.nodeEnabled ? "node-default" : null,
                docker_resource_id: null,
              },
            };

        if (sourceFolderPath || tempUploadId) {
          // 文件夹导入：通过 SSE 流式创建
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
                if (abortController.signal.aborted) {
                  return;
                }
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
                if (abortController.signal.aborted) {
                  return;
                }
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
                  console.log("[NewWorkspace] folder import completed", { workspaceId, preparedSessionId });
                  emitWorkspaceListRefreshEvent();
                  navigateToAnalysisSession(preparedSessionId, {
                    workspaceId,
                  });
                  await activatePreparedSession(preparedSessionId);
                  await refreshWorkspaceForSession(preparedSessionId, { force: true });
                  refreshSessionStatus();
                  setShowNewWorkspaceDialog(false);
                  setNewWorkspaceStage("idle");
                  setImportProgress(0);
                  setNewWorkspaceMessage(undefined);
                  workspaceInitAbortControllerRef.current = null;
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
        console.log("[NewWorkspace] creating workspace", { preparedSessionId });
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
        console.log("[NewWorkspace] workspace created", {
          workspaceId: createdWorkspace.workspace_id,
          preparedSessionId,
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

        const needsRuntimeInit =
          !resources.dockerEnabled &&
          resources.pythonSource?.kind !== "registered" &&
          (resources.pythonEnabled || resources.nodeEnabled);
        if (needsRuntimeInit) {
          setNewWorkspaceStage("waiting_runtime");
          let status = await getWorkspaceInitialization(
            createdWorkspace.workspace_id,
          );
          if (abortController.signal.aborted) {
            return;
          }
          setImportProgress(status.progress);
          setNewWorkspaceMessage(status.message);
          console.log("[NewWorkspace] runtime init status", status);
          // 最多轮询 5 分钟，防止后端状态丢失时前端无限等待
          let pollCount = 0;
          const MAX_POLL_COUNT = 375; // 375 * 800ms = 300s
          while (status.status === "pending" || status.status === "running") {
            if (pollCount >= MAX_POLL_COUNT) {
              throw new Error("运行环境初始化超时，请检查后端日志或稍后重试");
            }
            pollCount += 1;
            await sleepWithAbort(800);
            if (abortController.signal.aborted) {
              return;
            }
            status = await getWorkspaceInitialization(
              createdWorkspace.workspace_id,
            );
            setImportProgress(status.progress);
            setNewWorkspaceMessage(status.message);
            console.log("[NewWorkspace] runtime init status", status);
          }
          if (status.status === "failed") {
            throw new Error(
              status.error || status.message || "运行环境初始化失败",
            );
          }
          console.log("[NewWorkspace] runtime init completed");
        }

        emitWorkspaceListRefreshEvent();
        // 先同步路由上的 workspace_id，否则 activatePreparedSession 内部导航时无法取到新工作区
        navigateToAnalysisSession(preparedSessionId, {
          workspaceId: createdWorkspace.workspace_id,
        });
        console.log("[NewWorkspace] activating session", { preparedSessionId });

        await activatePreparedSession(preparedSessionId);
        console.log("[NewWorkspace] refreshing workspace files", { preparedSessionId });
        await refreshWorkspaceForSession(preparedSessionId, { force: true });
        refreshSessionStatus();
        console.log("[NewWorkspace] closing dialog");
        setShowNewWorkspaceDialog(false);
        setNewWorkspaceStage("idle");
        setImportProgress(0);
        setNewWorkspaceMessage(undefined);
        workspaceInitAbortControllerRef.current = null;
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
        if ((error as Error).name === "AbortError") {
          // 用户取消或组件卸载，静默处理
          console.log("[NewWorkspace] aborted");
          return;
        }
        const rawMessage = error instanceof Error ? error.message : "新建工作区失败";
        const isNodeError =
          /fnm|node\.js|nodejs|node/i.test(rawMessage) &&
          (/不可用|未找到|失败|install|failed|not found|cannot find/i.test(rawMessage) ||
            rawMessage.includes("Node.js"));
        const message = isNodeError
          ? `Node.js 运行环境初始化失败：${rawMessage}。如需使用 Node.js，请先安装 fnm（https://fnm.vercel.app/）；若暂时不需要，可取消勾选“Node.js 环境”后重试。`
          : rawMessage;
        console.error("[NewWorkspace] failed", error);
        setNewWorkspaceError(message);
        setNewWorkspaceStage("error");
        showError(message, 8000);
      } finally {
        if (workspaceInitAbortControllerRef.current === abortController) {
          workspaceInitAbortControllerRef.current = null;
        }
      }
    },
    [
      activatePreparedSession,
      prepareNewSession,
      refreshSessionStatus,
      refreshWorkspaceForSession,
      showError,
      showSuccess,
      navigateToAnalysisSession,
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
