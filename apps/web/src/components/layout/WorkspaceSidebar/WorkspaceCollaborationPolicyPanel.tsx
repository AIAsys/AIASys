import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  ExternalLink,
  Layers3,
  Loader2,
  Save,
  Settings2,
  ShieldCheck,
  Users,
  Wrench,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  getWorkspaceExpertPolicy,
  updateWorkspaceExpertPolicy,
} from "@/lib/api/roles";
import type {
  ExpertRoleSummary,
  SessionCollaborationPolicy,
  WorkspaceCollaborationPolicyResponse,
} from "@/types/expertRoles";

interface WorkspaceCollaborationPolicyPanelProps {
  workspaceId?: string;
  onSaved?: () => void;
  variant?: "summary" | "canvas";
  onOpenDetails?: () => void;
}

const DEFAULT_POLICY: SessionCollaborationPolicy = {
  max_depth: 1,
  max_threads: null,
  allow_nested_spawn: false,
  budget_policy: {},
  timeout_policy: {},
  stop_policy: {},
};

function getToolShortName(toolId: string): string {
  return toolId.split(":").pop()?.split(".").pop() || toolId;
}

function normalizeDepth(value: string): number {
  const parsed = Number.parseInt(value, 10);
  if (Number.isNaN(parsed)) return 1;
  return Math.min(Math.max(parsed, 1), 5);
}

function normalizeMaxThreads(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number.parseInt(value, 10);
  if (Number.isNaN(parsed)) return null;
  return Math.min(Math.max(parsed, 1), 32);
}

function resolveInitialEnabledRoleIds(
  policy: WorkspaceCollaborationPolicyResponse,
): Set<string> {
  const selectableRoleIds = new Set(
    policy.available_roles
      .filter((role) => role.host_selectable)
      .map((role) => role.role_id),
  );
  const ids = policy.configured_enabled_role_ids ?? policy.effective_enabled_role_ids;
  return new Set(ids.filter((roleId) => selectableRoleIds.has(roleId)));
}

function resolveInitialRoleTools(
  policy: WorkspaceCollaborationPolicyResponse,
): Record<string, Set<string>> {
  const result: Record<string, Set<string>> = {};
  for (const role of policy.available_roles.filter((item) => item.host_selectable)) {
    const configured = policy.configured_role_tool_ids?.[role.role_id];
    const effective = policy.effective_role_tool_ids?.[role.role_id];
    result[role.role_id] = new Set(configured ?? effective ?? role.tool_ids);
  }
  return result;
}

function roleToolSetToPayload(
  role: ExpertRoleSummary,
  selectedTools: Set<string>,
): string[] {
  return role.tool_ids.filter((toolId) => selectedTools.has(toolId));
}

function getEnabledRoleCount(
  policy: WorkspaceCollaborationPolicyResponse | null,
  enabledRoleIds: Set<string>,
): number {
  if (!policy) return 0;
  return policy.available_roles.filter((role) => role.host_selectable && enabledRoleIds.has(role.role_id)).length;
}

export function WorkspaceCollaborationPolicyPanel({
  workspaceId,
  onSaved,
  variant = "canvas",
  onOpenDetails,
}: WorkspaceCollaborationPolicyPanelProps) {
  const [policy, setPolicy] = useState<WorkspaceCollaborationPolicyResponse | null>(null);
  const [enabledRoleIds, setEnabledRoleIds] = useState<Set<string>>(new Set());
  const [roleToolIds, setRoleToolIds] = useState<Record<string, Set<string>>>({});
  const [maxDepth, setMaxDepth] = useState("1");
  const [maxThreads, setMaxThreads] = useState("");
  const [allowNestedSpawn, setAllowNestedSpawn] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadRequestRef = useRef(0);

  const canLoad = Boolean(workspaceId);
  const canSave = canLoad && !loading && !saving;

  const loadPolicy = useCallback(async () => {
    if (!workspaceId) return;
    const requestId = loadRequestRef.current + 1;
    loadRequestRef.current = requestId;
    setLoading(true);
    setError(null);
    try {
      const nextPolicy = await getWorkspaceExpertPolicy(workspaceId);
      if (requestId !== loadRequestRef.current) return;
      const collaboration = nextPolicy.collaboration_policy ?? DEFAULT_POLICY;
      setPolicy(nextPolicy);
      setEnabledRoleIds(resolveInitialEnabledRoleIds(nextPolicy));
      setRoleToolIds(resolveInitialRoleTools(nextPolicy));
      setMaxDepth(String(collaboration.max_depth ?? 1));
      setMaxThreads(collaboration.max_threads == null ? "" : String(collaboration.max_threads));
      setAllowNestedSpawn(Boolean(collaboration.allow_nested_spawn));
    } catch (err) {
      if (requestId !== loadRequestRef.current) return;
      setError(err instanceof Error ? err.message : "加载工作区协作配置失败");
    } finally {
      if (requestId === loadRequestRef.current) {
        setLoading(false);
      }
    }
  }, [workspaceId]);

  useEffect(() => {
    void loadPolicy();
  }, [loadPolicy]);

  const sortedRoles = useMemo(() => {
    return (policy?.available_roles ?? []).filter((role) => role.host_selectable).sort((left, right) => {
      if (left.source === right.source) {
        return left.display_name.localeCompare(right.display_name);
      }
      const order: Record<ExpertRoleSummary["source"], number> = {
        system: 0,
        global: 1,
        workspace: 2,
        custom: 3,
      };
      return (order[left.source] ?? 9) - (order[right.source] ?? 9);
    });
  }, [policy?.available_roles]);

  const enabledRoleCount = getEnabledRoleCount(policy, enabledRoleIds);
  const totalRoleCount = sortedRoles.length;
  const selectedToolCount = useMemo(() => {
    return sortedRoles.reduce((total, role) => {
      const selected = roleToolIds[role.role_id] ?? new Set(role.tool_ids);
      return total + role.tool_ids.filter((toolId) => selected.has(toolId)).length;
    }, 0);
  }, [roleToolIds, sortedRoles]);
  const totalToolCount = useMemo(() => {
    return sortedRoles.reduce((total, role) => total + role.tool_ids.length, 0);
  }, [sortedRoles]);

  const toggleTool = useCallback((role: ExpertRoleSummary, toolId: string, checked: boolean) => {
    setRoleToolIds((prev) => {
      const next = { ...prev };
      const roleSet = new Set(next[role.role_id] ?? role.tool_ids);
      if (checked) {
        roleSet.add(toolId);
      } else {
        roleSet.delete(toolId);
      }
      next[role.role_id] = roleSet;
      return next;
    });
  }, []);

  const savePolicy = useCallback(async () => {
    if (!workspaceId || !policy) return;
    setSaving(true);
    setError(null);
    try {
      const roleToolPayload: Record<string, string[]> = {};
      for (const role of sortedRoles) {
        const selected = roleToolIds[role.role_id] ?? new Set(role.tool_ids);
        const selectedIds = roleToolSetToPayload(role, selected);
        if (selectedIds.length !== role.tool_ids.length) {
          roleToolPayload[role.role_id] = selectedIds;
        }
      }

      const nextPolicy = await updateWorkspaceExpertPolicy(workspaceId, {
        enabled_role_ids: [...enabledRoleIds].filter((roleId) =>
          sortedRoles.some((role) => role.role_id === roleId),
        ),
        role_tool_ids: Object.keys(roleToolPayload).length > 0 ? roleToolPayload : null,
        collaboration_policy: {
          ...DEFAULT_POLICY,
          ...policy.collaboration_policy,
          max_depth: normalizeDepth(maxDepth),
          max_threads: normalizeMaxThreads(maxThreads),
          allow_nested_spawn: allowNestedSpawn,
        },
      });
      const collaboration = nextPolicy.collaboration_policy ?? DEFAULT_POLICY;
      setPolicy(nextPolicy);
      setEnabledRoleIds(resolveInitialEnabledRoleIds(nextPolicy));
      setRoleToolIds(resolveInitialRoleTools(nextPolicy));
      setMaxDepth(String(collaboration.max_depth ?? 1));
      setMaxThreads(collaboration.max_threads == null ? "" : String(collaboration.max_threads));
      setAllowNestedSpawn(Boolean(collaboration.allow_nested_spawn));
      onSaved?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存工作区协作配置失败");
    } finally {
      setSaving(false);
    }
  }, [
    allowNestedSpawn,
    enabledRoleIds,
    maxDepth,
    maxThreads,
    onSaved,
    policy,
    roleToolIds,
    sortedRoles,
    workspaceId,
  ]);

  if (!canLoad) {
    return (
      <div className="rounded-md border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
        打开工作区后可以配置协作专家启用策略。
      </div>
    );
  }

  if (variant === "summary") {
    return (
      <section
        data-testid="workspace-expert-policy-summary"
        data-workspace-id={workspaceId ?? ""}
        className="rounded-lg border border-border bg-card p-3"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Settings2 className="h-4 w-4 text-muted-foreground" />
              <div className="text-sm font-medium text-foreground">
                工作区协作配置
              </div>
            </div>
            <div className="mt-1 text-xs leading-5 text-muted-foreground">
              详细设置在主画布中打开。
            </div>
          </div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-8 shrink-0"
            onClick={onOpenDetails}
            disabled={!onOpenDetails}
            data-testid="open-workspace-collaboration-settings"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            详细设置
          </Button>
        </div>

        {error ? (
          <div className="mt-3 rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {error}
          </div>
        ) : null}

        {loading ? (
          <div className="mt-3 flex items-center gap-2 rounded-md border border-border px-3 py-3 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            加载策略中...
          </div>
        ) : (
          <div className="mt-3 grid grid-cols-2 gap-2">
            <div className="rounded-md border border-border bg-background px-3 py-2">
              <div className="text-[10px] text-muted-foreground">最大深度</div>
              <div className="mt-1 text-sm font-semibold text-foreground">
                {maxDepth || "1"}
              </div>
            </div>
            <div className="rounded-md border border-border bg-background px-3 py-2">
              <div className="text-[10px] text-muted-foreground">最大并发</div>
              <div className="mt-1 text-sm font-semibold text-foreground">
                {maxThreads || "默认"}
              </div>
            </div>
            <div className="rounded-md border border-border bg-background px-3 py-2">
              <div className="text-[10px] text-muted-foreground">启用专家</div>
              <div className="mt-1 text-sm font-semibold text-foreground">
                {enabledRoleCount}/{totalRoleCount}
              </div>
            </div>
            <div className="rounded-md border border-border bg-background px-3 py-2">
              <div className="text-[10px] text-muted-foreground">嵌套派发</div>
              <div className="mt-1 text-sm font-semibold text-foreground">
                {allowNestedSpawn ? "允许" : "关闭"}
              </div>
            </div>
          </div>
        )}
      </section>
    );
  }

  const policyMetrics = [
    { label: "最大深度", value: maxDepth || "1", icon: Layers3 },
    { label: "最大并发", value: maxThreads || "默认", icon: Bot },
    { label: "启用专家", value: `${enabledRoleCount}/${totalRoleCount}`, icon: Users },
    { label: "可用工具", value: `${selectedToolCount}/${totalToolCount}`, icon: Wrench },
  ];

  return (
    <div
      data-testid="workspace-expert-policy-panel"
      data-workspace-id={workspaceId ?? ""}
      className="flex min-h-0 flex-1 flex-col overflow-hidden bg-background"
    >
      <div className="border-b border-border bg-background px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Settings2 className="h-4 w-4 text-muted-foreground" />
              <h2 className="text-base font-semibold text-foreground">
                工作区协作配置
              </h2>
              <Badge variant="outline" className="rounded-md px-2 py-0.5 text-[10px]">
                next-run-only
              </Badge>
            </div>
            <div className="mt-1 text-xs leading-5 text-muted-foreground">
              保存后从下一轮执行开始使用新的工作区配置。
            </div>
          </div>
          <Button
            type="button"
            size="sm"
            onClick={() => void savePolicy()}
            disabled={!canSave}
            data-testid="workspace-expert-policy-save"
          >
            {saving ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Save className="h-3.5 w-3.5" />
            )}
            保存
          </Button>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-4">
          {policyMetrics.map((metric) => {
            const Icon = metric.icon;
            return (
              <div
                key={metric.label}
                className="rounded-lg border border-border bg-card px-3 py-2.5"
              >
                <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                  <Icon className="h-3.5 w-3.5" />
                  {metric.label}
                </div>
                <div className="mt-1 text-base font-semibold text-foreground">
                  {metric.value}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {error ? (
          <div className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {error}
          </div>
        ) : null}

        {loading ? (
          <div className="flex items-center gap-2 rounded-md border border-border px-3 py-3 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            加载策略中...
          </div>
        ) : null}

        {policy ? (
          <Tabs defaultValue="policy" className="flex min-h-0 flex-col">
            <TabsList className="h-9 w-fit">
              <TabsTrigger value="policy" className="gap-1.5 text-xs">
                <ShieldCheck className="h-3.5 w-3.5" />
                运行策略
              </TabsTrigger>
              <TabsTrigger value="tools" className="gap-1.5 text-xs">
                <Wrench className="h-3.5 w-3.5" />
                工具权限
              </TabsTrigger>
            </TabsList>

            <TabsContent value="policy" className="mt-4">
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
                <section className="rounded-lg border border-border bg-card p-4">
                  <div className="text-sm font-semibold text-foreground">
                    派发限制
                  </div>
                  <div className="mt-4 grid gap-4 md:grid-cols-3">
                    <div className="grid gap-1.5">
                      <Label htmlFor="workspace-collab-depth" className="text-xs">
                        最大深度
                      </Label>
                      <Input
                        id="workspace-collab-depth"
                        type="number"
                        min={1}
                        max={5}
                        value={maxDepth}
                        onChange={(event) => setMaxDepth(event.target.value)}
                        className="h-9"
                        disabled={false}
                      />
                    </div>
                    <div className="grid gap-1.5">
                      <Label htmlFor="workspace-collab-threads" className="text-xs">
                        最大并发
                      </Label>
                      <Input
                        id="workspace-collab-threads"
                        type="number"
                        min={1}
                        max={32}
                        placeholder="默认"
                        value={maxThreads}
                        onChange={(event) => setMaxThreads(event.target.value)}
                        className="h-9"
                        disabled={false}
                      />
                    </div>
                    <div className="rounded-lg border border-border bg-background px-3 py-2.5">
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-xs font-medium text-foreground">
                            允许嵌套派发
                          </div>
                          <div className="mt-1 text-[11px] text-muted-foreground">
                            子 Agent 是否可以继续派发协作节点
                          </div>
                        </div>
                        <Switch
                          checked={allowNestedSpawn}
                          onCheckedChange={setAllowNestedSpawn}
                        />
                      </div>
                    </div>
                  </div>
                </section>

                <section className="rounded-lg border border-border bg-card p-4">
                  <div className="text-sm font-semibold text-foreground">
                    当前状态
                  </div>
                  <div className="mt-4 space-y-3 text-sm">
                    <div className="flex items-center justify-between gap-4">
                      <span className="text-muted-foreground">策略生效</span>
                      <span className="font-medium text-foreground">下一轮执行</span>
                    </div>
                    <Separator />
                    <div className="flex items-center justify-between gap-4">
                      <span className="text-muted-foreground">启用专家</span>
                      <span className="font-medium text-foreground">
                        {enabledRoleCount}/{totalRoleCount}
                      </span>
                    </div>
                    <Separator />
                    <div className="flex items-center justify-between gap-4">
                      <span className="text-muted-foreground">工具权限</span>
                      <span className="font-medium text-foreground">
                        {selectedToolCount}/{totalToolCount}
                      </span>
                    </div>
                  </div>
                </section>
              </div>
            </TabsContent>

            <TabsContent value="tools" className="mt-4">
              <div className="space-y-3">
                {sortedRoles.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-border bg-card p-4 text-xs text-muted-foreground">
                    工作区暂无可配置工具的协作专家。
                  </div>
                ) : null}
                {sortedRoles.map((role) => {
                  const enabled = enabledRoleIds.has(role.role_id);
                  const selectedTools = roleToolIds[role.role_id] ?? new Set(role.tool_ids);
                  return (
                    <section
                      key={role.role_id}
                      className="rounded-lg border border-border bg-card p-4"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <div className="text-sm font-medium text-foreground">
                            {role.display_name}
                          </div>
                          <div className="mt-1 text-xs text-muted-foreground">
                            {selectedTools.size}/{role.tool_ids.length} 个工具已启用
                          </div>
                        </div>
                        <Badge variant={enabled ? "success" : "secondary"}>
                          {enabled ? "协作专家已启用" : "协作专家已关闭"}
                        </Badge>
                      </div>
                      {role.tool_ids.length > 0 ? (
                      <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                          {role.tool_ids.map((toolId) => {
                            const shortName = getToolShortName(toolId);
                            return (
                              <Checkbox
                                key={toolId}
                                checked={selectedTools.has(toolId)}
                                onCheckedChange={(checked) => toggleTool(role, toolId, checked === true)}
                                disabled={!enabled}
                                label={shortName}
                                className="min-w-0 rounded-md border border-border/70 bg-background px-2.5 py-2 text-[11px]"
                                aria-label={`${role.display_name} 工具 ${shortName}`}
                                data-testid={`workspace-expert-role-tool-toggle-${role.role_id}-${shortName}`}
                              />
                            );
                          })}
                        </div>
                      ) : (
                        <div className="mt-3 rounded-md border border-dashed border-border px-3 py-3 text-xs text-muted-foreground">
                          该角色继承工作区工具集。
                        </div>
                      )}
                    </section>
                  );
                })}
              </div>
            </TabsContent>
          </Tabs>
        ) : null}
      </div>
    </div>
  );
}
