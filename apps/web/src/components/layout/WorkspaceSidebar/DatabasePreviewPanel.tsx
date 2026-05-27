import { Database, Globe } from "lucide-react";
import { DatabaseQueryWorkbench } from "@/components/database/DatabaseQueryWorkbench";
import { DbFilePreview } from "./preview/DbFilePreview";

interface DatabaseResourceNode {
  name: string;
  path: string;
  meta?: Record<string, unknown>;
}

interface DatabasePreviewPanelProps {
  node: DatabaseResourceNode;
  sessionId?: string | null;
}

function getText(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function resolveHandleFromNode(node: DatabaseResourceNode): string {
  const explicit = getText(node.meta?.handle);
  if (explicit) {
    return explicit;
  }
  const id = getText(node.meta?.id);
  if (!id) {
    return "";
  }
  return `connector:${id}`;
}

function isLocalDbFile(node: DatabaseResourceNode): boolean {
  // 有 db_path 元数据且 handle 不以 connector: 开头的是工作区本地数据库文件
  const handle = getText(node.meta?.handle);
  const hasDbPath = getText(node.meta?.db_path).length > 0;
  return hasDbPath && !handle.startsWith("connector:");
}

function resolveDbFileName(node: DatabaseResourceNode): string {
  // db_path 形如 /workspace/research/data.sqlite，提取相对路径部分作为文件名
  const dbPath = getText(node.meta?.db_path);
  if (dbPath.startsWith("/workspace/")) {
    return dbPath.slice("/workspace/".length);
  }
  if (dbPath.startsWith("/global/")) {
    return dbPath.slice("/global/".length);
  }
  return dbPath;
}

function resolveDbScope(node: DatabaseResourceNode): "workspace" | "global" {
  const dbPath = getText(node.meta?.db_path);
  return dbPath.startsWith("/global/") || node.meta?._globalResource === true
    ? "global"
    : "workspace";
}

function getDbKindLabel(handle: string): { icon: React.ReactNode; label: string } {
  if (handle.startsWith("connector:")) {
    return {
      icon: <Globe className="h-4 w-4 shrink-0 text-tertiary" />,
      label: "远程连接",
    };
  }
  return {
    icon: <Database className="h-4 w-4 shrink-0 text-tertiary" />,
    label: "本地文件",
  };
}

export function DatabasePreviewPanel({
  node,
  sessionId,
}: DatabasePreviewPanelProps) {
  if (isLocalDbFile(node)) {
    const fileName = resolveDbFileName(node);
    return (
      <div className="flex h-full min-h-0 flex-col bg-background">
        <div className="flex-shrink-0 border-b border-border px-4 py-2">
          <div className="flex min-w-0 items-center gap-2">
            <Database className="h-4 w-4 shrink-0 text-tertiary" />
            <span className="truncate text-sm font-semibold">{node.name}</span>
            <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
              本地文件
            </span>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-hidden">
          <DbFilePreview
            fileName={fileName}
            sessionId={sessionId}
            scope={resolveDbScope(node)}
          />
        </div>
      </div>
    );
  }

  const handle = resolveHandleFromNode(node);
  const { icon, label } = getDbKindLabel(handle);

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      <div className="flex-shrink-0 border-b border-border px-4 py-2">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            {icon}
            <span className="truncate text-sm font-semibold">{node.name}</span>
            <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
              {label}
            </span>
          </div>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">
        <DatabaseQueryWorkbench
          sessionId={sessionId}
          initialHandle={handle}
          showHandleSelector={false}
        />
      </div>
    </div>
  );
}
