/**
 * 数据库文件预览组件
 * 支持 SQLite (.db, .sqlite, .sqlite3) 和 DuckDB (.duckdb) 文件的
 * Schema 查看与 SQL 查询，支持结果分页。
 */

import {
  AlertCircle,
  Database,
  Loader2,
  Play,
  Table2,
  ChevronRight,
  ChevronDown,
  ChevronLeft,
  ChevronFirst,
} from "lucide-react";
import React, { useCallback, useEffect, useState } from "react";
import Editor from "react-simple-code-editor";
import Prism from "prismjs";
import "prismjs/components/prism-sql";
import { API_ENDPOINTS, getCurrentUserId } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";

interface DbFilePreviewProps {
  fileName: string;
  sessionId?: string | null;
  scope?: "workspace" | "global";
}

interface DbColumnInfo {
  name: string;
  type: string | null;
}

interface DbTableInfo {
  name: string;
  columns: DbColumnInfo[];
}

interface DbSchemaResponse {
  tables: DbTableInfo[];
}

interface DbQueryResponse {
  columns: string[];
  rows: unknown[][];
  row_count: number;
}

type DbTab = "schema" | "query";

const DEFAULT_PAGE_SIZE = 100;

function highlightSql(code: string) {
  return Prism.highlight(code, Prism.languages.sql, "sql");
}

export const DbFilePreview: React.FC<DbFilePreviewProps> = ({
  fileName,
  sessionId,
  scope = "workspace",
}) => {
  const [activeTab, setActiveTab] = useState<DbTab>("schema");
  const [tables, setTables] = useState<DbTableInfo[]>([]);
  const [expandedTable, setExpandedTable] = useState<string | null>(null);
  const [isLoadingSchema, setIsLoadingSchema] = useState(false);
  const [schemaError, setSchemaError] = useState<string | null>(null);

  const [sql, setSql] = useState("SELECT 1 AS ok;");
  const [queryResult, setQueryResult] = useState<DbQueryResponse | null>(null);
  const [isQuerying, setIsQuerying] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);

  // 分页状态
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [hasMoreRows, setHasMoreRows] = useState(false);
  const [currentTable, setCurrentTable] = useState<string | null>(null);

  const dbType = fileName.toLowerCase().endsWith(".duckdb")
    ? "DuckDB"
    : "SQLite";

  const loadSchema = useCallback(async () => {
    if (scope === "workspace" && !sessionId) return;
    setIsLoadingSchema(true);
    setSchemaError(null);
    try {
      const userId = getCurrentUserId();
      const url =
        scope === "global"
          ? API_ENDPOINTS.GLOBAL_FILE_DATABASE_SCHEMA(userId, fileName)
          : API_ENDPOINTS.FILE_DATABASE_SCHEMA(userId, sessionId!, fileName);
      const data = await apiRequest<DbSchemaResponse>(url);
      setTables(data.tables);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "加载表结构失败";
      setSchemaError(message);
    } finally {
      setIsLoadingSchema(false);
    }
  }, [sessionId, fileName, scope]);

  useEffect(() => {
    if (activeTab === "schema") {
      void loadSchema();
    }
  }, [activeTab, loadSchema]);

  const handleQuery = useCallback(async (querySql?: string) => {
    if (scope === "workspace" && !sessionId) return;
    const sqlToExecute = (querySql ?? sql).trim();
    if (!sqlToExecute || isQuerying) return;
    setIsQuerying(true);
    setQueryError(null);
    try {
      const userId = getCurrentUserId();
      const url =
        scope === "global"
          ? API_ENDPOINTS.GLOBAL_FILE_DATABASE_QUERY(userId, fileName)
          : API_ENDPOINTS.FILE_DATABASE_QUERY(userId, sessionId!, fileName);
      const data = await apiRequest<DbQueryResponse>(url, {
        method: "POST",
        body: { sql: sqlToExecute },
      });
      setQueryResult(data);
      // 如果是分页查询，尝试解析总行数（简化处理：用返回行数作为参考）
      if (data.row_count < pageSize) {
        setHasMoreRows(false);
      } else {
        setHasMoreRows(true);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "查询失败";
      setQueryError(message);
      setQueryResult(null);
    } finally {
      setIsQuerying(false);
    }
  }, [sessionId, fileName, sql, isQuerying, pageSize, scope]);

  const buildPaginatedSql = useCallback((tableName: string, page: number, size: number) => {
    const offset = (page - 1) * size;
    return `SELECT * FROM "${tableName}" LIMIT ${size} OFFSET ${offset};`;
  }, []);

  const handlePreviewTable = useCallback((tableName: string) => {
    setCurrentTable(tableName);
    setCurrentPage(1);
    const paginatedSql = buildPaginatedSql(tableName, 1, pageSize);
    setSql(paginatedSql);
    setActiveTab("query");
  }, [buildPaginatedSql, pageSize]);

  const handlePageChange = useCallback((newPage: number) => {
    if (!currentTable || newPage < 1) return;
    setCurrentPage(newPage);
    const paginatedSql = buildPaginatedSql(currentTable, newPage, pageSize);
    setSql(paginatedSql);
    void handleQuery(paginatedSql);
  }, [currentTable, pageSize, buildPaginatedSql, handleQuery]);

  useEffect(() => {
    if (activeTab === "query" && sql.trim()) {
      void handleQuery();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  const startRow = queryResult ? (currentPage - 1) * pageSize + 1 : 0;
  const endRow = queryResult ? startRow + queryResult.row_count - 1 : 0;

  const tabs: { id: DbTab; label: string; icon: React.ReactNode }[] = [
    { id: "schema", label: "表结构", icon: <Table2 className="h-3.5 w-3.5" /> },
    { id: "query", label: "SQL 查询", icon: <Play className="h-3.5 w-3.5" /> },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      {/* 头部 */}
      <div className="border-b border-border px-4 py-3 shrink-0">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Database className="h-4 w-4 shrink-0 text-tertiary" />
              <span className="truncate">{fileName}</span>
            </div>
            <div className="mt-1 text-xs leading-5 text-muted-foreground">
              {dbType} 数据库文件
              {tables.length > 0 && ` · ${tables.length} 个表`}
            </div>
          </div>
        </div>
      </div>

      {/* Tab 切换 */}
      <div className="flex items-center gap-1 px-2 py-1.5 border-b border-border bg-muted/30 shrink-0">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              activeTab === tab.id
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground hover:bg-muted"
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* 内容区 */}
      <div className="flex-1 overflow-auto">
        {activeTab === "schema" && (
          <div className="p-4">
            {isLoadingSchema && (
              <div className="flex items-center justify-center py-8 text-muted-foreground">
                <Loader2 className="w-5 h-5 animate-spin mr-2" />
                <span className="text-sm">加载表结构中...</span>
              </div>
            )}

            {schemaError && (
              <div className="flex flex-col items-center justify-center py-8 text-destructive gap-2">
                <AlertCircle className="w-6 h-6" />
                <span className="text-sm">{schemaError}</span>
              </div>
            )}

            {!isLoadingSchema && !schemaError && tables.length === 0 && (
              <div className="flex items-center justify-center py-8 text-muted-foreground">
                <span className="text-sm">此数据库暂无表</span>
              </div>
            )}

            {!isLoadingSchema &&
              !schemaError &&
              tables.map((table) => (
                <div
                  key={table.name}
                  className="mb-2 border border-border rounded-lg overflow-hidden"
                >
                  <button
                    onClick={() =>
                      setExpandedTable((prev) =>
                        prev === table.name ? null : table.name
                      )
                    }
                    className="flex items-center justify-between w-full px-3 py-2 bg-muted/30 hover:bg-muted/50 transition-colors text-left"
                  >
                    <div className="flex items-center gap-2">
                      {expandedTable === table.name ? (
                        <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
                      ) : (
                        <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
                      )}
                      <span className="text-xs font-semibold text-foreground">
                        {table.name}
                      </span>
                      <span className="text-[10px] text-muted-foreground">
                        {table.columns.length} 列
                      </span>
                    </div>
                    <div
                      onClick={(e) => {
                        e.stopPropagation();
                        handlePreviewTable(table.name);
                      }}
                      className="flex items-center gap-1 px-2 py-0.5 text-[10px] bg-secondary hover:bg-secondary/80 rounded text-secondary-foreground transition-colors cursor-pointer"
                    >
                      <Play className="w-3 h-3" />
                      预览数据
                    </div>
                  </button>
                  {expandedTable === table.name && (
                    <div className="px-3 py-2 bg-background">
                      <table className="w-full text-[11px] border-collapse">
                        <thead>
                          <tr className="border-b border-border">
                            <th className="px-2 py-1 text-left font-medium text-muted-foreground">
                              列名
                            </th>
                            <th className="px-2 py-1 text-left font-medium text-muted-foreground">
                              类型
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {table.columns.map((col) => (
                            <tr
                              key={col.name}
                              className="border-b border-border/50"
                            >
                              <td className="px-2 py-1 text-foreground font-mono">
                                {col.name}
                              </td>
                              <td className="px-2 py-1 text-muted-foreground">
                                {col.type || "-"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              ))}
          </div>
        )}

        {activeTab === "query" && (
          <div className="flex flex-col h-full">
            <div className="p-3 border-b border-border shrink-0">
              <div className="flex items-center gap-2">
                <div className="flex-1 relative rounded border border-border bg-muted/30" style={{ minHeight: "100px" }}>
                  <Editor
                    value={sql}
                    onValueChange={setSql}
                    highlight={highlightSql}
                    padding={12}
                    className="font-mono text-[12px] leading-5"
                    textareaClassName="focus:outline-none bg-transparent"
                    preClassName="language-sql m-0 p-0 bg-transparent min-h-[100px]"
                    placeholder="输入 SQL 查询..."
                    style={{
                      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
                      fontSize: 12,
                      lineHeight: "20px",
                      minHeight: "100px",
                    }}
                  />
                </div>
                <button
                  onClick={() => handleQuery()}
                  disabled={isQuerying || !sql.trim()}
                  className="flex items-center gap-1.5 px-3 py-2 text-xs bg-primary hover:bg-primary/90 disabled:bg-muted disabled:opacity-50 disabled:cursor-not-allowed rounded-md text-primary-foreground transition-colors shrink-0"
                >
                  {isQuerying ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Play className="w-3.5 h-3.5" />
                  )}
                  执行
                </button>
              </div>
              <div className="mt-1 flex items-center justify-between text-[10px] text-muted-foreground">
                <span>Cmd/Ctrl + Enter 执行查询</span>
                {currentTable && (
                  <span className="text-[10px] text-muted-foreground">
                    当前表: {currentTable}
                  </span>
                )}
              </div>
            </div>

            <div className="flex-1 overflow-auto">
              {queryError && (
                <div className="p-4 text-destructive text-sm">
                  {queryError}
                </div>
              )}

              {queryResult && (
                <div className="p-3">
                  <div className="mb-2 text-[11px] text-muted-foreground">
                    共 {queryResult.row_count} 条记录
                    {currentTable && ` · 第 ${currentPage} 页`}
                  </div>
                  {queryResult.row_count > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs border-collapse">
                        <thead className="bg-muted/50 sticky top-0">
                          <tr>
                            {queryResult.columns.map((col) => (
                              <th
                                key={col}
                                className="px-3 py-2 text-left font-semibold text-foreground border-b border-border whitespace-nowrap"
                              >
                                {col}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {queryResult.rows.map((row, rowIndex) => (
                            <tr
                              key={rowIndex}
                              className="hover:bg-muted/30 transition-colors"
                            >
                              {row.map((cell, cellIndex) => (
                                <td
                                  key={cellIndex}
                                  className="px-3 py-1.5 text-foreground border-b border-border/50 max-w-[200px] truncate"
                                  title={String(cell ?? "")}
                                >
                                  {cell === null || cell === undefined
                                    ? "NULL"
                                    : String(cell)}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="py-8 text-center text-muted-foreground text-sm">
                      查询返回空结果
                    </div>
                  )}
                </div>
              )}

              {!queryResult && !queryError && (
                <div className="flex items-center justify-center h-full text-muted-foreground">
                  <span className="text-sm">输入 SQL 并点击执行</span>
                </div>
              )}
            </div>

            {/* 分页控件 */}
            {queryResult && currentTable && (
              <div className="flex-shrink-0 border-t border-border px-3 py-2 flex items-center justify-between bg-muted/20">
                <div className="text-[11px] text-muted-foreground">
                  第 {startRow}-{endRow} 条
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => handlePageChange(1)}
                    disabled={currentPage <= 1 || isQuerying}
                    className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed"
                    title="首页"
                  >
                    <ChevronFirst className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => handlePageChange(currentPage - 1)}
                    disabled={currentPage <= 1 || isQuerying}
                    className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed"
                    title="上一页"
                  >
                    <ChevronLeft className="h-3.5 w-3.5" />
                  </button>
                  <span className="text-[11px] text-muted-foreground px-2">
                    {currentPage}
                  </span>
                  <button
                    onClick={() => handlePageChange(currentPage + 1)}
                    disabled={!hasMoreRows || isQuerying}
                    className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed"
                    title="下一页"
                  >
                    <ChevronRight className="h-3.5 w-3.5" />
                  </button>
                </div>
                <div className="flex items-center gap-1">
                  <span className="text-[11px] text-muted-foreground">每页</span>
                  <select
                    value={pageSize}
                    onChange={(e) => {
                      const newSize = Number(e.target.value);
                      setPageSize(newSize);
                      if (currentTable) {
                        setCurrentPage(1);
                        const newSql = buildPaginatedSql(currentTable, 1, newSize);
                        setSql(newSql);
                        void handleQuery(newSql);
                      }
                    }}
                    className="h-6 text-[11px] rounded border border-border bg-background px-1"
                  >
                    <option value={50}>50</option>
                    <option value={100}>100</option>
                    <option value={200}>200</option>
                    <option value={500}>500</option>
                  </select>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
