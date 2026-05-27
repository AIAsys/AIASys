import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Database, RefreshCw } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  emitDatabaseConnectorSync,
  subscribeDatabaseConnectorSync,
} from "@/lib/databaseConnectorEvents";
import {
  describeRuntimeDatabaseTable,
  executeRuntimeDatabase,
  getDatabaseConnectorErrorMessage,
  listRuntimeDatabaseHandles,
  listRuntimeDatabaseTables,
  queryRuntimeDatabase,
} from "@/lib/api/databaseConnectors";
import {
  getRuntimeDatabaseTypeLabel,
  runtimeHandleSupportsWrite,
} from "@/types/databaseConnectors";
import type {
  RuntimeDatabaseDescribeTableResponse,
  RuntimeDatabaseExecuteResponse,
  RuntimeDatabaseHandleInfo,
  RuntimeDatabaseListTablesResponse,
  RuntimeDatabaseQueryResponse,
} from "@/types/databaseConnectors";
import { DatabaseSchemaTree } from "./DatabaseSchemaTree";
import { SqlQueryPanel } from "./SqlQueryPanel";
import { QueryResultPanel } from "./QueryResultPanel";

interface DatabaseQueryWorkbenchProps {
  sessionId?: string | null;
  initialHandle?: string;
  showHandleSelector?: boolean;
}

type QueryResultState =
  | { type: "query"; data: RuntimeDatabaseQueryResponse }
  | { type: "execute"; data: RuntimeDatabaseExecuteResponse }
  | null;

const DEFAULT_SQL = "SELECT 1 AS ok;";
const MIN_LEFT_WIDTH = 160;
const MAX_LEFT_WIDTH = 400;
const DEFAULT_LEFT_WIDTH = 220;
const NARROW_DEFAULT_LEFT_WIDTH = 180;

function quoteIdentifier(ident: string): string {
  return `"${ident.replace(/"/g, "\"\"")}"`;
}

function quoteTableName(fullName: string): string {
  const dot = fullName.indexOf(".");
  if (dot > 0) {
    const schema = fullName.slice(0, dot);
    const name = fullName.slice(dot + 1);
    return `${quoteIdentifier(schema)}.${quoteIdentifier(name)}`;
  }
  return quoteIdentifier(fullName);
}

function getHandleSubtitle(handle: RuntimeDatabaseHandleInfo): string {
  const typeLabel = getRuntimeDatabaseTypeLabel(handle.db_type);
  return `${typeLabel} · ${handle.name}`;
}

export function DatabaseQueryWorkbench({
  sessionId,
  initialHandle,
  showHandleSelector = true,
}: DatabaseQueryWorkbenchProps) {
  const [handles, setHandles] = useState<RuntimeDatabaseHandleInfo[]>([]);
  const [selectedHandle, setSelectedHandle] = useState<string>("");
  const [sql, setSql] = useState(DEFAULT_SQL);
  const [queryLimitInput, setQueryLimitInput] = useState("100");
  const [loadingHandles, setLoadingHandles] = useState(false);
  const [runningAction, setRunningAction] = useState<"query" | "execute" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<QueryResultState>(null);
  const [reloadToken, setReloadToken] = useState(0);

  // 结构树状态
  const [tablesResponse, setTablesResponse] = useState<RuntimeDatabaseListTablesResponse | null>(null);
  const [loadingTables, setLoadingTables] = useState(false);
  const [selectedTable, setSelectedTable] = useState<string | null>(null);
  const [tableDetail, setTableDetail] = useState<RuntimeDatabaseDescribeTableResponse | null>(null);
  const [loadingTableDetail, setLoadingTableDetail] = useState(false);
  const [expandedTables, setExpandedTables] = useState<Set<string>>(new Set());
  const [expandedSchemas, setExpandedSchemas] = useState<Set<string>>(new Set());

  // 左侧栏宽度 + 拖拽
  const [leftWidth, setLeftWidth] = useState(() => {
    if (typeof window !== "undefined" && window.innerWidth < 1440) {
      return NARROW_DEFAULT_LEFT_WIDTH;
    }
    return DEFAULT_LEFT_WIDTH;
  });
  const [isResizing, setIsResizing] = useState(false);
  const resizeStartX = useRef(0);
  const resizeStartWidth = useRef(0);

  // 加载句柄列表
  useEffect(() => {
    if (!sessionId) {
      setHandles([]);
      setSelectedHandle("");
      setError(null);
      setResult(null);
      setTablesResponse(null);
      setSelectedTable(null);
      setTableDetail(null);
      return;
    }

    let cancelled = false;
    const currentSessionId = sessionId;

    async function loadHandles() {
      setLoadingHandles(true);
      setError(null);
      try {
        const response = await listRuntimeDatabaseHandles(currentSessionId);
        if (cancelled) return;
        setHandles(response.handles);
        setSelectedHandle((current) => {
          if (initialHandle && response.handles.some((item) => item.handle === initialHandle)) {
            return initialHandle;
          }
          if (response.handles.some((item) => item.handle === current)) {
            return current;
          }
          return response.handles[0]?.handle ?? "";
        });
      } catch (err) {
        if (cancelled) return;
        setError(getDatabaseConnectorErrorMessage(err, "加载数据库句柄失败"));
      } finally {
        if (!cancelled) setLoadingHandles(false);
      }
    }

    void loadHandles();

    return () => {
      cancelled = true;
    };
  }, [reloadToken, sessionId, initialHandle]);

  // 同步事件订阅
  useEffect(() => {
    return subscribeDatabaseConnectorSync((event) => {
      if (!sessionId) return;
      if (event.scope === "attachments" && event.sessionId && event.sessionId !== sessionId) {
        return;
      }
      setReloadToken((current) => current + 1);
    });
  }, [sessionId]);

  // 加载表列表
  useEffect(() => {
    if (!sessionId || !selectedHandle) {
      setTablesResponse(null);
      setSelectedTable(null);
      setTableDetail(null);
      setExpandedTables(new Set());
      setExpandedSchemas(new Set());
      return;
    }

    let cancelled = false;

    async function loadTables() {
      setLoadingTables(true);
      try {
        const response = await listRuntimeDatabaseTables(sessionId!, selectedHandle!);
        if (cancelled) return;
        setTablesResponse(response);
      } catch (err) {
        if (cancelled) return;
        if (import.meta.env.DEV) {
          console.warn("加载表列表失败", err);
        }
        setTablesResponse(null);
      } finally {
        if (!cancelled) setLoadingTables(false);
      }
    }

    void loadTables();

    return () => {
      cancelled = true;
    };
  }, [sessionId, selectedHandle, reloadToken]);

  // 加载表结构详情
  useEffect(() => {
    if (!sessionId || !selectedHandle || !selectedTable) {
      setTableDetail(null);
      return;
    }

    let cancelled = false;

    async function loadDetail() {
      setLoadingTableDetail(true);
      try {
        const response = await describeRuntimeDatabaseTable(
          sessionId!,
          selectedTable!,
          selectedHandle!
        );
        if (cancelled) return;
        setTableDetail(response);
      } catch (err) {
        if (cancelled) return;
        if (import.meta.env.DEV) {
          console.warn("加载表结构失败", err);
        }
        setTableDetail(null);
      } finally {
        if (!cancelled) setLoadingTableDetail(false);
      }
    }

    void loadDetail();

    return () => {
      cancelled = true;
    };
  }, [sessionId, selectedHandle, selectedTable]);

  const selectedHandleInfo = useMemo(
    () => handles.find((handle) => handle.handle === selectedHandle) ?? null,
    [handles, selectedHandle]
  );
  const canExecute = selectedHandleInfo ? runtimeHandleSupportsWrite(selectedHandleInfo) : false;

  const handleRunQuery = useCallback(async () => {
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
  }, [sessionId, selectedHandle, sql, queryLimitInput]);

  const handleRunExecute = useCallback(async () => {
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
  }, [sessionId, selectedHandle, sql, canExecute]);

  // 点击表名：只选中 + 展开/收起，不替换 SQL
  const handleTableSelect = useCallback((fullTableName: string) => {
    setSelectedTable(fullTableName);
    setExpandedTables((prev) => {
      const next = new Set(prev);
      if (next.has(fullTableName)) {
        next.delete(fullTableName);
      } else {
        next.add(fullTableName);
      }
      return next;
    });
  }, []);

  const handleTableToggle = useCallback((fullTableName: string) => {
    setExpandedTables((prev) => {
      const next = new Set(prev);
      if (next.has(fullTableName)) {
        next.delete(fullTableName);
      } else {
        next.add(fullTableName);
      }
      return next;
    });
  }, []);

  const handleGenerateQuery = useCallback((fullTableName: string) => {
    setSql(`SELECT * FROM ${quoteTableName(fullTableName)} LIMIT 100;`);
  }, []);

  const handleSchemaToggle = useCallback((schema: string) => {
    setExpandedSchemas((prev) => {
      const next = new Set(prev);
      if (next.has(schema)) {
        next.delete(schema);
      } else {
        next.add(schema);
      }
      return next;
    });
  }, []);

  const handleRefresh = useCallback(() => {
    setReloadToken((current) => current + 1);
  }, []);

  // 拖拽调整宽度
  const handleResizeStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      setIsResizing(true);
      resizeStartX.current = e.clientX;
      resizeStartWidth.current = leftWidth;
    },
    [leftWidth]
  );

  useEffect(() => {
    if (!isResizing) return;

    function handleMouseMove(e: MouseEvent) {
      const delta = e.clientX - resizeStartX.current;
      const newWidth = Math.max(
        MIN_LEFT_WIDTH,
        Math.min(MAX_LEFT_WIDTH, resizeStartWidth.current + delta)
      );
      setLeftWidth(newWidth);
    }

    function handleMouseUp() {
      setIsResizing(false);
    }

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isResizing]);

  if (!sessionId) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6 text-center text-muted-foreground">
        <Database className="mb-2 h-8 w-8 opacity-50" />
        <p className="text-sm font-medium text-foreground/80">当前暂无可用会话</p>
        <p className="mt-1 text-xs leading-5">
          先进入一个具体会话，再使用 SQL 查询工作台。
        </p>
      </div>
    );
  }

  if (handles.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6 text-center text-muted-foreground">
        <Database className="mb-2 h-8 w-8 opacity-50" />
        <p className="text-sm font-medium text-foreground/80">当前会话没有可用的外部数据库连接</p>
        <p className="mt-1 text-xs leading-5">
          先在工作区挂载一个外部数据库连接，再使用 SQL 查询工作台。
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {showHandleSelector ? (
        <div className="flex-shrink-0 border-b border-border px-3 py-2">
          <div className="flex items-center gap-2">
            <Select
              value={selectedHandle}
              onValueChange={setSelectedHandle}
              disabled={loadingHandles || handles.length === 0}
            >
              <SelectTrigger className="h-8 text-[12px]">
                <SelectValue placeholder={loadingHandles ? "加载中..." : "选择数据源"} />
              </SelectTrigger>
              <SelectContent>
                {handles.map((handle) => (
                  <SelectItem key={handle.handle} value={handle.handle} className="text-[12px]">
                    <span className="flex items-center gap-1.5">
                      {handle.name}
                      <span className="text-[10px] text-muted-foreground">{getRuntimeDatabaseTypeLabel(handle.db_type)}</span>
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <button
              type="button"
              className="inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-accent disabled:opacity-50"
              onClick={handleRefresh}
              disabled={loadingHandles}
              title="刷新"
            >
              <RefreshCw className={`h-4 w-4 ${loadingHandles ? "animate-spin" : ""}`} />
            </button>

            {selectedHandleInfo ? (
              <span className="text-[11px] text-muted-foreground">
                {getHandleSubtitle(selectedHandleInfo)}
              </span>
            ) : null}
          </div>
        </div>
      ) : null}

      {/* 主体：左右分栏 */}
      <div className="min-h-0 flex-1 flex overflow-hidden">
        {/* 左侧：结构树 */}
        <div
          className="flex-shrink-0 border-r border-border flex flex-col"
          style={{ width: leftWidth }}
        >
          <DatabaseSchemaTree
            tables={tablesResponse?.tables ?? []}
            selectedTable={selectedTable}
            expandedTables={expandedTables}
            expandedSchemas={expandedSchemas}
            loadingTables={loadingTables}
            loadingTableDetail={loadingTableDetail}
            tableDetail={tableDetail}
            onTableSelect={handleTableSelect}
            onTableToggle={handleTableToggle}
            onSchemaToggle={handleSchemaToggle}
            onGenerateQuery={handleGenerateQuery}
          />
        </div>

        {/* 拖拽线 */}
        <div
          className={`w-[3px] flex-shrink-0 cursor-col-resize hover:bg-border active:bg-primary/30 transition-colors ${
            isResizing ? "bg-primary/30" : "bg-transparent"
          }`}
          onMouseDown={handleResizeStart}
          title="拖拽调整宽度"
        />

        {/* 右侧：SQL 编辑器 + 结果 */}
        <div className="min-w-0 flex-1 flex flex-col overflow-hidden">
          <SqlQueryPanel
            sql={sql}
            onSqlChange={setSql}
            queryLimitInput={queryLimitInput}
            onLimitChange={setQueryLimitInput}
            runningAction={runningAction}
            canExecute={canExecute}
            disabled={loadingHandles || handles.length === 0}
            error={error}
            onRunQuery={handleRunQuery}
            onRunExecute={handleRunExecute}
          />
          <QueryResultPanel result={result} />
        </div>
      </div>
    </div>
  );
}
