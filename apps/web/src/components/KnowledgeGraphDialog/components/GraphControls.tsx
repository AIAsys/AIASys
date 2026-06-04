import { LocateFixed, Minus, Plus, RotateCcw } from "lucide-react";
import type { RefObject } from "react";
import type { PixiGraphViewport } from "../lib/pixiGraph";

interface GraphControlsProps {
  graphRef: RefObject<PixiGraphViewport | null>;
  graphReady: boolean;
}

export function GraphControls({ graphRef, graphReady }: GraphControlsProps) {
  const baseButtonClass =
    "flex h-9 w-9 items-center justify-center rounded-xl border border-border bg-background text-foreground transition hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50";

  return (
    <div className="pointer-events-none absolute left-4 top-4 z-20 flex items-center gap-2">
      <div className="pointer-events-auto flex flex-col gap-2 rounded-2xl border border-border bg-card/95 p-2 shadow-sm backdrop-blur">
        <button
          type="button"
          className={baseButtonClass}
          title="放大"
          disabled={!graphReady}
          onClick={() => graphRef.current?.zoomBy(1.18)}
        >
          <Plus className="h-4 w-4" />
        </button>
        <button
          type="button"
          className={baseButtonClass}
          title="缩小"
          disabled={!graphReady}
          onClick={() => graphRef.current?.zoomBy(1 / 1.18)}
        >
          <Minus className="h-4 w-4" />
        </button>
        <button
          type="button"
          className={baseButtonClass}
          title="适应画布"
          disabled={!graphReady}
          onClick={() => graphRef.current?.fitToView()}
        >
          <LocateFixed className="h-4 w-4" />
        </button>
        <button
          type="button"
          className={baseButtonClass}
          title="重置缩放"
          disabled={!graphReady}
          onClick={() => graphRef.current?.resetView()}
        >
          <RotateCcw className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
