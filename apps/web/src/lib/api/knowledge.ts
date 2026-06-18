/**
 * 知识库 API 客户端
 */

import { API_BASE_URL, API_ENDPOINTS } from "@/config/api";
import { apiFetch, apiRequest } from "@/lib/api/httpClient";
import type {
  KnowledgeBase,
  CreateKnowledgeBaseRequest,
  UpdateKnowledgeBaseRequest,
  Document,
  UploadDocumentResponse,
  UploadDocumentOptions,
  BatchUploadDocumentResponse,
  QueryRequest,
  QueryResponse,
  KnowledgeBaseHealth,
  KnowledgeBaseTableInfo,
  KnowledgeBaseRawQueryResponse,
} from "@/types/knowledge";

/**
 * 获取请求头
 * 
 * 注意：认证通过 Cookie (access_token) 传递
 * fetch 默认会携带同源 cookie
 */
/**
 * 知识库 API
 */
export const knowledgeApi = {
  /**
   * 获取知识库列表
   */
  async listKnowledgeBases(): Promise<KnowledgeBase[]> {
    return apiRequest<KnowledgeBase[]>(
      `${API_BASE_URL}${API_ENDPOINTS.KNOWLEDGE_BASES}`,
    );
  },

  /**
   * 获取知识库详情
   */
  async getKnowledgeBase(kbId: string): Promise<KnowledgeBase> {
    return apiRequest<KnowledgeBase>(
      `${API_BASE_URL}${API_ENDPOINTS.KNOWLEDGE_BASE(kbId)}`,
    );
  },

  /**
   * 创建知识库
   */
  async createKnowledgeBase(
    data: CreateKnowledgeBaseRequest
  ): Promise<KnowledgeBase> {
    return apiRequest<KnowledgeBase>(`${API_BASE_URL}${API_ENDPOINTS.KNOWLEDGE_BASES}`, {
      method: "POST",
      body: data,
    });
  },

  /**
   * 更新知识库
   */
  async updateKnowledgeBase(
    kbId: string,
    data: UpdateKnowledgeBaseRequest
  ): Promise<KnowledgeBase> {
    return apiRequest<KnowledgeBase>(
      `${API_BASE_URL}${API_ENDPOINTS.KNOWLEDGE_BASE(kbId)}`,
      {
        method: "PUT",
        body: data,
      }
    );
  },

  /**
   * 删除知识库
   */
  async deleteKnowledgeBase(kbId: string): Promise<void> {
    await apiRequest<unknown>(
      `${API_BASE_URL}${API_ENDPOINTS.KNOWLEDGE_BASE(kbId)}`,
      {
        method: "DELETE",
      }
    );
  },

  /**
   * 获取文档列表
   */
  async listDocuments(kbId: string): Promise<Document[]> {
    return apiRequest<Document[]>(
      `${API_BASE_URL}${API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENTS(kbId)}`,
    );
  },

  /**
   * 上传文档
   */
  uploadDocument(
    kbId: string,
    file: File,
    onProgress?: (progress: number) => void,
    options: UploadDocumentOptions = {},
  ): { promise: Promise<UploadDocumentResponse>; abort: () => void } {
    const formData = new FormData();
    formData.append("file", file);
    appendUploadOptions(formData, options);

    // 如果有进度回调，使用 XMLHttpRequest
    if (onProgress) {
      const xhr = new XMLHttpRequest();
      const promise = new Promise<UploadDocumentResponse>((resolve, reject) => {
        xhr.upload.addEventListener("progress", (event) => {
          if (event.lengthComputable) {
            const progress = Math.round((event.loaded / event.total) * 100);
            onProgress(progress);
          }
        });

        xhr.addEventListener("load", () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              resolve(JSON.parse(xhr.responseText));
            } catch {
              reject(new Error("上传失败：服务端返回数据异常"));
            }
          } else {
            const payload = parseJsonSafely(xhr.responseText);
            reject(new Error(extractUploadErrorMessage(payload, xhr.status)));
          }
        });

        xhr.addEventListener("error", () => {
          reject(new Error("上传失败"));
        });

        xhr.addEventListener("abort", () => {
          reject(new Error("上传已取消"));
        });

        xhr.open(
          "POST",
          `${API_BASE_URL}${API_ENDPOINTS.KNOWLEDGE_BASE_UPLOAD(kbId)}`
        );
        // 重要：携带 cookie
        xhr.withCredentials = true;
        xhr.send(formData);
      });

      return { promise, abort: () => xhr.abort() };
    }

    // 普通 fetch 请求
    const controller = new AbortController();
    const promise = (async () => {
      const response = await apiFetch(
        `${API_BASE_URL}${API_ENDPOINTS.KNOWLEDGE_BASE_UPLOAD(kbId)}`,
        {
          method: "POST",
          body: formData,
          signal: controller.signal,
        }
      );
      if (!response.ok) {
        const error = await response.json().catch(() => ({ message: "请求失败" }));
        throw new Error(error.message || `HTTP ${response.status}`);
      }
      return response.json() as Promise<UploadDocumentResponse>;
    })();

    return { promise, abort: () => controller.abort() };
  },

  /**
   * 批量上传文档
   *
   * 通过 signal 支持取消正在进行的上传请求。
   */
  async uploadDocuments(
    kbId: string,
    files: File[],
    options: UploadDocumentOptions = {},
    signal?: AbortSignal,
  ): Promise<BatchUploadDocumentResponse> {
    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));
    appendUploadOptions(formData, options);

    return apiRequest<BatchUploadDocumentResponse>(
      `${API_BASE_URL}${API_ENDPOINTS.KNOWLEDGE_BASE_BATCH_UPLOAD(kbId)}`,
      {
        method: "POST",
        body: formData,
        signal,
      },
    );
  },

  /**
   * 删除文档
   */
  async deleteDocument(kbId: string, docId: string): Promise<void> {
    await apiRequest<unknown>(
      `${API_BASE_URL}${API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENT(kbId, docId)}`,
      {
        method: "DELETE",
      }
    );
  },

  /**
   * 查询知识库
   */
  async query(kbId: string, data: QueryRequest): Promise<QueryResponse> {
    return apiRequest<QueryResponse>(
      `${API_BASE_URL}${API_ENDPOINTS.KNOWLEDGE_BASE_QUERY(kbId)}`,
      {
        method: "POST",
        body: data,
      }
    );
  },

  /**
   * 获取知识库底层表列表
   */
  async getTables(kbId: string): Promise<KnowledgeBaseTableInfo[]> {
    return apiRequest<KnowledgeBaseTableInfo[]>(
      `${API_BASE_URL}${API_ENDPOINTS.KNOWLEDGE_BASE_TABLES(kbId)}`,
    );
  },

  /**
   * 执行原始 SQL 查询
   */
  async executeRawQuery(
    kbId: string,
    sql: string
  ): Promise<KnowledgeBaseRawQueryResponse> {
    return apiRequest<KnowledgeBaseRawQueryResponse>(
      `${API_BASE_URL}${API_ENDPOINTS.KNOWLEDGE_BASE_RAW_QUERY(kbId)}`,
      {
        method: "POST",
        body: { sql },
      }
    );
  },

  /**
   * 健康检查
   */
  async health(): Promise<KnowledgeBaseHealth> {
    return apiRequest<KnowledgeBaseHealth>(
      `${API_BASE_URL}${API_ENDPOINTS.KNOWLEDGE_HEALTH}`,
    );
  },
};

function appendUploadOptions(formData: FormData, options: UploadDocumentOptions): void {
  if (options.extraction_mode) {
    formData.append("extraction_mode", options.extraction_mode);
  }
  if (options.embedding_model !== undefined && options.embedding_model !== null) {
    formData.append("embedding_model", options.embedding_model);
  }
  if (typeof options.chunk_size === "number") {
    formData.append("chunk_size", String(options.chunk_size));
  }
  if (typeof options.chunk_overlap === "number") {
    formData.append("chunk_overlap", String(options.chunk_overlap));
  }
  if (options.search_mode) {
    formData.append("search_mode", options.search_mode);
  }
}

function parseJsonSafely(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function extractUploadErrorMessage(payload: unknown, status: number): string {
  if (payload && typeof payload === "object") {
    const candidate = payload as { detail?: unknown; message?: unknown; error?: unknown };
    if (typeof candidate.detail === "string" && candidate.detail.trim()) {
      return candidate.detail.trim();
    }
    if (typeof candidate.message === "string" && candidate.message.trim()) {
      return candidate.message.trim();
    }
    if (typeof candidate.error === "string" && candidate.error.trim()) {
      return candidate.error.trim();
    }
  }
  return `上传失败：HTTP ${status}`;
}

export default knowledgeApi;
