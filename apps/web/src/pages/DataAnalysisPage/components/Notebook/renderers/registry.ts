/**
 * Notebook 输出渲染器注册表。
 *
 * 参考 VS Code Jupyter 扩展的 MIME type 优先级策略：
 * 交互式格式优先，静态图片次之，纯文本兜底。
 */

import type { MimeRenderer } from "./types";

/** MIME type 优先级（越靠前越优先渲染） */
export const MIME_TYPE_PRIORITIES: readonly string[] = [
  // 交互式 / 富文本
  "application/vnd.plotly.v1+json",
  "application/vnd.bokehjs_exec.v0+json",
  "application/vnd.vega.v5+json",
  "application/vnd.vegalite.v4+json",
  "text/html",
  "image/svg+xml",
  // 静态图片
  "image/png",
  "image/jpeg",
  "image/gif",
  // 结构化数据
  "application/json",
  // 兜底文本
  "text/plain",
  "text/latex",
];

const rendererRegistry = new Map<string, MimeRenderer>();

/** 注册一个 MIME type 渲染器 */
export function registerMimeRenderer(
  mimeType: string,
  renderer: MimeRenderer,
): void {
  rendererRegistry.set(mimeType, renderer);
}

/** 注销一个 MIME type 渲染器 */
export function unregisterMimeRenderer(mimeType: string): void {
  rendererRegistry.delete(mimeType);
}

/** 查询已注册的渲染器 */
export function getMimeRenderer(mimeType: string): MimeRenderer | undefined {
  return rendererRegistry.get(mimeType);
}

/** 判断 MIME type 是否已注册 */
export function hasMimeRenderer(mimeType: string): boolean {
  return rendererRegistry.has(mimeType);
}

/**
 * 从 outputs.data 中按优先级选出最佳 MIME type。
 *
 * @param data - output.data 对象（mimeType → payload 的映射）
 * @returns 选中的 MIME type；如果没有匹配，返回 undefined
 */
export function pickBestMimeType(
  data: Record<string, unknown>,
): string | undefined {
  const available = new Set(Object.keys(data));

  // 按优先级表顺序匹配
  for (const mime of MIME_TYPE_PRIORITIES) {
    if (available.has(mime) && data[mime] !== undefined && data[mime] !== null) {
      return mime;
    }
  }

  // 优先级表未命中时，返回第一个可用的
  for (const mime of available) {
    if (data[mime] !== undefined && data[mime] !== null) {
      return mime;
    }
  }

  return undefined;
}
