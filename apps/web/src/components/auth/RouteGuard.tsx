"use client";

import { isSingleUserAuthMode } from "@/config/auth";
import { useAuthContext } from "@/contexts/AuthContext";

interface RouteGuardProps {
  children: React.ReactNode;
  /**
   * 是否需要登录才能访问
   * @default true
   */
  requireAuth?: boolean;
  /**
   * 登录后跳转的目标路径
   * @default 当前路径
   */
  fallbackUrl?: string;
}

/**
 * 路由守卫组件 - 类似 FastAPI 的 Depends(get_current_user)
 * 
 * 用法:
 * <RouteGuard requireAuth={true}>  // 需要登录
 *   <ProtectedPage />
 * </RouteGuard>
 * 
 * <RouteGuard requireAuth={false}> // 公开页面
 *   <PublicPage />
 * </RouteGuard>
 */
export function RouteGuard({ 
  children, 
  requireAuth = true,
  fallbackUrl: _fallbackUrl,
}: RouteGuardProps) {
  const { isAuthenticated, isLoading } = useAuthContext();
  const isDirectAccessMode = isSingleUserAuthMode();

  // 加载中显示 loading
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (isDirectAccessMode) {
    return <>{children}</>;
  }

  // 需要登录但未登录，显示跳转中（实际会被 useEffect 跳转）
  if (requireAuth && !isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-4"></div>
          <p className="text-muted-foreground">正在准备本地工作区...</p>
        </div>
      </div>
    );
  }

  // 已登录或不需要登录，正常显示
  return <>{children}</>;
}

/**
 * 公开路由 - 不需要登录
 */
export function PublicRoute({ children }: { children: React.ReactNode }) {
  return <RouteGuard requireAuth={false}>{children}</RouteGuard>;
}

/**
 * 受保护路由 - 必须登录
 */
export function ProtectedRoute({ 
  children,
  fallbackUrl 
}: { 
  children: React.ReactNode;
  fallbackUrl?: string;
}) {
  return <RouteGuard requireAuth={true} fallbackUrl={fallbackUrl}>{children}</RouteGuard>;
}
