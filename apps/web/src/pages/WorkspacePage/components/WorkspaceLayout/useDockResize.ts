import { useEffect, useRef, useState } from "react";

// 独立于主侧栏的轻量拖拽 hook，避免 dock 继续共享 analysis 主 chunk 里的 sidebar 运行时。
export function useDockResize(
  initialWidth: number,
  onWidthChange?: (width: number) => void,
) {
  const [isDragging, setIsDragging] = useState(false);
  const dragStartX = useRef(0);
  const dragStartWidth = useRef(0);

  useEffect(() => {
    if (!isDragging) {
      return;
    }

    const handleMouseMove = (event: MouseEvent) => {
      const deltaX = dragStartX.current - event.clientX;
      const maxWidth = Math.max(360, window.innerWidth * 0.6);
      const newWidth = Math.min(
        Math.max(360, dragStartWidth.current + deltaX),
        maxWidth,
      );
      onWidthChange?.(newWidth);
    };

    const handleMouseUp = () => {
      setIsDragging(false);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isDragging, onWidthChange]);

  const handleDragStart = (event: React.MouseEvent) => {
    dragStartX.current = event.clientX;
    dragStartWidth.current = initialWidth;
    setIsDragging(true);
  };

  return {
    isDragging,
    handleDragStart,
  };
}
