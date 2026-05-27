/**
 * XLSX 表格预览与编辑组件
 * 解析 Excel 文件并以表格形式展示，支持单元格编辑和保存
 */

import {
  AlertCircle,
  Download,
  FileSpreadsheet,
  FileWarning,
  Loader2,
  MoreHorizontal,
  Save,
} from "lucide-react";
import React, { useCallback, useEffect, useState } from "react";
import { API_ENDPOINTS } from "@/config/api";
import { apiFetch, apiRequest } from "@/lib/api/httpClient";
import { cn } from "@/lib/utils";

interface XlsxPreviewProps {
  url: string;
  fileName: string;
  workspaceId?: string | null;
  assetPath?: string;
}

interface SheetData {
  name: string;
  headers: string[];
  rows: string[][];
}

const MAX_FILE_SIZE = 10 * 1024 * 1024;

export const XlsxPreview: React.FC<XlsxPreviewProps> = ({
  url,
  fileName,
  workspaceId,
  assetPath,
}) => {
  const [sheets, setSheets] = useState<SheetData[]>([]);
  const [editedSheets, setEditedSheets] = useState<SheetData[]>([]);
  const [activeSheet, setActiveSheet] = useState<number>(0);
  const [isEditing, setIsEditing] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fileTooLarge, setFileTooLarge] = useState(false);
  const [fileSize, setFileSize] = useState<number>(0);
  const [editingCell, setEditingCell] = useState<{
    row: number;
    col: number;
  } | null>(null);
  const [editValue, setEditValue] = useState("");

  const canEdit = Boolean(workspaceId);

  useEffect(() => {
    const fetchXlsx = async () => {
      setLoading(true);
      setError(null);
      setSaveError(null);
      setFileTooLarge(false);
      setFileSize(0);
      setIsEditing(false);
      setHasChanges(false);
      setEditingCell(null);
      try {
        const response = await apiFetch(url);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const arrayBuffer = await response.arrayBuffer();
        if (arrayBuffer.byteLength > MAX_FILE_SIZE) {
          setFileSize(arrayBuffer.byteLength);
          setFileTooLarge(true);
          setLoading(false);
          return;
        }

        const XLSX = await import("xlsx");

        const workbook = XLSX.read(arrayBuffer, { type: "array" });

        const parsedSheets: SheetData[] = workbook.SheetNames.map(
          (sheetName) => {
            const worksheet = workbook.Sheets[sheetName];
            const jsonData = XLSX.utils.sheet_to_json<string[]>(worksheet, {
              header: 1,
              defval: "",
            });

            if (jsonData.length === 0) {
              return { name: sheetName, headers: [], rows: [] };
            }

            const headers = (jsonData[0] || []).map((h) => String(h));
            const rows = jsonData
              .slice(1)
              .map((row) => (row || []).map((cell) => String(cell ?? "")));

            return { name: sheetName, headers, rows };
          }
        );

        setSheets(parsedSheets);
        setEditedSheets(parsedSheets);
        setActiveSheet(0);
      } catch (err) {
        console.error("Failed to parse xlsx:", err);
        setError(err instanceof Error ? err.message : "加载失败");
      } finally {
        setLoading(false);
      }
    };

    fetchXlsx();
  }, [url]);

  const handleSave = useCallback(async () => {
    if (!workspaceId || !editedSheets.length) return;
    setIsSaving(true);
    setSaveError(null);
    try {
      const XLSX = await import("xlsx");
      const workbook = XLSX.utils.book_new();

      editedSheets.forEach((sheet) => {
        const aoa = [sheet.headers, ...sheet.rows];
        const worksheet = XLSX.utils.aoa_to_sheet(aoa);
        XLSX.utils.book_append_sheet(workbook, worksheet, sheet.name);
      });

      const arrayBuffer = XLSX.write(workbook, {
        type: "array",
        bookType: "xlsx",
      });
      const blob = new Blob([arrayBuffer], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      });

      const formData = new FormData();
      const targetPath = assetPath || fileName;
      formData.append("file", blob, targetPath);
      formData.append("path", targetPath);

      const uploadUrl = API_ENDPOINTS.WORKSPACE_FILE_UPLOAD(workspaceId);
      await apiRequest<unknown>(uploadUrl, {
        method: "POST",
        body: formData,
      });

      setSheets(editedSheets);
      setHasChanges(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : "保存失败";
      setSaveError(message);
    } finally {
      setIsSaving(false);
    }
  }, [workspaceId, assetPath, fileName, editedSheets]);

  const updateCell = useCallback(
    (sheetIndex: number, rowIndex: number, colIndex: number, value: string) => {
      setEditedSheets((prev) => {
        const newSheets = prev.map((sheet, sIdx) => {
          if (sIdx !== sheetIndex) return sheet;
          const newRows = sheet.rows.map((row, rIdx) =>
            rIdx === rowIndex
              ? row.map((cell, cIdx) => (cIdx === colIndex ? value : cell))
              : row
          );
          return { ...sheet, rows: newRows };
        });
        return newSheets;
      });
      setHasChanges(true);
    },
    []
  );

  const currentSheet = isEditing ? editedSheets[activeSheet] : sheets[activeSheet];

  const renderCell = (
    cell: string,
    rowIndex: number,
    colIndex: number
  ) => {
    const isEditingThisCell =
      isEditing &&
      editingCell?.row === rowIndex &&
      editingCell?.col === colIndex;

    if (isEditingThisCell) {
      return (
        <td className="px-0 py-0 border-b border-border/50">
          <input
            type="text"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onBlur={() => {
              updateCell(activeSheet, rowIndex, colIndex, editValue);
              setEditingCell(null);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                updateCell(activeSheet, rowIndex, colIndex, editValue);
                setEditingCell(null);
              }
              if (e.key === "Escape") {
                setEditingCell(null);
              }
            }}
            autoFocus
            className="w-full px-3 py-1.5 text-xs bg-yellow-50 border border-yellow-300 rounded-sm outline-none focus:ring-1 focus:ring-yellow-400"
          />
        </td>
      );
    }

    return (
      <td
        className={cn(
          "px-3 py-1.5 text-foreground border-b border-border/50 max-w-[200px] truncate",
          isEditing && "cursor-pointer hover:bg-yellow-50/50"
        )}
        title={cell}
        onClick={() => {
          if (isEditing) {
            setEditingCell({ row: rowIndex, col: colIndex });
            setEditValue(cell);
          }
        }}
      >
        {cell}
      </td>
    );
  };

  const renderTable = () => {
    if (!currentSheet) return null;

    const { headers, rows } = currentSheet;
    const showHeadTail = !isEditing && rows.length > 100;
    const showColHeadTail = !isEditing && headers.length > 10;
    const displayRows = showHeadTail
      ? [...rows.slice(0, 50), ...rows.slice(-50)]
      : rows;
    const displayHeaders = showColHeadTail
      ? [...headers.slice(0, 5), "...", ...headers.slice(-5)]
      : headers;

    return (
      <table className="w-full text-xs border-collapse">
        <thead className="bg-success-container/50 sticky top-0 z-10">
          <tr>
            <th className="px-3 py-2 text-left font-semibold text-muted-foreground border-b border-border w-10 font-mono">
              #
            </th>
            {displayHeaders.map((header, i) =>
              header === "..." ? (
                <th
                  key={`col-omit-${i}`}
                  className="px-3 py-2 text-center text-muted-foreground border-b border-border w-10"
                >
                  <MoreHorizontal className="w-3 h-3 mx-auto" />
                </th>
              ) : (
                <th
                  key={i}
                  className="px-3 py-2 text-left font-semibold text-foreground border-b border-border whitespace-nowrap"
                >
                  {header || `列${i + 1}`}
                </th>
              )
            )}
          </tr>
        </thead>
        <tbody>
          {displayRows.map((row, rowIndex) => {
            const realIndex = showHeadTail
              ? rowIndex < 50
                ? rowIndex
                : rows.length - 50 + (rowIndex - 50)
              : rowIndex;
            const isOmitRow = showHeadTail && rowIndex === 50;

            if (isOmitRow) {
              return (
                <tr key="omit" className="bg-muted/10">
                  <td className="px-3 py-2 text-muted-foreground border-b border-border/50 font-mono text-center">
                    <MoreHorizontal className="w-4 h-4 mx-auto" />
                  </td>
                  <td
                    colSpan={displayHeaders.length + 1}
                    className="px-3 py-2 text-muted-foreground/60 border-b border-border/50 text-center italic"
                  >
                    ... 隐藏中间 {rows.length - 100} 行 ...
                  </td>
                </tr>
              );
            }

            const displayCells = showColHeadTail
              ? [...row.slice(0, 5), "", ...row.slice(-5)]
              : row;

            return (
              <tr
                key={`row-${realIndex}`}
                className="hover:bg-success-container/30 transition-colors"
              >
                <td className="px-3 py-1.5 text-muted-foreground border-b border-border/50 font-mono">
                  {realIndex + 1}
                </td>
                {displayCells.map((cell, cellIndex) =>
                  cellIndex === 5 && showColHeadTail ? (
                    <td
                      key={`cell-omit-${cellIndex}`}
                      className="px-3 py-1.5 text-muted-foreground/30 border-b border-border/50 text-center text-[10px]"
                    >
                      ...
                    </td>
                  ) : (
                    <React.Fragment key={cellIndex}>
                      {renderCell(cell, realIndex, cellIndex)}
                    </React.Fragment>
                  )
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  };

  return (
    <div className="flex flex-col h-full bg-background">
      {/* 工具栏 */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-background shrink-0">
        <div className="flex items-center gap-2 overflow-hidden">
          <FileSpreadsheet className="w-3.5 h-3.5 text-success flex-shrink-0" />
          <span
            className="text-xs font-mono text-muted-foreground truncate max-w-[40%]"
            title={fileName}
          >
            {fileName}
          </span>
          {currentSheet && (
            <span className="text-[10px] bg-success-container text-success px-1.5 py-0.5 rounded-full font-mono">
              {currentSheet.rows.length} 行 × {currentSheet.headers.length} 列
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {canEdit && (
            <>
              <div className="flex items-center gap-1.5 mr-1">
                <div
                  className={`w-2 h-2 rounded-full ${
                    hasChanges ? "bg-yellow-500" : "bg-green-500"
                  }`}
                />
                <span className="text-[11px] text-muted-foreground">
                  {hasChanges ? "未保存" : "已保存"}
                </span>
              </div>
              <button
                onClick={() => {
                  setIsEditing((prev) => !prev);
                  setEditingCell(null);
                }}
                className="flex items-center gap-1 px-2.5 py-0.5 text-[11px] bg-secondary hover:bg-secondary/80 rounded text-secondary-foreground transition-colors"
              >
                {isEditing ? "预览" : "编辑"}
              </button>
              {isEditing && (
                <button
                  onClick={handleSave}
                  disabled={isSaving || !hasChanges}
                  className="flex items-center gap-1 px-2.5 py-0.5 text-[11px] bg-primary hover:bg-primary/90 disabled:bg-muted disabled:opacity-50 disabled:cursor-not-allowed rounded text-primary-foreground transition-colors"
                >
                  {isSaving ? (
                    <>
                      <Loader2 className="w-3 h-3 animate-spin" />
                      保存中
                    </>
                  ) : (
                    <>
                      <Save className="w-3 h-3" />
                      保存
                    </>
                  )}
                </button>
              )}
            </>
          )}
          <a
            href={url}
            download={fileName}
            className="p-1.5 hover:bg-muted rounded-md text-muted-foreground hover:text-foreground transition-colors"
            title="下载"
          >
            <Download className="w-3.5 h-3.5" />
          </a>
        </div>
      </div>

      {/* 保存错误提示 */}
      {saveError && (
        <div className="px-3 py-1.5 bg-destructive/10 border-b border-destructive/20 text-destructive text-xs">
          {saveError}
        </div>
      )}

      {/* 工作表标签 */}
      {sheets.length > 1 && (
        <div className="flex items-center gap-1 px-2 py-1.5 border-b border-border bg-muted/30 overflow-x-auto shrink-0">
          {(isEditing ? editedSheets : sheets).map((sheet, index) => (
            <button
              key={sheet.name}
              onClick={() => {
                setActiveSheet(index);
                setEditingCell(null);
              }}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors whitespace-nowrap ${
                index === activeSheet
                  ? "bg-success-container text-success shadow-sm"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              {sheet.name}
            </button>
          ))}
        </div>
      )}

      {/* 内容区 */}
      <div className="flex-1 overflow-auto">
        {loading && (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            <Loader2 className="w-5 h-5 animate-spin mr-2" />
            <span className="text-sm">解析 Excel 文件中...</span>
          </div>
        )}

        {error && (
          <div className="flex flex-col items-center justify-center h-full text-destructive gap-2">
            <AlertCircle className="w-6 h-6" />
            <span className="text-sm">{error}</span>
          </div>
        )}

        {fileTooLarge && (
          <div className="flex h-full flex-col items-center justify-center p-6 text-center">
            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-xl bg-warning-container">
              <FileWarning className="h-8 w-8 text-warning" />
            </div>
            <h3 className="mb-1 text-sm font-medium text-foreground">
              文件过大，无法预览
            </h3>
            <p className="mb-4 text-xs text-muted-foreground">
              文件大小 {(fileSize / 1024 / 1024).toFixed(2)} MB，超过 10MB 限制
            </p>
            <a
              href={url}
              download={fileName}
              className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-xs font-medium text-primary-foreground shadow-sm transition-colors hover:bg-primary/90"
            >
              <Download className="h-4 w-4" />
              下载文件
            </a>
          </div>
        )}

        {currentSheet && !loading && !fileTooLarge && renderTable()}

        {!isEditing && currentSheet && currentSheet.rows.length > 100 && (
          <div className="px-3 py-2 text-xs text-muted-foreground bg-muted/30 border-t border-border text-center">
            仅预览前 50 行/列 和 后 50 行/列，共 {currentSheet.rows.length} 行 ×{" "}
            {currentSheet.headers.length} 列
          </div>
        )}

        {currentSheet && currentSheet.rows.length === 0 && !loading && (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            <span className="text-sm">此工作表为空</span>
          </div>
        )}
      </div>
    </div>
  );
};
