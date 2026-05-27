import type { DatabaseConnector } from "@/types/databaseConnectors";

export function formatDateTime(value?: string | null): string {
  if (!value) {
    return "未记录";
  }

  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) {
    return value;
  }

  return timestamp.toLocaleString("zh-CN", {
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function describeConnectorTarget(connector: DatabaseConnector): string {
  const parts = [
    connector.host,
    connector.port ? String(connector.port) : null,
    connector.database_name,
  ].filter(Boolean);

  return parts.length > 0 ? parts.join(" / ") : "未配置";
}

export function formatTestStatus(connector: DatabaseConnector): string {
  if (connector.last_test_status === "passed") {
    return "最近测试通过";
  }
  if (connector.last_test_status === "failed") {
    return "最近测试失败";
  }
  return "最近尚未测试";
}
