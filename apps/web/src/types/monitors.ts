/**
 * Monitor 实时输出流类型定义
 */

export interface MonitorSegment {
  index: number;
  timestamp: string;
  content: string;
  is_stderr: boolean;
}

export interface MonitorSessionInfo {
  id: string;
  command: string;
  status: "running" | "completed" | "error" | "killed";
  exit_code: number | null;
  mode: "notify" | "silent";
  created_at: number;
  completed_at: number | null;
}

export interface MonitorListResponse {
  monitors: MonitorSessionInfo[];
}

export interface MonitorDetailResponse {
  info: MonitorSessionInfo;
  segments: MonitorSegment[];
}

export interface MonitorSegmentsResponse {
  monitor_id: string;
  segments: MonitorSegment[];
}

export interface MonitorSpawnRequest {
  command: string;
  description?: string;
  timeout_seconds?: number;
  cwd?: string;
  mode?: "notify" | "silent";
}

export interface MonitorSpawnResponse {
  monitor_id: string;
  command: string;
  status: string;
  mode?: string;
  created_at: number;
}

export interface GlobalMonitorInfo {
  id: string;
  command: string;
  status: "running" | "completed" | "error" | "killed";
  exit_code: number | null;
  mode: "notify" | "silent";
  created_at: number;
  completed_at: number | null;
  session_id: string;
  session_key: string;
  workspace_id: string;
  workspace_title: string;
}

export interface GlobalMonitorListResponse {
  monitors: GlobalMonitorInfo[];
}

export interface GlobalMonitorSummaryResponse {
  total: number;
  running: number;
  completed: number;
  error: number;
  killed: number;
}
