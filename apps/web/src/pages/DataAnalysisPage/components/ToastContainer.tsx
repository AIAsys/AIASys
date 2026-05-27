import React from "react";
import { FileUploadToast } from "../../../components/file/FileUploadToast";

interface ToastContainerProps {
  toasts: Array<{ id: string; message: string; type: "success" | "error" }>;
}

export const ToastContainer: React.FC<ToastContainerProps> = ({ toasts }) => {
  return (
    <div className="fixed bottom-4 right-4 z-50 space-y-2">
      {toasts.map((toast) => (
        <FileUploadToast
          key={toast.id}
          message={toast.message}
          type={toast.type}
          duration={3000}
        />
      ))}
    </div>
  );
};
