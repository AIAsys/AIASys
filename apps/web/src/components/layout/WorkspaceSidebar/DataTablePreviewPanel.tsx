import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Table, Loader2, AlertCircle, Database, Plus, Trash2, Check, X, Settings2 } from "lucide-react";
import { CanvasActionMenu } from "@/components/workspace/CanvasActionMenu";
import { API_ENDPOINTS } from "@/config/api";
import { useAuthContext } from "@/contexts/AuthContext";
import { apiRequest } from "@/lib/api/httpClient";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface DataTableResourceNode {
  name: string;
  path: string;
  meta?: Record<string, unknown>;
}

interface DataTableColumn {
  name: string;
  type: string;
  required?: boolean;
  options?: string[];
  precision?: number | null;
}

interface DataTableSchemaResponse {
  metadata: Record<string, unknown>;
  columns: DataTableColumn[];
}

interface DataTableRecordsResponse {
  records: Record<string, unknown>[];
  limit: number;
  offset: number;
}

interface DataTablePreviewPanelProps {
  node: DataTableResourceNode;
  workspaceId?: string | null;
  onClose?: () => void;
  closeLabel?: string;
  onSplitRight?: () => void;
  onSplitDown?: () => void;
}

const COLUMN_TYPES = [
  { value: "text", label: "文本" },
  { value: "number", label: "数字" },
  { value: "date", label: "日期" },
  { value: "single_select", label: "单选" },
  { value: "multi_select", label: "多选" },
  { value: "checkbox", label: "复选框" },
  { value: "file", label: "文件" },
  { value: "url", label: "链接" },
];

export function DataTablePreviewPanel({
  node,
  workspaceId: propWorkspaceId,
  onClose,
  closeLabel = "返回文件资产",
  onSplitRight,
  onSplitDown,
}: DataTablePreviewPanelProps) {
  const { session } = useAuthContext();
  const token = session?.token;

  const [schema, setSchema] = useState<DataTableSchemaResponse | null>(null);
  const [records, setRecords] = useState<Record<string, unknown>[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingCell, setEditingCell] = useState<{ recordId: string; column: string } | null>(null);
  const [editValue, setEditValue] = useState<string>("");
  const [saving, setSaving] = useState(false);

  // 列管理对话框
  const [showColumnDialog, setShowColumnDialog] = useState(false);
  const [editingColumn, setEditingColumn] = useState<DataTableColumn | null>(null);
  const [newColumnForm, setNewColumnForm] = useState<{
    name: string;
    type: string;
    options: string;
    required: boolean;
  }>({ name: "", type: "text", options: "", required: false });
  const [columnDialogError, setColumnDialogError] = useState<string | null>(null);
  const [deleteColumnDialogOpen, setDeleteColumnDialogOpen] = useState(false);
  const [deleteColumnName, setDeleteColumnName] = useState<string>("");

  const workspaceId = propWorkspaceId || (node.meta?.workspace_id as string) || "";
  const isGlobalTable =
    node.path.startsWith("global/") ||
    node.meta?.source === "global_workspace_asset";
  const tablePath = node.path.replace(/^(workspace|global)\//, "");
  const dataTableEndpoints = useMemo(
    () => isGlobalTable
      ? {
        schema: API_ENDPOINTS.GLOBAL_DATA_TABLE_SCHEMA,
        records: API_ENDPOINTS.GLOBAL_DATA_TABLE_RECORDS,
        columns: API_ENDPOINTS.GLOBAL_DATA_TABLE_COLUMNS,
        column: API_ENDPOINTS.GLOBAL_DATA_TABLE_COLUMN,
      }
      : {
        schema: API_ENDPOINTS.WORKSPACE_DATA_TABLE_SCHEMA,
        records: API_ENDPOINTS.WORKSPACE_DATA_TABLE_RECORDS,
        columns: API_ENDPOINTS.WORKSPACE_DATA_TABLE_COLUMNS,
        column: API_ENDPOINTS.WORKSPACE_DATA_TABLE_COLUMN,
      },
    [isGlobalTable],
  );

  const fetchData = useCallback(async () => {
    if (!workspaceId || !tablePath || !token) {
      setError("缺少工作区或数据表信息");
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const [schemaRes, recordsRes] = await Promise.all([
        apiRequest<DataTableSchemaResponse>(
          dataTableEndpoints.schema(workspaceId, tablePath),
          { method: "GET", headers: { Authorization: `Bearer ${token}` } },
        ),
        apiRequest<DataTableRecordsResponse>(
          dataTableEndpoints.records(workspaceId, tablePath),
          { method: "GET", headers: { Authorization: `Bearer ${token}` } },
        ),
      ]);
      setSchema(schemaRes);
      setRecords(recordsRes.records || []);
    } catch (err) {
      const message = err instanceof Error ? err.message : "加载失败";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId, tablePath, token, dataTableEndpoints]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const handleAddRecord = useCallback(async () => {
    if (!workspaceId || !tablePath || !token || !schema) return;
    setSaving(true);
    try {
      const newRecord: Record<string, unknown> = {};
      for (const col of schema.columns) {
        if (col.type === "checkbox") newRecord[col.name] = false;
        else if (col.type === "number") newRecord[col.name] = 0;
        else if (col.type === "single_select" && col.options && col.options.length > 0) {
          newRecord[col.name] = col.options[0];
        } else if (col.type === "multi_select") newRecord[col.name] = [];
        else newRecord[col.name] = "";
      }
      await apiRequest(
        dataTableEndpoints.records(workspaceId, tablePath),
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          body: { records: [newRecord] },
        },
      );
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "添加失败");
    } finally {
      setSaving(false);
    }
  }, [workspaceId, tablePath, token, schema, fetchData, dataTableEndpoints]);

  const handleDeleteRecord = useCallback(async (recordId: string) => {
    if (!workspaceId || !tablePath || !token) return;
    setSaving(true);
    try {
      await apiRequest(
        `${dataTableEndpoints.records(workspaceId, tablePath)}/${encodeURIComponent(recordId)}`,
        {
          method: "DELETE",
          headers: { Authorization: `Bearer ${token}` },
        },
      );
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setSaving(false);
    }
  }, [workspaceId, tablePath, token, fetchData, dataTableEndpoints]);

  const handleCellSave = useCallback(async () => {
    if (!editingCell || !workspaceId || !tablePath || !token) return;
    const { recordId, column } = editingCell;
    const colDef = schema?.columns.find((c) => c.name === column);
    let parsedValue: unknown = editValue;
    if (colDef?.type === "number") {
      parsedValue = editValue === "" ? null : parseFloat(editValue);
    } else if (colDef?.type === "checkbox") {
      parsedValue = editValue === "true";
    } else if (colDef?.type === "multi_select") {
      try {
        parsedValue = JSON.parse(editValue);
      } catch {
        parsedValue = editValue.split(",").map((s) => s.trim()).filter(Boolean);
      }
    }

    setSaving(true);
    try {
      await apiRequest(
        `${dataTableEndpoints.records(workspaceId, tablePath)}/${encodeURIComponent(recordId)}`,
        {
          method: "PUT",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          body: { data: { [column]: parsedValue } },
        },
      );
      setEditingCell(null);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }, [editingCell, editValue, workspaceId, tablePath, token, schema, fetchData, dataTableEndpoints]);

  const startEdit = useCallback((recordId: string, column: string, value: unknown) => {
    let strValue = "";
    if (value === null || value === undefined) strValue = "";
    else if (typeof value === "boolean") strValue = String(value);
    else if (Array.isArray(value)) strValue = JSON.stringify(value);
    else strValue = String(value);
    setEditValue(strValue);
    setEditingCell({ recordId, column });
  }, []);

  // 列管理操作
  const handleAddColumn = useCallback(async () => {
    if (!workspaceId || !tablePath || !token) return;
    if (!newColumnForm.name.trim()) {
      setColumnDialogError("列名不能为空");
      return;
    }
    setSaving(true);
    setColumnDialogError(null);
    try {
      const options = newColumnForm.options
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      await apiRequest(
        dataTableEndpoints.columns(workspaceId, tablePath),
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          body: {
            name: newColumnForm.name.trim(),
            type: newColumnForm.type,
            options: ["single_select", "multi_select"].includes(newColumnForm.type) ? options : undefined,
            required: newColumnForm.required,
          },
        },
      );
      setNewColumnForm({ name: "", type: "text", options: "", required: false });
      await fetchData();
    } catch (err) {
      setColumnDialogError(err instanceof Error ? err.message : "添加列失败");
    } finally {
      setSaving(false);
    }
  }, [workspaceId, tablePath, token, newColumnForm, fetchData, dataTableEndpoints]);

  const handleDeleteColumn = useCallback((columnName: string) => {
    if (!workspaceId || !tablePath || !token) return;
    setDeleteColumnName(columnName);
    setDeleteColumnDialogOpen(true);
  }, [workspaceId, tablePath, token]);

  const confirmDeleteColumn = useCallback(async () => {
    if (!workspaceId || !tablePath || !token || !deleteColumnName) return;
    setSaving(true);
    try {
      await apiRequest(
        dataTableEndpoints.column(workspaceId, tablePath, deleteColumnName),
        {
          method: "DELETE",
          headers: { Authorization: `Bearer ${token}` },
        },
      );
      await fetchData();
    } catch (err) {
      setColumnDialogError(err instanceof Error ? err.message : "删除列失败");
    } finally {
      setSaving(false);
      setDeleteColumnDialogOpen(false);
    }
  }, [workspaceId, tablePath, token, deleteColumnName, fetchData, dataTableEndpoints]);

  const handleUpdateColumn = useCallback(async () => {
    if (!workspaceId || !tablePath || !token || !editingColumn) return;
    setSaving(true);
    setColumnDialogError(null);
    try {
      const options = editingColumn.options || [];
      await apiRequest(
        dataTableEndpoints.column(workspaceId, tablePath, editingColumn.name),
        {
          method: "PUT",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          body: {
            name: editingColumn.name,
            type: editingColumn.type,
            options: ["single_select", "multi_select"].includes(editingColumn.type) ? options : undefined,
            required: editingColumn.required,
            precision: editingColumn.precision,
          },
        },
      );
      setEditingColumn(null);
      await fetchData();
    } catch (err) {
      setColumnDialogError(err instanceof Error ? err.message : "更新列失败");
    } finally {
      setSaving(false);
    }
  }, [workspaceId, tablePath, token, editingColumn, fetchData, dataTableEndpoints]);

  const columns = schema?.columns || [];

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      {/* 头部 */}
      <div className="flex-shrink-0 border-b border-border px-4 py-2">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <Table className="h-4 w-4 shrink-0 text-tertiary" />
            <span className="truncate text-sm font-semibold">{node.name}</span>
            <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
              多维表格
            </span>
            <span className="shrink-0 text-[10px] text-muted-foreground">
              {records.length} 条记录
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowColumnDialog(true)}
              disabled={saving || isLoading}
              className="inline-flex h-7 items-center gap-1 rounded-md border border-border bg-background px-2.5 text-[11px] font-medium text-foreground transition-colors hover:bg-muted disabled:opacity-50"
            >
              <Settings2 className="h-3 w-3" />
              编辑列
            </button>
            <button
              type="button"
              onClick={() => void handleAddRecord()}
              disabled={saving || isLoading}
              className="inline-flex h-7 items-center gap-1 rounded-md bg-primary px-2.5 text-[11px] font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              <Plus className="h-3 w-3" />
              添加记录
            </button>
            {onClose ? (
              <CanvasActionMenu
                onClose={onClose}
                closeLabel={closeLabel}
                onSplitRight={onSplitRight}
                onSplitDown={onSplitDown}
              />
            ) : null}
          </div>
        </div>
      </div>

      {/* 内容区 */}
      <div className="min-h-0 flex-1 overflow-auto">
        {isLoading ? (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            加载中...
          </div>
        ) : error ? (
          <div className="flex h-full flex-col items-center justify-center px-6 text-center text-muted-foreground">
            <AlertCircle className="mb-2 h-6 w-6 text-error" />
            <p className="text-sm">{error}</p>
          </div>
        ) : records.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center px-6 text-center text-muted-foreground">
            <Database className="mb-3 h-10 w-10 opacity-30" />
            <p className="text-sm font-medium text-foreground/80">暂无记录</p>
            <p className="mt-1 max-w-[280px] text-xs leading-5 text-muted-foreground">
              数据表已创建，点击"添加记录"开始录入数据。
            </p>
            <button
              type="button"
              onClick={() => void handleAddRecord()}
              disabled={saving}
              className="mt-4 inline-flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              <Plus className="h-3.5 w-3.5" />
              添加记录
            </button>
          </div>
        ) : (
          <div className="p-4">
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-left text-[12px]">
                <thead className="bg-muted/60">
                  <tr>
                    {columns.map((col) => (
                      <th
                        key={col.name}
                        className="border-b border-border px-3 py-2 font-medium text-foreground"
                      >
                        {col.name}
                        {col.required && <span className="ml-0.5 text-error">*</span>}
                      </th>
                    ))}
                    <th className="border-b border-border px-3 py-2 w-10"></th>
                  </tr>
                </thead>
                <tbody>
                  {records.map((record) => {
                    const recordId = String(record._id ?? "");
                    return (
                      <tr
                        key={recordId}
                        className="border-b border-border/50 last:border-b-0 hover:bg-muted/20"
                      >
                        {columns.map((col) => {
                          const isEditing =
                            editingCell?.recordId === recordId &&
                            editingCell?.column === col.name;
                          const cellValue = record[col.name];
                          return (
                            <td
                              key={col.name}
                              className="px-2 py-1.5 min-w-[120px] max-w-[300px]"
                              onDoubleClick={() => {
                                if (!isEditing && !saving) {
                                  startEdit(recordId, col.name, cellValue);
                                }
                              }}
                            >
                              {isEditing ? (
                                <CellEditor
                                  column={col}
                                  value={editValue}
                                  onChange={setEditValue}
                                  onSave={() => void handleCellSave()}
                                  onCancel={() => setEditingCell(null)}
                                  saving={saving}
                                />
                              ) : (
                                <span className="block truncate text-muted-foreground cursor-text hover:text-foreground hover:bg-muted/40 hover:outline hover:outline-dashed hover:outline-1 hover:outline-border/60 px-1 -mx-1 rounded-sm transition-all duration-150" title="双击编辑">
                                  {formatCellValue(cellValue, col.type)}
                                </span>
                              )}
                            </td>
                          );
                        })}
                        <td className="px-2 py-1.5 w-10">
                          <button
                            type="button"
                            onClick={() => void handleDeleteRecord(recordId)}
                            disabled={saving}
                            className="inline-flex h-6 w-6 items-center justify-center rounded text-muted-foreground/50 hover:bg-error/10 hover:text-error disabled:opacity-30"
                            title="删除"
                          >
                            <Trash2 className="h-3 w-3" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* 底部添加行 */}
            <button
              type="button"
              onClick={() => void handleAddRecord()}
              disabled={saving}
              className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-border py-2 text-[12px] text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-primary disabled:opacity-50"
            >
              <Plus className="h-3.5 w-3.5" />
              添加记录
            </button>
          </div>
        )}
      </div>

      <AlertDialog open={deleteColumnDialogOpen} onOpenChange={setDeleteColumnDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除列</AlertDialogTitle>
            <AlertDialogDescription>
              确定删除列 "{deleteColumnName}"？该列的所有数据将丢失。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setDeleteColumnDialogOpen(false)}>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => void confirmDeleteColumn()}
              className="bg-destructive text-destructive-foreground"
            >
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* 列管理对话框 */}
      {showColumnDialog && (
        <div className="absolute inset-0 z-50 flex items-start justify-center bg-black/30 pt-16">
          <div className="w-full max-w-md max-h-[80vh] overflow-auto rounded-lg border border-border bg-background shadow-lg">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <h3 className="text-sm font-semibold">列管理</h3>
              <button
                type="button"
                onClick={() => {
                  setShowColumnDialog(false);
                  setEditingColumn(null);
                  setColumnDialogError(null);
                }}
                className="inline-flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:bg-muted"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="p-4 space-y-4">
              {columnDialogError && (
                <div className="rounded bg-error/10 px-3 py-2 text-[11px] text-error">
                  {columnDialogError}
                </div>
              )}

              {/* 当前列列表 */}
              <div className="space-y-2">
                <h4 className="text-[11px] font-medium text-muted-foreground uppercase">当前列</h4>
                {columns.length === 0 ? (
                  <p className="text-[11px] text-muted-foreground">暂无自定义列</p>
                ) : (
                  <div className="space-y-1">
                    {columns.map((col) => (
                      <div
                        key={col.name}
                        className="flex items-center justify-between rounded border border-border px-3 py-2"
                      >
                        {editingColumn?.name === col.name ? (
                          <div className="flex-1 space-y-2">
                            <input
                              type="text"
                              value={editingColumn.name}
                              onChange={(e) =>
                                setEditingColumn({ ...editingColumn, name: e.target.value })
                              }
                              className="h-7 w-full rounded border border-border bg-background px-2 text-[12px] outline-none focus:border-primary"
                            />
                            <select
                              value={editingColumn.type}
                              onChange={(e) =>
                                setEditingColumn({ ...editingColumn, type: e.target.value })
                              }
                              className="h-7 w-full rounded border border-border bg-background px-2 text-[12px] outline-none focus:border-primary"
                            >
                              {COLUMN_TYPES.map((t) => (
                                <option key={t.value} value={t.value}>{t.label}</option>
                              ))}
                            </select>
                            {["single_select", "multi_select"].includes(editingColumn.type) && (
                              <input
                                type="text"
                                value={(editingColumn.options || []).join(", ")}
                                onChange={(e) =>
                                  setEditingColumn({
                                    ...editingColumn,
                                    options: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
                                  })
                                }
                                placeholder="选项1, 选项2, 选项3"
                                className="h-7 w-full rounded border border-border bg-background px-2 text-[12px] outline-none focus:border-primary"
                              />
                            )}
                            <label className="flex items-center gap-1.5 text-[11px]">
                              <input
                                type="checkbox"
                                checked={editingColumn.required || false}
                                onChange={(e) =>
                                  setEditingColumn({ ...editingColumn, required: e.target.checked })
                                }
                                className="h-3.5 w-3.5 rounded"
                              />
                              必填
                            </label>
                            <div className="flex items-center gap-2">
                              <button
                                type="button"
                                onClick={() => void handleUpdateColumn()}
                                disabled={saving}
                                className="inline-flex h-6 items-center gap-1 rounded bg-primary px-2 text-[11px] text-primary-foreground hover:opacity-90 disabled:opacity-50"
                              >
                                <Check className="h-3 w-3" />
                                保存
                              </button>
                              <button
                                type="button"
                                onClick={() => setEditingColumn(null)}
                                disabled={saving}
                                className="inline-flex h-6 items-center gap-1 rounded border border-border px-2 text-[11px] hover:bg-muted disabled:opacity-50"
                              >
                                取消
                              </button>
                            </div>
                          </div>
                        ) : (
                          <>
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="text-[12px] font-medium truncate">{col.name}</span>
                              <span className="shrink-0 rounded bg-muted px-1 py-0.5 text-[10px] text-muted-foreground">
                                {COLUMN_TYPES.find((t) => t.value === col.type)?.label || col.type}
                              </span>
                              {col.required && (
                                <span className="shrink-0 text-[10px] text-error">必填</span>
                              )}
                            </div>
                            <div className="flex items-center gap-1 ml-2">
                              <button
                                type="button"
                                onClick={() => setEditingColumn({ ...col })}
                                disabled={saving}
                                className="inline-flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:bg-muted disabled:opacity-30"
                                title="编辑"
                              >
                                <Settings2 className="h-3 w-3" />
                              </button>
                              <button
                                type="button"
                                onClick={() => void handleDeleteColumn(col.name)}
                                disabled={saving}
                                className="inline-flex h-6 w-6 items-center justify-center rounded text-muted-foreground/50 hover:bg-error/10 hover:text-error disabled:opacity-30"
                                title="删除"
                              >
                                <Trash2 className="h-3 w-3" />
                              </button>
                            </div>
                          </>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* 添加新列 */}
              <div className="border-t border-border pt-4 space-y-3">
                <h4 className="text-[11px] font-medium text-muted-foreground uppercase">添加列</h4>
                <div className="space-y-2">
                  <input
                    type="text"
                    value={newColumnForm.name}
                    onChange={(e) =>
                      setNewColumnForm({ ...newColumnForm, name: e.target.value })
                    }
                    placeholder="列名"
                    className="h-8 w-full rounded border border-border bg-background px-2.5 text-[12px] outline-none focus:border-primary"
                  />
                  <select
                    value={newColumnForm.type}
                    onChange={(e) =>
                      setNewColumnForm({ ...newColumnForm, type: e.target.value })
                    }
                    className="h-8 w-full rounded border border-border bg-background px-2.5 text-[12px] outline-none focus:border-primary"
                  >
                    {COLUMN_TYPES.map((t) => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </select>
                  {["single_select", "multi_select"].includes(newColumnForm.type) && (
                    <input
                      type="text"
                      value={newColumnForm.options}
                      onChange={(e) =>
                        setNewColumnForm({ ...newColumnForm, options: e.target.value })
                      }
                      placeholder="选项1, 选项2, 选项3"
                      className="h-8 w-full rounded border border-border bg-background px-2.5 text-[12px] outline-none focus:border-primary"
                    />
                  )}
                  <label className="flex items-center gap-1.5 text-[11px]">
                    <input
                      type="checkbox"
                      checked={newColumnForm.required}
                      onChange={(e) =>
                        setNewColumnForm({ ...newColumnForm, required: e.target.checked })
                      }
                      className="h-3.5 w-3.5 rounded"
                    />
                    必填
                  </label>
                  <button
                    type="button"
                    onClick={() => void handleAddColumn()}
                    disabled={saving || !newColumnForm.name.trim()}
                    className="inline-flex h-8 w-full items-center justify-center gap-1 rounded-md bg-primary px-3 text-[12px] font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    添加列
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CellEditor({
  column,
  value,
  onChange,
  onSave,
  onCancel,
  saving,
}: {
  column: DataTableColumn;
  value: string;
  onChange: (v: string) => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const inputRef = useRef<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = inputRef.current;
    if (el) {
      el.focus();
      if (el instanceof HTMLInputElement && el.type !== "date" && el.type !== "checkbox") {
        el.select();
      }
    }
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      onSave();
    } else if (e.key === "Escape") {
      e.preventDefault();
      onCancel();
    }
  };

  if (column.type === "single_select" && column.options && column.options.length > 0) {
    return (
      <div className="flex items-center gap-1">
        <select
          ref={inputRef as React.RefObject<HTMLSelectElement>}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={() => onSave()}
          onKeyDown={handleKeyDown}
          disabled={saving}
          className="h-7 min-w-[80px] rounded border border-border bg-background px-2 py-0.5 text-[12px] outline-none focus:border-primary"
        >
          {column.options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </div>
    );
  }

  if (column.type === "checkbox") {
    return (
      <div className="flex items-center gap-1">
        <input
          ref={inputRef as React.RefObject<HTMLInputElement>}
          type="checkbox"
          checked={value === "true"}
          onChange={(e) => {
            onChange(String(e.target.checked));
            setTimeout(() => onSave(), 50);
          }}
          disabled={saving}
          className="h-4 w-4 rounded border-border"
        />
      </div>
    );
  }

  if (column.type === "multi_select") {
    return (
      <div className="flex flex-col gap-1">
        <input
          ref={inputRef as React.RefObject<HTMLInputElement>}
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={saving}
          placeholder={column.options ? column.options.join(", ") : "逗号分隔"}
          className="h-7 w-full rounded border border-border bg-background px-2 py-0.5 text-[12px] outline-none focus:border-primary"
        />
        {column.options && (
          <div className="flex flex-wrap gap-1">
            {column.options.map((opt) => (
              <button
                key={opt}
                type="button"
                onClick={() => {
                  const current = value
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean);
                  const next = current.includes(opt)
                    ? current.filter((x) => x !== opt)
                    : [...current, opt];
                  onChange(next.join(", "));
                }}
                className={`rounded px-1.5 py-0.5 text-[10px] ${
                  value.split(",").map((s) => s.trim()).includes(opt)
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                {opt}
              </button>
            ))}
          </div>
        )}
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onSave}
            disabled={saving}
            className="inline-flex h-5 w-5 items-center justify-center rounded bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            <Check className="h-3 w-3" />
          </button>
          <button
            type="button"
            onClick={onCancel}
            disabled={saving}
            className="inline-flex h-5 w-5 items-center justify-center rounded bg-muted text-muted-foreground hover:bg-muted/80 disabled:opacity-50"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      </div>
    );
  }

  const inputType =
    column.type === "number" ? "number" : column.type === "date" ? "date" : "text";

  return (
    <div className="flex items-center gap-1">
      <input
        ref={inputRef as React.RefObject<HTMLInputElement>}
        type={inputType}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={() => onSave()}
        onKeyDown={handleKeyDown}
        disabled={saving}
        className="h-7 min-w-[80px] flex-1 rounded border border-border bg-background px-2 py-0.5 text-[12px] outline-none focus:border-primary"
      />
    </div>
  );
}

function formatCellValue(value: unknown, _type?: string): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (typeof value === "boolean") {
    return value ? "是" : "否";
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return "—";
    return value.join(", ");
  }
  return String(value);
}
