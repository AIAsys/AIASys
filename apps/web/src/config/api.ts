/**
 * Centralized API Configuration
 *
 * This file serves as the single source of truth for the API base URL.
 * It is used across the application to ensure consistency.
 *
 * Defaults to "" (empty string) to allow Vite proxy to handle requests in development.
 * Can be overridden via VITE_API_BASE_URL environment variable.
 */

// 默认使用相对路径，允许通过环境变量覆盖到独立后端地址
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").trim();

declare global {
  interface Window {
    __AIASYS_CURRENT_USER_ID__?: string;
  }
}

export function encodePathPreservingSlashes(path: string): string {
  return path
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}

/**
 * API 端点定义
 * 与后端 API 保持一致
 */
export const API_ENDPOINTS = {
  DIFF_TEXT: "/api/diff/text",
  DIFF_FILES: "/api/diff/files",
  DIFF_DIRECTORIES: "/api/diff/directories",

  // Agent 执行
  AGENT_STREAM: "/api/agent/execute/stream",

  // 执行历史
  EXECUTION_FLOW: (userId: string, sessionId: string) =>
    `/api/agent/execution/${userId}/${sessionId}/flow`,

  // 文件管理
  FILES_DELETE: (userId: string, sessionId: string, filename: string) =>
    `/api/files/delete/${userId}/${sessionId}/${encodePathPreservingSlashes(filename)}`,
  FILES_DOWNLOAD: (userId: string, sessionId: string, filename: string) =>
    `/api/files/download/${userId}/${sessionId}/${encodePathPreservingSlashes(filename)}`,
  FILES_EXPORT: (userId: string, sessionId: string) =>
    `/api/files/export/${userId}/${sessionId}`,
  FILES_EXPORT_DOCUMENT: (
    userId: string,
    sessionId: string,
    filename: string,
  ) =>
    `/api/files/export-document/${userId}/${sessionId}/${encodePathPreservingSlashes(filename)}`,
  FILES_CONTENT: (userId: string, sessionId: string, filename: string) =>
    `/api/files/content/${userId}/${sessionId}/${encodePathPreservingSlashes(filename)}`,
  FILES_CSV_PREVIEW: (userId: string, sessionId: string, filename: string) =>
    `/api/files/csv-preview/${userId}/${sessionId}/${encodePathPreservingSlashes(filename)}`,
  FILE_DATABASE_SCHEMA: (userId: string, sessionId: string, filename: string) =>
    `/api/file-database/schema/${userId}/${sessionId}/${encodePathPreservingSlashes(filename)}`,
  FILE_DATABASE_QUERY: (userId: string, sessionId: string, filename: string) =>
    `/api/file-database/query/${userId}/${sessionId}/${encodePathPreservingSlashes(filename)}`,
  GLOBAL_FILE_DATABASE_SCHEMA: (userId: string, filename: string) =>
    `/api/file-database/schema/${userId}/global/${encodePathPreservingSlashes(filename)}`,
  GLOBAL_FILE_DATABASE_QUERY: (userId: string, filename: string) =>
    `/api/file-database/query/${userId}/global/${encodePathPreservingSlashes(filename)}`,
  NOTEBOOKS_ROOT: (userId: string, sessionId: string) =>
    `/api/notebooks/${userId}/${sessionId}`,
  NOTEBOOKS_WORKBENCH: (userId: string, sessionId: string) =>
    `/api/notebooks/${userId}/${sessionId}/workbench`,
  NOTEBOOKS_STATE: (userId: string, sessionId: string) =>
    `/api/notebooks/${userId}/${sessionId}/state`,
  NOTEBOOKS_SEARCH_CELLS: (userId: string, sessionId: string) =>
    `/api/notebooks/${userId}/${sessionId}/search-cells`,
  NOTEBOOKS_OUTLINE: (userId: string, sessionId: string) =>
    `/api/notebooks/${userId}/${sessionId}/outline`,
  NOTEBOOKS_RUNTIME_STATE: (userId: string, sessionId: string) =>
    `/api/notebooks/${userId}/${sessionId}/runtime-state`,
  NOTEBOOKS_VARIABLES: (userId: string, sessionId: string) =>
    `/api/notebooks/${userId}/${sessionId}/variables`,
  NOTEBOOKS_ARTIFACTS: (userId: string, sessionId: string) =>
    `/api/notebooks/${userId}/${sessionId}/artifacts`,
  NOTEBOOKS_EXECUTION_RECORDS: (userId: string, sessionId: string) =>
    `/api/notebooks/${userId}/${sessionId}/execution-records`,
  NOTEBOOKS_DOCUMENT: (
    userId: string,
    sessionId: string,
    notebookPath: string,
  ) =>
    `/api/notebooks/${userId}/${sessionId}/document/${encodePathPreservingSlashes(notebookPath)}`,
  NOTEBOOKS_DOCUMENT_SAVE: (userId: string, sessionId: string) =>
    `/api/notebooks/${userId}/${sessionId}/document`,
  NOTEBOOKS_FORK: (userId: string, sessionId: string) =>
    `/api/notebooks/${userId}/${sessionId}/fork`,
  NOTEBOOKS_PROMOTE: (userId: string, sessionId: string) =>
    `/api/notebooks/${userId}/${sessionId}/promote`,
  NOTEBOOKS_DIFF: (userId: string, sessionId: string) =>
    `/api/notebooks/${userId}/${sessionId}/diff`,
  NOTEBOOKS_INSERT_CELL: (userId: string, sessionId: string) =>
    `/api/notebooks/${userId}/${sessionId}/cells/insert`,
  NOTEBOOKS_UPDATE_CELL: (userId: string, sessionId: string) =>
    `/api/notebooks/${userId}/${sessionId}/cells/update`,
  NOTEBOOKS_MOVE_CELL: (userId: string, sessionId: string) =>
    `/api/notebooks/${userId}/${sessionId}/cells/move`,
  NOTEBOOKS_DELETE_CELL: (userId: string, sessionId: string) =>
    `/api/notebooks/${userId}/${sessionId}/cells/delete`,
  NOTEBOOKS_CLEAR_OUTPUTS: (userId: string, sessionId: string) =>
    `/api/notebooks/${userId}/${sessionId}/clear-outputs`,
  NOTEBOOKS_RUNTIME_INTERRUPT: (userId: string, sessionId: string) =>
    `/api/notebooks/${userId}/${sessionId}/runtime/interrupt`,
  NOTEBOOKS_RUNTIME_RESTART: (userId: string, sessionId: string) =>
    `/api/notebooks/${userId}/${sessionId}/runtime/restart`,
  NOTEBOOKS_RUNTIME_STOP: (userId: string, sessionId: string) =>
    `/api/notebooks/${userId}/${sessionId}/runtime/stop`,
  NOTEBOOKS_RUN: (userId: string, sessionId: string) =>
    `/api/notebooks/${userId}/${sessionId}/run`,
  NOTEBOOKS_KERNELS: (userId: string) =>
    `/api/notebooks/${userId}/kernels`,
  NOTEBOOKS_KERNEL_INTERRUPT: (userId: string) =>
    `/api/notebooks/${userId}/kernel/interrupt`,
  NOTEBOOKS_KERNEL_RESTART: (userId: string) =>
    `/api/notebooks/${userId}/kernel/restart`,
  NOTEBOOKS_KERNEL_STOP: (userId: string) =>
    `/api/notebooks/${userId}/kernel/stop`,
  // Skills 管理
  SKILLS_STORE_LIST: `/api/skills/store`,
  SKILLS_STORE_IMPORT: `/api/skills/store/import`,
  SKILLS_STORE_DELETE: (skillName: string) =>
    `/api/skills/store/${encodeURIComponent(skillName)}`,
  SKILLS_GLOBAL_LIST: `/api/skills/global`,
  SKILLS_GLOBAL_ENABLE: `/api/skills/global/enable`,
  SKILLS_GLOBAL_DISABLE: `/api/skills/global/disable`,
  SKILLS_WORKSPACE_LIST: (workspaceId: string) =>
    `/api/skills/workspaces/${encodeURIComponent(workspaceId)}`,
  SKILLS_WORKSPACE_ENABLE: (workspaceId: string) =>
    `/api/skills/workspaces/${encodeURIComponent(workspaceId)}/enable`,
  SKILLS_WORKSPACE_DISABLE: (workspaceId: string) =>
    `/api/skills/workspaces/${encodeURIComponent(workspaceId)}/disable`,
  SKILLS_WORKSPACE_UPDATE: (workspaceId: string) =>
    `/api/skills/workspaces/${encodeURIComponent(workspaceId)}/update`,
  SKILLS_WORKSPACE_ENTRY: (workspaceId: string, skillName: string) =>
    `/api/skills/workspaces/${encodeURIComponent(workspaceId)}/${encodeURIComponent(skillName)}/entry`,
  SKILLS_WORKSPACE_README: (workspaceId: string, skillName: string) =>
    `/api/skills/workspaces/${encodeURIComponent(workspaceId)}/${encodeURIComponent(skillName)}/readme`,
  SKILLS_EXTERNAL_MARKET_SOURCES: `/api/skills/external-market/sources`,
  SKILLS_EXTERNAL_MARKET_ITEMS: `/api/skills/external-market/items`,
  SKILLS_EXTERNAL_MARKET_DETAIL: `/api/skills/external-market/detail`,
  SKILLS_EXTERNAL_MARKET_INSTALL: (workspaceId: string) =>
    `/api/skills/external-market/workspaces/${encodeURIComponent(workspaceId)}/install`,

  // Session
  SESSIONS_LIST: (userId: string) => `/api/sessions/${userId}`,
  SESSION_DELETE: (userId: string, sessionId: string) =>
    `/api/sessions/${userId}/${sessionId}`,
  SESSION_EXPORT: (userId: string, sessionId: string) =>
    `/api/sessions/${userId}/${sessionId}/export`,
  SESSION_IMPORT: (userId: string) => `/api/sessions/${userId}/import`,
  SESSION_HISTORY: (userId: string, sessionId: string) =>
    `/api/sessions/history/${userId}/${sessionId}`,
  SESSION_REWRITE_FROM_MESSAGE: (userId: string, sessionId: string) =>
    `/api/sessions/${userId}/${sessionId}/rewrite-from-message`,
  SESSION_EXECUTION_RECORDS: (userId: string, sessionId: string) =>
    `/api/sessions/${userId}/${sessionId}/execution-records`,
  SESSION_COMPACT: (userId: string, sessionId: string) =>
    `/api/sessions/${userId}/${sessionId}/compact`,
  SESSION_UPDATE_TITLE: (userId: string, sessionId: string) =>
    `/api/sessions/${userId}/${sessionId}/title`,
  SESSION_LLM_SELECTION: (userId: string, sessionId: string) =>
    `/api/sessions/${userId}/${sessionId}/llm-selection`,
  MEMORY_RESOLVE: "/api/memory/resolve",
  MEMORY_STATUS: "/api/memory/status",
  MEMORY_RETENTION: "/api/memory/retention",
  MEMORY_WORKSPACE_CONTENT: "/api/memory/workspace/content",
  MEMORY_VERSIONS: "/api/memory/versions",
  MEMORY_VERSION_DETAIL: (versionId: string) =>
    `/api/memory/versions/${encodeURIComponent(versionId)}`,
  MEMORY_VERSION_RESTORE: (versionId: string) =>
    `/api/memory/versions/${encodeURIComponent(versionId)}/restore`,
  CLAW_GATEWAY_SESSIONS: "/api/claw/gateway-sessions",
  CLAW_PLATFORMS: "/api/claw/platforms",
  CLAW_QR_LOGIN_START: (platform: string) =>
    `/api/claw/${encodeURIComponent(platform)}/qr-login/start`,
  CLAW_QR_LOGIN_POLL: (platform: string, flowId: string) =>
    `/api/claw/${encodeURIComponent(platform)}/qr-login/${encodeURIComponent(flowId)}/poll`,
  CLAW_SESSION_BINDING: (sessionId: string) =>
    `/api/claw/sessions/${encodeURIComponent(sessionId)}/binding`,
  CLAW_SESSION_START: (sessionId: string) =>
    `/api/claw/sessions/${encodeURIComponent(sessionId)}/start`,
  CLAW_SESSION_STOP: (sessionId: string) =>
    `/api/claw/sessions/${encodeURIComponent(sessionId)}/stop`,

  CLAW_SESSION_OUTBOUND_PREVIEW: (sessionId: string) =>
    `/api/claw/sessions/${encodeURIComponent(sessionId)}/outbound-preview`,
  CLAW_SESSION_DISPATCH_LAST_REPLY: (sessionId: string) =>
    `/api/claw/sessions/${encodeURIComponent(sessionId)}/dispatch-last-reply`,
  CLAW_CHANNEL_BINDINGS: (channelId: string) =>
    `/api/claw/channels/${encodeURIComponent(channelId)}/bindings`,

  // Channels (new channel management API)
  CHANNELS: "/api/channels",
  CHANNEL: (channelId: string) => `/api/channels/${encodeURIComponent(channelId)}`,
  CHANNEL_ENABLED: (channelId: string) =>
    `/api/channels/${encodeURIComponent(channelId)}/enabled`,
  CHANNEL_PLATFORMS: "/api/channels/platforms",

  // Workspaces
  WORKSPACES_LIST: "/api/workspaces",
  WORKSPACES_CREATE: "/api/workspaces",
  WORKSPACES_IMPORT_FOLDER_PREVIEW: "/api/workspaces/import-folder-preview",
  WORKSPACES_IMPORT_FOLDER_UPLOAD: "/api/workspaces/import-folder-upload",
  WORKSPACES_IMPORT_FOLDER_STREAM: "/api/workspaces/import-folder-stream",
  WORKSPACE_DETAIL: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}`,
  WORKSPACE_INITIALIZATION: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/initialization`,
  WORKSPACE_OVERVIEW: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/overview`,
  WORKSPACE_RESOURCE_LAYERS: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/resource-layers`,
  WORKSPACE_EXPERTS: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/experts`,
  WORKSPACE_EXPERT_POLICY: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/experts/policy`,
  WORKSPACE_EXPERT_DETAIL: (workspaceId: string, name: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/experts/${encodeURIComponent(name)}`,
  WORKSPACE_EXPERT_ENABLE: (workspaceId: string, name: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/experts/${encodeURIComponent(name)}/enable`,
  WORKSPACE_EXPERT_VISIBILITY: (workspaceId: string, name: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/experts/${encodeURIComponent(name)}/visibility`,
  GLOBAL_EXPERTS: "/api/experts/global",
  GLOBAL_EXPERT_POLICY: "/api/experts/global/policy",
  GLOBAL_EXPERT_DETAIL: (name: string) =>
    `/api/experts/global/${encodeURIComponent(name)}`,
  GLOBAL_EXPERT_ENABLE: (name: string) =>
    `/api/experts/global/${encodeURIComponent(name)}/enable`,
  GLOBAL_EXPERT_VISIBILITY: (name: string) =>
    `/api/experts/global/${encodeURIComponent(name)}/visibility`,
  WORKSPACE_LLM_SELECTION: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/llm-selection`,
  WORKSPACE_RESOURCE_VERIFICATION: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/resource-verification`,
  WORKSPACE_RUNTIME_ENVIRONMENTS: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/runtime-environments`,
  WORKSPACE_RUNTIME_ENVIRONMENT: (workspaceId: string, envId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/runtime-environments/${encodeURIComponent(envId)}`,
  WORKSPACE_RUNTIME_ENVIRONMENT_UV: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/runtime-environments/uv`,
  WORKSPACE_RUNTIME_ENVIRONMENT_REGISTERED_PYTHON: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/runtime-environments/registered-python`,
  WORKSPACE_RUNTIME_ENVIRONMENT_PACKAGES: (workspaceId: string, envId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/runtime-environments/${encodeURIComponent(envId)}/packages`,
  WORKSPACE_RUNTIME_ENVIRONMENT_ACTIVE: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/runtime-environments/active`,
  WORKSPACE_RUNTIME_ENVIRONMENT_NODE: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/runtime-environments/node`,
  WORKSPACE_RUNTIME_ENVIRONMENT_NODE_INSTALL: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/runtime-environments/node/install`,
  WORKSPACE_RUNTIME_ENVIRONMENT_NODE_USE: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/runtime-environments/node/use`,
  WORKSPACE_RUNTIME_ENVIRONMENT_NODE_DEFAULT: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/runtime-environments/node/default`,
  WORKSPACE_RUNTIME_ENVIRONMENT_NODE_CURRENT: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/runtime-environments/node/current`,
  WORKSPACE_RUNTIME_ENVIRONMENT_NODE_UNINSTALL: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/runtime-environments/node/uninstall`,
  WORKSPACE_RUNTIME_ENVIRONMENT_NODE_REMOTE: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/runtime-environments/node/remote`,
  WORKSPACE_CONTAINER_RESOURCES: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/container-resources`,
  WORKSPACE_CONTAINER_RESOURCE: (workspaceId: string, containerId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/container-resources/${encodeURIComponent(containerId)}`,
  WORKSPACE_CONTAINER_RESOURCE_START: (workspaceId: string, containerId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/container-resources/${encodeURIComponent(containerId)}/start`,
  WORKSPACE_CONTAINER_RESOURCE_STOP: (workspaceId: string, containerId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/container-resources/${encodeURIComponent(containerId)}/stop`,
  WORKSPACE_CONTAINER_RESOURCE_LOGS: (workspaceId: string, containerId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/container-resources/${encodeURIComponent(containerId)}/logs`,
  WORKSPACE_DATABASE_CONNECTORS: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/database-connectors`,
  WORKSPACE_KNOWLEDGE_BASES: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/knowledge-bases`,
  WORKSPACE_FILE_LIST: (
    workspaceId: string,
    params?: {
      directory?: string;
      recursive?: boolean;
      maxDepth?: number;
      limit?: number;
      offset?: number;
      includeTotal?: boolean;
    },
  ) => {
    const search = new URLSearchParams();
    if (params?.directory) search.set("directory", params.directory);
    if (params?.recursive !== undefined) {
      search.set("recursive", String(params.recursive));
    }
    if (params?.maxDepth !== undefined) {
      search.set("max_depth", String(params.maxDepth));
    }
    if (params?.limit !== undefined) search.set("limit", String(params.limit));
    if (params?.offset !== undefined) search.set("offset", String(params.offset));
    if (params?.includeTotal !== undefined) {
      search.set("include_total", String(params.includeTotal));
    }
    const query = search.toString();
    return `/api/workspaces/${encodeURIComponent(workspaceId)}/files/list${query ? `?${query}` : ""}`;
  },
  WORKSPACE_RESOURCES_TREE: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/resources/tree`,
  WORKSPACE_RESOURCES_TREE_CHILDREN: (workspaceId: string, directoryPath: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/resources/tree/children/${encodePathPreservingSlashes(directoryPath)}`,
  GLOBAL_WORKSPACE_TREE: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/global-workspace/tree`,
  GLOBAL_WORKSPACE_CONTENT: (workspaceId: string, assetPath: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/global-workspace/content/${encodePathPreservingSlashes(assetPath)}`,
  GLOBAL_WORKSPACE_CONTENT_SAVE: (workspaceId: string, assetPath: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/global-workspace/content/${encodePathPreservingSlashes(assetPath)}`,
  GLOBAL_WORKSPACE_CSV_PREVIEW: (workspaceId: string, assetPath: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/global-workspace/csv-preview/${encodePathPreservingSlashes(assetPath)}`,
  GLOBAL_WORKSPACE_DOWNLOAD: (workspaceId: string, assetPath: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/global-workspace/download/${encodePathPreservingSlashes(assetPath)}`,
  GLOBAL_WORKSPACE_UPLOAD: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/global-workspace/upload`,
  GLOBAL_WORKSPACE_CREATE: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/global-workspace/create`,
  GLOBAL_WORKSPACE_COPY: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/global-workspace/copy`,
  GLOBAL_WORKSPACE_MOVE: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/global-workspace/move`,
  GLOBAL_WORKSPACE_DELETE: (workspaceId: string, assetPath: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/global-workspace/${encodePathPreservingSlashes(assetPath)}`,
  GLOBAL_WORKSPACE_HISTORY_LIST: (workspaceId: string, assetPath: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/global-workspace/history/list/${encodePathPreservingSlashes(assetPath)}`,
  GLOBAL_WORKSPACE_HISTORY_CONTENT: (workspaceId: string, entryId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/global-workspace/history/entries/${encodeURIComponent(entryId)}/content`,
  GLOBAL_WORKSPACE_HISTORY_DIFF: (workspaceId: string, entryId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/global-workspace/history/entries/${encodeURIComponent(entryId)}/diff`,
  GLOBAL_WORKSPACE_HISTORY_RESTORE: (workspaceId: string, entryId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/global-workspace/history/entries/${encodeURIComponent(entryId)}/restore`,
  WORKSPACE_FILE_COPY: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/files/copy`,
  WORKSPACE_FILE_MOVE: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/files/move`,
  WORKSPACE_FILE_CONTENT: (workspaceId: string, filename: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/files/content/${encodePathPreservingSlashes(filename)}`,
  WORKSPACE_FILE_CSV_PREVIEW: (workspaceId: string, filename: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/files/csv-preview/${encodePathPreservingSlashes(filename)}`,
  WORKSPACE_FILE_DOWNLOAD: (workspaceId: string, filename: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/files/download/${encodePathPreservingSlashes(filename)}`,
  WORKSPACE_FILE_HISTORY_LIST: (workspaceId: string, filename: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/files/history/list/${encodePathPreservingSlashes(filename)}`,
  WORKSPACE_FILE_HISTORY_CONTENT: (workspaceId: string, entryId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/files/history/entries/${encodeURIComponent(entryId)}/content`,
  WORKSPACE_FILE_HISTORY_DIFF: (workspaceId: string, entryId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/files/history/entries/${encodeURIComponent(entryId)}/diff`,
  WORKSPACE_FILE_HISTORY_RESTORE: (workspaceId: string, entryId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/files/history/entries/${encodeURIComponent(entryId)}/restore`,
  WORKSPACE_RECENT_CHANGES: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/files/history/recent-changes`,
  GLOBAL_WORKSPACE_RECENT_CHANGES: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/global-workspace/history/recent-changes`,
  WORKSPACE_FILE_UPLOAD: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/files/upload`,
  WORKSPACE_FILE_CREATE: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/files/create`,
  WORKSPACE_CREATE_KNOWLEDGE_DB: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/files/create-knowledge-db`,
  WORKSPACE_FILE_DELETE: (workspaceId: string, filename: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/files/${encodePathPreservingSlashes(filename)}`,
  WORKSPACE_DATA_TABLES: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/data-tables`,
  WORKSPACE_DATA_TABLE_SCHEMA: (workspaceId: string, tablePath: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/data-tables/${encodePathPreservingSlashes(tablePath)}/schema`,
  WORKSPACE_DATA_TABLE_RECORDS: (workspaceId: string, tablePath: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/data-tables/${encodePathPreservingSlashes(tablePath)}/records`,
  WORKSPACE_DATA_TABLE_COLUMNS: (workspaceId: string, tablePath: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/data-tables/${encodePathPreservingSlashes(tablePath)}/schema/columns`,
  WORKSPACE_DATA_TABLE_COLUMN: (workspaceId: string, tablePath: string, columnName: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/data-tables/${encodePathPreservingSlashes(tablePath)}/schema/columns/${encodeURIComponent(columnName)}`,
  GLOBAL_DATA_TABLES: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/global-workspace/data-tables`,
  GLOBAL_DATA_TABLE_SCHEMA: (workspaceId: string, tablePath: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/global-workspace/data-tables/${encodePathPreservingSlashes(tablePath)}/schema`,
  GLOBAL_DATA_TABLE_RECORDS: (workspaceId: string, tablePath: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/global-workspace/data-tables/${encodePathPreservingSlashes(tablePath)}/records`,
  GLOBAL_DATA_TABLE_COLUMNS: (workspaceId: string, tablePath: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/global-workspace/data-tables/${encodePathPreservingSlashes(tablePath)}/schema/columns`,
  GLOBAL_DATA_TABLE_COLUMN: (workspaceId: string, tablePath: string, columnName: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/global-workspace/data-tables/${encodePathPreservingSlashes(tablePath)}/schema/columns/${encodeURIComponent(columnName)}`,
  GLOBAL_CREATE_KNOWLEDGE_DB: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/global-workspace/create-knowledge-db`,
  GLOBAL_CREATE_GRAPH_DB: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/global-workspace/create-graph-db`,
  WORKSPACE_TEMPLATES_LIST: `/api/workspace-templates`,
  WORKSPACE_TEMPLATE_DETAIL: (templateId: string) =>
    `/api/workspace-templates/${encodeURIComponent(templateId)}`,
  WORKSPACE_TEMPLATE_DELETE: (templateId: string) =>
    `/api/workspace-templates/${encodeURIComponent(templateId)}`,
  WORKSPACE_TEMPLATE_EXPORT: (workspaceId: string) =>
    `/api/workspace-templates/${encodeURIComponent(workspaceId)}/export`,
  TEMPLATE_MARKET_SOURCES: `/api/workspace-templates/external-market/sources`,
  TEMPLATE_MARKET_ITEMS: `/api/workspace-templates/external-market/items`,
  TEMPLATE_MARKET_DETAIL: `/api/workspace-templates/external-market/detail`,
  TEMPLATE_MARKET_INSTALL: `/api/workspace-templates/external-market/install`,
  WORKSPACE_CONVERSATIONS: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/conversations`,
  WORKSPACE_CONVERSATION_RUNTIMES: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/conversation-runtimes`,
  WORKSPACE_CONVERSATION_RUNTIME_START: (
    workspaceId: string,
    conversationId: string,
  ) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/conversations/${encodeURIComponent(conversationId)}/runtime/start`,
  WORKSPACE_CONVERSATION_RUNTIME_STOP: (
    workspaceId: string,
    conversationId: string,
  ) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/conversations/${encodeURIComponent(conversationId)}/runtime/stop`,
  WORKSPACE_CANVAS: (workspaceId: string, filePath: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/canvas/${encodePathPreservingSlashes(filePath)}`,
  WORKSPACE_EXPORT: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/export`,
  WORKSPACE_IMPORT: `/api/workspaces/import`,
  WORKSPACE_AUTO_TASKS: (workspaceId: string) =>
    `/api/auto-tasks/workspaces/${encodeURIComponent(workspaceId)}/tasks`,
  WORKSPACE_AUTO_TASK: (workspaceId: string, taskId: string) =>
    `/api/auto-tasks/workspaces/${encodeURIComponent(workspaceId)}/tasks/${encodeURIComponent(taskId)}`,
  WORKSPACE_AUTO_TASK_RUN: (workspaceId: string, taskId: string) =>
    `/api/auto-tasks/workspaces/${encodeURIComponent(workspaceId)}/tasks/${encodeURIComponent(taskId)}/run`,
  AUTO_TASKS_ALL: "/api/auto-tasks/tasks",
  AUTO_TASKS_SUMMARY: "/api/auto-tasks/tasks/summary",

  // Capabilities (统一能力层)
  CAPABILITIES_AVAILABLE: "/api/capabilities/available",
  WORKSPACE_CAPABILITIES: (workspaceId: string) =>
    `/api/capabilities/workspaces/${encodeURIComponent(workspaceId)}`,
  WORKSPACE_CAPABILITY_INSTALL: (workspaceId: string) =>
    `/api/capabilities/workspaces/${encodeURIComponent(workspaceId)}/install`,
  WORKSPACE_CAPABILITY_UNINSTALL: (workspaceId: string) =>
    `/api/capabilities/workspaces/${encodeURIComponent(workspaceId)}/uninstall`,
  WORKSPACE_CAPABILITY_ACTIVATE: (workspaceId: string) =>
    `/api/capabilities/workspaces/${encodeURIComponent(workspaceId)}/activate`,
  WORKSPACE_CAPABILITY_DEACTIVATE: (workspaceId: string) =>
    `/api/capabilities/workspaces/${encodeURIComponent(workspaceId)}/deactivate`,
  WORKSPACE_CAPABILITY_VERIFY: (workspaceId: string) =>
    `/api/capabilities/workspaces/${encodeURIComponent(workspaceId)}/verify`,
  GLOBAL_CAPABILITIES: "/api/capabilities/global",
  GLOBAL_CAPABILITY_INSTALL: "/api/capabilities/global/install",
  GLOBAL_CAPABILITY_UNINSTALL: "/api/capabilities/global/uninstall",
  GLOBAL_CAPABILITY_ACTIVATE: "/api/capabilities/global/activate",
  GLOBAL_CAPABILITY_DEACTIVATE: "/api/capabilities/global/deactivate",
  GLOBAL_CAPABILITY_VERIFY: "/api/capabilities/global/verify",
  CAPABILITY_SOURCE: (capabilityId: string, file: string = "SKILL.md") =>
    `/api/capabilities/${encodeURIComponent(capabilityId)}/source?file=${encodeURIComponent(file)}`,
  CAPABILITY_SOURCE_TREE: (capabilityId: string) =>
    `/api/capabilities/${encodeURIComponent(capabilityId)}/source?list=true`,

  // UI 设置
  UI_SETTINGS: (userId: string) => `/api/ui-settings/${encodeURIComponent(userId)}`,
  STORAGE_SETTINGS: "/api/system/storage-settings",
  STORAGE_SETTINGS_VALIDATE_PATH: "/api/system/storage-settings/validate-path",
  STORAGE_SETTINGS_MIGRATION: "/api/system/storage-settings/migration",
  STORAGE_SETTINGS_MIGRATION_PREVIEW: "/api/system/storage-settings/migration/preview",
  STORAGE_SETTINGS_MIGRATION_START: "/api/system/storage-settings/migration/start",
  UV_MIRROR_CONFIG: "/api/system/uv/mirror-config",
  SHELL_ENVIRONMENT: "/api/system/shell-environment",
  SHELL_ENVIRONMENT_INSTALL_BUSYBOX: "/api/system/shell-environment/install-busybox",
  SHELL_ENVIRONMENT_INSTALL_BUSYBOX_STREAM: "/api/system/shell-environment/install-busybox/stream",

  // Knowledge Base 知识库
  KNOWLEDGE_BASES: "/api/knowledge/bases",
  KNOWLEDGE_BASE: (kbId: string) => `/api/knowledge/bases/${kbId}`,
  KNOWLEDGE_BASE_DOCUMENTS: (kbId: string) =>
    `/api/knowledge/bases/${kbId}/docs`,
  KNOWLEDGE_BASE_DOCUMENT: (kbId: string, docId: string) =>
    `/api/knowledge/bases/${kbId}/docs/${docId}`,
  KNOWLEDGE_BASE_UPLOAD: (kbId: string) =>
    `/api/knowledge/bases/${kbId}/docs/upload`,
  KNOWLEDGE_BASE_BATCH_UPLOAD: (kbId: string) =>
    `/api/knowledge/bases/${kbId}/docs/batch-upload`,
  KNOWLEDGE_BASE_QUERY: (kbId: string) => `/api/knowledge/bases/${kbId}/query`,
  KNOWLEDGE_BASE_TABLES: (kbId: string) => `/api/knowledge/bases/${kbId}/tables`,
  KNOWLEDGE_BASE_RAW_QUERY: (kbId: string) => `/api/knowledge/bases/${kbId}/raw-query`,
  KNOWLEDGE_HEALTH: "/api/knowledge/health",

  // GraphRAG 知识图谱
  GRAPH_HEALTH: "/api/graph/health",
  GRAPH_LLM_STATUS: "/api/graph/config/llm/status",
  GRAPH_DOCUMENTS: "/api/graph/documents",
  GRAPH_DOCUMENTS_UPLOAD: "/api/graph/documents/upload",
  GRAPH_QUERY: "/api/graph/query",
  GRAPH_ENTITIES: "/api/graph/entities",
  GRAPH_RELATIONS: "/api/graph/relations",
  GRAPH_ENTITY: (name: string) => `/api/graph/entities/${name}`,
  GRAPH_ENTITY_UPDATE: (entityId: string) => `/api/graph/entities/${entityId}`,
  GRAPH_SEARCH: "/api/graph/search",
  GRAPH_STATISTICS: "/api/graph/statistics",
  GRAPH_VISUALIZATION: "/api/graph/visualization",
  GRAPH_COMMUNITIES: "/api/graph/communities",
  GRAPH_COMMUNITY_REPORTS: "/api/graph/communities/reports",
  GRAPH_TABLES: "/api/graph/tables",
  GRAPH_RAW_QUERY: "/api/graph/raw-query",
  GRAPH_LAYOUT: "/api/graph/layout",
  WORKSPACE_CREATE_GRAPH_DB: (workspaceId: string) =>
    `/api/workspaces/${encodeURIComponent(workspaceId)}/files/create-graph-db`,
} as const;

/**
 * 获取当前用户 ID
 * 单机默认用户模式下回退到固定工作区用户 ID
 */
export function getCurrentUserId(): string {
  const authMode = getAuthMode();
  if (authMode === "none") {
    return "test_anonymous_dev";
  }
  let storedUserId: string | null = null;
  try {
    storedUserId = localStorage.getItem("user_id");
  } catch {
    // 隐私模式或 localStorage 不可用时静默忽略
  }
  if (authMode === "local") {
    return (
      window.__AIASYS_CURRENT_USER_ID__ ||
      storedUserId ||
      "local_default"
    );
  }
  return (
    window.__AIASYS_CURRENT_USER_ID__ || storedUserId || ""
  );
}

/**
 * 设置当前用户 ID
 */
export function setCurrentUserId(userId: string): void {
  window.__AIASYS_CURRENT_USER_ID__ = userId;
  try {
    localStorage.setItem("user_id", userId);
  } catch {
    // 存储不可用时静默忽略（如隐私模式或配额已满）
  }
}

export function clearCurrentUserId(): void {
  delete window.__AIASYS_CURRENT_USER_ID__;
  try {
    localStorage.removeItem("user_id");
  } catch {
    // 忽略
  }
}
import { getAuthMode } from "./auth";
