import { useCallback, useEffect, useRef, useState, lazy, Suspense } from "react";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { RoleDetailDialog } from "@/components/RoleDetailDialog";
const LazyRoleFormDialog = lazy(() =>
  import("@/components/RoleFormDialog").then((module) => ({
    default: module.RoleFormDialog,
  })),
);
import { RoleListItem } from "@/components/RoleListItem";
import {
  createRoleForScope,
  deleteRoleForScope,
  enableGlobalBuiltinRole,
  enableWorkspaceBuiltinRole,
  getRoleDetailForScope,
  listInstalledRolesForScope,
  listRolesForScope,
  updateRoleForScope,
  updateRoleVisibilityForScope,
} from "@/lib/api/roles";
import type {
  RoleManagerScope,
  RoleDetail,
  RoleItem,
  RoleVisibilityUpdatePayload,
} from "@/lib/api/roles";
import { cn } from "@/lib/utils";

interface RolesManagerPanelProps {
  scope?: RoleManagerScope;
  workspaceId?: string | null;
  title?: string;
  description?: string;
  readOnly?: boolean;
  roleFilter?: (role: RoleItem) => boolean;
  mode?: "manage" | "market";
  hideCreateButton?: boolean;
  className?: string;
}

export function RolesManagerPanel({
  scope = "workspace",
  workspaceId,
  title,
  description,
  readOnly = false,
  roleFilter,
  mode = "manage",
  hideCreateButton = false,
  className,
}: RolesManagerPanelProps) {
  const [roles, setRoles] = useState<RoleItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogMode, setDialogMode] = useState<"create" | "edit">("create");
  const [editData, setEditData] = useState<RoleDetail | undefined>();
  const [deleteAlertOpen, setDeleteAlertOpen] = useState(false);
  const [roleToDelete, setRoleToDelete] = useState<RoleItem | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailRole, setDetailRole] = useState<RoleItem | null>(null);
  const [detailData, setDetailData] = useState<RoleDetail | null>(null);
  const loadRequestRef = useRef(0);
  const detailRequestRef = useRef(0);

  const resolvedWorkspaceId = workspaceId || null;
  const canManage = scope === "global" || Boolean(resolvedWorkspaceId);
  const isMarket = mode === "market";
  const canCreate = canManage && !readOnly && !hideCreateButton;
  const panelTitle = title ?? (
    isMarket
      ? "协作专家市场"
      : scope === "global"
        ? "已安装的专家"
        : "当前工作区启用"
  );
  const panelDescription = description ?? (
    isMarket
      ? "系统内置专家默认可用。如需自定义，可覆盖到我的协作专家或工作区。"
      : scope === "global"
        ? "管理已安装到可选集合的协作专家。新工作区会按这里的策略继承。"
        : "管理安装到当前工作区的协作专家，保存后下一轮执行生效。"
  );

  const load = useCallback(async (showLoading = true) => {
    if (!canManage) {
      setRoles([]);
      setLoading(false);
      return;
    }

    const requestId = loadRequestRef.current + 1;
    loadRequestRef.current = requestId;
    if (showLoading) {
      setLoading(true);
    }
    try {
      const data = await (
        isMarket
          ? listRolesForScope(
              resolvedWorkspaceId ? "workspace" : scope,
              resolvedWorkspaceId,
            )
          : listInstalledRolesForScope(scope, resolvedWorkspaceId)
      );
      if (requestId !== loadRequestRef.current) return;
      setRoles(roleFilter ? data.filter(roleFilter) : data);
    } catch (err) {
      if (requestId !== loadRequestRef.current) return;
      console.error("加载协作专家失败:", err);
    } finally {
      if (requestId === loadRequestRef.current) {
        setLoading(false);
      }
    }
  }, [canManage, resolvedWorkspaceId, roleFilter, scope, isMarket]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleEdit = useCallback(async (role: RoleItem) => {
    if (!canManage || readOnly) return;
    try {
      const detail = await getRoleDetailForScope(
        scope,
        role.name,
        resolvedWorkspaceId,
      );
      setEditData(detail);
      setDialogMode("edit");
      setDialogOpen(true);
    } catch (err) {
      console.error("获取协作专家详情失败:", err);
    }
  }, [canManage, readOnly, resolvedWorkspaceId, scope]);

  const handlePreview = useCallback(async (role: RoleItem) => {
    const requestId = detailRequestRef.current + 1;
    detailRequestRef.current = requestId;
    setDetailRole(role);
    setDetailOpen(true);
    setDetailData(null);
    try {
      const d = await getRoleDetailForScope(
        scope,
        role.name,
        resolvedWorkspaceId,
      );
      if (requestId === detailRequestRef.current) {
        setDetailData(d);
      }
    } catch (err) {
      if (requestId === detailRequestRef.current) {
        console.error("获取协作专家详情失败:", err);
      }
    }
  }, [scope, resolvedWorkspaceId]);

  const handleCreate = useCallback(() => {
    if (!canCreate) return;
    setEditData(undefined);
    setDialogMode("create");
    setDialogOpen(true);
  }, [canCreate]);

  const handleDelete = useCallback((role: RoleItem) => {
    if (readOnly) return;
    setRoleToDelete(role);
    setDeleteAlertOpen(true);
  }, [readOnly]);

  const handleVisibilitySave = useCallback(async (
    role: RoleItem,
    payload: RoleVisibilityUpdatePayload,
  ) => {
    if (!canManage || readOnly) return;
    const visibility = await updateRoleVisibilityForScope(
      scope,
      role.name,
      payload,
      resolvedWorkspaceId,
    );
    setRoles((prev) =>
      prev.map((item) =>
        item.name === role.name
          ? {
              ...item,
              catalogVisible: visibility.catalog_visible,
              hostSelectable: visibility.host_selectable,
              defaultEnabled: visibility.default_enabled,
              visibilitySource: visibility.visibility_source,
              lockReason: visibility.lock_reason,
            }
          : item,
      ),
    );
    await load(false);
  }, [canManage, load, readOnly, resolvedWorkspaceId, scope]);

  const handleDefaultEnabledChange = useCallback(async (
    role: RoleItem,
    enabled: boolean,
  ) => {
    if (!canManage || readOnly) return;
    setRoles((prev) =>
      prev.map((item) =>
        item.name === role.name
          ? { ...item, defaultEnabled: enabled }
          : item,
      ),
    );
    try {
      const visibility = await updateRoleVisibilityForScope(
        scope,
        role.name,
        {
          catalog_visible: role.catalogVisible,
          host_selectable: role.hostSelectable,
          default_enabled: enabled,
        },
        resolvedWorkspaceId,
      );
      setRoles((prev) =>
        prev.map((item) =>
          item.name === role.name
            ? {
                ...item,
                catalogVisible: visibility.catalog_visible,
                hostSelectable: visibility.host_selectable,
                defaultEnabled: visibility.default_enabled,
                visibilitySource: visibility.visibility_source,
                lockReason: visibility.lock_reason,
              }
            : item,
        ),
      );
    } catch (err) {
      setRoles((prev) =>
        prev.map((item) =>
          item.name === role.name
            ? { ...item, defaultEnabled: role.defaultEnabled }
            : item,
        ),
      );
      console.error("保存协作专家默认启用失败:", err);
      alert("保存默认启用失败");
    }
  }, [canManage, readOnly, resolvedWorkspaceId, scope]);

  const handleEnableDefault = useCallback(async (role: RoleItem) => {
    if (!canManage) return;
    try {
      await enableGlobalBuiltinRole(role.name);
      // 安装后仅进入可选集合，不自动默认启用
      await load();
    } catch (err) {
      console.error("安装到我的协作专家失败:", err);
      alert("安装到我的协作专家失败");
    }
  }, [canManage, load]);

  const handleEnableWorkspace = useCallback(async (role: RoleItem) => {
    if (!resolvedWorkspaceId) return;
    try {
      await enableWorkspaceBuiltinRole(resolvedWorkspaceId, role.name);
      await load();
    } catch (err) {
      console.error("安装到工作区失败:", err);
      alert("安装到工作区失败");
    }
  }, [load, resolvedWorkspaceId]);

  const handleSubmitRole = useCallback(async (
    mode: "create" | "edit",
    payload: {
      name: string;
      description: string;
      system_prompt: string;
      model: string | null;
      scope: RoleManagerScope;
    },
    initialName?: string,
  ) => {
    if (!canManage || readOnly || isMarket) return;
    if (mode === "edit" && initialName) {
      await updateRoleForScope(
        scope,
        initialName,
        {
          description: payload.description,
          system_prompt: payload.system_prompt,
          model: payload.model,
        },
        resolvedWorkspaceId,
      );
      return;
    }
    await createRoleForScope(
      scope,
      payload,
      resolvedWorkspaceId,
    );
  }, [canManage, isMarket, readOnly, resolvedWorkspaceId, scope]);

  const doDelete = useCallback(async () => {
    if (!roleToDelete || !canManage || readOnly) return;
    try {
      await deleteRoleForScope(
        scope,
        roleToDelete.name,
        resolvedWorkspaceId,
      );
      await load();
    } catch (err) {
      console.error("删除角色失败:", err);
      alert("删除失败");
    } finally {
      setDeleteAlertOpen(false);
      setRoleToDelete(null);
    }
  }, [canManage, load, readOnly, resolvedWorkspaceId, roleToDelete, scope]);

  const deleteActionLabel = roleToDelete?.source === "system" ||
    roleToDelete?.source === "builtin"
    ? scope === "global"
      ? "移出我的默认"
      : "移出当前工作区"
    : "删除";

  return (
    <div
      data-testid="roles-manager-panel"
      data-scope={scope}
      data-workspace-id={resolvedWorkspaceId ?? ""}
      className={cn("flex h-full min-h-0 flex-col gap-4", className)}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-foreground">
            {panelTitle}
          </h2>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            {panelDescription}
          </p>
        </div>
        {canCreate ? (
          <Button
            type="button"
            onClick={handleCreate}
            data-testid="roles-manager-create"
          >
            <Plus className="mr-2 h-4 w-4" />
            新建协作专家
          </Button>
        ) : null}
      </div>

      <Card className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <CardContent className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
          {loading && (
            <div className="text-sm text-muted-foreground">加载中...</div>
          )}
          {!canManage && (
            <div className="text-sm text-muted-foreground">
              打开工作区后可以管理协作专家。
            </div>
          )}
          {!loading && canManage && roles.length === 0 && (
            <div className="text-sm text-muted-foreground">
              暂无协作专家
            </div>
          )}
          {roles.map((role) => (
            <RoleListItem
              key={role.name}
              role={role}
              onEdit={readOnly ? undefined : handleEdit}
              onDelete={isMarket ? undefined : handleDelete}
              onPreview={handlePreview}
              onVisibilitySave={readOnly ? undefined : handleVisibilitySave}
              onDefaultEnabledChange={
                !readOnly ? handleDefaultEnabledChange : undefined
              }
              onEnableDefault={handleEnableDefault}
              onEnableWorkspace={
                resolvedWorkspaceId ? handleEnableWorkspace : undefined
              }
            />
          ))}
        </CardContent>
      </Card>

      {canManage && !readOnly ? (
        <Suspense fallback={null}>
          <LazyRoleFormDialog
            open={dialogOpen}
            onOpenChange={setDialogOpen}
            mode={dialogMode}
            initialData={editData}
            workspaceId={resolvedWorkspaceId ?? "__global__"}
            scope={scope}
            onSubmitRole={handleSubmitRole}
            onSuccess={() => void load()}
          />
        </Suspense>
      ) : null}

      <RoleDetailDialog
        open={detailOpen}
        onOpenChange={setDetailOpen}
        role={detailRole}
        detail={detailData}
        onEdit={readOnly ? undefined : handleEdit}
        onDelete={readOnly ? undefined : handleDelete}
      />

      <AlertDialog open={deleteAlertOpen} onOpenChange={setDeleteAlertOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认{deleteActionLabel}</AlertDialogTitle>
            <AlertDialogDescription>
              {roleToDelete?.source === "system" || roleToDelete?.source === "builtin"
                ? `确定要将协作专家 "${roleToDelete?.name}" ${deleteActionLabel}吗？内置源仍保留在市场里，可以重新安装。`
                : `确定要删除协作专家 "${roleToDelete?.name}" 吗？此操作不可撤销。`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setRoleToDelete(null)}>
              取消
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={doDelete}
              className="bg-destructive text-destructive-foreground"
              data-testid="roles-manager-confirm-delete"
            >
              确认{deleteActionLabel}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
