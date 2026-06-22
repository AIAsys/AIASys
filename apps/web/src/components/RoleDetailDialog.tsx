import { useState, useEffect, useCallback } from "react";
import { Pencil, Trash2, X, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  listCapabilitySourceTree,
  getCapabilitySourceFile,
  type CapabilitySourceTreeEntry,
} from "@/lib/api/capabilities";
import { CapabilitySourceTree } from "@/components/CapabilityPanel/CapabilitySourceTree";
import type { RoleItem, RoleDetail } from "@/lib/api/roles";

interface RoleDetailDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  role: RoleItem | null;
  detail?: RoleDetail | null;
  onEdit?: (role: RoleItem) => void;
  onDelete?: (role: RoleItem) => void;
}

export function RoleDetailDialog({
  open,
  onOpenChange,
  role,
  detail,
  onEdit,
  onDelete,
}: RoleDetailDialogProps) {
  const isSystemRole = role?.source === "system" || role?.source === "builtin";

  // Source tree state for system roles
  const [sourceTreeLoading, setSourceTreeLoading] = useState(false);
  const [sourceTreeEntries, setSourceTreeEntries] = useState<CapabilitySourceTreeEntry[]>([]);
  const [sourceTreeError, setSourceTreeError] = useState<string | null>(null);
  const [selectedSourceFile, setSelectedSourceFile] = useState<string>("");
  const [sourceFileContent, setSourceFileContent] = useState<string | null>(null);
  const [sourceFileLoading, setSourceFileLoading] = useState(false);
  const [sourceFileError, setSourceFileError] = useState<string | null>(null);

  const visibilityLabel = !role
    ? ""
    : !role.catalogVisible
      ? "目录隐藏"
      : role.hostSelectable
        ? "主控可选"
        : "不可派发";

  const installedLabel = role
    ? role.installedToWorkspace
      ? "已安装到当前工作区"
      : role.installedToGlobal
        ? "已安装到我的默认"
        : "未安装"
    : "";

  const installedInCurrentScope = role
    ? role.scope === "global"
      ? role.installedToGlobal || role.source === "global"
      : role.installedToWorkspace || role.source === "workspace"
    : false;

  const canEdit = Boolean(onEdit) && !isSystemRole;
  const canDelete = Boolean(onDelete) && installedInCurrentScope;

  const systemPrompt = detail?.system_prompt || "";

  // Load source tree for system roles when dialog opens
  useEffect(() => {
    if (!open || !role || !isSystemRole) {
      setSourceTreeEntries([]);
      setSourceTreeError(null);
      setSelectedSourceFile("");
      setSourceFileContent(null);
      setSourceFileError(null);
      return;
    }
    setSourceTreeLoading(true);
    setSourceTreeEntries([]);
    setSourceTreeError(null);
    setSelectedSourceFile("");
    setSourceFileContent(null);
    setSourceFileError(null);

    listCapabilitySourceTree(role.name)
      .then((resp) => {
        const entries = resp?.entries ?? [];
        setSourceTreeEntries(entries);

        const defaultFile = "prompt.md";
        const entry = entries.find((e) => e.path === defaultFile && !e.is_dir);
        if (entry) {
          setSelectedSourceFile(entry.path);
          setSourceFileLoading(true);
          setSourceFileError(null);
          getCapabilitySourceFile(role.name, entry.path)
            .then((fileResp) => {
              setSourceFileContent(fileResp?.content ?? "暂无内容");
            })
            .catch((err) => {
              console.error("加载能力源文件失败", err);
              setSourceFileContent(null);
              setSourceFileError("加载源文件失败");
            })
            .finally(() => setSourceFileLoading(false));
        }
      })
      .catch((err) => {
        console.error("加载能力源码树失败", err);
        setSourceTreeEntries([]);
        setSourceTreeError("加载源码树失败");
      })
      .finally(() => setSourceTreeLoading(false));
  }, [open, role, isSystemRole]);

  const handleSelectSourceFile = useCallback(
    (path: string) => {
      if (!role || path === selectedSourceFile) return;
      setSelectedSourceFile(path);
      setSourceFileLoading(true);
      setSourceFileError(null);
      getCapabilitySourceFile(role.name, path)
        .then((resp) => {
          setSourceFileContent(resp?.content ?? "暂无内容");
        })
        .catch((err) => {
          console.error("加载能力源文件失败", err);
          setSourceFileContent(null);
          setSourceFileError("加载源文件失败");
        })
        .finally(() => setSourceFileLoading(false));
    },
    [role, selectedSourceFile],
  );

  if (!role) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-hidden flex flex-col bg-background">
        <DialogHeader className="shrink-0">
          <DialogTitle>协作专家详情</DialogTitle>
          <DialogDescription>
            查看 {role.displayName} 的详细配置信息
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto min-h-0 pr-1 space-y-4">
          {/* 基本信息卡 */}
          <div className="rounded-xl border border-border bg-card p-4 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-foreground">
                {role.displayName}
              </span>
              {role.displayName !== role.name ? (
                <Badge variant="outline" className="text-[10px]">
                  {role.name}
                </Badge>
              ) : null}
              {isSystemRole ? (
                <Badge variant="outline" className="text-[10px]">
                  系统
                </Badge>
              ) : (
                <Badge variant="outline" className="text-[10px]">
                  自定义
                </Badge>
              )}
            </div>

            {role.description ? (
              <div className="rounded-xl border border-border bg-muted/50 p-4 text-sm text-foreground">
                {role.description}
              </div>
            ) : (
              <div className="rounded-xl border border-dashed border-border bg-muted/40 p-4 text-sm text-muted-foreground">
                暂无描述
              </div>
            )}

            <div className="flex flex-wrap items-center gap-2">
              <Badge
                variant={role.hostSelectable ? "success" : "outline"}
                className="text-[10px]"
              >
                {visibilityLabel}
              </Badge>
              <Badge variant="info" className="text-[10px]">
                {installedLabel}
              </Badge>
              {role.lockReason ? (
                <Badge variant="warning" className="text-[10px]">
                  锁定
                </Badge>
              ) : null}
            </div>
          </div>

          {/* System Prompt（仅自定义角色展示，系统角色通过目录树查看 prompt.md） */}
          {!isSystemRole && (
            <div className="rounded-xl border border-border bg-card p-4 space-y-3">
              <h3 className="text-sm font-medium text-foreground">
                System Prompt
              </h3>
              {systemPrompt ? (
                <pre className="rounded-xl border border-border bg-muted/50 p-4 text-xs text-foreground overflow-x-auto whitespace-pre-wrap break-all">
                  {systemPrompt}
                </pre>
              ) : (
                <div className="rounded-xl border border-dashed border-border bg-muted/40 p-4 text-sm text-muted-foreground">
                  无 System Prompt
                </div>
              )}
            </div>
          )}

          {/* 能力源文件（系统内置角色） */}
          {isSystemRole && (
            <div className="rounded-xl border border-border bg-card p-4 space-y-3">
              <h3 className="text-sm font-medium text-foreground">
                能力源文件
              </h3>
              {sourceTreeLoading ? (
                <div className="flex items-center gap-2 py-4 text-xs text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  正在扫描文件...
                </div>
              ) : sourceTreeError ? (
                <div className="rounded-xl border border-dashed border-destructive/50 bg-destructive/5 p-4 text-xs text-destructive">
                  {sourceTreeError}
                </div>
              ) : sourceTreeEntries.length === 0 ? (
                <div className="rounded-xl border border-dashed border-border bg-muted/40 p-4 text-xs text-muted-foreground">
                  该能力源下暂无文件。
                </div>
              ) : (
                <div className="flex gap-2 rounded-md border border-border bg-muted/20 overflow-hidden" style={{ minHeight: "160px", maxHeight: "400px" }}>
                  <div className="w-40 shrink-0 overflow-y-auto border-r border-border bg-background py-2">
                    <CapabilitySourceTree
                      entries={sourceTreeEntries}
                      selectedPath={selectedSourceFile}
                      onSelectFile={handleSelectSourceFile}
                    />
                  </div>
                  <div className="flex-1 min-w-0 overflow-y-auto">
                    {sourceFileLoading ? (
                      <div className="flex items-center justify-center gap-2 py-8 text-xs text-muted-foreground">
                        <Loader2 className="h-3 w-3 animate-spin" />
                        正在加载...
                      </div>
                    ) : sourceFileError ? (
                      <div className="flex items-center justify-center py-8 text-xs text-destructive">
                        {sourceFileError}
                      </div>
                    ) : sourceFileContent !== null ? (
                      <pre className="p-3 text-[11px] leading-5 text-foreground whitespace-pre-wrap break-words">
                        {sourceFileContent}
                      </pre>
                    ) : (
                      <div className="flex items-center justify-center py-8 text-xs text-muted-foreground">
                        无法加载文件内容
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 模型与工具 */}
          {(role.model || role.toolCount > 0) && (
            <div className="rounded-xl border border-border bg-card p-4 space-y-3">
              {role.model ? (
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-muted-foreground">模型</span>
                  <span className="text-foreground">{role.model}</span>
                </div>
              ) : null}
              {role.toolCount > 0 ? (
                <div className="space-y-2">
                  <div className="text-sm text-muted-foreground">
                    工具 ({role.toolCount} 个)
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {(detail?.tools ?? role.toolNames ?? []).map((tool) => (
                      <Badge
                        key={tool}
                        variant="outline"
                        className="text-[10px] font-normal"
                      >
                        {tool}
                      </Badge>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          )}
        </div>

        <div className="shrink-0 flex items-center justify-end gap-2 pt-4 border-t border-border">
          {canDelete ? (
            <Button
              type="button"
              variant="outline"
              className="text-destructive hover:text-destructive"
              onClick={() => {
                onDelete?.(role);
                onOpenChange(false);
              }}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              删除
            </Button>
          ) : null}
          {canEdit ? (
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                onEdit?.(role);
                onOpenChange(false);
              }}
            >
              <Pencil className="mr-2 h-4 w-4" />
              编辑
            </Button>
          ) : null}
          <Button type="button" onClick={() => onOpenChange(false)}>
            <X className="mr-2 h-4 w-4" />
            关闭
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
