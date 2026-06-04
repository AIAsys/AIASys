import { API_BASE_URL } from "@/config/api";

type QueryValue = string | number | boolean | null | undefined;

export interface ApiRequestOptions extends Omit<RequestInit, "body"> {
  query?: Record<string, QueryValue>;
  body?: BodyInit | unknown | null;
  timeoutMs?: number;
}

interface ErrorPayloadLike {
  detail?: unknown;
  message?: unknown;
  error?: unknown;
}

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const base =
    path.startsWith("http://") || path.startsWith("https://")
      ? path
      : `${API_BASE_URL}${path}`;

  if (!query) {
    return base;
  }

  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value === null || value === undefined || value === "") {
      return;
    }
    params.set(key, String(value));
  });
  const queryString = params.toString();
  return queryString ? `${base}${base.includes("?") ? "&" : "?"}${queryString}` : base;
}

function isBodyInit(value: unknown): value is BodyInit {
  return (
    typeof value === "string" ||
    value instanceof FormData ||
    value instanceof URLSearchParams ||
    value instanceof Blob ||
    value instanceof ArrayBuffer ||
    value instanceof ReadableStream
  );
}

function extractErrorMessage(payload: unknown, status: number): string {
  if (!payload || typeof payload !== "object") {
    return `HTTP ${status}`;
  }
  const candidate = payload as ErrorPayloadLike;
  if (typeof candidate.detail === "string" && candidate.detail.trim()) {
    return candidate.detail.trim();
  }
  if (typeof candidate.message === "string" && candidate.message.trim()) {
    return candidate.message.trim();
  }
  if (typeof candidate.error === "string" && candidate.error.trim()) {
    return candidate.error.trim();
  }
  if (
    candidate.detail &&
    typeof candidate.detail === "object" &&
    "message" in candidate.detail
  ) {
    const detailMessage = (candidate.detail as { message?: unknown }).message;
    if (typeof detailMessage === "string" && detailMessage.trim()) {
      return detailMessage.trim();
    }
  }
  return `HTTP ${status}`;
}

async function parseResponseBody(response: Response): Promise<unknown> {
  if (response.status === 204) {
    return null;
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

export class ApiRequestError extends Error {
  status: number;
  payload: unknown;

  constructor(status: number, payload: unknown) {
    super(extractErrorMessage(payload, status));
    this.name = "ApiRequestError";
    this.status = status;
    this.payload = payload;
  }
}

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const {
    query,
    body,
    timeoutMs,
    headers,
    signal,
    method,
    credentials,
    ...rest
  } = options;

  const requestHeaders = new Headers(headers);
  let requestBody: BodyInit | undefined;
  if (body !== undefined && body !== null) {
    if (isBodyInit(body)) {
      requestBody = body;
    } else {
      if (!requestHeaders.has("Content-Type")) {
        requestHeaders.set("Content-Type", "application/json");
      }
      requestBody = JSON.stringify(body);
    }
  }

  const controller = new AbortController();
  let timeoutId: number | null = null;

  // Merge external signal: if external signal aborts, also abort our controller
  if (signal) {
    if (signal.aborted) {
      controller.abort();
    } else {
      signal.addEventListener("abort", () => controller.abort(), { once: true });
    }
  }

  // Set up timeout
  if (timeoutMs) {
    timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  }
  const requestSignal = controller.signal;

  try {
    const response = await fetch(buildUrl(path, query), {
      method: method || (requestBody ? "POST" : "GET"),
      credentials: credentials ?? "include",
      headers: requestHeaders,
      body: requestBody,
      signal: requestSignal,
      ...rest,
    });

    const payload = await parseResponseBody(response);
    if (!response.ok) {
      throw new ApiRequestError(response.status, payload);
    }
    return payload as T;
  } finally {
    if (timeoutId !== null) {
      window.clearTimeout(timeoutId);
    }
  }
}

export async function apiFetch(
  path: string,
  options: ApiRequestOptions = {},
): Promise<Response> {
  const {
    query,
    body,
    timeoutMs,
    headers,
    signal,
    method,
    credentials,
    ...rest
  } = options;

  const requestHeaders = new Headers(headers);
  let requestBody: BodyInit | undefined;
  if (body !== undefined && body !== null) {
    if (isBodyInit(body)) {
      requestBody = body;
    } else {
      if (!requestHeaders.has("Content-Type")) {
        requestHeaders.set("Content-Type", "application/json");
      }
      requestBody = JSON.stringify(body);
    }
  }

  const controller = new AbortController();
  let timeoutId: number | null = null;

  // Merge external signal: if external signal aborts, also abort our controller
  if (signal) {
    if (signal.aborted) {
      controller.abort();
    } else {
      signal.addEventListener("abort", () => controller.abort(), { once: true });
    }
  }

  // Set up timeout
  if (timeoutMs) {
    timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  }
  const requestSignal = controller.signal;

  try {
    return await fetch(buildUrl(path, query), {
      method: method || (requestBody ? "POST" : "GET"),
      credentials: credentials ?? "include",
      headers: requestHeaders,
      body: requestBody,
      signal: requestSignal,
      ...rest,
    });
  } finally {
    if (timeoutId !== null) {
      window.clearTimeout(timeoutId);
    }
  }
}
