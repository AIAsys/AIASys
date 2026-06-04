export * from "./types";
export * from "./registry";

export { StreamRenderer } from "./StreamRenderer";
export { ErrorRenderer } from "./ErrorRenderer";
export { ImageRenderer } from "./ImageRenderer";
export { SvgRenderer } from "./SvgRenderer";
export { HtmlRenderer } from "./HtmlRenderer";
export { PlainTextRenderer } from "./PlainTextRenderer";
export { JsonRenderer } from "./JsonRenderer";
export { FallbackRenderer } from "./FallbackRenderer";
export { NotebookOutputBlock } from "./NotebookOutputBlock";

// ------------------------------------------------------------------
// 默认渲染器注册
// ------------------------------------------------------------------

import { registerMimeRenderer } from "./registry";
import { ImageRenderer } from "./ImageRenderer";
import { SvgRenderer } from "./SvgRenderer";
import { HtmlRenderer } from "./HtmlRenderer";
import { PlainTextRenderer } from "./PlainTextRenderer";
import { JsonRenderer } from "./JsonRenderer";

registerMimeRenderer("image/png", ImageRenderer);
registerMimeRenderer("image/jpeg", ImageRenderer);
registerMimeRenderer("image/gif", ImageRenderer);
registerMimeRenderer("image/svg+xml", SvgRenderer);
registerMimeRenderer("text/html", HtmlRenderer);
registerMimeRenderer("text/plain", PlainTextRenderer);
registerMimeRenderer("application/json", JsonRenderer);

// 兜底：未显式注册但出现的 MIME type，用 FallbackRenderer 展示原始内容
// 注意：实际 fallback 逻辑在 NotebookOutputBlock 中处理，这里不注册通配符
