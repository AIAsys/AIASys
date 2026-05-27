import { cn } from "@/lib/utils";
import { appendAccessToken, stripApiBaseUrl } from "@/utils/urlUtils";
import { API_ENDPOINTS, getCurrentUserId } from "@/config/api";
import { useMemo } from "react";
import {
  ImageLightbox,
  type ImageLightboxSlide,
} from "@/components/ui/image-lightbox";

/**
 * 将 /workspace/ 路径转换为完整的下载 URL
 * 格式: /api/files/download/{userId}/{sessionId}/{filename}?user_id={userId}
 */
function resolveWorkspaceImage(src: string, sessionId?: string): string {
  if (!src?.startsWith("/workspace/")) {
    return src;
  }

  // 优先使用传入的 sessionId，否则尝试从 URL 解析
  if (!sessionId) {
    const pathname = window.location.pathname;
    const match = pathname.match(/\/analysis\/([^/]+)/);
    sessionId = match?.[1];
  }

  if (!sessionId) {
    console.warn(
      "[MarkdownImage] Cannot resolve workspace image: no sessionId",
      { src },
    );
    return src;
  }

  // 提取文件名
  const filename = src.replace("/workspace/", "");
  const userId = getCurrentUserId();

  // 构建完整 URL
  const url =
    `${API_ENDPOINTS.FILES_DOWNLOAD(userId, sessionId, filename)}?user_id=${userId}`;
  return url;
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
