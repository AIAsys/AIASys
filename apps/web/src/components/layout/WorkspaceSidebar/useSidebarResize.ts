import { useEffect, useRef, useState } from "react";

export function useSidebarResize(
  initialWidth: number,
  onWidthChange?: (width: number) => void,
) {
  const [isDragging, setIsDragging] = useState(false);
  const dragStartX = useRef(0);
  const dragStartWidth = useRef(0);
  const onWidthChangeRef = useRef(onWidthChange);
  onWidthChangeRef.current = onWidthChange;

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      const deltaX = dragStartX.current - e.clientX;
      const newWidth = Math.min(
        Math.max(350, dragStartWidth.current + deltaX),
        window.innerWidth * 0.5,
      );
      onWidthChangeRef.current?.(newWidth);
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
  }, [isDragging]);

  const handleDragStart = (e: React.MouseEvent) => {
    dragStartX.current = e.clientX;
    dragStartWidth.current = initialWidth;
    setIsDragging(true);
  };

  return {
    isDragging,
    handleDragStart,
  };
}
