/**
 * FileUploadToast - 文件上传提示组件
 *
 * 简单的浮动提示框，用于显示文件上传结果
 */
import { CheckCircle, XCircle } from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";

export interface FileUploadToastProps {
  message: string;
  type: "success" | "error";
  duration?: number; // 毫秒，默认 3000
  onClose?: () => void;
}

export const FileUploadToast: React.FC<FileUploadToastProps> = ({
  message,
  type,
  duration = 3000,
  onClose,
}) => {
  const [isVisible, setIsVisible] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsVisible(false);
      onClose?.();
    }, duration);

    return () => clearTimeout(timer);
  }, [duration, onClose]);

  if (!isVisible) return null;

  return (
    <div
      className={`fixed bottom-6 right-6 px-5 py-3 rounded-lg shadow-lg flex items-center gap-3 animate-in fade-in slide-in-from-bottom-4 duration-300 ${
        type === "success" ? "bg-success text-white" : "bg-error text-white"
      }`}
    >
      {type === "success" ? (
        <CheckCircle className="w-5 h-5 flex-shrink-0" />
      ) : (
        <XCircle className="w-5 h-5 flex-shrink-0" />
      )}
      <span className="text-sm font-medium">{message}</span>
    </div>
  );
};

/**
 * useFileUploadToast - Toast 管理 Hook
 *
 * 返回显示 Toast 的函数
 */
export function useFileUploadToast() {
  const [toasts, setToasts] = useState<
    Array<{
      id: string;
      message: string;
      type: "success" | "error";
    }>
  >([]);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    return () => {
      timersRef.current.forEach(clearTimeout);
      timersRef.current = [];
    };
  }, []);

  const showToast = useCallback(
    (
      message: string,
      type: "success" | "error" = "success",
      duration = 3000,
    ) => {
      const id = Date.now().toString();
      setToasts((prev) => [...prev, { id, message, type }]);

      const timer = setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, duration);
      timersRef.current.push(timer);
    },
    [],
  );

  const showSuccess = useCallback(
    (message: string, duration?: number) => {
      showToast(message, "success", duration);
    },
    [showToast],
  );

  const showError = useCallback(
    (message: string, duration?: number) => {
      showToast(message, "error", duration);
    },
    [showToast],
  );

  return {
    toasts,
    showToast,
    showSuccess,
    showError,
  };
}
