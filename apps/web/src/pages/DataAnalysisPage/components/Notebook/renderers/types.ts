/**
 * Notebook 输出渲染器类型定义。
 *
 * 设计目标：
 * - 统一 MIME type 渲染器的接口契约
 * - 与 output_type（stream / error / display_data）解耦
 * - 新格式只需要注册一个组件，无需改核心调度逻辑
 */

/** 用于 stream / error 等 output_type 级别的渲染器 */
export interface OutputRendererProps {
  output: Record<string, unknown>;
}

/** 用于 display_data / execute_result 中单个 MIME type 的渲染器 */
export interface MimeRendererProps {
  /** 对应 MIME type 的原始数据 */
  data: unknown;
  /** 当前选中的 MIME type */
  mimeType: string;
}

/** MIME type 渲染器组件签名 */
export type MimeRenderer = React.FC<MimeRendererProps>;
