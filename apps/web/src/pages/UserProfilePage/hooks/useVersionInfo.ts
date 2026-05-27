import { useCallback, useEffect, useState } from "react";
import { formatVersionLabel } from "@/lib/version";
import { apiRequest } from "@/lib/api/httpClient";

interface UseVersionInfoReturn {
  showVersionDetails: boolean;
  backendVersion: string;
  frontendVersion: string;
  systemVersion: string;
  toggleVersionDetails: () => void;
}

export function useVersionInfo(): UseVersionInfoReturn {
  const [showVersionDetails, setShowVersionDetails] = useState(false);
  const [backendVersion, setBackendVersion] = useState<string>("-");
  const [frontendVersion, setFrontendVersion] = useState<string>("-");
  const [systemVersion, setSystemVersion] = useState<string>("-");

  useEffect(() => {
    const fetchVersion = async () => {
      try {
        const data = await apiRequest<{ version?: string }>("/health");
        const version = formatVersionLabel(data.version);
        setBackendVersion(version);
        setSystemVersion(version);
      } catch {
        setBackendVersion("-");
        setSystemVersion("-");
      }
    };
    void fetchVersion();
  }, []);

  useEffect(() => {
    const fetchFrontendVersion = async () => {
      try {
        const pkg = (await import("../../../../package.json")) as {
          version?: string;
        };
        setFrontendVersion(formatVersionLabel(pkg.version));
      } catch {
        setFrontendVersion("-");
      }
    };
    void fetchFrontendVersion();
  }, []);

  const toggleVersionDetails = useCallback(() => {
    setShowVersionDetails((prev) => !prev);
  }, []);

  return {
    showVersionDetails,
    backendVersion,
    frontendVersion,
    systemVersion,
    toggleVersionDetails,
  };
}
