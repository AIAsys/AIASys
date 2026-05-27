import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * 类型守卫：检查值是否为 Error 实例
 */
export function isError(err: unknown): err is Error {
  return err instanceof Error;
}

/**
 * 类型守卫：检查值是否为带有 message 属性的对象
 */
export function hasMessage(err: unknown): err is { message: string } {
  return (
    typeof err === "object" &&
    err !== null &&
    "message" in err &&
    typeof (err as { message: unknown }).message === "string"
  );
}

/**
 * 安全地获取错误信息
 */
export function getErrorMessage(err: unknown): string {
  if (isError(err)) {
    return err.message;
  }
  if (hasMessage(err)) {
    return err.message;
  }
  return String(err);
}
