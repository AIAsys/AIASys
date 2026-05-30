import { memo, useMemo } from "react";

import { CsvPreview } from "@/components/layout/WorkspaceSidebar/preview/CsvPreview";
import {
  resolveWorkspaceFileUrl,
  workspacePathToFilename,
} from "@/utils/workspaceFiles";

interface CsvArtifactRendererProps {
  artifactPath: string;
  sessionId?: string;
  token?: string;
  variant?: "chat" | "workspace";
  className?: string;
}

function getDisplayFileName(path: string): string {
  const normalizedPath = workspacePathToFilename(path).replace(/\\/g, "/");
  const basename = normalizedPath.split("/").pop();
  return basename || normalizedPath || path;
}

export const CsvArtifactRenderer = memo(function CsvArtifactRenderer({
  artifactPath,
  sessionId,
  token,
  variant = "chat",
  className,
}: CsvArtifactRendererProps) {
  const fileUrl = useMemo(
    () => resolveWorkspaceFileUrl(artifactPath, sessionId, token),
    [artifactPath, sessionId, token],
  );
  const fileName = useMemo(() => getDisplayFileName(artifactPath), [artifactPath]);

  return (
    <CsvPreview
      url={fileUrl}
      fileName={fileName}
      sessionId={sessionId}
      variant={variant}
      className={className}
      scope="session"
      assetPath={workspacePathToFilename(artifactPath)}
    />
  );
});
