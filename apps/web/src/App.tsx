import { Suspense, lazy, useCallback, useEffect, useState } from "react";

import { PublicRoute, ProtectedRoute } from "./components/auth/RouteGuard";

const HomePage = lazy(() => import("./pages/HomePage"));
const DataAnalysisPage = lazy(() => import("./pages/DataAnalysisPage"));

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
  const isAnalysisRoute = normalizedPathname === "/analysis";
  const initialAnalysisSessionId =
    isAnalysisRoute
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

  useEffect(() => {
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
    navigate(query ? `/analysis?${query}` : "/analysis", { replace: true });
  }, [locationState.search, navigate, normalizedPathname]);

  // 路由匹配
  const routeConfig = {
    isHome: normalizedPathname === "/" || normalizedPathname === "/home",
    isAnalysis: isAnalysisRoute,
    isProfile: normalizedPathname === "/profile",
  };

  // 首页 - 公开访问
  if (routeConfig.isHome) {
    return (
      <PublicRoute>
        <Suspense fallback={<RouteLoading />}>
          <HomePage />
        </Suspense>
      </PublicRoute>
    );
  }

  // 分析页面 - 需要登录
  if (routeConfig.isAnalysis) {
    return (
      <ProtectedRoute fallbackUrl="/analysis">
        <Suspense fallback={<RouteLoading />}>
          <DataAnalysisPage initialSessionId={initialAnalysisSessionId} />
        </Suspense>
      </ProtectedRoute>
    );
  }

  // 用户资料 - 需要登录
  if (routeConfig.isProfile) {
    return (
      <ProtectedRoute fallbackUrl="/profile">
        <Suspense fallback={<RouteLoading />}>
          <UserProfilePage />
        </Suspense>
      </ProtectedRoute>
    );
  }

  // 默认首页
  return (
    <PublicRoute>
      <Suspense fallback={<RouteLoading />}>
        <HomePage />
      </Suspense>
    </PublicRoute>
  );
}

export default App;
