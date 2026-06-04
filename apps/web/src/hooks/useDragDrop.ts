import { useState, useCallback } from "react";

export interface UseDragDropResult {
  isDragging: boolean;
  dragProps: {
    onDragEnter: (e: React.DragEvent) => void;
    onDragOver: (e: React.DragEvent) => void;
    onDragLeave: (e: React.DragEvent) => void;
    onDrop: (e: React.DragEvent) => void;
  };
}

function hasDraggedFiles(dataTransfer: DataTransfer): boolean {
  return (
    Array.from(dataTransfer.types).includes("Files") ||
    dataTransfer.files.length > 0
  );
}

export function useDragDrop(onDropCallback: (files: FileList) => void): UseDragDropResult {
  const [isDragging, setIsDragging] = useState(false);

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    if (!hasDraggedFiles(e.dataTransfer)) {
      return;
    }
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    if (!hasDraggedFiles(e.dataTransfer)) {
      return;
    }
    e.preventDefault();
    e.stopPropagation();
    if (!isDragging) {
      setIsDragging(true);
    }
  }, [isDragging]);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    if (!isDragging) {
      return;
    }
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, [isDragging]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    if (!isDragging && e.dataTransfer.files.length === 0) {
      return;
    }
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      onDropCallback(e.dataTransfer.files);
    }
  }, [onDropCallback, isDragging]);

  return {
    isDragging,
    dragProps: {
      onDragEnter: handleDragEnter,
      onDragOver: handleDragOver,
      onDragLeave: handleDragLeave,
      onDrop: handleDrop,
    },
  };
}
