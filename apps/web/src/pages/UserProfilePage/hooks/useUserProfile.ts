/**
 * 用户资料页面状态管理 Hook
 */

import { useState, useEffect, useCallback, useMemo } from "react";
import { getAuthMode } from "@/config/auth";
import { useAuthContext } from "@/contexts/AuthContext";
import { apiRequest } from "@/lib/api/httpClient";
import type { AuthUser } from "../types";

interface ApiUserPayload {
  id?: string;
  email?: string;
  name?: string;
  phone?: string | null;
  created_at?: string;
  updated_at?: string;
  createdAt?: string;
  updatedAt?: string;
}

function mapApiUserToAuthUser(
  payload: ApiUserPayload,
  fallback: AuthUser | null,
): AuthUser {
  const name = payload.name || fallback?.nickname || "User";
  return {
    id: payload.id || fallback?.id || "",
    email: payload.email || fallback?.email || "",
    nickname: name,
    username: name,
    createdAt:
      payload.created_at ||
      payload.createdAt ||
      fallback?.createdAt ||
      new Date().toISOString(),
    phone: payload.phone ?? fallback?.phone ?? "",
    updatedAt: payload.updated_at || payload.updatedAt || fallback?.updatedAt,
    avatarColor: fallback?.avatarColor,
  };
}

export function useUserProfile() {
  const {
    user: currentUser,
    isAuthenticated,
    isLoading: authLoading,
    refreshSession,
  } = useAuthContext();

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [profileUser, setProfileUser] = useState<AuthUser | null>(null);
  const [nameInput, setNameInput] = useState("");
  const [phoneInput, setPhoneInput] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [submitSuccess, setSubmitSuccess] = useState("");

  useEffect(() => {
    if (authLoading) return;
    setIsLoading(false);
  }, [authLoading]);

  const authMode = getAuthMode();
  const isLocalEditable = authMode === "local" || authMode === "none";
  const typedCurrentUser = (currentUser as AuthUser | null) ?? null;

  const user = useMemo(() => {
    if (profileUser) return profileUser;
    return typedCurrentUser;
  }, [profileUser, typedCurrentUser]);

  useEffect(() => {
    if (!typedCurrentUser) return;
    setProfileUser(typedCurrentUser);
    setNameInput(typedCurrentUser.nickname || "");
    setPhoneInput(typedCurrentUser.phone || "");
  }, [typedCurrentUser]);

  const fetchProfile = useCallback(async () => {
    if (!isAuthenticated) return;

    try {
      const data = await apiRequest<{ user?: ApiUserPayload }>("/api/auth/me");
      if (!data.user?.id) return;

      const mappedUser = mapApiUserToAuthUser(data.user, typedCurrentUser);
      setProfileUser(mappedUser);
      setNameInput(mappedUser.nickname || "");
      setPhoneInput(mappedUser.phone || "");
    } catch {
      // 保持当前展示，不中断页面渲染
    }
  }, [isAuthenticated, typedCurrentUser]);

  useEffect(() => {
    void fetchProfile();
  }, [fetchProfile]);

  const startEdit = useCallback(() => {
    if (!isLocalEditable) {
      alert("当前运行模式不支持在线编辑个人资料");
      return;
    }
    setSubmitError("");
    setSubmitSuccess("");
    setNameInput(user?.nickname || "");
    setPhoneInput(user?.phone || "");
    setIsEditing(true);
  }, [isLocalEditable, user]);

  const cancelEdit = useCallback(() => {
    setSubmitError("");
    setSubmitSuccess("");
    setNameInput(user?.nickname || "");
    setPhoneInput(user?.phone || "");
    setIsEditing(false);
  }, [user]);

  const saveProfile = useCallback(async () => {
    const cleanedName = nameInput.trim();
    if (!cleanedName) {
      setSubmitError("昵称不能为空");
      return;
    }

    setIsSaving(true);
    setSubmitError("");
    setSubmitSuccess("");

    try {
      const data = await apiRequest<{
        detail?: string;
        user?: ApiUserPayload;
      }>("/api/auth/me", {
        method: "PUT",
        body: {
          name: cleanedName,
          phone: phoneInput,
        },
      });

      const mappedUser = mapApiUserToAuthUser(data.user || {}, user);
      setProfileUser(mappedUser);
      setNameInput(mappedUser.nickname || "");
      setPhoneInput(mappedUser.phone || "");
      setIsEditing(false);
      setSubmitSuccess("个人信息已更新");

      await refreshSession();
    } catch (error: unknown) {
      setSubmitError(error instanceof Error ? error.message : "保存失败，请重试");
    } finally {
      setIsSaving(false);
    }
  }, [nameInput, phoneInput, user, refreshSession]);

  const showAuthModeNotice = useCallback(() => {
    alert("当前版本只保留本地默认用户模式");
  }, []);

  const reloadProfileContext = useCallback(() => {
    window.location.reload();
  }, []);

  return {
    // 状态
    isLoading,
    isSaving,
    isEditing,
    submitError,
    submitSuccess,
    isAuthenticated,
    authLoading,
    isLocalEditable,
    
    // 数据
    user,
    nameInput,
    phoneInput,
    
    // Actions
    setNameInput,
    setPhoneInput,
    startEdit,
    cancelEdit,
    saveProfile,
    showAuthModeNotice,
    reloadProfileContext,
  };
}
