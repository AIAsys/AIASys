import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { clearCurrentUserId, setCurrentUserId } from "@/config/api";
import { getAuthMode } from "@/config/auth";
import { apiFetch } from "@/lib/api/httpClient";

/**
 * 认证用户信息
 */
interface AuthUser {
  id: string;
  email: string;
  nickname: string;
  username: string;
  createdAt: string;
  phone?: string;
  updatedAt?: string;
  role?: "admin" | "user";
  avatarColor?: string;
  avatarChar?: string;
}

/**
 * 认证会话信息
 */
interface AuthSession {
  token: string;
  expiresAt: number;
}

/**
 * 认证上下文类型
 */
interface AuthContextValue {
  user: AuthUser | null;
  session: AuthSession | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string;
  isAdmin: boolean;
  refreshSession: () => Promise<void>;
  handleLogout: () => Promise<void>;
  updateProfile: (data: { name?: string; avatarColor?: string; avatarChar?: string }) => Promise<boolean>;
}

/**
 * 认证上下文
 */
const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * AuthProvider Props
 */
interface AuthProviderProps {
  children: ReactNode;
}

function extractSessionErrorMessage(payload: unknown, status: number): string {
  if (!payload || typeof payload !== "object") {
    return `会话接口返回 ${status}`;
  }

  const candidate = payload as {
    detail?: unknown;
    message?: unknown;
    error?: unknown;
  };

  if (typeof candidate.detail === "string" && candidate.detail.trim()) {
    return candidate.detail.trim();
  }
  if (typeof candidate.message === "string" && candidate.message.trim()) {
    return candidate.message.trim();
  }
  if (typeof candidate.error === "string" && candidate.error.trim()) {
    return candidate.error.trim();
  }

  return `会话接口返回 ${status}`;
}

async function readSessionError(response: Response): Promise<string> {
  try {
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const payload = (await response.json()) as unknown;
      return extractSessionErrorMessage(payload, response.status);
    }

    const rawText = await response.text();
    const text = rawText.trim();
    if (text) {
      return text.length > 160 ? `${text.slice(0, 157)}...` : text;
    }
  } catch {
    // ignore parse errors and fall through to generic message
  }

  return `会话接口返回 ${response.status}`;
}

function normalizeSessionLoadError(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error || "");
  const normalized = message.trim();
  const lowered = normalized.toLowerCase();

  if (
    lowered.includes("failed to fetch") ||
    lowered.includes("networkerror") ||
    lowered.includes("load failed")
  ) {
    return "无法连接本地后端，/api/auth/session 请求失败";
  }

  if (lowered.includes("abort")) {
    return "加载本地用户会话超时";
  }

  if (normalized) {
    return `加载本地用户会话失败：${normalized}`;
  }

  return "加载本地用户会话失败";
}

/**
 * 认证上下文提供者
 *
 * 当前默认使用本地默认用户模式，通过 `/api/auth/session` 拉取当前工作区用户。
 */
export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [session, setSession] = useState<AuthSession | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string>("");

  const refreshSession = useCallback(async () => {
    try {
      setError("");

      // 检查是否是无认证模式
      const authMode = getAuthMode();
      if (authMode === "none") {
        // 无认证模式：使用固定测试用户（管理员）
        const defaultUser: AuthUser = {
          id: "test_anonymous_dev",
          email: "test@local.com",
          nickname: "测试用户",
          username: "testuser",
          createdAt: new Date().toISOString(),
          phone: "",
          role: "admin",
        };
        setUser(defaultUser);
        setSession({
          token: "none-mode-token",
          expiresAt: Date.now() + 24 * 60 * 60 * 1000,
        });
        setCurrentUserId(defaultUser.id);
        setIsAuthenticated(true);
        setError("");
        return;
      }

      // 从后端获取会话（本地认证模式）
      const res = await apiFetch("/api/auth/session");

      if (res.ok) {
        const data = (await res.json()) as {
          user?: {
            id?: string;
            email?: string;
            name?: string;
            phone?: string;
            role?: "admin" | "user";
            created_at?: string;
            updated_at?: string;
            createdAt?: string;
            updatedAt?: string;
            avatar_color?: string;
            avatar_char?: string;
          };
        };

        if (data?.user?.id) {
          const userId = data.user.id;
          const profileName = data.user.name || "User";
          setUser({
            id: userId,
            email: data.user.email || "",
            nickname: profileName,
            username: profileName,
            createdAt:
              data.user.created_at ||
              data.user.createdAt ||
              new Date().toISOString(),
            phone: data.user.phone || "",
            updatedAt: data.user.updated_at || data.user.updatedAt,
            role: (data.user as { role?: "admin" | "user" }).role || "user",
            avatarColor: data.user.avatar_color || "",
            avatarChar: data.user.avatar_char || "",
          });
          setSession({
            token: "local-jwt-token",
            expiresAt: Date.now() + 30 * 24 * 60 * 60 * 1000,
          });
          setCurrentUserId(userId);
          setIsAuthenticated(true);
          setError("");
          return;
        }

        setError("本地后端已响应，但没有返回可用用户。");
      } else {
        setError(await readSessionError(res));
      }

      // 未登录
      setIsAuthenticated(false);
      setUser(null);
      setSession(null);
      clearCurrentUserId();
    } catch (error) {
      // 不再信任本地缓存的 user_id，避免跨账号残留导致请求打到错误用户空间
      clearCurrentUserId();
      setIsAuthenticated(false);
      setUser(null);
      setSession(null);
      setError(normalizeSessionLoadError(error));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshSession();
  }, [refreshSession]);

  const updateProfile = useCallback(
    async (data: { name?: string; avatarColor?: string; avatarChar?: string }): Promise<boolean> => {
      try {
        const res = await apiFetch("/api/auth/me", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        });
        if (!res.ok) return false;

        const json = (await res.json()) as {
          user?: {
            id?: string;
            email?: string;
            name?: string;
            phone?: string;
            role?: "admin" | "user";
            created_at?: string;
            updated_at?: string;
            avatar_color?: string;
            avatar_char?: string;
          };
        };
        if (json?.user?.id) {
          setUser((prev) =>
            prev
              ? {
                  ...prev,
                  nickname: json.user?.name ?? prev.nickname,
                  username: json.user?.name ?? prev.username,
                  phone: json.user?.phone ?? prev.phone,
                  avatarColor: json.user?.avatar_color ?? prev.avatarColor,
                  avatarChar: json.user?.avatar_char ?? prev.avatarChar,
                }
              : prev,
          );
        }
        return true;
      } catch {
        return false;
      }
    },
    [],
  );

  const value: AuthContextValue = {
    user,
    session,
    isAuthenticated,
    isLoading,
    error,
    isAdmin: user?.role === "admin",
    refreshSession,
    handleLogout: async () => {
      clearCurrentUserId();
      // 调用后端登出 API
      try {
        await apiFetch("/api/auth/logout", {
          method: "POST",
        });
      } catch (e) {
        console.error("Logout failed:", e);
      }
      if (getAuthMode() === "local") {
        await refreshSession();
        window.location.href = "/workspace";
        return;
      }
      window.location.href = "/home";
    },
    updateProfile,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/**
 * 使用认证上下文的 Hook
 */
export function useAuthContext() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuthContext must be used within an AuthProvider");
  }
  return context;
}

export function useAuthState() {
  return useAuthContext();
}
