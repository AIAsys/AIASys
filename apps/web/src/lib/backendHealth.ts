import { API_BASE_URL } from "@/config/api";

/**
 * 后端健康状态监控器（被动检测 + 主动轮询恢复）。
 *
 * 工作原理：
 * - 被动检测：httpClient 在每次 fetch 网络级失败时调用 recordFailure()，
 *   连续达到阈值后标记后端不可达。
 * - 主动恢复：一旦标记不可达，开始轮询 /health 端点，检测到成功响应后恢复。
 *
 * 仅检测 fetch 本身抛异常（网络不可达 / 连接被拒绝），不把 HTTP 4xx/5xx
 * 视为后端不可达——能返回 HTTP 响应说明后端是活着的。
 *
 * 浏览器离线（navigator.onLine === false）时不计入后端故障，由
 * NetworkStatusOverlay 负责提示。
 */

const FAILURE_THRESHOLD = 2;
const POLL_INTERVAL_MS = 5000;
const HEALTH_CHECK_TIMEOUT_MS = 4000;

type HealthListener = (healthy: boolean) => void;

class BackendHealthMonitor {
  private consecutiveFailures = 0;
  private healthy = true;
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private listeners = new Set<HealthListener>();

  get isHealthy(): boolean {
    return this.healthy;
  }

  subscribe(listener: HealthListener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  /** 后端返回了 HTTP 响应（任意状态码）→ 后端可达。 */
  recordSuccess(): void {
    this.consecutiveFailures = 0;
    if (!this.healthy) {
      this.setHealthy(true);
    }
  }

  /** fetch 本身抛异常（网络不可达 / 连接拒绝）→ 计入故障。 */
  recordFailure(): void {
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      return;
    }
    this.consecutiveFailures++;
    if (this.healthy && this.consecutiveFailures >= FAILURE_THRESHOLD) {
      this.setHealthy(false);
    }
  }

  private setHealthy(healthy: boolean): void {
    this.healthy = healthy;
    if (healthy) {
      this.stopPolling();
    } else {
      this.startPolling();
    }
    this.listeners.forEach((fn) => fn(healthy));
  }

  private startPolling(): void {
    if (this.pollTimer !== null) return;
    this.checkHealth();
    this.pollTimer = setInterval(() => this.checkHealth(), POLL_INTERVAL_MS);
  }

  private stopPolling(): void {
    if (this.pollTimer !== null) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  private async checkHealth(): Promise<void> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), HEALTH_CHECK_TIMEOUT_MS);
    try {
      const response = await fetch(`${API_BASE_URL}/health`, {
        method: "GET",
        cache: "no-store",
        signal: controller.signal,
      });
      if (response.ok) {
        this.recordSuccess();
      }
    } catch {
      // 仍然不可达，继续轮询
    } finally {
      clearTimeout(timeoutId);
    }
  }
}

export const backendHealth = new BackendHealthMonitor();
