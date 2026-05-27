/**
 * MCP 管理 Hook（三层合并模型）
 *
 * 支持两种使用模式：
 * 1. 我的默认 MCP 管理（无需 workspaceId）
 * 2. 工作区配置管理（需要 workspaceId）
 */

import { useState, useEffect, useCallback, useRef } from "react";
import {
  getMCPStoreList,
  getMCPWorkspaceList,
  saveMCPStoreServer,
  deleteMCPStoreServer,
  addMCPWorkspaceServer,
  removeMCPWorkspaceServer,
  getMCPWorkspaceServerTools,
  updateMCPWorkspaceServerEnabledTools,
  type MCPServerConfig,
  type MCPToolInfo,
} from "@/lib/api/mcp";

export interface MCPStoreEnvField {
  name: string;
  required: boolean;
  description?: string;
  default_value?: string;
}

export interface MCPStoreItem {
  name: string;
  display_name: string;
  type: string;
  url?: string;
  command?: string;
  args?: string[];
  headers?: Record<string, string>;
  env?: Record<string, string>;
  env_schema?: Record<string, string>;
  env_fields?: MCPStoreEnvField[];
  readme_excerpt?: string;
  description?: string;
  timeout_ms?: number;
  is_system_default: boolean;
  auto_attach_modes?: string[];
  enabled_tools?: string[];
}

export interface MCPWorkspaceItem {
  name: string;
  display_name: string;
  type: string;
  url?: string;
  command?: string;
  args?: string[];
  headers?: Record<string, string>;
  env?: Record<string, string>;
  env_schema?: Record<string, string>;
  description?: string;
  timeout_ms?: number;
  enabled: boolean;
  is_system_default: boolean;
  auto_attach_modes?: string[];
  enabled_tools?: string[];
}

interface UseSessionMCPManagerOptions {
  workspaceId?: string | null;
  enabled?: boolean;
}

export interface MCPServerToolsState {
  serverName: string;
  tools: MCPToolInfo[];
  enabledTools: string[];
  loading: boolean;
}

interface UseSessionMCPManagerReturn {
  // 我的默认 MCP 数据
  storeServers: MCPStoreItem[];
  storeLoading: boolean;

  // 工作区数据
  workspaceServers: MCPWorkspaceItem[];
  workspaceLoading: boolean;
  workspaceOnlyServers: MCPWorkspaceItem[];
  workspaceOnlyLoading: boolean;

  // 工具列表
  serverToolsMap: Map<string, MCPServerToolsState>;

  // 状态
  error: string | null;

  // 操作
  refreshStore: () => Promise<void>;
  refreshWorkspace: () => Promise<void>;
  refreshWorkspaceOnly: () => Promise<void>;
  addStoreServer: (server: Omit<MCPServerConfig, "is_system_default">) => Promise<boolean>;
  removeStoreServer: (name: string) => Promise<boolean>;
  addWorkspaceServer: (name: string) => Promise<boolean>;
  removeWorkspaceServer: (name: string) => Promise<boolean>;
  isInWorkspaceOnly: (name: string) => boolean;
  loadServerTools: (serverName: string) => Promise<MCPServerToolsState | null>;
  updateServerEnabledTools: (serverName: string, enabledTools: string[]) => Promise<boolean>;
}

export function useSessionMCPManager(
  options: UseSessionMCPManagerOptions
): UseSessionMCPManagerReturn {
  const { workspaceId, enabled = true } = options;

  const [storeServers, setStoreServers] = useState<MCPStoreItem[]>([]);
  const [workspaceServers, setWorkspaceServers] = useState<MCPWorkspaceItem[]>([]);
  const [workspaceOnlyServers, setWorkspaceOnlyServers] = useState<MCPWorkspaceItem[]>([]);
  const [storeLoading, setStoreLoading] = useState(false);
  const [workspaceLoading, setWorkspaceLoading] = useState(false);
  const [workspaceOnlyLoading, setWorkspaceOnlyLoading] = useState(false);
  const [serverToolsMap, setServerToolsMap] = useState<Map<string, MCPServerToolsState>>(new Map());
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

  // 加载我的默认 MCP
  const loadStore = useCallback(async () => {
    if (!enabled) {
      safeSet(setStoreServers, []);
      return;
    }
    safeSet(setStoreLoading, true);
    safeSet(setError, null);
    try {
      const data = await getMCPStoreList();
      safeSet(setStoreServers, data.servers || []);
    } catch (err) {
      console.error("加载全局 MCP 仓库失败:", err);
      safeSet(setError, err instanceof Error ? err.message : "加载失败");
    } finally {
      safeSet(setStoreLoading, false);
    }
  }, [enabled]);

  // 加载工作区启用（三层合并后的生效配置）
  const loadWorkspace = useCallback(async () => {
    if (!enabled || !workspaceId) {
      safeSet(setWorkspaceServers, []);
      return;
    }
    safeSet(setWorkspaceLoading, true);
    safeSet(setError, null);
    try {
      const data = await getMCPWorkspaceList(workspaceId, "effective");
      safeSet(setWorkspaceServers, data.servers || []);
    } catch (err) {
      console.error("加载工作区 MCP 配置失败:", err);
      safeSet(setError, err instanceof Error ? err.message : "加载失败");
    } finally {
      safeSet(setWorkspaceLoading, false);
    }
  }, [enabled, workspaceId]);

  // 加载仅工作区配置中的 server
  const loadWorkspaceOnly = useCallback(async () => {
    if (!enabled || !workspaceId) {
      safeSet(setWorkspaceOnlyServers, []);
      return;
    }
    safeSet(setWorkspaceOnlyLoading, true);
    try {
      const data = await getMCPWorkspaceList(workspaceId, "workspace");
      safeSet(setWorkspaceOnlyServers, data.servers || []);
    } catch (err) {
      console.error("加载工作区单独配置失败:", err);
      safeSet(setError, err instanceof Error ? err.message : "加载工作区单独配置失败");
      safeSet(setWorkspaceOnlyServers, []);
    } finally {
      safeSet(setWorkspaceOnlyLoading, false);
    }
  }, [enabled, workspaceId]);

  // 初始加载
  useEffect(() => {
    void loadStore();
  }, [loadStore]);

  useEffect(() => {
    void loadWorkspace();
    void loadWorkspaceOnly();
  }, [loadWorkspace, loadWorkspaceOnly]);

  // 添加全局 server
  const addStoreServer = async (
    server: Omit<MCPServerConfig, "is_system_default">
  ): Promise<boolean> => {
    try {
      await saveMCPStoreServer(server as MCPServerConfig);
      await loadStore();
      return true;
    } catch (err) {
      console.error("添加 MCP server 失败:", err);
      safeSet(setError, err instanceof Error ? err.message : "添加失败");
      return false;
    }
  };

  // 删除全局 server
  const removeStoreServer = async (name: string): Promise<boolean> => {
    try {
      await deleteMCPStoreServer(name);
      await loadStore();
      return true;
    } catch (err) {
      console.error("删除 MCP server 失败:", err);
      safeSet(setError, err instanceof Error ? err.message : "删除失败");
      return false;
    }
  };

  // 添加工作区 server（从全局复制）
  const addWorkspaceServer = async (name: string): Promise<boolean> => {
    if (!workspaceId) return false;
    try {
      await addMCPWorkspaceServer(workspaceId, name);
      await loadWorkspace();
      await loadWorkspaceOnly();
      return true;
    } catch (err) {
      console.error("添加工作区 MCP server 失败:", err);
      safeSet(setError, err instanceof Error ? err.message : "添加失败");
      return false;
    }
  };

  // 移除工作区 server
  const removeWorkspaceServer = async (name: string): Promise<boolean> => {
    if (!workspaceId) return false;
    try {
      await removeMCPWorkspaceServer(workspaceId, name);
      await loadWorkspace();
      await loadWorkspaceOnly();
      return true;
    } catch (err) {
      console.error("移除工作区 MCP server 失败:", err);
      safeSet(setError, err instanceof Error ? err.message : "移除失败");
      return false;
    }
  };

  const isInWorkspaceOnly = useCallback(
    (name: string) => workspaceServers.some((s) => s.name === name),
    [workspaceServers]
  );

  // 加载 server 工具列表
  const loadServerRequestSeqRef = useRef(0);
  const loadServerTools = useCallback(
    async (serverName: string): Promise<MCPServerToolsState | null> => {
      if (!workspaceId) return null;

      loadServerRequestSeqRef.current += 1;
      const requestSeq = loadServerRequestSeqRef.current;

      setServerToolsMap((prev) => {
        const next = new Map(prev);
        next.set(serverName, {
          serverName,
          tools: prev.get(serverName)?.tools || [],
          enabledTools: prev.get(serverName)?.enabledTools || [],
          loading: true,
        });
        return next;
      });
      try {
        const data = await getMCPWorkspaceServerTools(workspaceId, serverName);
        if (loadServerRequestSeqRef.current !== requestSeq) return null;
        const state: MCPServerToolsState = {
          serverName,
          tools: data.tools || [],
          enabledTools: data.enabled_tools || [],
          loading: false,
        };
        setServerToolsMap((prev) => {
          const next = new Map(prev);
          next.set(serverName, state);
          return next;
        });
        return state;
      } catch (err) {
        if (loadServerRequestSeqRef.current !== requestSeq) return null;
        console.error("加载 MCP 工具列表失败:", err);
        setServerToolsMap((prev) => {
          const next = new Map(prev);
          const existing = prev.get(serverName);
          if (existing) {
            next.set(serverName, { ...existing, loading: false });
          }
          return next;
        });
        return null;
      }
    },
    [workspaceId]
  );

  // 更新 server 启用工具列表
  const updateServerEnabledTools = useCallback(
    async (serverName: string, enabledTools: string[]): Promise<boolean> => {
      if (!workspaceId) return false;
      try {
        await updateMCPWorkspaceServerEnabledTools(workspaceId, serverName, enabledTools);
        setServerToolsMap((prev) => {
          const next = new Map(prev);
          const existing = prev.get(serverName);
          if (existing) {
            next.set(serverName, { ...existing, enabledTools });
          }
          return next;
        });
        return true;
      } catch (err) {
        console.error("更新启用工具列表失败:", err);
        safeSet(setError, err instanceof Error ? err.message : "更新失败");
        return false;
      }
    },
    [workspaceId]
  );

  return {
    storeServers,
    storeLoading,
    workspaceServers,
    workspaceLoading,
    workspaceOnlyServers,
    workspaceOnlyLoading,
    serverToolsMap,
    error,
    refreshStore: loadStore,
    refreshWorkspace: loadWorkspace,
    refreshWorkspaceOnly: loadWorkspaceOnly,
    addStoreServer,
    removeStoreServer,
    addWorkspaceServer,
    removeWorkspaceServer,
    isInWorkspaceOnly,
    loadServerTools,
    updateServerEnabledTools,
  };
}
