import { ArrowRight, FolderKanban, Plus } from "lucide-react";
import { BrandLogo } from "@/components/branding/BrandLogo";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { TaskWorkspaceSummary } from "../../types";
import { SetupChecklist } from "./SetupChecklist";

interface WorkspaceHomeScreenProps {
  workspaces: TaskWorkspaceSummary[];
  isLoading: boolean;
  onOpenWorkspace: (workspaceId: string) => void;
  onCreateWorkspace: () => void;
}

const CLAW_WS_TITLE = "Claw 远程会话";

export function WorkspaceHomeScreen({
  workspaces,
  isLoading,
  onOpenWorkspace,
  onCreateWorkspace,
}: WorkspaceHomeScreenProps) {
  const displayWorkspaces = workspaces.filter(
    (w) => w.workspace_kind !== "claw" && w.title !== CLAW_WS_TITLE,
  );
  const recentWorkspaces = displayWorkspaces.slice(0, 8);

  return (
    <div className="flex-1 overflow-y-auto bg-background">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-8 py-10">
        <section className="rounded-2xl border border-border bg-card p-8 shadow-sm">
          <div className="flex flex-col gap-8 lg:flex-row lg:items-center lg:justify-between">
            <div className="max-w-3xl space-y-5">
              <div className="inline-flex items-center gap-2 rounded-full border border-border bg-muted px-3 py-1 text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                Workspace Home
              </div>
              <BrandLogo
                variant="stacked"
                alt="艾斯"
                className="h-16 w-auto object-contain"
              />
              <div className="space-y-3">
                <h1 className="text-3xl font-semibold tracking-tight text-foreground">
                  先选择一个工作区，再进入对应会话继续工作
                </h1>
                <p className="max-w-2xl text-sm leading-7 text-muted-foreground">
                  知识库、知识图谱、数据库连接这些资源本体可以长期存在并复用；当前工作区只决定这次实际可见和使用哪些资源。
                </p>
              </div>
            </div>

            <div className="flex w-full max-w-xs flex-col gap-3">
              <div className="rounded-2xl border border-border bg-muted px-4 py-3 text-sm leading-6 text-muted-foreground">
                当前默认不强制打开任何工作区。你可以直接从最近任务里恢复，或者新建一个长期任务工作区。
              </div>
            </div>
          </div>
        </section>

        <section className="space-y-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-sm font-semibold text-foreground">最近工作区</div>
              <div className="mt-1 text-sm text-muted-foreground">
                从最近的任务工作区恢复上下文，而不是先进入一个空会话。
              </div>
            </div>
            <div className="text-xs font-medium text-muted-foreground">
              {isLoading ? "加载中..." : `${displayWorkspaces.length} 个工作区`}
            </div>
          </div>

          {isLoading ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 3 }).map((_, index) => (
                <div
                  key={index}
                  className="h-40 rounded-2xl border border-border bg-muted"
                />
              ))}
            </div>
          ) : recentWorkspaces.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {recentWorkspaces.map((workspace) => {
                return (
                  <button
                    key={workspace.workspace_id}
                    type="button"
                    onClick={() => onOpenWorkspace(workspace.workspace_id)}
                    className={cn(
                      "group rounded-2xl border border-border bg-card p-5 text-left shadow-sm transition-all",
                      "hover:-translate-y-0.5 hover:border-border hover:shadow-sm",
                    )}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="rounded-2xl border border-border bg-muted p-3 text-muted-foreground">
                        <FolderKanban className="h-5 w-5 text-tertiary" />
                      </div>
                      <div className="rounded-full border border-border bg-muted px-2.5 py-1 text-[11px] font-medium text-muted-foreground">
                        任务工作区
                      </div>
                    </div>

                    <div className="mt-5">
                      <div className="truncate text-lg font-semibold text-foreground">
                        {workspace.title || "未命名工作区"}
                      </div>
                      <div className="mt-2 min-h-[44px] text-sm leading-6 text-muted-foreground">
                        {workspace.description?.trim() || "这个工作区还没有补充描述。"}
                      </div>
                    </div>
                    <div className="mt-5 inline-flex items-center gap-2 text-sm font-medium text-foreground">
                      打开工作区
                      <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                    </div>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="space-y-4">
              <SetupChecklist onCreateWorkspace={onCreateWorkspace} />
              <div className="rounded-2xl border border-dashed border-border bg-muted px-6 py-10 text-center">
                <div className="text-lg font-semibold text-foreground">还没有工作区</div>
                <div className="mt-2 text-sm leading-6 text-muted-foreground">
                  先创建一个长期任务工作区，后续再在里面展开多个会话、资源范围和执行记录。
                </div>
                <Button
                  type="button"
                  size="lg"
                  className="mt-5 rounded-2xl"
                  onClick={onCreateWorkspace}
                >
                  <Plus className="mr-2 h-4 w-4" />
                  新建第一个任务
                </Button>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
