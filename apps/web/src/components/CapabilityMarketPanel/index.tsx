import { useState } from "react";
import { Puzzle, Plug } from "lucide-react";
import { cn } from "@/lib/utils";
import { SettingsSkillMarketPanel } from "@/components/settings/SettingsSkillMarketPanel";
import { SettingsMCPMarketPanel } from "@/components/settings/SettingsMCPMarketPanel";

interface CapabilityMarketPanelProps {
  workspaceId?: string | null;
}

type MarketKind = "skill" | "mcp";

interface NavGroup {
  id: MarketKind;
  label: string;
  icon: React.ReactNode;
  description: string;
}

const NAV_GROUPS: NavGroup[] = [
  {
    id: "skill",
    label: "技能",
    icon: <Puzzle className="h-4 w-4" />,
    description: "管理内置技能、全局默认和外部技能市场",
  },
  {
    id: "mcp",
    label: "连接器",
    icon: <Plug className="h-4 w-4" />,
    description: "管理内置连接器和外部连接器市场",
  },
];

export function CapabilityMarketPanel({ workspaceId }: CapabilityMarketPanelProps) {
  const [activeKind, setActiveKind] = useState<MarketKind>("skill");

  return (
    <div className="flex h-full">
      {/* 左侧 Kind 导航 */}
      <div className="w-48 shrink-0 border-r bg-muted/30">
        <div className="px-3 py-2 text-xs font-medium text-muted-foreground">
          能力市场
        </div>
        <nav className="space-y-0.5 px-2">
          {NAV_GROUPS.map((group) => (
            <button
              key={group.id}
              type="button"
              onClick={() => setActiveKind(group.id)}
              className={cn(
                "flex w-full flex-col gap-0.5 rounded-md px-2.5 py-2 text-left text-sm transition-colors",
                activeKind === group.id
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <div className="flex items-center gap-1.5">
                {group.icon}
                <span className="font-medium">{group.label}</span>
              </div>
              <span className="text-[10px] leading-tight opacity-70">
                {group.description}
              </span>
            </button>
          ))}
        </nav>
      </div>

      {/* 右侧内容 */}
      <div className="min-w-0 flex-1 overflow-hidden">
        {activeKind === "skill" ? (
          <SettingsSkillMarketPanel workspaceId={workspaceId ?? null} />
        ) : (
          <SettingsMCPMarketPanel />
        )}
      </div>
    </div>
  );
}
