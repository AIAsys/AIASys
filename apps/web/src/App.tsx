import { Suspense, lazy, useCallback, useEffect, useState } from "react";

import { PublicRoute, ProtectedRoute } from "./components/auth/RouteGuard";
import { BackendCrashOverlay } from "./components/error/BackendCrashOverlay";
import { ErrorBoundary } from "./components/error/ErrorBoundary";
import NetworkStatusOverlay from "./components/error/NetworkStatusOverlay";
import { RouteErrorFallback } from "./components/error/RouteErrorFallback";

const HomePage = lazy(() => import("./pages/HomePage"));
const WorkspacePage = lazy(() => import("./pages/WorkspacePage"));
const TokenDashboard = lazy(() => import("./pages/TokenDashboard"));

const UserProfilePage = lazy(() => import("@/pages/UserProfilePage"));

function RouteLoading() {
  return (
    <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground">
      页面加载中...
    </div>
  );
}

/**
 * 应用程序根组件
 *
 * 当前默认按单机默认用户模式运行。
 */
function App() {
  const [locationState, setLocationState] = useState(() => ({
    pathname: globalThis.location.pathname,
    search: globalThis.location.search,
  }));
  const pathname = locationState.pathname;
  const normalizedPathname =
    pathname.endsWith("/") && pathname.length > 1
      ? pathname.slice(0, -1)
      : pathname;

  const isWorkspaceRoute =
    normalizedPathname === "/workspace" || normalizedPathname === "/analysis";
  const initialWorkspaceSessionId =
    isWorkspaceRoute
      ? new URLSearchParams(locationState.search).get("session_id")
      : null;

  // 导航函数
  const navigate = useCallback((path: string, options?: { replace?: boolean }) => {
    const nextUrl = new URL(path, globalThis.location.origin);
    if (options?.replace) {
      globalThis.history.replaceState({}, "", nextUrl);
    } else {
      globalThis.history.pushState({}, "", nextUrl);
    }
    setLocationState({
      pathname: nextUrl.pathname,
      search: nextUrl.search,
    });
  }, []);

  // 监听浏览器前进/后退
  useEffect(() => {
    const onPopState = () =>
      setLocationState({
        pathname: globalThis.location.pathname,
        search: globalThis.location.search,
      });
    globalThis.addEventListener("popstate", onPopState);

    // 暴露导航函数到全局
    const withAppNavigate = globalThis as typeof globalThis & {
      appNavigate?: (path: string, options?: { replace?: boolean }) => void;
    };
    withAppNavigate.appNavigate = navigate;

    return () => {
      globalThis.removeEventListener("popstate", onPopState);
      delete withAppNavigate.appNavigate;
    };
  }, [navigate]);

  // 将旧 /analysis 路由重定向到 /workspace
  useEffect(() => {
    if (normalizedPathname === "/analysis") {
      const nextSearch = locationState.search;
      navigate(nextSearch ? `/workspace${nextSearch}` : "/workspace", { replace: true });
      return;
    }

    const analysisSessionPrefix = "/analysis/";
    if (!normalizedPathname.startsWith(analysisSessionPrefix)) {
      return;
    }
    const sessionIdFromPath = normalizedPathname
      .slice(analysisSessionPrefix.length)
      .split("/")[0];
    const nextSearch = new URLSearchParams(locationState.search);
    if (sessionIdFromPath) {
      nextSearch.set("session_id", sessionIdFromPath);
    }
    const query = nextSearch.toString();
    navigate(query ? `/workspace?${query}` : "/workspace", { replace: true });
  }, [locationState.search, navigate, normalizedPathname]);

  // 路由匹配
  const routeConfig = {
    isHome: normalizedPathname === "/" || normalizedPathname === "/home",
    isWorkspace: normalizedPathname === "/workspace",
    isProfile: normalizedPathname === "/profile",
    isDashboard: normalizedPathname === "/dashboard",
  };

  let page: React.ReactNode;
  if (routeConfig.isHome) {
    page = (
      <PublicRoute>
        <ErrorBoundary fallback={(error, reset) => <RouteErrorFallback error={error} reset={reset} />}>
          <Suspense fallback={<RouteLoading />}>
            <HomePage />
          </Suspense>
        </ErrorBoundary>
      </PublicRoute>
    );
  } else if (routeConfig.isWorkspace) {
    page = (
      <ProtectedRoute fallbackUrl="/workspace">
        <ErrorBoundary fallback={(error, reset) => <RouteErrorFallback error={error} reset={reset} />}>
          <Suspense fallback={<RouteLoading />}>
            <WorkspacePage initialSessionId={initialWorkspaceSessionId} />
          </Suspense>
        </ErrorBoundary>
      </ProtectedRoute>
    );
  } else if (routeConfig.isProfile) {
    page = (
      <ProtectedRoute fallbackUrl="/profile">
        <ErrorBoundary fallback={(error, reset) => <RouteErrorFallback error={error} reset={reset} />}>
          <Suspense fallback={<RouteLoading />}>
            <UserProfilePage />
          </Suspense>
        </ErrorBoundary>
      </ProtectedRoute>
    );
  } else if (routeConfig.isDashboard) {
    page = (
      <ProtectedRoute fallbackUrl="/dashboard">
        <ErrorBoundary fallback={(error, reset) => <RouteErrorFallback error={error} reset={reset} />}>
          <Suspense fallback={<RouteLoading />}>
            <TokenDashboard />
          </Suspense>
        </ErrorBoundary>
      </ProtectedRoute>
    );
  } else {
    page = (
      <PublicRoute>
        <ErrorBoundary fallback={(error, reset) => <RouteErrorFallback error={error} reset={reset} />}>
          <Suspense fallback={<RouteLoading />}>
            <HomePage />
          </Suspense>
        </ErrorBoundary>
      </PublicRoute>
    );
  }

  return (
    <>
      <NetworkStatusOverlay />
      <BackendCrashOverlay />
      {page}
    </>
  );
}

export default App;
