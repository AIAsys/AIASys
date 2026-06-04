import type { ReactNode } from "react";

export function getText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export function getNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

export function getBoolean(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

export function MetadataRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="grid gap-1 rounded-md border border-border bg-background px-3 py-2">
      <div className="text-[11px] font-medium text-muted-foreground">
        {label}
      </div>
      <div
        className={
          mono
            ? "break-all font-mono text-xs leading-5 text-foreground"
            : "text-sm leading-5 text-foreground"
        }
      >
        {value}
      </div>
    </div>
  );
}
