/**
 * WorkspaceSummaryCards — 工作区概览卡片组件与工具函数。
 *
 * 从 WorkspaceContextPanel.tsx 提取的纯展示组件，不依赖父组件闭包状态。
 */

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type {
  WorkspaceOverviewResourceBucket,
} from "@/types/workspace";
import type { SessionRuntimeSummary } from "@/types/workspace";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export function getRuntimeStateLabel(lastRuntimeState?: string | null): string {
  switch (lastRuntimeState) {
    case "ready":
      return "已就绪";
    case "busy":
      return "执行中";
    case "not_started":
      return "尚未使用";
    case "released":
      return "已释放";
    case "refresh_required":
      return "待更新";
    case "available":
      return "已就绪";
    case "failed":
      return "上次失败";
    case "discarded":
      return "已释放";
    case "fresh":
      return "尚未使用";
    case "missing":
      return "已回收";
    default:
      return "等待执行";
  }
}

export function getRuntimeSummaryLabel(
  runtimeSummary?: SessionRuntimeSummary | null,
  lastRuntimeState?: string | null,
): string {
  return runtimeSummary?.status_label || getRuntimeStateLabel(lastRuntimeState);
}

export function getBucketCount(
  bucket?: WorkspaceOverviewResourceBucket | null,
): number {
  if (!bucket) {
    return 0;
  }
  return Math.max(
    bucket.runtime_available_count,
    bucket.session_attached_count,
  );
}

export function getBucketAvailabilityLabel(
  bucket?: WorkspaceOverviewResourceBucket | null,
): string {
  if (!bucket) {
    return "暂无数据";
  }
  if (bucket.disabled_reason) {
    return bucket.disabled_reason;
  }
  if (bucket.available) {
    return "可使用";
  }
  if (bucket.mounted) {
    return bucket.stale ? "已纳入，待检查" : "已纳入";
  }
  if (bucket.configured) {
    return "已配置，待启用";
  }
  return bucket.next_check_hint || "当前未配置";
}

export function getBucketStatusClass(
  bucket?: WorkspaceOverviewResourceBucket | null,
): string {
  if (!bucket) {
    return "";
  }
  if (bucket.status === "unavailable") {
    return "border-error/20 bg-error-container text-on-error-container";
  }
  if (bucket.stale || bucket.status === "degraded" || bucket.status === "not_verified") {
    return "border-warning/20 bg-warning-container text-on-warning-container";
  }
  if (bucket.available) {
    return "border-success/20 bg-success-container text-on-success-container";
  }
  if (bucket.configured || bucket.mounted) {
    return "border-tertiary/20 bg-tertiary-container text-on-tertiary-container";
  }
  return "";
}

// ---------------------------------------------------------------------------
// Components
// ---------------------------------------------------------------------------

export function SummaryChip({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap rounded-full border border-border bg-background px-2.5 py-1 text-[11px] font-medium text-muted-foreground ${className}`}
    >
      {children}
    </span>
  );
}

export function ResourceMetricCard({
  label,
  value,
  hint,
  onClick,
}: {
  label: string;
  value: React.ReactNode;
  hint: string;
  onClick?: () => void;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-border bg-card px-4 py-4 shadow-sm",
        onClick &&
          "cursor-pointer transition-all hover:border-tertiary/40 hover:shadow-md",
      )}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={(e) => {
        if (onClick && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onClick();
        }
      }}
    >
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="mt-3 text-3xl font-semibold tracking-tight text-foreground">
        {value}
      </div>
      <div className="mt-2 text-xs leading-5 text-muted-foreground">{hint}</div>
    </div>
  );
}

export function ResourceLayerStat({
  label,
  value,
}: {
  label: string;
  value: number;
}) {
  return (
    <div className="rounded-xl border border-border bg-muted/60 px-3 py-2">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-1 text-lg font-semibold text-foreground">{value}</div>
    </div>
  );
}

export function WorkspaceResourceMountCard({
  title,
  description,
  icon,
  bucket,
  actionLabel,
  onAction,
  secondaryActionLabel,
  onSecondaryAction,
  testId,
}: {
  title: string;
  description: string;
  icon: React.ReactNode;
  bucket?: WorkspaceOverviewResourceBucket | null;
  actionLabel?: string;
  onAction?: () => void;
  secondaryActionLabel?: string;
  onSecondaryAction?: () => void;
  testId?: string;
}) {
  const statusLabel = getBucketAvailabilityLabel(bucket);
  const detail = bucket?.detail || bucket?.next_check_hint || description;

  return (
    <section
      data-testid={testId}
      className="rounded-2xl border border-border bg-card px-5 py-5 shadow-sm"
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
            {icon}
            {title}
          </div>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            {detail}
          </p>
        </div>
        <SummaryChip className={getBucketStatusClass(bucket)}>
          {statusLabel}
        </SummaryChip>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <ResourceLayerStat label="我的资产" value={bucket?.user_asset_count ?? 0} />
        <ResourceLayerStat
          label="当前会话"
          value={bucket?.session_attached_count ?? 0}
        />
        <ResourceLayerStat
          label="运行时可用"
          value={bucket?.runtime_available_count ?? 0}
        />
      </div>

      {(actionLabel && onAction) || (secondaryActionLabel && onSecondaryAction) ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {actionLabel && onAction ? (
            <Button
              type="button"
              size="sm"
              className="h-8 rounded-xl px-3 text-[12px]"
              onClick={onAction}
            >
              {actionLabel}
            </Button>
          ) : null}
          {secondaryActionLabel && onSecondaryAction ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8 rounded-xl px-3 text-[12px]"
              onClick={onSecondaryAction}
            >
              {secondaryActionLabel}
            </Button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export function CenterCanvasHero({
  eyebrow,
  title,
  description,
  badge,
}: {
  eyebrow: string;
  title: string;
  description: string;
  badge?: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-border bg-card px-6 py-5 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="text-xs font-medium text-muted-foreground">
            {eyebrow}
          </div>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight text-foreground">
            {title}
          </h2>
          <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground">
            {description}
          </p>
        </div>
        {badge ? <div className="shrink-0">{badge}</div> : null}
      </div>
    </section>
  );
}

export function LocalResourceCard({
  title,
  count,
  items,
  icon,
  actionLabel,
  onAction,
  createLabel,
  onCreate,
  testId,
}: {
  title: string;
  count: number;
  items: Array<{ id: string; label: string; badge?: string }>;
  icon: React.ReactNode;
  actionLabel?: string;
  onAction?: () => void;
  createLabel?: string;
  onCreate?: () => void;
  testId?: string;
}) {
  return (
    <section
      data-testid={testId}
      className="rounded-2xl border border-border bg-card px-5 py-5 shadow-sm"
    >
      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
        {icon}
        {title}
        <span className="ml-auto text-xs font-normal text-muted-foreground">
          {count} 个
        </span>
      </div>
      {items.length > 0 ? (
        <div className="mt-3 flex flex-col gap-2">
          {items.map((item) => (
            <div
              key={item.id}
              className="flex items-center justify-between rounded-lg border border-border bg-muted/40 px-3 py-2"
            >
              <span className="truncate text-sm text-foreground">
                {item.label}
              </span>
              {item.badge ? (
                <SummaryChip>{item.badge}</SummaryChip>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-sm text-muted-foreground">暂无</p>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        {actionLabel && onAction ? (
          <Button
            type="button"
            size="sm"
            className="h-8 rounded-xl px-3 text-[12px]"
            onClick={onAction}
          >
            {actionLabel}
          </Button>
        ) : null}
        {createLabel && onCreate ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 rounded-xl px-3 text-[12px]"
            onClick={onCreate}
          >
            {createLabel}
          </Button>
        ) : null}
      </div>
    </section>
  );
}
