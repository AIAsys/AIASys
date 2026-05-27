import { useEffect, useRef, useState } from "react";
import { ServerCog, Store } from "lucide-react";

import { SkillMarket } from "@/components/SkillMarket";
import { ExternalSkillMarketPanel } from "@/components/settings/ExternalSkillMarketPanel";
import { useSkills } from "@/hooks/useSkills";
import { cn } from "@/lib/utils";
import type { MarketSkill, SkillEntryResponse } from "@/types/api";

type SkillMarketTabId = "builtin" | "external";

const TABS: Array<{
  id: SkillMarketTabId;
  label: string;
  description: string;
  icon: typeof ServerCog;
}> = [
  {
    id: "builtin",
    label: "技能仓库",
    description: "系统内置和已导入的技能",
    icon: ServerCog,
  },
  {
    id: "external",
    label: "外部技能市场",
    description: "从外部来源安装技能",
    icon: Store,
  },
];

interface SettingsSkillMarketPanelProps {
  workspaceId?: string | null;
  skills?: MarketSkill[];
  isLoading?: boolean;
  onLoad?: () => void;
  onInstall?: (skillName: string, version?: string) => Promise<boolean>;
  onUninstall?: (skillName: string) => Promise<boolean>;
  onImportArchive?: (file: File) => Promise<boolean>;
  onViewEntry?: (skillName: string) => Promise<SkillEntryResponse | null>;
  activeTab?: SkillMarketTabId;
  onActiveTabChange?: (tab: SkillMarketTabId) => void;
  hideTabBar?: boolean;
}

export function SettingsSkillMarketPanel({
  workspaceId,
  skills,
  isLoading,
  onLoad,
  onInstall,
  onUninstall,
  onImportArchive,
  onViewEntry,
  activeTab: controlledActiveTab,
  onActiveTabChange,
  hideTabBar = false,
}: SettingsSkillMarketPanelProps) {
  const [internalActiveTab, setInternalActiveTab] = useState<SkillMarketTabId>("builtin");
  const activeTab = controlledActiveTab !== undefined ? controlledActiveTab : internalActiveTab;
  const setActiveTab = (tab: SkillMarketTabId) => {
    if (onActiveTabChange) {
      onActiveTabChange(tab);
    } else {
      setInternalActiveTab(tab);
    }
  };
  const {
    marketSkills: internalSkills,
    isLoading: internalLoading,
    loadMarketSkills,
    enableSkill: enableWorkspaceSkill,
    disableSkill: disableWorkspaceSkill,
    updateSkill,
    enableGlobalSkill,
    disableGlobalSkill,
    importSkillArchive,
    getSkillEntryContent,
    getSkillReadmeContent,
    removeStoreSkill,
  } = useSkills();
  const lastLoadedScopeRef = useRef<string | null>(null);
  const isControlled =
    Array.isArray(skills) &&
    typeof isLoading === "boolean" &&
    typeof onLoad === "function" &&
    typeof onInstall === "function" &&
    typeof onUninstall === "function" &&
    typeof onViewEntry === "function";

  const resolvedSkills = isControlled ? skills : internalSkills;
  const resolvedLoading = isControlled ? isLoading : internalLoading;
  const installedSkillNames = (resolvedSkills || [])
    .filter((skill) => skill.installed)
    .map((skill) => skill.name);

  useEffect(() => {
    const scopeKey = workspaceId ?? "__catalog__";
    if (lastLoadedScopeRef.current === scopeKey) {
      return;
    }
    lastLoadedScopeRef.current = scopeKey;
    if (isControlled) {
      void onLoad?.();
      return;
    }
    void loadMarketSkills(workspaceId);
  }, [isControlled, loadMarketSkills, onLoad, workspaceId]);

  const handleInstall = async (skillName: string, version?: string) => {
    if (onInstall) {
      return onInstall(skillName, version);
    }
    if (!workspaceId) {
      return false;
    }
    return enableWorkspaceSkill(workspaceId, skillName, version || undefined);
  };

  const handleUninstall = async (skillName: string) => {
    if (onUninstall) {
      return onUninstall(skillName);
    }
    if (!workspaceId) {
      return false;
    }
    return disableWorkspaceSkill(workspaceId, skillName);
  };

  const handleUpdate = async (skillName: string) => {
    if (!workspaceId) {
      return false;
    }
    return updateSkill(workspaceId, skillName);
  };

  const handleToggleGlobal = async (skillName: string, enabled: boolean) => {
    if (enabled) {
      return disableGlobalSkill(skillName);
    }
    return enableGlobalSkill(skillName);
  };

  const handleImportArchive = onImportArchive
    ? onImportArchive
    : workspaceId
      ? (file: File) => importSkillArchive(file)
      : undefined;

  const handleViewEntry = onViewEntry
    ? onViewEntry
    : workspaceId
      ? (skillName: string) => getSkillEntryContent(workspaceId, skillName)
      : undefined;

  const handleViewReadme = workspaceId
    ? (skillName: string) => getSkillReadmeContent(workspaceId, skillName)
    : undefined;

  const reloadLocalSkills = async () => {
    if (isControlled) {
      await onLoad?.();
      return;
    }
    await loadMarketSkills(workspaceId);
  };



  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      {!hideTabBar && (
        <div className="shrink-0 px-1 pt-1 pb-2">
          <div className="flex rounded-md bg-muted p-0.5">
            {TABS.map((tab) => {
              const active = tab.id === activeTab;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    "flex-1 px-3 py-1.5 text-xs text-center rounded transition-colors",
                    active
                      ? "bg-background text-foreground shadow-sm font-medium"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>
        </div>
      )}

      <div className="flex-1 min-h-0 overflow-hidden p-4">
        {activeTab === "builtin" ? (
          <SkillMarket
            workspaceId={workspaceId}
            marketSkills={resolvedSkills || []}
            isLoading={resolvedLoading || false}
            onInstall={handleInstall}
            onUninstall={handleUninstall}
            onUpdate={handleUpdate}
            onToggleGlobal={handleToggleGlobal}
            onImportArchive={handleImportArchive}
            onViewEntry={handleViewEntry}
            onViewReadme={handleViewReadme}
            onRemoveStore={(name) => removeStoreSkill(name)}
          />
        ) : null}

        {activeTab === "external" ? (
          <ExternalSkillMarketPanel
            workspaceId={workspaceId}
            installedSkillNames={installedSkillNames}
            onInstalled={() => {
              void reloadLocalSkills();
            }}
          />
        ) : null}
      </div>
    </div>
  );
}
