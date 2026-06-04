import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

const ENTITY_TYPE_LABELS: Record<string, string> = {
  person: "人物",
  organization: "组织",
  technology: "技术",
  concept: "概念",
  product: "产品",
  industry: "行业",
  event: "事件",
  location: "地点",
  unknown: "未知",
};

const ENTITY_TYPE_STYLES: Record<string, string> = {
  person: "border-info/20 bg-info-container text-tertiary",
  organization: "border-success/20 bg-success-container text-success",
  technology: "border-info/20 bg-info-container text-info",
  concept: "border-warning/20 bg-warning-container text-warning",
  product: "border-error/20 bg-error-container text-error",
  industry: "border-info/20 bg-info-container text-info",
  event: "border-info/20 bg-info-container text-info",
  location: "border-success/20 bg-success-container text-success",
  unknown: "border-border bg-muted text-muted-foreground",
};

export function normalizeDisplayText(value?: string | null): string {
  const raw = value?.trim();
  if (!raw) {
    return "";
  }

  const pairs: Array<[string, string]> = [
    ['"', '"'],
    ["'", "'"],
    ["`", "`"],
  ];

  for (const [start, end] of pairs) {
    if (raw.startsWith(start) && raw.endsWith(end) && raw.length >= 2) {
      return raw.slice(1, -1).trim();
    }
  }

  return raw;
}

export function normalizeEntityType(value?: string | null): string {
  const normalized = normalizeDisplayText(value || "unknown").toLowerCase();
  return normalized || "unknown";
}

export function getEntityTypeLabel(value?: string | null): string {
  const normalized = normalizeEntityType(value);
  return ENTITY_TYPE_LABELS[normalized] || normalized;
}

function getEntityTypeClasses(value?: string | null): string {
  const normalized = normalizeEntityType(value);
  return ENTITY_TYPE_STYLES[normalized] || ENTITY_TYPE_STYLES.unknown;
}

export function formatGraphNumber(value?: number | null): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "--";
  }
  return new Intl.NumberFormat("zh-CN").format(value);
}

export function formatMetadataValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "--";
  }
  if (typeof value === "string") {
    return normalizeDisplayText(value);
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map((item) => formatMetadataValue(item)).join(", ");
  }
  return JSON.stringify(value, null, 2);
}

export function EntityTypeBadge({
  entityType,
  className,
}: {
  entityType?: string | null;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium",
        getEntityTypeClasses(entityType),
        className,
      )}
    >
      {getEntityTypeLabel(entityType)}
    </span>
  );
}

export function MetricCard({
  label,
  value,
  helper,
}: {
  label: string;
  value: ReactNode;
  helper?: ReactNode;
}) {
  return (
    <Card className="border-border/80 shadow-sm">
      <CardContent className="p-5">
        <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
          {label}
        </div>
        <div className="mt-3 text-3xl font-semibold text-foreground">{value}</div>
        {helper ? (
          <div className="mt-2 text-sm text-muted-foreground">{helper}</div>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function EmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-2xl border border-dashed border-border bg-white/80 p-8 text-center">
      <h3 className="text-lg font-semibold text-foreground">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p>
    </div>
  );
}
