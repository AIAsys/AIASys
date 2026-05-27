import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { DatabaseConnector, SessionDatabaseAttachment } from "@/types/databaseConnectors";
import {
  describeConnectorTarget,
  formatDateTime,
  formatTestStatus,
} from "./utils";

interface ConnectorCardProps {
  connector: DatabaseConnector;
  currentAttachment?: SessionDatabaseAttachment;
  sessionId?: string | null;
  testingConnectorId: string | null;
  sessionActionKey: string | null;
  compact?: boolean;
  onEdit: (connector: DatabaseConnector) => void;
  onDelete: (connector: DatabaseConnector) => void;
  onTest: (connector: DatabaseConnector) => void;
  onAttach: (connector: DatabaseConnector) => void;
  onDetach: (connector: DatabaseConnector) => void;
}

export function ConnectorCard({
  connector,
  currentAttachment,
  sessionId,
  testingConnectorId,
  sessionActionKey,
  compact,
  onEdit,
  onDelete,
  onTest,
  onAttach,
  onDetach,
}: ConnectorCardProps) {
  const currentSessionStatus = currentAttachment
    ? "已挂载到当前会话"
    : "未挂载到当前会话";

  return (
    <div className="rounded-lg border border-border bg-background">
      <div
        className={
          compact
            ? "flex flex-col gap-3 border-b border-border px-3 py-3"
            : "flex flex-col gap-4 border-b border-border px-4 py-4 lg:flex-row lg:items-start lg:justify-between"
        }
      >
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3
              className={
                compact ? "text-sm font-semibold text-foreground" : "text-base font-semibold text-foreground"
              }
            >
              {connector.name}
            </h3>
            <span className="rounded border border-border px-2 py-0.5 text-[11px] text-muted-foreground">
              {connector.db_type === "postgres" ? "PostgreSQL" : connector.db_type === "mysql" ? "MySQL" : "InfluxDB 3"}
            </span>
          </div>
          <p
            className={
              compact ? "mt-1 truncate text-xs text-muted-foreground" : "mt-2 text-sm text-muted-foreground"
            }
          >
            {describeConnectorTarget(connector)}
          </p>
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
                {sessionActionKey === `detach:${connector.connector_id}` ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : null}
                从当前会话卸载
              </Button>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={() => onAttach(connector)}
                disabled={sessionActionKey === `attach:${connector.connector_id}`}
              >
                {sessionActionKey === `attach:${connector.connector_id}` ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : null}
                附加到当前会话
              </Button>
            )
          ) : null}
          <Button
            variant="outline"
            size="sm"
            onClick={() => onTest(connector)}
            disabled={testingConnectorId === connector.connector_id}
          >
            {testingConnectorId === connector.connector_id ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
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

      {!compact && (
        <div className="grid gap-4 px-4 py-4 md:grid-cols-3">
          <div>
            <div className="text-xs text-muted-foreground">最近测试</div>
            <div className="mt-1 text-sm text-foreground">{formatTestStatus(connector)}</div>
            <div className="mt-1 text-xs text-muted-foreground">
              {connector.last_test_message || "暂无测试说明"}
            </div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">用途描述</div>
            <div className="mt-1 text-sm text-foreground">{connector.description || "无描述"}</div>
            {connector.allow_notebook_access ? (
              <div className="mt-1 text-xs text-amber-600">已导出凭据给 Notebook 运行时</div>
            ) : null}
          </div>
          <div>
            <div className="text-xs text-muted-foreground">更新时间</div>
            <div className="mt-1 text-sm text-foreground">{formatDateTime(connector.updated_at)}</div>
            {currentAttachment ? (
              <div className="mt-1 text-xs text-muted-foreground">
                当前会话挂载于 {formatDateTime(currentAttachment.attached_at)}
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
