import { AlertTriangle, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { DatabaseConnector, SessionDatabaseAttachment } from "@/types/databaseConnectors";
import {
  describeConnectorTarget,
  formatDateTime,
  formatTestStatus,
} from "./utils";

interface ConnectorCardCompactProps {
  connector: DatabaseConnector;
  currentAttachment?: SessionDatabaseAttachment;
  sessionId?: string | null;
  testingConnectorId: string | null;
  sessionActionKey: string | null;
  isDetailExpanded: boolean;
  onEdit: (connector: DatabaseConnector) => void;
  onDelete: (connector: DatabaseConnector) => void;
  onTest: (connector: DatabaseConnector) => void;
  onAttach: (connector: DatabaseConnector) => void;
  onDetach: (connector: DatabaseConnector) => void;
  onToggleDetails: (connectorId: string) => void;
}

export function ConnectorCardCompact({
  connector,
  currentAttachment,
  sessionId,
  testingConnectorId,
  sessionActionKey,
  isDetailExpanded,
  onEdit,
  onDelete,
  onTest,
  onAttach,
  onDetach,
  onToggleDetails,
}: ConnectorCardCompactProps) {
  const currentSessionStatus = currentAttachment
    ? "已挂载到当前会话"
    : "未挂载到当前会话";

  return (
    <div className="rounded-lg border border-border bg-background">
      <div className="flex flex-col gap-3 border-b border-border px-3 py-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground">{connector.name}</h3>
            <span className="rounded border border-border px-2 py-0.5 text-[11px] text-muted-foreground">
              {connector.db_type === "postgres" ? "PostgreSQL" : connector.db_type === "mysql" ? "MySQL" : "InfluxDB 3"}
            </span>
          </div>
          <p className="mt-1 truncate text-xs text-muted-foreground">{describeConnectorTarget(connector)}</p>
          {sessionId ? (
            <div className="mt-2 space-y-1">
              <p className="text-xs font-medium text-foreground">当前会话：{currentSessionStatus}</p>
            </div>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {sessionId ? (
            currentAttachment ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => onDetach(connector)}
                disabled={sessionActionKey === `detach:${connector.connector_id}`}
              >
                从当前会话卸载
              </Button>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={() => onAttach(connector)}
                disabled={sessionActionKey === `attach:${connector.connector_id}`}
              >
                附加到当前会话
              </Button>
            )
          ) : null}
          <Button variant="outline" size="sm" onClick={() => onTest(connector)} disabled={testingConnectorId === connector.connector_id}>
            测试连接
          </Button>
          <Button variant="outline" size="sm" onClick={() => onEdit(connector)}>
            编辑
          </Button>
          <Button variant="outline" size="sm" onClick={() => onDelete(connector)}>
            删除
          </Button>
        </div>
      </div>

      <div className="px-3 py-2">
        <button
          type="button"
          onClick={() => onToggleDetails(connector.connector_id)}
          className="flex w-full items-center justify-between gap-3 rounded-md border border-border bg-muted/20 px-3 py-2 text-left"
        >
          <div className="flex items-center gap-2 text-xs font-medium text-foreground">
            <AlertTriangle className="h-3.5 w-3.5 text-muted-foreground" />
            <span>详情</span>
          </div>
          <ChevronDown
            className={`h-4 w-4 text-muted-foreground transition-transform ${isDetailExpanded ? "rotate-180" : ""}`}
          />
        </button>
        {isDetailExpanded ? (
          <div className="mt-2 grid gap-3 rounded-md border border-border bg-muted/10 px-3 py-3 text-xs md:grid-cols-2">
            <div>
              <div className="text-muted-foreground">最近测试</div>
              <div className="mt-1 text-foreground">{formatTestStatus(connector)}</div>
              <div className="mt-1 text-muted-foreground">
                {connector.last_test_message || "暂无测试说明"}
              </div>
            </div>
            <div>
              <div className="text-muted-foreground">用途描述</div>
              <div className="mt-1 text-foreground">{connector.description || "无描述"}</div>
              {connector.allow_notebook_access ? (
                <div className="mt-1 text-amber-600">已导出凭据给 Notebook 运行时</div>
              ) : null}
              <div className="mt-1 text-muted-foreground">
                超时 {connector.query_timeout_seconds}s · 行数 {connector.row_limit}
              </div>
              <div className="mt-1 text-muted-foreground">更新时间：{formatDateTime(connector.updated_at)}</div>
              {currentAttachment ? (
                <div className="mt-1 text-muted-foreground">
                  当前会话挂载于 {formatDateTime(currentAttachment.attached_at)}
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
