import { cn } from "@/lib/utils";
import { appendAccessToken, stripApiBaseUrl } from "@/utils/urlUtils";
import { API_ENDPOINTS, getCurrentUserId } from "@/config/api";
import { useMemo } from "react";
import {
  ImageLightbox,
  type ImageLightboxSlide,
} from "@/components/ui/image-lightbox";

type WorkspaceImageScope = "workspace" | "global";

interface ResolvedWorkspaceImage {
  scope: WorkspaceImageScope;
  path: string;
}

/**
 * 解析工作区图片路径，支持以下前缀：
 * - /workspace/, workspace/, ./workspace/
 * - /global/, global/, ./global/
 */
function parseWorkspaceImagePath(src: string): ResolvedWorkspaceImage | null {
  const normalized = src?.replace(/^file:\/\//, "").trim() ?? "";
  if (!normalized) {
    return null;
  }

  const workspacePrefixes = ["/workspace/", "workspace/", "./workspace/"];
  for (const prefix of workspacePrefixes) {
    if (normalized.toLowerCase().startsWith(prefix.toLowerCase())) {
      return {
        scope: "workspace",
        path: normalized.slice(prefix.length),
      };
    }
  }

  const globalPrefixes = ["/global/", "global/", "./global/"];
  for (const prefix of globalPrefixes) {
    if (normalized.toLowerCase().startsWith(prefix.toLowerCase())) {
      return {
        scope: "global",
        path: normalized.slice(prefix.length),
      };
    }
  }

  return null;
}

/**
 * 从当前 URL 解析 workspaceId
 */
function inferWorkspaceIdFromUrl(): string | undefined {
  const pathname = window.location.pathname;
  const match = pathname.match(/\/workspace\/([^/]+)/);
  return match?.[1];
}

/**
 * 将 /workspace/ 或 workspace/ 等路径转换为完整的下载 URL
 * 格式:
 * - workspace: /api/files/download/{userId}/{sessionId}/{filename}?user_id={userId}
 * - global: /api/workspaces/{workspaceId}/global-workspace/download/{assetPath}
 */
function resolveWorkspaceImage(src: string, sessionId?: string): string {
  let normalized = src?.replace(/^file:\/\//, "").trim() ?? "";

  // LLM 可能只返回文件名（如 industrial_analysis_dashboard.png）。
  // 如果看起来是纯文件名，兜底补全为 /workspace/{filename}。
  const looksLikePlainFilename =
    normalized.length > 0 &&
    !normalized.includes("/") &&
    !normalized.includes(":") &&
    !normalized.startsWith("data:");
  if (looksLikePlainFilename) {
    normalized = `/workspace/${normalized}`;
  }

  const resolved = parseWorkspaceImagePath(normalized);
  if (!resolved) {
    return src ?? "";
  }

  const workspaceId = inferWorkspaceIdFromUrl();

  if (resolved.scope === "workspace") {
    // 优先使用传入的 sessionId，否则尝试从 URL 解析
    const resolvedSessionId = sessionId || workspaceId;

    if (!resolvedSessionId) {
      console.warn(
        "[MarkdownImage] Cannot resolve workspace image: no sessionId",
        { src },
      );
      return src;
    }

    const userId = getCurrentUserId();
    return `${API_ENDPOINTS.FILES_DOWNLOAD(userId, resolvedSessionId, resolved.path)}?user_id=${userId}`;
  }

  // global scope
  if (!workspaceId) {
    console.warn(
      "[MarkdownImage] Cannot resolve global workspace image: no workspaceId",
      { src },
    );
    return src;
  }

  const userId = getCurrentUserId();
  return `${API_ENDPOINTS.GLOBAL_WORKSPACE_DOWNLOAD(workspaceId, resolved.path)}?user_id=${userId}`;
}

/**
 * Markdown 图片组件
 *
 * 特性：
 * - 行内显示图片（max-width 75%）
 * - 点击使用统一图片放大组件预览
 */
export const MarkdownImage = ({
  src,
  alt,
  token,
  sessionId,
  className,
  containerClassName,
  slides,
  startIndex,
}: {
  src?: string;
  alt?: string;
  token?: string;
  sessionId?: string;
  className?: string;
  containerClassName?: string;
  slides?: readonly ImageLightboxSlide[];
  startIndex?: number;
}) => {
  const finalSrc = useMemo(() => {
    const cleanSrc = stripApiBaseUrl(src || "");
    const resolvedSrc = resolveWorkspaceImage(cleanSrc, sessionId);
    return appendAccessToken(resolvedSrc, token);
  }, [src, token, sessionId]);

  return (
    <div
      className={cn("flex justify-center my-4 w-full", containerClassName)}
      onClick={(e) => e.stopPropagation()}
    >
      <ImageLightbox
        src={finalSrc}
        alt={alt}
        slides={slides}
        startIndex={startIndex}
        wrapElement="span"
        zoomMargin={32}
        title={alt}
        className={cn(
          "rounded-lg shadow-md border border-border cursor-zoom-in hover:opacity-95 transition-[opacity,transform,box-shadow] block max-w-[75%]",
          className,
        )}
      />
    </div>
  );
};
