import { Download, FileJson } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { RenderPlan } from "./types";

interface ChartCardProps {
  renderPlan: RenderPlan | null;
  sourceLabel: string;
  variant: "chat" | "workspace";
  className?: string;
  canExportPng?: boolean;
  onExportPng?: () => void;
  children: React.ReactNode;
}

export function ChartCard({
  renderPlan,
  sourceLabel,
  variant,
  className,
  canExportPng = false,
  onExportPng,
  children,
}: ChartCardProps) {
  const layoutClasses =
    variant === "workspace"
      ? {
          root: "not-prose flex h-full flex-col bg-background",
          body: "flex-1 p-4",
        }
      : {
          root:
            "not-prose my-4 overflow-hidden rounded-xl border border-border bg-background shadow-sm",
          body: "p-4",
        };

  return (
    <div className={cn(layoutClasses.root, className)}>
      <div className="border-b border-border px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-sm font-medium text-foreground">
              {renderPlan?.title || "交互式图表"}
            </div>
            {renderPlan?.description ? (
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                {renderPlan.description}
              </p>
            ) : null}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className="h-7 w-7 text-muted-foreground hover:text-foreground"
                  disabled={!canExportPng}
                  onClick={onExportPng}
                  aria-label="导出 PNG"
                >
                  <Download className="h-3.5 w-3.5" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>导出 PNG</TooltipContent>
            </Tooltip>
            <div className="flex items-center gap-1 rounded-full bg-muted px-2 py-1 text-[11px] text-muted-foreground">
              <FileJson className="h-3.5 w-3.5" />
              <span>ECharts</span>
            </div>
          </div>
        </div>
        <div className="mt-2 truncate text-[11px] text-muted-foreground">
          {sourceLabel}
        </div>
      </div>

      <div className={layoutClasses.body}>{children}</div>
    </div>
  );
}
