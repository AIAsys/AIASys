/**
 * CSV 表格预览与页内编辑组件
 *
 * 大文件通过后端分页接口读取，避免前端全量下载、解析和渲染。
 */

import {
  AlertCircle,
  ChevronFirst,
  ChevronLeft,
  ChevronRight,
  Columns3,
  Loader2,
  Save,
  Table,
} from "lucide-react";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { API_ENDPOINTS, getCurrentUserId } from "@/config/api";
import { apiFetch, apiRequest } from "@/lib/api/httpClient";
import { cn } from "@/lib/utils";

interface CsvPreviewProps {
  url: string;
  fileName: string;
  sessionId?: string | null;
  variant?: "chat" | "workspace";
  className?: string;
  workspaceId?: string | null;
  scope?: "session" | "workspace" | "global" | "url";
  assetPath?: string;
}

interface CsvPreviewPage {
  filename: string;
  size: number;
  headers: string[];
  rows: string[][];
  page: number;
  page_size: number;
  start_row: number;
  returned_rows: number;
  has_previous: boolean;
  has_next: boolean;
  total_columns: number;
  column_offset: number;
  column_limit: number;
  returned_columns: number;
  has_previous_columns: boolean;
  has_more_columns: boolean;
  editable: boolean;
}

interface CsvData {
  headers: string[];
  rows: string[][];
}

const DEFAULT_PAGE_SIZE = 100;
const DEFAULT_COLUMN_LIMIT = 40;
const PAGE_SIZE_OPTIONS = [50, 100, 200, 500] as const;
const COLUMN_LIMIT_OPTIONS = [20, 40, 80, 120] as const;

function parseCsv(text: string): CsvData {
  const lines = text.trim().split("\n");
  if (lines.length === 0 || (lines.length === 1 && lines[0] === "")) {
    return { headers: [], rows: [] };
  }

  const parseRow = (line: string): string[] => {
    const result: string[] = [];
    let current = "";
    let inQuotes = false;

    for (let i = 0; i < line.length; i += 1) {
      const char = line[i];
      const nextChar = line[i + 1];
      if (char === '"' && inQuotes && nextChar === '"') {
        current += '"';
        i += 1;
      } else if (char === '"') {
        inQuotes = !inQuotes;
      } else if (char === "," && !inQuotes) {
        result.push(current.trim());
        current = "";
      } else {
        current += char;
      }
    }
    result.push(current.trim());
    return result;
  };

  const headers = parseRow(lines[0]);
  const rows = lines.slice(1).map(parseRow);
  return { headers, rows };
}

function formatBytes(size: number): string {
  if (!Number.isFinite(size) || size <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = size;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function toPreviewPage(
  data: CsvData,
  fileName: string,
  pageSize: number,
  columnLimit: number,
): CsvPreviewPage {
  const headers = data.headers.slice(0, columnLimit);
  const rows = data.rows.slice(0, pageSize).map((row) => row.slice(0, columnLimit));
  return {
    filename: fileName,
    size: 0,
    headers,
    rows,
    page: 1,
    page_size: pageSize,
    start_row: rows.length ? 1 : 0,
    returned_rows: rows.length,
    has_previous: false,
    has_next: data.rows.length > pageSize,
    total_columns: data.headers.length,
    column_offset: 0,
    column_limit: columnLimit,
    returned_columns: headers.length,
    has_previous_columns: false,
    has_more_columns: data.headers.length > columnLimit,
    editable: false,
  };
}

function resolveCsvEndpoint({
  scope,
  sessionId,
  workspaceId,
  assetPath,
}: {
  scope: CsvPreviewProps["scope"];
  sessionId?: string | null;
  workspaceId?: string | null;
  assetPath: string;
}): string | null {
  if (scope === "global") {
    return workspaceId
      ? API_ENDPOINTS.GLOBAL_WORKSPACE_CSV_PREVIEW(workspaceId, assetPath)
      : null;
  }
  if (scope === "workspace") {
    return workspaceId
      ? API_ENDPOINTS.WORKSPACE_FILE_CSV_PREVIEW(workspaceId, assetPath)
      : null;
  }
  if (scope === "session") {
    return sessionId
      ? API_ENDPOINTS.FILES_CSV_PREVIEW(
          getCurrentUserId(),
          sessionId,
          assetPath,
        )
      : null;
  }
  return null;
}

export const CsvPreview: React.FC<CsvPreviewProps> = ({
  url,
  fileName,
  sessionId,
  variant = "workspace",
  className,
  workspaceId,
  scope = sessionId ? "session" : "url",
  assetPath,
}) => {
  const normalizedAssetPath = assetPath || fileName;
  const endpoint = useMemo(
    () =>
      resolveCsvEndpoint({
        scope,
        sessionId,
        workspaceId,
        assetPath: normalizedAssetPath,
      }),
    [scope, sessionId, workspaceId, normalizedAssetPath],
  );
  const isUrlFallback = !endpoint;

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [columnOffset, setColumnOffset] = useState(0);
  const [columnLimit, setColumnLimit] = useState(DEFAULT_COLUMN_LIMIT);
  const [data, setData] = useState<CsvPreviewPage | null>(null);
  const [editedRows, setEditedRows] = useState<string[][] | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingCell, setEditingCell] = useState<{
    row: number;
    col: number;
  } | null>(null);
  const [editValue, setEditValue] = useState("");
  const requestSeqRef = useRef(0);

  const canEdit =
    variant === "workspace" &&
    Boolean(endpoint) &&
    Boolean(data?.editable);

  const resetEditingState = useCallback(() => {
    setIsEditing(false);
    setHasChanges(false);
    setEditingCell(null);
    setEditValue("");
    setSaveError(null);
  }, []);

  const confirmDiscardChanges = useCallback(() => {
    if (!hasChanges) return true;
    return window.confirm("当前页有未保存修改，切换后会放弃这些修改。");
  }, [hasChanges]);

  const loadPage = useCallback(async () => {
    const requestId = requestSeqRef.current + 1;
    requestSeqRef.current = requestId;
    setLoading(true);
    setError(null);
    setSaveError(null);

    try {
      let nextData: CsvPreviewPage;
      if (endpoint) {
        nextData = await apiRequest<CsvPreviewPage>(endpoint, {
          method: "GET",
          query: {
            page,
            page_size: pageSize,
            column_offset: columnOffset,
            column_limit: columnLimit,
          },
        });
      } else {
        const response = await apiFetch(url);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const text = await response.text();
        nextData = toPreviewPage(parseCsv(text), fileName, pageSize, columnLimit);
      }

      if (requestSeqRef.current !== requestId) return;
      setData(nextData);
      setEditedRows(nextData.rows.map((row) => [...row]));
      resetEditingState();
    } catch (err) {
      if (requestSeqRef.current !== requestId) return;
      setData(null);
      setEditedRows(null);
      resetEditingState();
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      if (requestSeqRef.current === requestId) {
        setLoading(false);
      }
    }
  }, [
    endpoint,
    fileName,
    page,
    pageSize,
    columnOffset,
    columnLimit,
    url,
    resetEditingState,
  ]);

  useEffect(() => {
    void loadPage();
  }, [loadPage]);

  useEffect(() => {
    setPage(1);
    setColumnOffset(0);
  }, [endpoint, url, fileName]);

  const handleSave = useCallback(async () => {
    if (!endpoint || !editedRows || !data || !hasChanges) return;
    setIsSaving(true);
    setSaveError(null);
    try {
      await apiRequest<unknown>(endpoint, {
        method: "PUT",
        body: {
          rows: editedRows,
          page: data.page,
          page_size: data.page_size,
          column_offset: data.column_offset,
          column_limit: data.column_limit,
        },
      });
      await loadPage();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setIsSaving(false);
    }
  }, [endpoint, editedRows, data, hasChanges, loadPage]);

  const updateCell = useCallback(
    (rowIndex: number, colIndex: number, value: string) => {
      setEditedRows((prev) => {
        if (!prev) return prev;
        const nextRows = prev.map((row, currentRowIndex) =>
          currentRowIndex === rowIndex
            ? row.map((cell, currentColIndex) =>
                currentColIndex === colIndex ? value : cell,
              )
            : row,
        );
        return nextRows;
      });
      setHasChanges(true);
    },
    [],
  );

  const displayRows = isEditing && editedRows ? editedRows : data?.rows ?? [];
  const startRow = data?.returned_rows ? data.start_row : 0;
  const endRow = data?.returned_rows
    ? data.start_row + data.returned_rows - 1
    : 0;
  const startColumn = data ? data.column_offset + 1 : 0;
  const endColumn = data
    ? data.column_offset + data.returned_columns
    : 0;

  const goToPage = useCallback(
    (nextPage: number) => {
      if (nextPage < 1 || !confirmDiscardChanges()) return;
      setPage(nextPage);
    },
    [confirmDiscardChanges],
  );

  const setPageSizeSafely = useCallback(
    (nextPageSize: number) => {
      if (!confirmDiscardChanges()) return;
      setPage(1);
      setPageSize(nextPageSize);
    },
    [confirmDiscardChanges],
  );

  const setColumnLimitSafely = useCallback(
    (nextColumnLimit: number) => {
      if (!confirmDiscardChanges()) return;
      setColumnOffset(0);
      setColumnLimit(nextColumnLimit);
    },
    [confirmDiscardChanges],
  );

  const shiftColumnWindow = useCallback(
    (direction: "previous" | "next") => {
      if (!data || !confirmDiscardChanges()) return;
      const nextOffset =
        direction === "previous"
          ? Math.max(0, columnOffset - columnLimit)
          : columnOffset + columnLimit;
      setColumnOffset(nextOffset);
    },
    [columnLimit, columnOffset, confirmDiscardChanges, data],
  );

  const renderCell = (cell: string, rowIndex: number, colIndex: number) => {
    const isEditingThisCell =
      isEditing &&
      editingCell?.row === rowIndex &&
      editingCell?.col === colIndex;

    if (isEditingThisCell) {
      return (
        <td className="border-b border-border/50 px-0 py-0">
          <input
            type="text"
            value={editValue}
            onChange={(event) => setEditValue(event.target.value)}
            onBlur={() => {
              updateCell(rowIndex, colIndex, editValue);
              setEditingCell(null);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                updateCell(rowIndex, colIndex, editValue);
                setEditingCell(null);
              }
              if (event.key === "Escape") {
                setEditingCell(null);
              }
            }}
            autoFocus
            className="w-full min-w-[160px] rounded-sm border border-warning/40 bg-warning-container/40 px-3 py-1.5 text-xs outline-none focus:ring-1 focus:ring-warning"
          />
        </td>
      );
    }

    return (
      <td
        className={cn(
          "max-w-[240px] truncate border-b border-border/50 px-3 py-1.5 text-foreground",
          isEditing && "cursor-pointer hover:bg-warning-container/40",
        )}
        title={cell}
        onClick={() => {
          if (!isEditing) return;
          setEditingCell({ row: rowIndex, col: colIndex });
          setEditValue(cell);
        }}
      >
        {cell}
      </td>
    );
  };

  return (
    <div
      className={cn(
        "flex flex-col bg-background",
        variant === "workspace"
          ? "h-full"
          : "not-prose my-4 max-h-[420px] overflow-hidden rounded-xl border border-border shadow-sm",
        className,
      )}
      data-testid="csv-preview"
    >
      <div className="shrink-0 border-b border-border bg-background px-3 py-2">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <Table className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            <span
              className="truncate font-mono text-xs text-muted-foreground"
              title={fileName}
            >
              {fileName}
            </span>
            {data ? (
              <span className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                {formatBytes(data.size)}
                {data.total_columns ? ` · ${data.total_columns} 列` : ""}
              </span>
            ) : null}
            {isUrlFallback ? (
              <span className="shrink-0 rounded-full bg-warning-container px-1.5 py-0.5 text-[10px] text-warning">
                简略预览
              </span>
            ) : null}
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {canEdit ? (
              <>
                <div className="flex items-center gap-1.5">
                  <div
                    className={cn(
                      "h-2 w-2 rounded-full",
                      hasChanges ? "bg-warning" : "bg-success",
                    )}
                  />
                  <span className="text-[11px] text-muted-foreground">
                    {hasChanges ? "未保存" : "已保存"}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    if (isEditing && !confirmDiscardChanges()) return;
                    setIsEditing((current) => !current);
                    setEditingCell(null);
                    setEditedRows(data?.rows.map((row) => [...row]) ?? null);
                    setHasChanges(false);
                  }}
                  className="rounded bg-secondary px-2.5 py-0.5 text-[11px] text-secondary-foreground transition-colors hover:bg-secondary/80"
                  data-testid="csv-preview-toggle-edit"
                >
                  {isEditing ? "预览" : "编辑当前页"}
                </button>
                {isEditing ? (
                  <button
                    type="button"
                    onClick={handleSave}
                    disabled={isSaving || !hasChanges}
                    className="flex items-center gap-1 rounded bg-primary px-2.5 py-0.5 text-[11px] text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:bg-muted disabled:opacity-50"
                    data-testid="csv-preview-save"
                  >
                    {isSaving ? (
                      <>
                        <Loader2 className="h-3 w-3 animate-spin" />
                        保存中
                      </>
                    ) : (
                      <>
                        <Save className="h-3 w-3" />
                        保存
                      </>
                    )}
                  </button>
                ) : null}
              </>
            ) : null}
          </div>
        </div>
      </div>

      {saveError ? (
        <div className="shrink-0 border-b border-error-container bg-error-container/60 px-3 py-1.5 text-xs text-error">
          {saveError}
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-auto">
        {loading ? (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
            <span className="text-sm">加载 CSV 分页中...</span>
          </div>
        ) : null}

        {!loading && error ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-error">
            <AlertCircle className="h-6 w-6" />
            <span className="text-sm">{error}</span>
          </div>
        ) : null}

        {!loading && !error && data ? (
          <table className="w-full min-w-max border-collapse text-xs">
            <thead className="sticky top-0 z-10 bg-muted/80">
              <tr>
                <th className="w-14 border-b border-border px-3 py-2 text-left font-mono font-semibold text-muted-foreground">
                  #
                </th>
                {data.headers.map((header, index) => (
                  <th
                    key={`${data.column_offset}-${index}-${header}`}
                    className="whitespace-nowrap border-b border-border px-3 py-2 text-left font-semibold text-foreground"
                  >
                    {header || `列${data.column_offset + index + 1}`}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {displayRows.map((row, rowIndex) => (
                <tr
                  key={`${data.page}-${data.column_offset}-${rowIndex}`}
                  className="transition-colors hover:bg-muted/30"
                >
                  <td className="border-b border-border/50 px-3 py-1.5 font-mono text-muted-foreground">
                    {data.start_row + rowIndex}
                  </td>
                  {data.headers.map((_, colIndex) => (
                    <React.Fragment key={colIndex}>
                      {renderCell(row[colIndex] ?? "", rowIndex, colIndex)}
                    </React.Fragment>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}

        {!loading && !error && data && data.returned_rows === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            当前页没有数据
          </div>
        ) : null}
      </div>

      {data ? (
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-border bg-muted/20 px-3 py-2">
          <div className="flex min-w-0 items-center gap-2 text-[11px] text-muted-foreground">
            <span>
              行 {startRow}-{endRow}
            </span>
            <span>列 {startColumn}-{endColumn}</span>
          </div>

          <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => goToPage(1)}
                disabled={!data.has_previous || loading}
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-30"
                title="首页"
                data-testid="csv-preview-first-page"
              >
              <ChevronFirst className="h-3.5 w-3.5" />
            </button>
              <button
                type="button"
                onClick={() => goToPage(page - 1)}
                disabled={!data.has_previous || loading}
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-30"
                title="上一页"
                data-testid="csv-preview-prev-page"
              >
              <ChevronLeft className="h-3.5 w-3.5" />
            </button>
            <span className="px-2 text-[11px] text-muted-foreground">
              第 {page} 页
            </span>
              <button
                type="button"
                onClick={() => goToPage(page + 1)}
                disabled={!data.has_next || loading}
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-30"
                title="下一页"
                data-testid="csv-preview-next-page"
              >
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[11px] text-muted-foreground">每页</span>
              <select
                value={pageSize}
                onChange={(event) => setPageSizeSafely(Number(event.target.value))}
                disabled={loading}
                className="h-7 rounded-md border border-border bg-background px-2 text-[11px] text-foreground outline-none"
                data-testid="csv-preview-page-size"
              >
              {PAGE_SIZE_OPTIONS.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
            <div className="ml-2 flex items-center gap-1">
              <Columns3 className="h-3.5 w-3.5 text-muted-foreground" />
              <button
                type="button"
                onClick={() => shiftColumnWindow("previous")}
                disabled={!data.has_previous_columns || loading}
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-30"
                title="上一组列"
                data-testid="csv-preview-prev-columns"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => shiftColumnWindow("next")}
                disabled={!data.has_more_columns || loading}
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-30"
                title="下一组列"
                data-testid="csv-preview-next-columns"
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
              <select
                value={columnLimit}
                onChange={(event) =>
                  setColumnLimitSafely(Number(event.target.value))
                }
                disabled={loading}
                className="h-7 rounded-md border border-border bg-background px-2 text-[11px] text-foreground outline-none"
                data-testid="csv-preview-column-limit"
              >
                {COLUMN_LIMIT_OPTIONS.map((size) => (
                  <option key={size} value={size}>
                    {size} 列
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};
