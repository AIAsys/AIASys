import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";

import { expect, type APIRequestContext } from "@playwright/test";

export const DEFAULT_ENV_ID = "python-data-analysis";

export interface LifecycleUserMeta {
  userId: string;
  email: string;
  password: string;
}

export interface RuntimeEnvironmentSummary {
  id: string;
  name: string;
}

export interface WorkspaceMeta {
  workspaceId: string;
  currentConversationId: string;
  currentSessionId: string;
}

const BACKEND_WORKSPACES_ROOT = path.resolve(
  process.cwd(),
  "../backend/data/workspaces",
);

export function getWorkspaceRoot(userId: string, workspaceId: string): string {
  return path.join(BACKEND_WORKSPACES_ROOT, userId, workspaceId);
}

export async function registerLifecycleUser(
  api: APIRequestContext,
): Promise<LifecycleUserMeta> {
  const response = await api.get("/api/auth/session");

  const body = (await response.json()) as {
    user?: { id?: string; email?: string };
    detail?: string;
    error?: string;
  };

  if (!response.ok() || !body.user?.id) {
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : body.detail
          ? JSON.stringify(body.detail)
          : body.error || response.status();
    throw new Error(
      `Failed to register lifecycle user: ${detail}`,
    );
  }

  const meta: LifecycleUserMeta = {
    userId: body.user.id,
    email: body.user.email || "local_default@localhost",
    password: "",
  };

  return meta;
}

export async function listEnvironments(
  api: APIRequestContext,
): Promise<RuntimeEnvironmentSummary[]> {
  const response = await api.get("/api/runtime-envs");
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as RuntimeEnvironmentSummary[];
}

export async function createSession(
  api: APIRequestContext,
  options: {
    title: string;
    envId?: string;
    sandboxMode?: "docker" | "local";
  },
): Promise<string> {
  const sessionId = randomUUID();
  const response = await api.post("/api/sessions/create", {
    data: {
      session_id: sessionId,
      title: options.title,
      env_id: options.envId || DEFAULT_ENV_ID,
      sandbox_mode: options.sandboxMode || "local",
    },
  });

  expect(response.ok()).toBeTruthy();
  return sessionId;
}

export async function createWorkspace(
  api: APIRequestContext,
  options: {
    title: string;
    workspaceId?: string;
    mode?: "analysis" | "research";
    initialConversationId?: string;
    initialConversationTitle?: string;
  },
): Promise<WorkspaceMeta> {
  const workspaceId = options.workspaceId || randomUUID();
  const initialConversationId = options.initialConversationId || randomUUID();
  const response = await api.post("/api/workspaces", {
    data: {
      workspace_id: workspaceId,
      title: options.title,
      mode: options.mode || "analysis",
      initial_conversation_id: initialConversationId,
      initial_conversation_title: options.initialConversationTitle || "新会话",
    },
  });

  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as {
    workspace_id: string;
    current_conversation?: {
      conversation_id?: string;
      session_id?: string;
    };
  };

  return {
    workspaceId: body.workspace_id,
    currentConversationId:
      body.current_conversation?.conversation_id || initialConversationId,
    currentSessionId:
      body.current_conversation?.session_id || initialConversationId,
  };
}

export async function createWorkspaceConversation(
  api: APIRequestContext,
  workspaceId: string,
  options: {
    title: string;
    conversationId?: string;
    mode?: "analysis" | "research";
    branchedFromConversationId?: string;
  },
): Promise<string> {
  const conversationId = options.conversationId || randomUUID();
  const response = await api.post(`/api/workspaces/${workspaceId}/conversations`, {
    data: {
      conversation_id: conversationId,
      title: options.title,
      mode: options.mode || "analysis",
      branched_from_conversation_id: options.branchedFromConversationId,
    },
  });

  expect(response.ok()).toBeTruthy();
  return conversationId;
}

export async function addSessionMessage(
  api: APIRequestContext,
  userId: string,
  sessionId: string,
  content: string,
  role: "user" | "assistant" = "user",
): Promise<void> {
  const response = await api.post(`/api/sessions/${userId}/${sessionId}/messages`, {
    data: {
      role,
      content,
    },
  });

  expect(response.ok()).toBeTruthy();
}

export async function deleteSession(
  api: APIRequestContext,
  userId: string,
  sessionId: string | null | undefined,
): Promise<void> {
  if (!sessionId) {
    return;
  }

  try {
    const deletePromise = api
      .delete(`/api/sessions/${userId}/${sessionId}`, {
        timeout: 5_000,
      })
      .catch((error) => {
        console.warn(`[Lifecycle] 删除会话失败或超时: ${sessionId}`, error);
        return null;
      });

    const response = await Promise.race<
      Awaited<ReturnType<typeof api.delete>> | null
    >([
      deletePromise,
      new Promise<null>((resolve) => {
        setTimeout(() => resolve(null), 5_000);
      }),
    ]);

    if (!response) {
      console.warn(`[Lifecycle] 删除会话超时，跳过清理: ${sessionId}`);
      return;
    }

    if (!response.ok() && response.status() !== 404) {
      console.warn(
        `[Lifecycle] 删除会话失败: ${sessionId} status=${response.status()}`,
      );
    }
  } catch (error) {
    console.warn(`[Lifecycle] 删除会话失败或超时: ${sessionId}`, error);
  }
}

export async function deleteWorkspace(
  api: APIRequestContext,
  workspaceId: string | null | undefined,
): Promise<void> {
  if (!workspaceId) {
    return;
  }

  try {
    const response = await api.delete(`/api/workspaces/${workspaceId}`, {
      timeout: 10_000,
    });

    if (!response.ok() && response.status() !== 404) {
      console.warn(
        `[Lifecycle] 删除工作区失败: ${workspaceId} status=${response.status()}`,
      );
    }
  } catch (error) {
    console.warn(`[Lifecycle] 删除工作区失败或超时: ${workspaceId}`, error);
  }
}

export async function seedWorkspaceFile(options: {
  userId: string;
  workspaceId: string;
  filePath: string;
  content: string;
}): Promise<void> {
  const targetPath = path.join(
    BACKEND_WORKSPACES_ROOT,
    options.userId,
    options.workspaceId,
    "workspace",
    options.filePath,
  );
  await mkdir(path.dirname(targetPath), { recursive: true });
  await writeFile(targetPath, options.content, "utf-8");
}

export async function setWorkspaceCurrentConversation(options: {
  userId: string;
  workspaceId: string;
  conversationId: string;
}): Promise<void> {
  const metaPath = path.join(
    BACKEND_WORKSPACES_ROOT,
    options.userId,
    options.workspaceId,
    ".aiasys/workspace",
    "workspace.json",
  );
  const payload = JSON.parse(await readFile(metaPath, "utf-8")) as Record<string, unknown>;
  payload.current_conversation_id = options.conversationId;
  payload.updated_at = new Date().toISOString();
  await writeFile(metaPath, `${JSON.stringify(payload, null, 2)}\n`, "utf-8");
}

export async function createPendingAskUser(
  api: APIRequestContext,
  sessionId: string,
  overrides?: Partial<{
    title: string;
    message: string;
    timeout: number;
  }>,
): Promise<string> {
  const response = await api.post("/api/ask-user/dev/create-pending", {
    data: {
      session_id: sessionId,
      title: overrides?.title || "键盘保护测试",
      message: overrides?.message || "请确认 AskUser 打开时页面级快捷键不会误触发。",
      timeout: overrides?.timeout || 120,
    },
  });

  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as { request_id: string };
  return body.request_id;
}

export async function resolveAskUser(
  api: APIRequestContext,
  requestId: string,
  approved = false,
): Promise<void> {
  const response = await api.post("/api/ask-user/resolve", {
    data: {
      request_id: requestId,
      approved,
    },
  });

  if (!response.ok() && response.status() !== 404) {
    throw new Error(`Failed to resolve AskUser request ${requestId}: ${response.status()}`);
  }
}

export function extractSessionIdFromUrl(url: string): string | null {
  const analysisUrl = new URL(url, "http://localhost");
  const sessionIdFromQuery = analysisUrl.searchParams.get("session_id");
  if (sessionIdFromQuery) {
    return sessionIdFromQuery;
  }
  const match = analysisUrl.pathname.match(/\/analysis\/([^/?#]+)/);
  return match?.[1] || null;
}

export function extractWorkspaceIdFromUrl(url: string): string | null {
  const analysisUrl = new URL(url, "http://localhost");
  return analysisUrl.searchParams.get("workspace_id");
}

export function extractConversationIdFromUrl(url: string): string | null {
  const analysisUrl = new URL(url, "http://localhost");
  return (
    analysisUrl.searchParams.get("conversation_id") ||
    analysisUrl.searchParams.get("session_id")
  );
}

export function buildAnalysisUrl(options: {
  workspaceId?: string | null;
  conversationId?: string | null;
  sessionId?: string | null;
}): string {
  const search = new URLSearchParams();
  if (options.workspaceId) {
    search.set("workspace_id", options.workspaceId);
  }
  if (options.conversationId) {
    search.set("conversation_id", options.conversationId);
  }
  if (options.sessionId) {
    search.set("session_id", options.sessionId);
  }
  const query = search.toString();
  return query ? `/analysis?${query}` : "/analysis";
}
