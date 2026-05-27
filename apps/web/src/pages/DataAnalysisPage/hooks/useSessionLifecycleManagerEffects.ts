import { apiRequest } from "@/lib/api/httpClient";

import { useEffect, type MutableRefObject } from "react";
import type { AskUserRequest } from "@/types/askUser";
import type { SessionStatusInfo } from "../types";

interface UseSessionStatusLoaderOptions {
  apiBaseUrl: string;
  sessionId?: string;
  enabled?: boolean;
  refreshKey: number;
  sessionStatusRequestIdRef: MutableRefObject<number>;
  setSessionStatus: (status: SessionStatusInfo | null) => void;
}

export function useSessionStatusLoader({
  apiBaseUrl,
  sessionId,
  enabled = true,
  refreshKey,
  sessionStatusRequestIdRef,
  setSessionStatus,
}: UseSessionStatusLoaderOptions) {
  useEffect(() => {
    if (!enabled || !sessionId) {
      setSessionStatus(null);
      return;
    }

    const requestId = (sessionStatusRequestIdRef.current += 1);
    const controller = new AbortController();

    const loadSessionStatus = async () => {
      try {
        const data = await apiRequest<SessionStatusInfo>(
          `${apiBaseUrl}/api/sessions/status/${sessionId}`,
          {
          signal: controller.signal,
          cache: "no-store",
          },
        );
        if (!data) {
          return;
        }
        if (sessionStatusRequestIdRef.current !== requestId) {
          return;
        }

        setSessionStatus({
          ...data,
          session_id: data.session_id || sessionId,
          title: data.title || "",
        });
      } catch (error) {
        if ((error as Error).name === "AbortError") {
          return;
        }
        if (
          (error as { status?: number }).status === 404
        ) {
          setSessionStatus(null);
          return;
        }
        console.warn("Failed to load session status:", error);
      }
    };

    void loadSessionStatus();
    return () => controller.abort();
  }, [
    apiBaseUrl,
    enabled,
    refreshKey,
    sessionId,
    sessionStatusRequestIdRef,
    setSessionStatus,
  ]);
}

interface UseSessionStatusRefreshOnRunCompleteOptions {
  isRunning: boolean;
  sessionId?: string;
  previousActiveSessionRunningRef: MutableRefObject<boolean>;
  refreshSessionStatus: () => void;
}

export function useSessionStatusRefreshOnRunComplete({
  isRunning,
  sessionId,
  previousActiveSessionRunningRef,
  refreshSessionStatus,
}: UseSessionStatusRefreshOnRunCompleteOptions) {
  useEffect(() => {
    if (!sessionId) {
      previousActiveSessionRunningRef.current = false;
      return;
    }

    if (isRunning) {
      previousActiveSessionRunningRef.current = true;
      return;
    }

    if (!previousActiveSessionRunningRef.current) {
      return;
    }

    previousActiveSessionRunningRef.current = false;
    const timer = window.setTimeout(() => {
      refreshSessionStatus();
    }, 300);

    return () => window.clearTimeout(timer);
  }, [isRunning, previousActiveSessionRunningRef, refreshSessionStatus, sessionId]);
}

interface UseAskUserSessionSyncOptions {
  sessionId?: string;
  setAskUserActiveSessionId: (sessionId: string) => void;
}

export function useAskUserSessionSync({
  sessionId,
  setAskUserActiveSessionId,
}: UseAskUserSessionSyncOptions) {
  useEffect(() => {
    if (sessionId) {
      setAskUserActiveSessionId(sessionId);
    }
  }, [sessionId, setAskUserActiveSessionId]);
}

interface UsePendingAskUserRestoreOptions {
  apiBaseUrl: string;
  sessionId?: string;
  enabled?: boolean;
  showAskUser: (request: AskUserRequest, sessionId: string) => void;
}

export function usePendingAskUserRestore({
  apiBaseUrl,
  sessionId,
  enabled = true,
  showAskUser,
}: UsePendingAskUserRestoreOptions) {
  useEffect(() => {
    if (!enabled || !sessionId) {
      return;
    }

    let cancelled = false;

    const restorePendingAskUser = async () => {
      try {
        const data = await apiRequest<{
          requests?: Array<{
            session_id?: string;
            request?: AskUserRequest;
          }>;
        }>(
          `${apiBaseUrl}/api/ask-user/pending?session_id=${sessionId}`,
        );
        const pendingRequest = data.requests?.[0];

        if (
          !cancelled &&
          pendingRequest?.request &&
          pendingRequest.session_id === sessionId
        ) {
          showAskUser(pendingRequest.request, sessionId);
        }
      } catch (error) {
        console.warn("Failed to restore pending AskUser request:", error);
      }
    };

    void restorePendingAskUser();
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, enabled, sessionId, showAskUser]);
}
