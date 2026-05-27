import { useEffect, useState } from "react";
import { getWorkspaceOverview } from "@/lib/api/workspaces";
import type { WorkspaceOverviewResponse } from "@/types/workspace";

const workspaceOverviewInFlight = new Map<
  string,
  Promise<WorkspaceOverviewResponse>
>();

export function useWorkspaceOverview(
  workspaceId: string | undefined,
  sessionId: string | undefined,
  enabled: boolean,
) {
  const [workspaceOverview, setWorkspaceOverview] =
    useState<WorkspaceOverviewResponse | null>(null);
  const [isLoadingOverview, setIsLoadingOverview] = useState(false);

  useEffect(() => {
    if (!workspaceId || !enabled) {
      setWorkspaceOverview(null);
      return;
    }

    let cancelled = false;
    const resolvedWorkspaceId = workspaceId;
    const resolvedSessionKey = sessionId || "no-session";
    const requestKey = `${resolvedWorkspaceId}:${resolvedSessionKey}`;

    async function loadOverview() {
      setIsLoadingOverview(true);
      try {
        const inflightRequest =
          workspaceOverviewInFlight.get(requestKey) ||
          (async () => {
            try {
              return await getWorkspaceOverview(resolvedWorkspaceId);
            } finally {
              workspaceOverviewInFlight.delete(requestKey);
            }
          })();

        if (!workspaceOverviewInFlight.has(requestKey)) {
          workspaceOverviewInFlight.set(requestKey, inflightRequest);
        }

        const nextOverview = await inflightRequest;

        if (cancelled) {
          return;
        }

        setWorkspaceOverview(nextOverview);
      } catch (error) {
        if (!cancelled) {
          console.error("Failed to load workspace overview:", error);
        }
      } finally {
        if (!cancelled) {
          setIsLoadingOverview(false);
        }
      }
    }

    void loadOverview();
    return () => {
      cancelled = true;
    };
  }, [workspaceId, sessionId, enabled]);

  return { workspaceOverview, isLoadingOverview };
}
