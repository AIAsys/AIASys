import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

export interface KnowledgeDialogNavItem<TTab extends string> {
  id: TTab;
  label: string;
  description: string;
  icon: LucideIcon;
}

interface KnowledgeDialogScaffoldProps<TTab extends string> {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  sidebarSummary: string;
  activeTab: TTab;
  navItems: Array<KnowledgeDialogNavItem<TTab>>;
  onTabChange: (tab: TTab) => void;
  children: ReactNode;
  testIdPrefix: string;
  sidebarFooter?: ReactNode;
}

export function KnowledgeDialogScaffold<TTab extends string>({
  open,
  onOpenChange,
  title,
  description,
  sidebarSummary,
  activeTab,
  navItems,
  onTabChange,
  children,
  testIdPrefix,
  sidebarFooter,
}: KnowledgeDialogScaffoldProps<TTab>) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="grid h-[88vh] max-w-[min(1480px,96vw)] grid-cols-[252px_minmax(0,1fr)] gap-0 overflow-hidden p-0">
        <DialogTitle className="sr-only">{title}</DialogTitle>
        <DialogDescription className="sr-only">{description}</DialogDescription>

        <aside className="flex min-h-0 flex-col border-r bg-muted/20">
          <div className="border-b px-5 py-5">
            <div className="text-sm font-semibold text-foreground">{title}</div>
            <div className="mt-1 text-xs leading-5 text-muted-foreground">
              {sidebarSummary}
            </div>
          </div>

          <div className="flex-1 space-y-2 p-3">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = item.id === activeTab;
              return (
                <button
                  key={item.id}
                  type="button"
                  data-testid={`${testIdPrefix}-tab-${item.id}`}
                  onClick={() => onTabChange(item.id)}
                  className={cn(
                    "w-full rounded-2xl border px-4 py-3 text-left transition-colors",
                    active
                      ? "border-border bg-background shadow-sm"
                      : "border-transparent hover:border-border/60 hover:bg-background/60",
                  )}
                >
                  <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                    <Icon className="h-4 w-4 text-muted-foreground" />
                    {item.label}
                  </div>
                  <div className="mt-1 text-xs leading-5 text-muted-foreground">
                    {item.description}
                  </div>
                </button>
              );
            })}
          </div>

          {sidebarFooter ? (
            <div className="border-t p-3">{sidebarFooter}</div>
          ) : null}
        </aside>

        <div className="min-h-0 overflow-hidden bg-background">{children}</div>
      </DialogContent>
    </Dialog>
  );
}
