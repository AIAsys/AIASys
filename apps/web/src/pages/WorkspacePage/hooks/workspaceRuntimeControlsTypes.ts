import type {
  NewTaskLifecycleState,
  NewTaskStage,
} from "@/types/workspace";
import type { KernelEnvItem } from "@/lib/api/kernelEnvs";
import type { TaskWorkspaceSummary } from "../types";
import type { ExecutionResourceSelection } from "@/components/NewWorkspaceDialog";
import type { WorkspaceRefreshOptions } from "./useCodeExecutor/executorTypes";

export interface ActiveEnvironmentInfo {
  id: string;
  name: string;
  image: string;
  sandbox_mode?: "local" | "docker";
  is_default: boolean;
}

export interface UseWorkspaceRuntimeControlsProps {
  userId: string;
  workspace?: TaskWorkspaceSummary | null;
  sessionId?: string;
  prepareNewSession: () => Promise<string>;
  activatePreparedSession: (sessionId: string) => Promise<string>;
  refreshWorkspaceForSession: (
    sessionId: string,
    options?: WorkspaceRefreshOptions,
  ) => Promise<void>;
  refreshSessionStatus: () => void;
}

export interface UseWorkspaceRuntimeControlsReturn {
  toasts: Array<{ id: string; message: string; type: "success" | "error" }>;
  /** 页面级提示（经 ToastContainer 渲染），供各生命周期动作复用 */
  showError: (message: string, duration?: number) => void;
  showSuccess: (message: string, duration?: number) => void;
  showNewWorkspaceDialog: boolean;
  showRestartRuntimeConfirmDialog: boolean;
  isRestartingRuntime: boolean;
  isCreatingWorkspace: boolean;
  isInitializingEnvironment: boolean;
  newWorkspaceStage: NewTaskStage;
  newWorkspaceLifecycleState: NewTaskLifecycleState;
  newWorkspaceError: string | null;
  activeEnv: ActiveEnvironmentInfo | null;
  registeredPythonEnvs: KernelEnvItem[];
  isLoadingRegisteredPythonEnvs: boolean;
  closeNewWorkspaceDialog: () => void;
  openNewWorkspaceDialog: () => void;
  handleConfirmNewWorkspace: (
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
    },
  ) => Promise<void>;
  handleRestartRuntime: () => Promise<void>;
  openRestartRuntimeConfirmDialog: () => void;
  closeRestartRuntimeConfirmDialog: () => void;
  confirmRestartRuntime: () => Promise<void>;
}
