import { API_BASE_URL, API_ENDPOINTS } from "@/config/api";
import { apiFetch, apiRequest } from "@/lib/api/httpClient";
import type {
  AddGraphDocumentRequest,
  AddGraphDocumentResponse,
  CreateGraphEntityRequest,
  CreateGraphRelationRequest,
  DeleteGraphEntityResponse,
  GraphCommunityReportsResponse,
  GraphCommunitySummary,
  GraphEntity,
  GraphHealth,
  GraphLlmStatus,
  GraphQueryRequest,
  GraphQueryResponse,
  GraphRawQueryResponse,
  GraphRelation,
  GraphSearchResponse,
  GraphStatistics,
  GraphTableInfo,
  GraphVisualizationResponse,
  UpdateGraphEntityRequest,
  UploadGraphDocumentOptions,
  UploadGraphDocumentResponse,
} from "@/types/graphrag";

function getHeaders(): HeadersInit {
  return {
    "Content-Type": "application/json",
  };
}

function getFetchOptions(): RequestInit {
  return {
    credentials: "include",
  };
}

function resolveWorkspaceId(explicitWorkspaceId?: string | null): string | null {
  if (explicitWorkspaceId !== undefined) {
    return explicitWorkspaceId?.trim() || null;
  }

  if (typeof window === "undefined") {
    return null;
  }

  return new URLSearchParams(window.location.search).get("workspace_id");
}

function resolveGraphId(explicitGraphId?: string | null): string | null {
  if (explicitGraphId !== undefined) {
    return explicitGraphId?.trim() || null;
  }

  if (typeof window === "undefined") {
    return null;
  }

  return new URLSearchParams(window.location.search).get("graph_id");
}

function resolveDbPath(
  scope?: {
    workspaceId?: string | null;
    graphId?: string | null;
    dbPath?: string | null;
  },
): string | null {
  if (scope?.dbPath) {
    return scope.dbPath;
  }
  const graphId = resolveGraphId(scope?.graphId);
  if (!graphId) {
    return null;
  }
  const workspaceId = resolveWorkspaceId(scope?.workspaceId);
  if (workspaceId) {
    return `/workspace/${graphId}.graph.db`;
  }
  return `/global/graphs/${graphId}.db`;
}

function getWorkspaceScopedUrl(
  path: string,
  scope?: {
    workspaceId?: string | null;
    graphId?: string | null;
    dbPath?: string | null;
  },
): string {
  const url = new URL(`${API_BASE_URL}${path}`, window.location.origin);
  const currentWorkspaceId = resolveWorkspaceId(scope?.workspaceId);
  const currentDbPath = resolveDbPath(scope);
  if (currentWorkspaceId && !url.searchParams.has("workspace_id")) {
    url.searchParams.set("workspace_id", currentWorkspaceId);
  }
  if (currentDbPath && !url.searchParams.has("db_path")) {
    url.searchParams.set("db_path", currentDbPath);
  }
  return `${url.pathname}${url.search}`;
}

async function fetchWithTimeout(
  input: string,
  init?: RequestInit,
  timeoutMs = 8000,
): Promise<Response> {
  try {
    return await apiFetch(input, {
      ...init,
      timeoutMs,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("请求超时，请稍后重试");
    }
    throw error;
  }
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (!error || typeof error !== "object") {
    return fallback;
  }

  const detail = "detail" in error ? error.detail : null;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = detail.message;
    if (typeof message === "string" && message.trim()) {
      return message;
    }
  }
  if ("message" in error) {
    const message = error.message;
    if (typeof message === "string" && message.trim()) {
      return message;
    }
  }

  return fallback;
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(getErrorMessage(error, `HTTP ${response.status}`));
  }

  return response.json() as Promise<T>;
}

export function createGraphragApi(scope?: {
  workspaceId?: string | null;
  graphId?: string | null;
  dbPath?: string | null;
}) {
  return {
    async getHealth(): Promise<GraphHealth> {
      const response = await fetchWithTimeout(
        getWorkspaceScopedUrl(API_ENDPOINTS.GRAPH_HEALTH, scope),
        getFetchOptions(),
        6000,
      );
      return handleResponse<GraphHealth>(response);
    },

    async getLlmStatus(): Promise<GraphLlmStatus> {
      const response = await fetchWithTimeout(
        getWorkspaceScopedUrl(API_ENDPOINTS.GRAPH_LLM_STATUS, scope),
        getFetchOptions(),
        6000,
      );
      return handleResponse<GraphLlmStatus>(response);
    },

    async getStatistics(): Promise<GraphStatistics> {
      const response = await fetchWithTimeout(
        getWorkspaceScopedUrl(API_ENDPOINTS.GRAPH_STATISTICS, scope),
        getFetchOptions(),
        6000,
      );
      return handleResponse<GraphStatistics>(response);
    },

    async getVisualization(
      limit = 180,
      communityLevel = 0,
      includeCommunities = false,
    ): Promise<GraphVisualizationResponse> {
      const params = new URLSearchParams();
      params.set("limit", String(limit));
      params.set("community_level", String(communityLevel));
      params.set("include_communities", String(includeCommunities));

      const visualizationPath = `${API_ENDPOINTS.GRAPH_VISUALIZATION}?${params.toString()}`;
      const response = await fetchWithTimeout(
        getWorkspaceScopedUrl(visualizationPath, scope),
        getFetchOptions(),
        8000,
      );
      return handleResponse<GraphVisualizationResponse>(response);
    },

    async addDocument(
      data: AddGraphDocumentRequest,
    ): Promise<AddGraphDocumentResponse> {
      const response = await apiFetch(
        getWorkspaceScopedUrl(API_ENDPOINTS.GRAPH_DOCUMENTS, scope),
        {
          ...getFetchOptions(),
          method: "POST",
          headers: getHeaders(),
          body: JSON.stringify(data),
        },
      );
      return handleResponse<AddGraphDocumentResponse>(response);
    },

    async uploadDocument(
      file: File,
      options: UploadGraphDocumentOptions = {},
    ): Promise<UploadGraphDocumentResponse> {
      const formData = new FormData();
      formData.append("file", file);
      if (options.doc_id?.trim()) {
        formData.append("doc_id", options.doc_id.trim());
      }
      formData.append(
        "resolve_entities",
        String(options.resolve_entities ?? true),
      );
      if (options.extraction_mode) {
        formData.append("extraction_mode", options.extraction_mode);
      }

      const response = await apiFetch(
        getWorkspaceScopedUrl(API_ENDPOINTS.GRAPH_DOCUMENTS_UPLOAD, scope),
        {
          ...getFetchOptions(),
          method: "POST",
          body: formData,
        },
      );
      return handleResponse<UploadGraphDocumentResponse>(response);
    },

    async query(data: GraphQueryRequest): Promise<GraphQueryResponse> {
      return apiRequest<GraphQueryResponse>(
        getWorkspaceScopedUrl(API_ENDPOINTS.GRAPH_QUERY, scope),
        {
          ...getFetchOptions(),
          method: "POST",
          headers: getHeaders(),
          body: JSON.stringify(data),
        },
      );
    },

    async listEntities(
      entityType?: string,
      limit = 100,
    ): Promise<GraphEntity[]> {
      const params = new URLSearchParams();
      params.set("limit", String(limit));
      if (entityType) {
        params.set("entity_type", entityType);
      }

      return apiRequest<GraphEntity[]>(
        getWorkspaceScopedUrl(`${API_ENDPOINTS.GRAPH_ENTITIES}?${params.toString()}`, scope),
        {
          ...getFetchOptions(),
          headers: getHeaders(),
        },
      );
    },

    async createEntity(data: CreateGraphEntityRequest): Promise<GraphEntity> {
      const response = await apiFetch(
        getWorkspaceScopedUrl(API_ENDPOINTS.GRAPH_ENTITIES, scope),
        {
          ...getFetchOptions(),
          method: "POST",
          headers: getHeaders(),
          body: JSON.stringify(data),
        },
      );
      return handleResponse<GraphEntity>(response);
    },

    async createRelation(data: CreateGraphRelationRequest): Promise<GraphRelation> {
      const response = await apiFetch(
        getWorkspaceScopedUrl(API_ENDPOINTS.GRAPH_RELATIONS, scope),
        {
          ...getFetchOptions(),
          method: "POST",
          headers: getHeaders(),
          body: JSON.stringify(data),
        },
      );
      return handleResponse<GraphRelation>(response);
    },

    async getEntity(name: string): Promise<GraphEntity> {
      const response = await fetchWithTimeout(
        getWorkspaceScopedUrl(API_ENDPOINTS.GRAPH_ENTITY(encodeURIComponent(name)), scope),
        {
          ...getFetchOptions(),
          headers: getHeaders(),
        },
        6000,
      );
      return handleResponse<GraphEntity>(response);
    },

    async updateEntity(
      entityId: string,
      data: UpdateGraphEntityRequest,
    ): Promise<GraphEntity> {
      const response = await apiFetch(
        getWorkspaceScopedUrl(API_ENDPOINTS.GRAPH_ENTITY_UPDATE(entityId), scope),
        {
          ...getFetchOptions(),
          method: "PUT",
          headers: getHeaders(),
          body: JSON.stringify(data),
        },
      );
      return handleResponse<GraphEntity>(response);
    },

    async deleteEntity(entityId: string): Promise<DeleteGraphEntityResponse> {
      const response = await apiFetch(
        getWorkspaceScopedUrl(API_ENDPOINTS.GRAPH_ENTITY(encodeURIComponent(entityId)), scope),
        {
          ...getFetchOptions(),
          method: "DELETE",
          headers: getHeaders(),
        },
      );
      return handleResponse<DeleteGraphEntityResponse>(response);
    },

    async searchEntities(
      query: string,
      entityType?: string,
    ): Promise<GraphSearchResponse> {
      const params = new URLSearchParams();
      params.set("query", query);
      if (entityType) {
        params.set("entity_type", entityType);
      }

      const response = await fetchWithTimeout(
        getWorkspaceScopedUrl(`${API_ENDPOINTS.GRAPH_SEARCH}?${params.toString()}`, scope),
        {
          ...getFetchOptions(),
          headers: getHeaders(),
        },
        6000,
      );
      return handleResponse<GraphSearchResponse>(response);
    },

    async listCommunities(level = 0): Promise<GraphCommunitySummary[]> {
      const params = new URLSearchParams();
      params.set("level", String(level));

      const response = await fetchWithTimeout(
        getWorkspaceScopedUrl(`${API_ENDPOINTS.GRAPH_COMMUNITIES}?${params.toString()}`, scope),
        getFetchOptions(),
        20000,
      );
      return handleResponse<GraphCommunitySummary[]>(response);
    },

    async generateCommunityReports(
      level = 0,
    ): Promise<GraphCommunityReportsResponse> {
      const params = new URLSearchParams();
      params.set("level", String(level));

      const response = await apiFetch(
        getWorkspaceScopedUrl(
          `${API_ENDPOINTS.GRAPH_COMMUNITY_REPORTS}?${params.toString()}`,
          scope,
        ),
        {
          ...getFetchOptions(),
          method: "POST",
        },
      );
      return handleResponse<GraphCommunityReportsResponse>(response);
    },

    async getTables(): Promise<GraphTableInfo[]> {
      const response = await fetchWithTimeout(
        getWorkspaceScopedUrl(API_ENDPOINTS.GRAPH_TABLES, scope),
        {
          ...getFetchOptions(),
          headers: getHeaders(),
        },
        8000,
      );
      return handleResponse<GraphTableInfo[]>(response);
    },

    async executeRawQuery(sql: string): Promise<GraphRawQueryResponse> {
      const response = await apiFetch(
        getWorkspaceScopedUrl(API_ENDPOINTS.GRAPH_RAW_QUERY, scope),
        {
          ...getFetchOptions(),
          method: "POST",
          headers: getHeaders(),
          body: JSON.stringify({ sql }),
        },
      );
      return handleResponse<GraphRawQueryResponse>(response);
    },
  };
}

export const graphragApi = createGraphragApi();

export default graphragApi;
