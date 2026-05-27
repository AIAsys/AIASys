import { apiRequest } from "@/lib/api/httpClient";

export interface KernelEnvItem {
  name: string;
  display_name: string;
  language: string;
  executable: string | null;
  executable_exists?: boolean;
  protected: boolean;
  forbidden?: boolean;
  forbidden_reason?: string | null;
}

export interface KernelEnvListResponse {
  status: string;
  count: number;
  kernels: KernelEnvItem[];
}

export interface KernelEnvRegisterRequest {
  name: string;
  python_path: string;
}

export interface KernelEnvOperationResponse {
  status: string;
  operation: string;
  name: string;
  [key: string]: unknown;
}

export function isAbsoluteExecutablePath(value: string | null | undefined): value is string {
  const path = value?.trim();
  if (!path) {
    return false;
  }
  return path.startsWith("/") || /^[A-Za-z]:[\\/]/.test(path) || path.startsWith("\\\\");
}

export function canBindKernelEnvToWorkspace(env: KernelEnvItem): env is KernelEnvItem & { executable: string } {
  return !env.forbidden && env.executable_exists !== false && isAbsoluteExecutablePath(env.executable);
}

export function listBindableKernelEnvs(envs: KernelEnvItem[]): Array<KernelEnvItem & { executable: string }> {
  return envs.filter(canBindKernelEnvToWorkspace);
}

export async function listKernelEnvs(): Promise<KernelEnvListResponse> {
  return apiRequest<KernelEnvListResponse>("/api/kernel-envs");
}

export async function registerKernelEnv(
  name: string,
  pythonPath: string,
): Promise<KernelEnvOperationResponse> {
  return apiRequest<KernelEnvOperationResponse>("/api/kernel-envs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, python_path: pythonPath }),
  });
}

export async function removeKernelEnv(
  name: string,
): Promise<KernelEnvOperationResponse> {
  return apiRequest<KernelEnvOperationResponse>(`/api/kernel-envs/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
}
