import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Database,
  Loader2,
  Play,
  RefreshCw,
  ShieldAlert,
  Table2,
  SquareTerminal,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  emitDatabaseConnectorSync,
  subscribeDatabaseConnectorSync,
} from "@/lib/databaseConnectorEvents";
import {
  executeRuntimeDatabase,
  getDatabaseConnectorErrorMessage,
  listRuntimeDatabaseHandles,
  queryRuntimeDatabase,
} from "@/lib/api/databaseConnectors";
import { cn } from "@/lib/utils";
import {
  getRuntimeDatabaseTypeLabel,
  runtimeHandleSupportsWrite,
} from "@/types/databaseConnectors";
import type {
  RuntimeDatabaseExecuteResponse,
  RuntimeDatabaseHandleInfo,
  RuntimeDatabaseQueryResponse,
} from "@/types/databaseConnectors";

interface RuntimeDatabaseConsoleProps {
  sessionId?: string | null;
}

type QueryResultState =
  | {
      type: "query";
      data: RuntimeDatabaseQueryResponse;
    }
  | {
      type: "execute";
      data: RuntimeDatabaseExecuteResponse;
    }
  | null;

const DEFAULT_SQL = "SELECT 1 AS ok;";

function formatCellValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "NULL";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function getHandleSubtitle(handle: RuntimeDatabaseHandleInfo): string {
  const typeLabel = getRuntimeDatabaseTypeLabel(handle.db_type);
  return `${typeLabel} · 当前会话挂载`;
}

export function RuntimeDatabaseConsole({
  sessionId,
}: RuntimeDatabaseConsoleProps) {
  const [handles, setHandles] = useState<RuntimeDatabaseHandleInfo[]>([]);
  const [selectedHandle, setSelectedHandle] = useState<string>("");
  const [sql, setSql] = useState(DEFAULT_SQL);
  const [queryLimitInput, setQueryLimitInput] = useState("100");
  const [loadingHandles, setLoadingHandles] = useState(false);
  const [runningAction, setRunningAction] = useState<"query" | "execute" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<QueryResultState>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (!sessionId) {
      setHandles([]);
      setSelectedHandle("");
      setError(null);
      setResult(null);
      return;
    }

    let cancelled = false;
    const currentSessionId = sessionId;

    async function loadHandles() {
      setLoadingHandles(true);
      setError(null);

      try {
        const response = await listRuntimeDatabaseHandles(currentSessionId);
        if (cancelled) {
          return;
        }
        setHandles(response.handles);
        setSelectedHandle((current) => {
          const fallback = response.handles[0]?.handle ?? "";
          return response.handles.some((item) => item.handle === current) ? current : fallback;
        });
      } catch (err) {
        if (cancelled) {
          return;
        }
        setError(getDatabaseConnectorErrorMessage(err, "加载 SQL 数据库句柄失败"));
      } finally {
        if (!cancelled) {
          setLoadingHandles(false);
        }
      }
    }

    void loadHandles();

    return () => {
      cancelled = true;
    };
  }, [reloadToken, sessionId]);

  useEffect(() => {
    return subscribeDatabaseConnectorSync((event) => {
      if (!sessionId) {
        return;
      }
      if (event.scope === "attachments" && event.sessionId && event.sessionId !== sessionId) {
        return;
      }
      setReloadToken((current) => current + 1);
    });
  }, [sessionId]);

  const selectedHandleInfo = useMemo(
    () => handles.find((handle) => handle.handle === selectedHandle) ?? null,
    [handles, selectedHandle],
  );
  const canExecute = selectedHandleInfo ? runtimeHandleSupportsWrite(selectedHandleInfo) : false;

  async function handleRunQuery() {
    if (!sessionId) {
      setError("当前暂无可用会话，无法执行 SQL。");
      return;
    }
    if (!selectedHandle) {
      setError("当前没有可用的数据库句柄。");
      return;
    }
    if (!sql.trim()) {
      setError("请输入要执行的 SQL。");
      return;
    }

    const parsedLimit = Number.parseInt(queryLimitInput, 10);
    const limit = Number.isFinite(parsedLimit) && parsedLimit > 0 ? parsedLimit : 100;

    setRunningAction("query");
    setError(null);
    try {
      const response = await queryRuntimeDatabase(sessionId, {
        handle: selectedHandle,
        sql,
        limit,
      });
      setResult({ type: "query", data: response });
    } catch (err) {
      setError(getDatabaseConnectorErrorMessage(err, "执行 SQL 查询失败"));
    } finally {
      setRunningAction(null);
    }
  }

  async function handleRunExecute() {
    if (!sessionId) {
      setError("当前暂无可用会话，无法执行 SQL。");
      return;
    }
    if (!selectedHandle) {
      setError("当前没有可用的数据库句柄。");
      return;
    }
    if (!sql.trim()) {
      setError("请输入要执行的 SQL。");
      return;
    }
    if (!canExecute) {
      setError("当前数据库句柄只开放查询，不支持写入或 DDL。");
      return;
    }

    setRunningAction("execute");
    setError(null);
    try {
      const response = await executeRuntimeDatabase(sessionId, {
        handle: selectedHandle,
        sql,
      });
      setResult({ type: "execute", data: response });
      emitDatabaseConnectorSync({ scope: "attachments", sessionId });
    } catch (err) {
      setError(getDatabaseConnectorErrorMessage(err, "执行 SQL 写入失败"));
    } finally {
      setRunningAction(null);
    }
  }

  return (
    <div className="rounded-lg border border-border bg-background">
      <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div>
          <div className="flex items-center gap-2">
            <SquareTerminal className="h-4 w-4" />
            <h3 className="text-sm font-semibold text-foreground">SQL 控制台</h3>
          </div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            直接对平台内置 DuckDB 或当前会话挂载的外部数据库输入 SQL。查询与写入共用同一入口，外部连接仍受挂载授权、能力上限和审批策略约束。
          </p>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={() => setReloadToken((current) => current + 1)}
          disabled={!sessionId || loadingHandles}
        >
          <RefreshCw className={`h-4 w-4 ${loadingHandles ? "animate-spin" : ""}`} />
          刷新句柄
        </Button>
      </div>

      <div className="space-y-4 p-4">
        {!sessionId ? (
          <div className="flex min-h-36 flex-col items-center justify-center rounded-lg border border-dashed border-border bg-muted/20 px-6 text-center text-muted-foreground">
            <Database className="mb-2 h-8 w-8 opacity-50" />
            <p className="text-sm font-medium text-foreground/80">当前暂无可用会话</p>
            <p className="mt-1 text-xs leading-5">
              先进入一个具体会话，再使用 SQL 控制台访问内置库或挂载库。
            </p>
          </div>
        ) : null}

        {sessionId ? (
          <>
            <div className="rounded-lg border border-border bg-muted/20 p-3">
              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                <Database className="h-4 w-4" />
                可用连接
              </div>
              <p className="mt-1 text-[11px] leading-5 text-muted-foreground">
                这里显示当前会话已经挂载的数据库连接。
              </p>
              <div className="mt-3 space-y-2">
                {handles.length > 0 ? (
                  handles.map((handle) => (
                    <button
                      key={handle.handle}
                      type="button"
                      onClick={() => setSelectedHandle(handle.handle)}
                      className={cn(
                        "w-full rounded-lg border px-3 py-2 text-left transition-colors",
                        selectedHandle === handle.handle
                          ? "border-foreground bg-background"
                          : "border-border bg-background hover:border-foreground/30",
                      )}
                    >
                      <div className="text-xs font-medium text-foreground">{handle.name}</div>
                      <div className="mt-1 text-[11px] text-muted-foreground">
                        {getHandleSubtitle(handle)}
                      </div>
                    </button>
                  ))
                ) : (
                  <div className="rounded-lg border border-dashed border-border px-3 py-4 text-[11px] text-muted-foreground">
                    当前会话暂无数据库挂载。
                  </div>
                )}
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_120px]">
              <div className="space-y-2">
                <label className="text-xs font-medium text-foreground">当前数据源</label>
                <Select
                  value={selectedHandle}
                  onValueChange={setSelectedHandle}
                  disabled={loadingHandles || handles.length === 0}
                >
                  <SelectTrigger>
                    <SelectValue placeholder={loadingHandles ? "加载数据库句柄中..." : "选择当前数据源"} />
                  </SelectTrigger>
                  <SelectContent>
                    {handles.map((handle) => (
                      <SelectItem key={handle.handle} value={handle.handle}>
                        {handle.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <label className="text-xs font-medium text-foreground">查询行数上限</label>
                <Input
                  value={queryLimitInput}
                  onChange={(event) => setQueryLimitInput(event.target.value)}
                  inputMode="numeric"
                  placeholder="100"
                />
              </div>
            </div>

            {selectedHandleInfo ? (
              <div className="rounded-lg border border-border bg-muted/20 px-3 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">{getHandleSubtitle(selectedHandleInfo)}</Badge>
                </div>
                <p className="mt-2 text-[11px] leading-5 text-muted-foreground">
                  {canExecute
                    ? "这个句柄支持查询，也支持写入或 DDL（最终权限由目标数据库账号控制）。"
                    : "这个句柄当前只开放查询能力，不允许写入或变更结构。"}
                </p>
              </div>
            ) : null}

            <div className="space-y-2">
              <label className="text-xs font-medium text-foreground">SQL</label>
              <Textarea
                value={sql}
                onChange={(event) => setSql(event.target.value)}
                placeholder="例如：SELECT * FROM your_table LIMIT 20;"
                className="min-h-44 font-mono text-[12px] leading-6"
              />
            </div>

            {error ? (
              <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                <div className="flex items-start gap-2">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{error}</span>
                </div>
              </div>
            ) : null}

            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={handleRunQuery} disabled={runningAction !== null || loadingHandles}>
                {runningAction === "query" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Play className="h-4 w-4" />
                )}
                执行查询
              </Button>
              <Button
                variant="outline"
                onClick={handleRunExecute}
                disabled={runningAction !== null || loadingHandles || !canExecute}
              >
                {runningAction === "execute" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <ShieldAlert className="h-4 w-4" />
                )}
                执行写入 / DDL
              </Button>
            </div>

            <div className="rounded-lg border border-border bg-background">
              <div className="flex items-center gap-2 border-b border-border px-4 py-3">
                <Table2 className="h-4 w-4" />
                <h4 className="text-sm font-semibold text-foreground">执行结果</h4>
              </div>

              {!result ? (
                <div className="flex min-h-32 items-center justify-center px-6 text-center text-xs leading-5 text-muted-foreground">
                  这里会显示 SQL 查询结果、影响行数、审批策略和审计编号。
                </div>
              ) : null}

              {result?.type === "execute" ? (
                <div className="space-y-3 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline">affected_rows: {result.data.affected_rows}</Badge>

                    {result.data.duration_ms !== null ? (
                      <Badge variant="outline">{result.data.duration_ms} ms</Badge>
                    ) : null}
                  </div>
                  <p className="text-sm text-foreground">{result.data.message || "执行完成"}</p>
                  {result.data.audit_id ? (
                    <p className="text-[11px] font-mono text-muted-foreground">
                      audit_id: {result.data.audit_id}
                    </p>
                  ) : null}
                </div>
              ) : null}

              {result?.type === "query" ? (
                <div className="space-y-3 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline">rows: {result.data.row_count}</Badge>
                    {result.data.applied_limit !== null ? (
                      <Badge variant="outline">limit: {result.data.applied_limit}</Badge>
                    ) : null}
                    {result.data.duration_ms !== null ? (
                      <Badge variant="outline">{result.data.duration_ms} ms</Badge>
                    ) : null}
                    {result.data.truncated ? (
                      <Badge variant="outline">结果已截断</Badge>
                    ) : null}
                  </div>

                  <div className="overflow-hidden rounded-lg border border-border">
                    {result.data.columns.length === 0 ? (
                      <div className="px-4 py-6 text-center text-xs text-muted-foreground">
                        查询已执行，但当前结果没有可展示的列。
                      </div>
                    ) : (
                      <div className="max-h-72 overflow-auto">
                        <table className="w-full text-left text-xs">
                          <thead className="sticky top-0 bg-muted/60">
                            <tr>
                              {result.data.columns.map((column) => (
                                <th
                                  key={column}
                                  className="border-b border-border px-3 py-2 font-medium text-muted-foreground"
                                >
                                  {column}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {result.data.rows.map((row, index) => (
                              <tr key={`${index}-${row.length}`} className="border-b border-border/60 last:border-b-0">
                                {result.data.columns.map((column, columnIndex) => (
                                  <td
                                    key={`${column}-${index}`}
                                    className="px-3 py-2 align-top font-mono text-[11px] text-foreground"
                                  >
                                    {formatCellValue(row[columnIndex])}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>

                  {result.data.audit_id ? (
                    <p className="text-[11px] font-mono text-muted-foreground">
                      audit_id: {result.data.audit_id}
                    </p>
                  ) : null}
                </div>
              ) : null}
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
