import { useEffect, useState, lazy, Suspense } from "react";
// 本地组件
const DataAnalysisDialogLayer = lazy(() =>
  import("./components/DataAnalysisDialogLayer").then((module) => ({
    default: module.DataAnalysisDialogLayer,
  })),
);
import { AnalysisWorkspaceLayout } from "./components/AnalysisWorkspaceLayout";

// 本地 Hooks
import { getCurrentUserId } from "@/config/api";
import { getAuthMode } from "@/config/auth";
import { useAuthState } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useDataAnalysisPageController } from "./hooks/useDataAnalysisPageController";
import type { AnalysisDialogOverlay } from "./hooks/useDataAnalysisOverlayState";
import { Home, RefreshCw, TriangleAlert } from "lucide-react";

interface DataAnalysisPageContentProps {
  userId: string;
  initialSessionId?: string | null;
}

function getOverlayFromRoute(): AnalysisDialogOverlay {
  if (typeof window === "undefined") {
    return null;
  }

  const normalizedPath =
    window.location.pathname.replace(/\/+$/, "") || "/";
  if (normalizedPath !== "/analysis") {
    return null;
  }

  const overlay = new URLSearchParams(window.location.search).get("overlay");
  if (
    overlay === "database" ||
    overlay === "knowledge_base" ||
    overlay === "knowledge_graph" ||
    overlay === "agent-config" ||
    overlay === "agent_config"
  ) {
    return overlay === "agent-config" ? "agent_config" : overlay;
  }
  return null;
}

function stripWorkspaceSettingsIntentFromRoute(): void {
  if (typeof window === "undefined") {
    return;
  }

  const normalizedPath =
    window.location.pathname.replace(/\/+$/, "") || "/";
  if (normalizedPath !== "/analysis") {
    return;
  }

  const searchParams = new URLSearchParams(window.location.search);
  const settingsScope = searchParams.get("settings");
  if (settingsScope !== "workspace") {
    return;
  }

  searchParams.delete("settings");
  searchParams.delete("tab");
  const nextSearch = searchParams.toString();
  const nextUrl = nextSearch ? `/analysis?${nextSearch}` : "/analysis";
  window.history.replaceState(window.history.state, "", nextUrl);
}

function DataAnalysisPageContent({
  userId,
  initialSessionId,
}: DataAnalysisPageContentProps) {
  const controller = useDataAnalysisPageController({
    userId,
    initialSessionId,
  });
  const [routeOverlay, setRouteOverlay] =
    useState<AnalysisDialogOverlay>(getOverlayFromRoute);

  useEffect(() => {
    const syncRouteState = () => {
      setRouteOverlay(getOverlayFromRoute());
      stripWorkspaceSettingsIntentFromRoute();
    };

    syncRouteState();
    window.addEventListener("popstate", syncRouteState);
    return () => {
      window.removeEventListener("popstate", syncRouteState);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    controller.overlayState.syncRouteOverlay(routeOverlay);
  }, [controller.overlayState.syncRouteOverlay, routeOverlay]);

  return (
    <div className="flex h-screen w-full bg-muted overflow-hidden font-sans text-muted-foreground relative">
      <AnalysisWorkspaceLayout
        apiBaseUrl={controller.apiBaseUrl}
        executor={controller.executor}
        workspaces={controller.workspaces}
        isLoadingWorkspaces={controller.isLoadingWorkspaces}
        currentWorkspaceId={controller.currentWorkspaceId}
        currentWorkspace={controller.currentWorkspace}
        loadWorkspaces={controller.loadWorkspaces}
        runtimeControls={controller.runtimeControls}
        sessionLifecycle={controller.sessionLifecycle}
        userModels={controller.userModels}
        selectedModelId={controller.selectedModelId}
        effectiveModelDisplayName={controller.effectiveModelDisplayName}
        onSelectModel={controller.setSelectedModelId}
        thinkingEnabled={controller.thinkingEnabled}
        thinkingEffort={controller.thinkingEffort}
        setThinkingEnabled={controller.setThinkingEnabled}
        setThinkingEffort={controller.setThinkingEffort}
        selectedModelSupportsThinking={controller.selectedModelSupportsThinking}
        hasMessagesForMcp={controller.hasMessagesForMcp}
        hasMCPConfig={controller.hasMCPConfig}
        onDeleteSession={controller.handleDeleteSession}
        onOpenDatabaseConnectionsDialog={() =>
          controller.overlayState.openDatabaseConnectionsDialog()
        }
        onCreateDatabaseConnectionDialog={() =>
          controller.overlayState.openDatabaseConnectionsDialog("catalog", {
            action: "create",
          })
        }
        onOpenKnowledgeBaseDialog={() =>
          controller.overlayState.openKnowledgeBaseDialog()
        }
        onOpenKnowledgeGraphDialog={() =>
          controller.overlayState.openKnowledgeGraphDialog()
        }
        onOpenLLMConfigDialog={() =>
          controller.overlayState.openLLMConfigDialog()
        }
        onOpenToolConfig={controller.overlayState.openAgentConfigDialog}
        onViewToolDetails={controller.toolPreview.handleViewToolDetails}
      />

      <Suspense fallback={null}>
        <DataAnalysisDialogLayer controller={controller} />
      </Suspense>
    </div>
  );
}

interface AuthContextFallbackProps {
  authMode: "local" | "none";
  error: string;
  cachedUserId: string;
  isRetrying: boolean;
  onRetry: () => void | Promise<void>;
}

function DataAnalysisAuthContextFallback({
  authMode,
  error,
  cachedUserId,
  isRetrying,
  onRetry,
}: AuthContextFallbackProps) {
  const rootCause = error || "本地用户上下文还没有完成初始化。";
  const looksLikeBackendUnavailable =
    rootCause.includes("无法连接本地后端") ||
    rootCause.includes("/api/auth/session 请求失败");
  const title = looksLikeBackendUnavailable
    ? "本地后端还没有连上"
    : "本地工作区用户上下文尚未就绪";
  const description =
    authMode === "local"
      ? looksLikeBackendUnavailable
        ? "前端页面已经打开，但 `/api/auth/session` 还拿不到本地默认用户。通常是本地后端未启动、刚重启，或代理尚未恢复。"
        : "页面需要先拿到本地默认用户，才能继续加载工作区、会话和运行时资源。"
      : "当前页面仍在等待认证上下文恢复。";

  return (
    <div className="flex h-screen items-center justify-center bg-muted p-6">
      <Card className="w-full max-w-xl shadow-sm">
        <CardHeader className="space-y-3">
          <div className="flex items-start gap-3">
            <div className="rounded-md border border-warning/20 bg-warning-container p-2 text-warning">
              <TriangleAlert className="h-5 w-5" />
            </div>
            <div className="space-y-1">
              <CardTitle>{title}</CardTitle>
              <CardDescription>{description}</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-md border border-border bg-background px-3 py-3 text-sm">
            <div className="font-medium text-foreground">当前状态</div>
            <div className="mt-2 space-y-1 text-muted-foreground">
              <div>认证模式：{authMode}</div>
              <div>缓存用户：{cachedUserId || "空"}</div>
              <div>错误详情：{rootCause}</div>
            </div>
          </div>

          <div className="rounded-md border border-border bg-background px-3 py-3 text-sm text-muted-foreground">
            <div className="font-medium text-foreground">建议操作</div>
            <div className="mt-2 space-y-1">
              <div>1. 先点“重新加载上下文”，不要只靠反复刷新页面。</div>
              {authMode === "local" ? (
                <div>2. 如果仍失败，请确认本地后端 `13001` 的 `/health` 和 `/api/auth/session` 已恢复。</div>
              ) : null}
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <Button onClick={() => void onRetry()} disabled={isRetrying}>
              <RefreshCw className={`h-4 w-4 ${isRetrying ? "animate-spin" : ""}`} />
              重新加载上下文
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                window.location.href = "/";
              }}
            >
              <Home className="h-4 w-4" />
              返回首页
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

interface DataAnalysisPageProps {
  initialSessionId?: string | null;
}

export default function DataAnalysisPage({
  initialSessionId,
}: DataAnalysisPageProps) {
  const {
    user,
    isLoading: isAuthLoading,
    isAuthenticated,
    error,
    refreshSession,
  } = useAuthState();
  const authMode = getAuthMode();
  const userId = user?.id || getCurrentUserId();
  const [isRetryingContext, setIsRetryingContext] = useState(false);

  const handleRetryContext = async () => {
    setIsRetryingContext(true);
    try {
      await refreshSession();
    } finally {
      setIsRetryingContext(false);
    }
  };

  if (isAuthLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-muted text-sm text-muted-foreground">
        正在校验登录状态...
      </div>
    );
  }

  if (!isAuthenticated || !userId) {
    return (
      <DataAnalysisAuthContextFallback
        authMode={authMode}
        error={error}
        cachedUserId={getCurrentUserId()}
        isRetrying={isRetryingContext}
        onRetry={handleRetryContext}
      />
    );
  }

  return (
    <DataAnalysisPageContent
      userId={userId}
      initialSessionId={initialSessionId}
    />
  );
}
