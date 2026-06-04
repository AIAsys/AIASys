import { cn } from "@/lib/utils";

type PillProps = {
  children: React.ReactNode;
  className?: string;
};

export const Pill = ({ children, className }: PillProps) => {
  return (
    <div
      className={cn(
        "inline-flex h-9 items-center justify-center gap-3 rounded-full border border-foreground/10 bg-white/72 px-4 text-[12px] font-medium tracking-[0.08em] text-muted-foreground shadow-[0_16px_40px_-28px_rgba(15,23,42,0.45)] backdrop-blur-md",
        className,
      )}
    >
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-foreground" />
      {children}
    </div>
  );
};
