export function DockStatusChip({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full border border-border bg-background px-2.5 py-1 text-[11px] font-medium text-muted-foreground ${className}`}
    >
      {children}
    </span>
  );
}
