import { useCallback, useEffect, useState } from "react";

import { getCapabilityRegistry } from "@/lib/api/capabilityRegistry";
import type { CapabilityRegistryResponse } from "@/types/capability";

interface UseCapabilityRegistryOptions {
  enabled?: boolean;
  analysisSandboxMode?: string | null;
}

interface UseCapabilityRegistryReturn {
  registry: CapabilityRegistryResponse | null;
  loading: boolean;
  error: Error | null;
  refresh: () => Promise<void>;
}

export function useCapabilityRegistry(
  options: UseCapabilityRegistryOptions = {},
): UseCapabilityRegistryReturn {
  const { enabled = true, analysisSandboxMode } = options;
  const [registry, setRegistry] = useState<CapabilityRegistryResponse | null>(null);
  const [loading, setLoading] = useState(Boolean(enabled));
  const [error, setError] = useState<Error | null>(null);

  const loadRegistry = useCallback(async () => {
    if (!enabled) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const data = await getCapabilityRegistry(analysisSandboxMode);
      setRegistry(data);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoading(false);
    }
  }, [analysisSandboxMode, enabled]);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    void loadRegistry();
  }, [enabled, loadRegistry]);

  return {
    registry,
    loading,
    error,
    refresh: loadRegistry,
  };
}
