import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

export function SectionBlock({
  title,
  description,
  icon: Icon,
  children,
}: {
  title: string;
  description?: string;
  icon: LucideIcon;
  children: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-border bg-background p-4">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border bg-muted/20">
          <Icon className="h-4 w-4 text-muted-foreground" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-foreground">{title}</div>
          {description ? (
            <div className="mt-1 text-[12px] leading-5 text-muted-foreground">
              {description}
            </div>
          ) : null}
        </div>
      </div>
      <div className="mt-4 space-y-4">{children}</div>
    </section>
  );
}

export function ChoiceButton<TValue extends string>({
  value,
  selected,
  label,
  description,
  icon: Icon,
  disabled,
  onSelect,
}: {
  value: TValue;
  selected: boolean;
  label: string;
  description: string;
  icon?: LucideIcon;
  disabled?: boolean;
  onSelect: (value: TValue) => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      disabled={disabled}
      className={cn(
        "group flex min-h-[82px] w-full items-start gap-3 rounded-xl border px-3 py-3 text-left transition",
        selected
          ? "border-foreground bg-foreground text-background shadow-sm"
          : "border-border bg-background hover:border-foreground/30 hover:bg-muted/20",
        disabled &&
          "cursor-not-allowed opacity-50 hover:border-border hover:bg-background",
      )}
      onClick={() => onSelect(value)}
    >
      {Icon ? (
        <span
          className={cn(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border",
            selected
              ? "border-background/20 bg-background/10"
              : "border-border bg-muted/15",
          )}
        >
          <Icon
            className={cn(
              "h-4 w-4",
              selected ? "text-background" : "text-muted-foreground",
            )}
          />
        </span>
      ) : null}
      <span className="min-w-0">
        <span className="block text-sm font-semibold">{label}</span>
        <span
          className={cn(
            "mt-1 block text-[12px] leading-5",
            selected ? "text-background/75" : "text-muted-foreground",
          )}
        >
          {description}
        </span>
      </span>
    </button>
  );
}

export function PreviewRow({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="border-t border-border/70 py-3 first:border-t-0 first:pt-0 last:pb-0">
      <div className="text-[11px] font-semibold text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 text-sm font-medium leading-6 text-foreground">
        {value}
      </div>
      {hint ? (
        <div className="mt-1 text-[11px] leading-5 text-muted-foreground">
          {hint}
        </div>
      ) : null}
    </div>
  );
}

export function ToggleRow({
  title,
  description,
  checked,
  onCheckedChange,
}: {
  title: string;
  description: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-xl border border-border bg-muted/10 px-3 py-3">
      <div>
        <div className="text-sm font-medium text-foreground">{title}</div>
        <div className="mt-1 text-[12px] leading-5 text-muted-foreground">
          {description}
        </div>
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  );
}
