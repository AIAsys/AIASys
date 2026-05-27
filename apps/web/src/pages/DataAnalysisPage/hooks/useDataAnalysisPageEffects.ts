import { useEffect } from "react";

interface UseDataAnalysisPageEffectsParams {
  apiBaseUrl: string;
  sessionId?: string;
  chatItemCount: number;
  setIsRightSidebarOpen: (
    open: boolean | ((prev: boolean) => boolean),
  ) => void;
}

export function useDataAnalysisPageEffects({
  apiBaseUrl,
  sessionId,
  chatItemCount,
  setIsRightSidebarOpen,
}: UseDataAnalysisPageEffectsParams) {
  useEffect(() => {
    const handleGlobalKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented) {
        return;
      }

      if (event.key === "Escape") {
        setIsRightSidebarOpen((prev) => !prev);
      }
    };

    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, [setIsRightSidebarOpen]);

  useEffect(() => {
    const handleBeforeUnload = () => {
      if (!sessionId || chatItemCount > 0) {
        return;
      }

      const blob = new Blob([JSON.stringify({ sessionId, empty: true })], {
        type: "application/json",
      });
      navigator.sendBeacon(`${apiBaseUrl}/api/sessions/mark-draft-for-cleanup`, blob);
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [apiBaseUrl, chatItemCount, sessionId]);
}
