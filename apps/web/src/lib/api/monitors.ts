/**
 * Monitor API 封装
 */

import type {
  MonitorListResponse,
  MonitorDetailResponse,
  MonitorSegmentsResponse,
  MonitorSpawnRequest,
  MonitorSpawnResponse,
  GlobalMonitorListResponse,
  GlobalMonitorSummaryResponse,
} from "@/types/monitors";

const API_BASE = "/api/sessions";

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.text().catch(() => "unknown error");
    throw new Error(`HTTP ${res.status}: ${err}`);
  }
  return res.json() as Promise<T>;
}

export function listSessionMonitors(
  userId: string,
  sessionId: string,
): Promise<MonitorListResponse> {
  return fetchJson<MonitorListResponse>(
    `${API_BASE}/${userId}/${sessionId}/monitors`,
  );
}

export function getMonitorDetail(
  userId: string,
  sessionId: string,
  monitorId: string,
): Promise<MonitorDetailResponse> {
  return fetchJson<MonitorDetailResponse>(
    `${API_BASE}/${userId}/${sessionId}/monitors/${monitorId}`,
  );
}

export function getMonitorSegments(
  userId: string,
  sessionId: string,
  monitorId: string,
  sinceIndex: number,
): Promise<MonitorSegmentsResponse> {
  return fetchJson<MonitorSegmentsResponse>(
    `${API_BASE}/${userId}/${sessionId}/monitors/${monitorId}/segments?since_index=${sinceIndex}`,
  );
}

export function killMonitor(
  userId: string,
  sessionId: string,
  monitorId: string,
): Promise<{ success: boolean; monitor_id: string }> {
  return fetchJson<{ success: boolean; monitor_id: string }>(
    `${API_BASE}/${userId}/${sessionId}/monitors/${monitorId}/kill`,
    { method: "POST" },
  );
}

export function spawnMonitor(
  userId: string,
  sessionId: string,
  req: MonitorSpawnRequest,
): Promise<MonitorSpawnResponse> {
  return fetchJson<MonitorSpawnResponse>(
    `${API_BASE}/${userId}/${sessionId}/monitors/spawn`,
    {
      method: "POST",
      body: JSON.stringify(req),
    },
  );
}

export function deleteMonitor(
  userId: string,
  sessionId: string,
  monitorId: string,
): Promise<{ success: boolean; monitor_id: string }> {
  return fetchJson<{ success: boolean; monitor_id: string }>(
    `${API_BASE}/${userId}/${sessionId}/monitors/${monitorId}`,
    { method: "DELETE" },
  );
}

export function updateMonitorMode(
  userId: string,
  sessionId: string,
  monitorId: string,
  mode: "notify" | "silent",
): Promise<{ success: boolean; monitor_id: string; mode: string }> {
  return fetchJson<{ success: boolean; monitor_id: string; mode: string }>(
    `${API_BASE}/${userId}/${sessionId}/monitors/${monitorId}/mode?mode=${mode}`,
    { method: "PUT" },
  );
}

export function listGlobalMonitors(
  status?: string,
): Promise<GlobalMonitorListResponse> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return fetchJson<GlobalMonitorListResponse>(`${API_BASE}/monitors${query}`);
}

export function getGlobalMonitorSummary(): Promise<GlobalMonitorSummaryResponse> {
  return fetchJson<GlobalMonitorSummaryResponse>(`${API_BASE}/monitors/summary`);
}
