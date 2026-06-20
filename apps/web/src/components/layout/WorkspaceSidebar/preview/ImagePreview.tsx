/**
 * 图片预览组件
 * 在预览面板内显示图片，支持缩放控制
 */

import { Download, RotateCcw, ZoomIn, ZoomOut } from "lucide-react";
import React, { useState } from "react";

interface ImagePreviewProps {
  url: string;
  fileName: string;
}

export const ImagePreview: React.FC<ImagePreviewProps> = ({
  url,
  fileName,
}) => {
  const [scale, setScale] = useState(1);

  const handleZoomIn = () => setScale((prev) => Math.min(prev + 0.25, 3));
  const handleZoomOut = () => setScale((prev) => Math.max(prev - 0.25, 0.25));
  const handleReset = () => setScale(1);

  return (
    <div className="flex flex-col h-full bg-muted/20">
      {/* 工具栏 */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-background">
        <span
          className="text-xs font-mono text-muted-foreground truncate max-w-[60%]"
          title={fileName}
        >
          {fileName}
        </span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={handleZoomOut}
            className="p-1.5 hover:bg-muted rounded-md text-muted-foreground hover:text-foreground transition-colors"
            title="缩小"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </button>
          <span className="text-[10px] font-mono text-muted-foreground w-10 text-center">
            {Math.round(scale * 100)}%
          </span>
          <button
            type="button"
            onClick={handleZoomIn}
            className="p-1.5 hover:bg-muted rounded-md text-muted-foreground hover:text-foreground transition-colors"
            title="放大"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={handleReset}
            className="p-1.5 hover:bg-muted rounded-md text-muted-foreground hover:text-foreground transition-colors"
            title="重置"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
          <div className="w-px h-4 bg-border mx-1" />
          <a
            href={url}
            download={fileName}
            className="p-1.5 hover:bg-muted rounded-md text-muted-foreground hover:text-foreground transition-colors"
            title="下载"
          >
            <Download className="w-3.5 h-3.5" />
          </a>
        </div>
      </div>

      {/* 图片显示区 */}
      <div className="flex-1 overflow-auto flex items-center justify-center p-4">
        <img
          src={url}
          alt={fileName}
          className="max-w-full max-h-full object-contain rounded-md shadow-sm transition-transform duration-200"
          style={{ transform: `scale(${scale})` }}
          draggable={false}
        />
      </div>
    </div>
  );
};
