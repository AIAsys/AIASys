/**
 * Notebook 输出块调度器。
 *
 * 负责根据 output_type 分发到对应的渲染器：
 * - stream / error：直接走专用渲染器
 * - display_data / execute_result：按 MIME type 优先级查注册表
 *
 * 新增格式不需要改这个文件，只需在 registry 中注册渲染器即可。
 */

import { pickBestMimeType, getMimeRenderer } from "./registry";
import { StreamRenderer } from "./StreamRenderer";
import { ErrorRenderer } from "./ErrorRenderer";
import { FallbackRenderer } from "./FallbackRenderer";

export interface NotebookOutputBlockProps {
  output: Record<string, unknown>;
}

export function NotebookOutputBlock({ output }: NotebookOutputBlockProps) {
  const outputType = String(output.output_type || "unknown");

  if (outputType === "stream") {
    return <StreamRenderer output={output} />;
  }

  if (outputType === "error") {
    return <ErrorRenderer output={output} />;
  }

  if (outputType === "display_data" || outputType === "execute_result") {
    const data =
      output.data && typeof output.data === "object"
        ? (output.data as Record<string, unknown>)
        : null;

    if (!data) {
      return null;
    }

    const bestMime = pickBestMimeType(data);
    if (!bestMime) {
      return null;
    }

    const Renderer = getMimeRenderer(bestMime);
    if (Renderer) {
      return <Renderer data={data[bestMime]} mimeType={bestMime} />;
    }

    // 未注册的 MIME type，用兜底渲染器显示原始内容
    return <FallbackRenderer data={data[bestMime]} mimeType={bestMime} />;
  }

  return null;
}
