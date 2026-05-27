/**
 * Skills 管理 Hook（全局存储 + 工作区复制启用模型）
 *
 * 当前口径：
 * - 内置仓库 `skills/builtin/`：系统预装 skill，不可删除
 * - 用户仓库 `skills/store/`：用户导入 skill（zip / 外部市场）
 * - Skill 仓库展示 = builtin + store 合并，builtin 标记 source="builtin"
 * - 工作区启用 = 复制：`workspaces/{user_id}/{workspace_id}/.aiasys/skills/{name}`
 * - 我的默认启用：`global_workspace/.aiasys/skills/{name}` 跨工作区共享
 * - 前端展示两个面板：Skill 仓库 + 工作区已启用
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { API_ENDPOINTS } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";
import type {
  SessionSkill,
  MarketSkill,
  StoreSkill,
  StoreSkillsListResponse,
  SkillEntryResponse,
  SkillReadmeResponse,
  SkillInstallResponse,
  SkillEnableRequest,
  SkillDisableRequest,
  WorkspaceSkillPackage,
  WorkspaceSkillsListResponse,
} from "@/types/api";

export interface UseSkillsReturn {
  /** 当前工作区已启用的 Skills */
  sessionSkills: SessionSkill[];
  /** 我的默认已启用的 Skills */
  globalSkills: SessionSkill[];
  /** Skill 仓库 Skills */
  storeSkills: StoreSkill[];
  /** Skill 市场视图数据 */
  marketSkills: MarketSkill[];
  /** 是否加载中 */
  isLoading: boolean;
  /** 错误信息 */
  error: string | null;
  /** 加载Skill 仓库 Skills */
  loadStoreSkills: () => Promise<void>;
  /** 加载当前工作区已启用 Skills */
  loadEnabledSkills: (workspaceId: string) => Promise<void>;
  /** 加载我的默认已启用 Skills */
  loadGlobalSkills: () => Promise<void>;
  /** 加载 Skill 市场视图数据 */
  loadMarketSkills: (workspaceId?: string | null) => Promise<void>;
  /** 启用 Skill（复制到工作区） */
  enableSkill: (workspaceId: string, skillName: string, version?: string | null) => Promise<boolean>;
  /** 禁用 Skill（删除工作区目录） */
  disableSkill: (workspaceId: string, skillName: string) => Promise<boolean>;
  /** 更新 Skill（从源重新复制） */
  updateSkill: (workspaceId: string, skillName: string) => Promise<boolean>;
  /** 启用到我的默认 Skill */
  enableGlobalSkill: (skillName: string, version?: string | null) => Promise<boolean>;
  /** 从我的默认禁用 Skill */
  disableGlobalSkill: (skillName: string) => Promise<boolean>;
  /** 导入 zip Skill 包到 Skill 仓库 */
  importSkillArchive: (file: File) => Promise<boolean>;
  /** 从 Skill 仓库删除 Skill */
  removeStoreSkill: (skillName: string) => Promise<boolean>;
  /** 获取 Skill 入口内容 */
  getSkillEntryContent: (
    workspaceId: string,
    skillName: string,
  ) => Promise<SkillEntryResponse | null>;
  /** 获取 Skill README 内容 */
  getSkillReadmeContent: (
    workspaceId: string,
    skillName: string,
  ) => Promise<SkillReadmeResponse | null>;
}

function buildMarketSkills(
  storeSkills: StoreSkill[],
  enabledSkills: WorkspaceSkillPackage[],
  globalSkills: WorkspaceSkillPackage[] = [],
): MarketSkill[] {
  const enabledMap = new Map(
    enabledSkills.map((skill) => [skill.name, skill] as const),
  );
  const globalMap = new Map(
    globalSkills.map((skill) => [skill.name, true] as const),
  );

  return storeSkills.map((skill) => {
    const enabled = enabledMap.get(skill.name);
    const globallyEnabled = globalMap.has(skill.name);
    return {
      name: skill.name,
      display_name: skill.display_name,
      description: skill.description,
      installed: Boolean(enabled),
      globally_enabled: globallyEnabled || skill.globally_enabled,
      source: enabled ? "workspace" : skill.source,
      versions: skill.versions,
      env_fields: skill.env_fields,
      hash_status: enabled?.hash_status,
      version: enabled?.version,
    };
  });
}

/**
 * Skills 管理 Hook
 */
export function useSkills(): UseSkillsReturn {
  const [sessionSkills, setSessionSkills] = useState<SessionSkill[]>([]);
  const [globalSkills, setGlobalSkills] = useState<SessionSkill[]>([]);
  const [storeSkills, setStoreSkills] = useState<StoreSkill[]>([]);
  const [marketSkills, setMarketSkills] = useState<MarketSkill[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const safeSet = useCallback(<T,>(
    setter: React.Dispatch<React.SetStateAction<T>>,
    value: NoInfer<T>,
  ) => {
    if (isMountedRef.current) {
      setter(value);
    }
  }, []);

  /**
   * 加载Skill 仓库 Skills 列表
   */
  const loadStoreSkills = useCallback(async () => {
    safeSet(setIsLoading, true);
    safeSet(setError, null);

    try {
      const data = await apiRequest<StoreSkillsListResponse>(
        API_ENDPOINTS.SKILLS_STORE_LIST,
      );
      safeSet(setStoreSkills, data.skills || []);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "未知错误";
      safeSet(setError, errorMsg);
    } finally {
      safeSet(setIsLoading, false);
    }
  }, []);

  /**
   * 加载当前工作区已启用 Skills 列表
   */
  const loadEnabledSkills = useCallback(async (workspaceId: string) => {
    safeSet(setIsLoading, true);
    safeSet(setError, null);

    try {
      const endpoint = API_ENDPOINTS.SKILLS_WORKSPACE_LIST(workspaceId);
      const data = await apiRequest<WorkspaceSkillsListResponse>(endpoint);
      const skills = data.skills || [];
      safeSet(setSessionSkills,
        skills.map((skill) => ({
          name: skill.name,
          display_name: skill.display_name,
          description: skill.description,
          enabled: true,
          source: skill.source,
        })),
      );
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "未知错误";
      safeSet(setError, errorMsg);
    } finally {
      safeSet(setIsLoading, false);
    }
  }, []);

  /**
   * 加载我的默认已启用 Skills 列表
   */
  const loadGlobalSkills = useCallback(async () => {
    safeSet(setIsLoading, true);
    safeSet(setError, null);

    try {
      const data = await apiRequest<WorkspaceSkillsListResponse>(
        API_ENDPOINTS.SKILLS_GLOBAL_LIST,
      );
      const skills = data.skills || [];
      safeSet(setGlobalSkills,
        skills.map((skill) => ({
          name: skill.name,
          display_name: skill.display_name,
          description: skill.description,
          enabled: true,
          source: skill.source,
        })),
      );
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "未知错误";
      safeSet(setError, errorMsg);
    } finally {
      safeSet(setIsLoading, false);
    }
  }, []);

  /**
   * 加载 Skill 市场视图数据，合并 Skill 仓库、我的默认启用和工作区已启用状态。
   */
  const loadMarketSkills = useCallback(async (workspaceId?: string | null) => {
    safeSet(setIsLoading, true);
    safeSet(setError, null);

    try {
      const [storeData, globalData, workspaceData] = await Promise.all([
        apiRequest<StoreSkillsListResponse>(API_ENDPOINTS.SKILLS_STORE_LIST),
        apiRequest<WorkspaceSkillsListResponse>(API_ENDPOINTS.SKILLS_GLOBAL_LIST).catch(() => null),
        workspaceId
          ? apiRequest<WorkspaceSkillsListResponse>(
              API_ENDPOINTS.SKILLS_WORKSPACE_LIST(workspaceId),
            )
          : Promise.resolve(null),
      ]);

      const store = storeData.skills || [];
      safeSet(setStoreSkills, store);

      const globalEnabled = globalData?.skills || [];
      safeSet(setGlobalSkills,
        globalEnabled.map((skill) => ({
          name: skill.name,
          display_name: skill.display_name,
          description: skill.description,
          enabled: true,
          source: skill.source,
        })),
      );

      const enabled = workspaceData?.skills || [];
      safeSet(setSessionSkills,
        enabled.map((skill) => ({
          name: skill.name,
          display_name: skill.display_name,
          description: skill.description,
          enabled: true,
          source: skill.source,
        })),
      );

      safeSet(setMarketSkills, buildMarketSkills(store, enabled, globalEnabled));
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "未知错误";
      safeSet(setError, errorMsg);
    } finally {
      safeSet(setIsLoading, false);
    }
  }, []);

  /**
   * 启用 Skill（复制到工作区）
   */
  const enableSkill = useCallback(
    async (workspaceId: string, skillName: string, version?: string | null): Promise<boolean> => {
      safeSet(setIsLoading, true);
      safeSet(setError, null);

      try {
        const endpoint = API_ENDPOINTS.SKILLS_WORKSPACE_ENABLE(workspaceId);
        const body: SkillEnableRequest = {
          skill_name: skillName,
          version: version || undefined,
        };

        const data = await apiRequest<SkillInstallResponse>(endpoint, {
          method: "POST",
          body,
        });

        if (data.success) {
          await loadEnabledSkills(workspaceId);
          await loadStoreSkills();
          return true;
        } else {
          safeSet(setError, data.message);
          return false;
        }
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : "未知错误";
        safeSet(setError, errorMsg);
        return false;
      } finally {
        safeSet(setIsLoading, false);
      }
    },
    [loadEnabledSkills, loadStoreSkills],
  );

  /**
   * 更新 Skill（从源重新复制）
   */
  const updateSkill = useCallback(
    async (workspaceId: string, skillName: string): Promise<boolean> => {
      safeSet(setIsLoading, true);
      safeSet(setError, null);

      try {
        const endpoint = API_ENDPOINTS.SKILLS_WORKSPACE_UPDATE(workspaceId);
        const body = { skill_name: skillName };

        const data = await apiRequest<SkillInstallResponse>(endpoint, {
          method: "POST",
          body,
        });

        if (data.success) {
          await loadEnabledSkills(workspaceId);
          await loadStoreSkills();
          return true;
        } else {
          safeSet(setError, data.message);
          return false;
        }
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : "未知错误";
        safeSet(setError, errorMsg);
        return false;
      } finally {
        safeSet(setIsLoading, false);
      }
    },
    [loadEnabledSkills, loadStoreSkills],
  );

  /**
   * 禁用 Skill（删除工作区目录）
   */
  const disableSkill = useCallback(
    async (workspaceId: string, skillName: string): Promise<boolean> => {
      safeSet(setIsLoading, true);
      safeSet(setError, null);

      try {
        const endpoint = API_ENDPOINTS.SKILLS_WORKSPACE_DISABLE(workspaceId);
        const body: SkillDisableRequest = {
          skill_name: skillName,
        };

        const data = await apiRequest<SkillInstallResponse>(endpoint, {
          method: "POST",
          body,
        });

        if (data.success) {
          await loadEnabledSkills(workspaceId);
          await loadStoreSkills();
          return true;
        } else {
          safeSet(setError, data.message);
          return false;
        }
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : "未知错误";
        safeSet(setError, errorMsg);
        return false;
      } finally {
        safeSet(setIsLoading, false);
      }
    },
    [loadEnabledSkills, loadStoreSkills],
  );

  /**
   * 启用到我的默认 Skill
   */
  const enableGlobalSkill = useCallback(
    async (skillName: string, version?: string | null): Promise<boolean> => {
      safeSet(setIsLoading, true);
      safeSet(setError, null);

      try {
        const body: SkillEnableRequest = {
          skill_name: skillName,
          version: version || undefined,
        };

        const data = await apiRequest<SkillInstallResponse>(
          API_ENDPOINTS.SKILLS_GLOBAL_ENABLE,
          {
            method: "POST",
            body,
          },
        );

        if (data.success) {
          await loadGlobalSkills();
          await loadStoreSkills();
          return true;
        } else {
          safeSet(setError, data.message);
          return false;
        }
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : "未知错误";
        safeSet(setError, errorMsg);
        return false;
      } finally {
        safeSet(setIsLoading, false);
      }
    },
    [loadGlobalSkills, loadStoreSkills],
  );

  /**
   * 全局禁用 Skill
   */
  const disableGlobalSkill = useCallback(
    async (skillName: string): Promise<boolean> => {
      safeSet(setIsLoading, true);
      safeSet(setError, null);

      try {
        const body: SkillDisableRequest = {
          skill_name: skillName,
        };

        const data = await apiRequest<SkillInstallResponse>(
          API_ENDPOINTS.SKILLS_GLOBAL_DISABLE,
          {
            method: "POST",
            body,
          },
        );

        if (data.success) {
          await loadGlobalSkills();
          await loadStoreSkills();
          return true;
        } else {
          safeSet(setError, data.message);
          return false;
        }
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : "未知错误";
        safeSet(setError, errorMsg);
        return false;
      } finally {
        safeSet(setIsLoading, false);
      }
    },
    [loadGlobalSkills, loadStoreSkills],
  );

  /**
   * 导入 zip Skill 包到 Skill 仓库
   */
  const importSkillArchive = useCallback(
    async (file: File): Promise<boolean> => {
      safeSet(setIsLoading, true);
      safeSet(setError, null);

      try {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("force", "false");

        const endpoint = API_ENDPOINTS.SKILLS_STORE_IMPORT;
        const data = await apiRequest<SkillInstallResponse>(endpoint, {
          method: "POST",
          body: formData,
        });

        if (!data.success) {
          safeSet(setError, data.message);
          return false;
        }

        await loadStoreSkills();
        return true;
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : "未知错误";
        safeSet(setError, errorMsg);
        return false;
      } finally {
        safeSet(setIsLoading, false);
      }
    },
    [loadStoreSkills],
  );

  /**
   * 从 Skill 仓库删除 Skill
   */
  const removeStoreSkill = useCallback(
    async (skillName: string): Promise<boolean> => {
      safeSet(setIsLoading, true);
      safeSet(setError, null);

      try {
        const endpoint = API_ENDPOINTS.SKILLS_STORE_DELETE(skillName);
        const data = await apiRequest<SkillInstallResponse>(endpoint, {
          method: "DELETE",
        });

        if (data.success) {
          await loadStoreSkills();
          return true;
        } else {
          safeSet(setError, data.message);
          return false;
        }
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : "未知错误";
        safeSet(setError, errorMsg);
        return false;
      } finally {
        safeSet(setIsLoading, false);
      }
    },
    [loadStoreSkills],
  );

  /**
   * 获取 Skill 入口内容
   */
  const getSkillEntryContent = useCallback(
    async (
      workspaceId: string,
      skillName: string,
    ): Promise<SkillEntryResponse | null> => {
      try {
        return await apiRequest<SkillEntryResponse>(
          API_ENDPOINTS.SKILLS_WORKSPACE_ENTRY(workspaceId, skillName),
          { cache: "no-store" },
        );
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : "未知错误";
        safeSet(setError, errorMsg);
        return null;
      }
    },
    [],
  );

  /**
   * 获取 Skill README 内容
   */
  const getSkillReadmeContent = useCallback(
    async (
      workspaceId: string,
      skillName: string,
    ): Promise<SkillReadmeResponse | null> => {
      try {
        return await apiRequest<SkillReadmeResponse>(
          API_ENDPOINTS.SKILLS_WORKSPACE_README(workspaceId, skillName),
          { cache: "no-store" },
        );
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : "未知错误";
        safeSet(setError, errorMsg);
        return null;
      }
    },
    [],
  );

  return {
    sessionSkills,
    globalSkills,
    storeSkills,
    marketSkills,
    isLoading,
    error,
    loadStoreSkills,
    loadEnabledSkills,
    loadGlobalSkills,
    loadMarketSkills,
    enableSkill,
    disableSkill,
    updateSkill,
    enableGlobalSkill,
    disableGlobalSkill,
    importSkillArchive,
    removeStoreSkill,
    getSkillEntryContent,
    getSkillReadmeContent,
  };
}
