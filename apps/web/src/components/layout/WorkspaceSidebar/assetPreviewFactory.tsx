import { Suspense, type ReactNode } from "react";

import { extensionRegistry } from "@/lib/extensionRegistry";
import { ensureBuiltinPreviewsRegistered } from "@/lib/registerBuiltinPreviews";
import {
  getWorkspaceResourceBaseName,
  inferWorkspaceResourceFileType,
  normalizeWorkspaceResourcePath,
} from "@/utils/workspaceResourceFileTypes";

export type AssetResourceType = string;

const BUILTIN_ASSET_RESOURCE_TYPES = new Set([
  "knowledge",
  "database",
  "graph",
  "memory",
  "data_table",
]);

export interface AssetResourceNode {
  name: string;
  path: string;
  absolute_path?: string | null;
  node_type?: "directory" | "resource";
  resource_type?: AssetResourceType | "mcp";
  schema_kind?: string;
  preview_kind?: string;
  renderer_hint?: string;
  meta?: Record<string, unknown>;
}

export interface GlobalResourceNode extends AssetResourceNode {
  node_type: "directory" | "resource";
  children?: GlobalResourceNode[];
}

interface WorkspaceAssetFileInput {
  name: string;
  resource_type?: string;
  schema_kind?: string;
  preview_kind?: string;
  renderer_hint?: string;
  meta?: Record<string, unknown>;
}

interface RenderAssetResourcePreviewOptions {
  node: AssetResourceNode;
  sessionId?: string | null;
  workspaceId?: string | null;
  onRefresh?: () => Promise<void> | void;
  onClose?: () => void;
  closeLabel?: string;
  onSplitRight?: () => void;
  onSplitDown?: () => void;
}

export function isAssetResourceType(
  type: AssetResourceNode["resource_type"],
): type is AssetResourceType {
  return typeof type === "string" && BUILTIN_ASSET_RESOURCE_TYPES.has(type);
}

function stripKnownDbSuffix(baseName: string, resourceType: AssetResourceType) {
  const escapedType =
    resourceType === "knowledge"
      ? "(knowledge|kb|knowledge-base|knowledge_base)"
      : resourceType === "graph"
        ? "(graph|kg|knowledge-graph|knowledge_graph)"
        : "(database|sqlite|duckdb|sql)";
  const typedSuffix = new RegExp(
    `[._-]${escapedType}\\.(kg|db|sqlite|sqlite3|duckdb)$`,
    "i",
  );
  return baseName
    .replace(typedSuffix, "")
    .replace(/\.(kg|db|sqlite|sqlite3|duckdb)$/i, "");
}

function getStringValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function hasResourceMetadata(file: WorkspaceAssetFileInput): boolean {
  const meta = file.meta ?? {};
  return Boolean(
    file.resource_type ||
      meta.resource_type ||
      file.preview_kind ||
      meta.preview_kind ||
      file.schema_kind ||
      meta.schema_kind ||
      file.renderer_hint ||
      meta.renderer_hint,
  );
}

export function resolveAssetResourceNodeFromWorkspaceFile(
  file: string | WorkspaceAssetFileInput,
): AssetResourceNode | null {
  const fileName = typeof file === "string" ? file : file.name;
  const normalizedPath = normalizeWorkspaceResourcePath(fileName);
  if (!normalizedPath) {
    return null;
  }

  const fileInput: WorkspaceAssetFileInput =
    typeof file === "string" ? { name: file } : file;
  const sourceMeta = fileInput.meta ?? {};
  const resourceType = inferWorkspaceResourceFileType(fileInput, {
    isDirectory: sourceMeta.source === "workspace_directory",
  });
  if (!resourceType) {
    return null;
  }

  const baseName = getWorkspaceResourceBaseName(normalizedPath);
  const id = stripKnownDbSuffix(baseName, resourceType as AssetResourceType);
  const extension = baseName.split(".").pop()?.toLowerCase();
  const isGlobalResource = sourceMeta._globalResource === true;
  const logicalPrefix = isGlobalResource ? "/global" : "/workspace";
  const nodePathPrefix = isGlobalResource ? "global" : "workspace";
  const mergedMeta: Record<string, unknown> = {
    ...sourceMeta,
    id: sourceMeta.id ?? id,
    db_path: sourceMeta.db_path ?? `${logicalPrefix}/${normalizedPath}`,
    source:
      sourceMeta.source ??
      (hasResourceMetadata(fileInput)
        ? isGlobalResource
          ? "global_workspace_file_metadata"
          : "workspace_file_metadata"
        : isGlobalResource
          ? "global_workspace_asset"
          : "workspace_asset"),
    type:
      sourceMeta.type ??
      (extension === "duckdb" ? "duckdb" : "sqlite"),
    handle:
      sourceMeta.handle ?? (resourceType === "database" ? id : undefined),
  };

  return {
    name: baseName,
    path: `${nodePathPrefix}/${normalizedPath}`,
    node_type: "resource",
    resource_type: resourceType as AssetResourceType,
    schema_kind: fileInput.schema_kind ?? getStringValue(sourceMeta.schema_kind),
    preview_kind: fileInput.preview_kind ?? getStringValue(sourceMeta.preview_kind),
    renderer_hint: fileInput.renderer_hint ?? getStringValue(sourceMeta.renderer_hint),
    meta: mergedMeta,
  };
}

export function renderAssetResourcePreview({
  node,
  sessionId,
  workspaceId,
  onRefresh,
  onClose,
  closeLabel,
  onSplitRight,
  onSplitDown,
}: RenderAssetResourcePreviewOptions): ReactNode | null {
  const kind = node.resource_type;
  if (!kind) return null;

  ensureBuiltinPreviewsRegistered();

  const preview = extensionRegistry.getPreview(kind);
  if (!preview) return null;

  const Component = preview.component;

  // database 类型：render 时不再过滤 workspace 文件，由 DatabasePreviewPanel
  // 自行根据 node.meta.handle 区分 runtime connector 和本地文件路径
  if (kind === "database") {
    return (
      <Suspense fallback={<AssetResourcePreviewFallback />}>
        <Component
          node={node}
          sessionId={sessionId}
          onClose={onClose}
          closeLabel={closeLabel}
          onSplitRight={onSplitRight}
          onSplitDown={onSplitDown}
        />
      </Suspense>
    );
  }

  return (
    <Suspense fallback={<AssetResourcePreviewFallback />}>
      <Component
        node={node}
        sessionId={sessionId}
        workspaceId={workspaceId}
        onRefresh={onRefresh}
        onClose={onClose}
        closeLabel={closeLabel}
        onSplitRight={onSplitRight}
        onSplitDown={onSplitDown}
      />
    </Suspense>
  );
}

function AssetResourcePreviewFallback() {
  return (
    <div className="flex h-full min-h-0 items-center justify-center px-6 text-sm text-muted-foreground">
      正在加载资源预览...
    </div>
  );
}
