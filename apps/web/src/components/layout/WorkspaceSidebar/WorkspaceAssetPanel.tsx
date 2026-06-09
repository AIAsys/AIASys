import { useAuthContext } from "@/contexts/AuthContext";
import { API_ENDPOINTS, getCurrentUserId } from "@/config/api";
import { useDragDrop } from "@/hooks/useDragDrop";
import type { FileCreateResponse } from "@/types/api";
import type { WorkspaceFile } from "@/types/task";
import { apiRequest } from "@/lib/api/httpClient";
import { cn } from "@/lib/utils";
import {
  createGlobalWorkspacePreviewFile,
  createWorkspacePreviewFile,
} from "@/utils/workspaceFiles";
import {
  WORKSPACE_FOLDER_MARKER_FILENAME,
  type FileTreeNode,
  isWorkspaceFolderMarkerFile,
} from "@/utils/fileTreeUtils";
import { countWorkspaceAssetEntries, countAssetTreeEntries } from "@/utils/assetTreeCounts";
import { extractClipboardFiles } from "@/utils/clipboardFiles";
import {
  Clipboard,
  Copy,
  FilePlus,
  FileText,
  FolderPlus,
  FolderTree,
  Globe,
  HardDrive,
  Loader2,
  RefreshCw,
  ServerCog,
  Upload,
  X,
} from "lucide-react";
import React, {
  useCallback,
  useEffect,
  lazy,
  useMemo,
  useRef,
  Suspense,
  useState,
} from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { FileTreeView } from "./FileTreeView";
import type { FileTreeClipboardItem } from "./FileTreeView";
const LazyFileHistoryDialog = lazy(() =>
  import("./FileHistoryDialog").then((module) => ({
    default: module.FileHistoryDialog,
  })),
);
import { AssetTreePanelHeader } from "./AssetTreePanelHeader";
import { getWorkspaceRuntimeEnvironments } from "@/lib/api/workspaces";
import type { TaskWorkspaceSummary } from "@/pages/WorkspacePage/types";
import type {
  WorkspaceRuntimeEnvironment,
  WorkspaceRuntimeEnvironmentRegistry,
} from "@/types/workspace";
import type { PreviewFile } from "./preview";
import {
  renderAssetResourcePreview,
  resolveAssetResourceNodeFromWorkspaceFile,
  type GlobalResourceNode,
} from "./assetPreviewFactory";
import { writeTextToClipboard } from "@/utils/clipboardText";

export type AssetScope = "current" | "global";

function findGlobalResourceNode(
  nodes: GlobalResourceNode[],
  path: string,
): GlobalResourceNode | null {
  for (const node of nodes) {
    if (node.path === path) {
      return node;
    }
    if (node.children) {
      const found = findGlobalResourceNode(node.children, path);
      if (found) return found;
    }
  }
  return null;
}

function globalResourceNodeToWorkspaceFile(node: GlobalResourceNode): WorkspaceFile {
  return {
    name: node.path,
    size: 0,
    mtime: "",
    absolute_path: node.absolute_path,
    resource_type: node.resource_type ?? undefined,
    schema_kind: node.schema_kind,
    preview_kind: node.preview_kind,
    renderer_hint: node.renderer_hint,
    meta: node.meta as Record<string, unknown> | undefined,
  };
}

function sortFileTreeNodes(nodes: FileTreeNode[]): FileTreeNode[] {
  return [...nodes].sort((a, b) => {
    if (a.isDirectory !== b.isDirectory) {
      return a.isDirectory ? -1 : 1;
    }
    return a.name.localeCompare(b.name);
  });
}

function normalizeLogicalFilePath(path: string): string {
  return path.trim().replace(/\\/g, "/").replace(/^\/+/, "");
}

function pathFromUrl(value: string): string {
  if (!/^https?:\/\//i.test(value.trim())) {
    return value;
  }

  try {
    const url = new URL(value);
    const pathname = decodeURIComponent(url.pathname);
    const workspaceMatch = pathname.match(
      /\/api\/files\/(?:download|content)\/[^/]+\/[^/]+\/(.+)$/,
    );
    if (workspaceMatch?.[1]) {
      return workspaceMatch[1];
    }

    const scopedWorkspaceMatch = pathname.match(
      /\/api\/workspaces\/[^/]+\/files\/(?:download|content)\/(.+)$/,
    );
    if (scopedWorkspaceMatch?.[1]) {
      return scopedWorkspaceMatch[1];
    }

    const globalMatch = pathname.match(
      /\/api\/workspaces\/[^/]+\/global-workspace\/(?:download|content)\/(.+)$/,
    );
    if (globalMatch?.[1]) {
      return globalMatch[1];
    }

    return pathname;
  } catch {
    return value;
  }
}

function normalizeWorkspaceInputPath(path: string): string {
  const fromUrl = pathFromUrl(path);
  let normalized = fromUrl.trim().replace(/\\/g, "/");
  normalized = normalized.replace(/^\/?(workspace|global)\//i, "");
  normalized = normalized.replace(/^\/+/, "");
  normalized = normalized.replace(/\/{2,}/g, "/");
  return normalized;
}

function normalizeWorkspaceFileInputPath(path: string): string {
  return normalizeWorkspaceInputPath(path);
}

function normalizeWorkspaceFolderInputPath(path: string): string {
  return normalizeWorkspaceInputPath(path).replace(/\/+$/g, "");
}

function flattenGlobalResourcesToFiles(nodes: GlobalResourceNode[]): WorkspaceFile[] {
  const result: WorkspaceFile[] = [];
  function walk(list: GlobalResourceNode[]) {
    for (const node of list) {
      if (node.node_type === "resource") {
        result.push(globalResourceNodeToWorkspaceFile(node));
      }
      if (node.children) walk(node.children);
    }
  }
  walk(nodes);
  return result;
}

function globalResourcesToFileTree(nodes: GlobalResourceNode[]): FileTreeNode[] {
  return sortFileTreeNodes(
    nodes
      .filter((node) => !node.path.startsWith(".aiasys") && node.name !== ".aiasys")
      .map((node) => {
        if (node.node_type === "directory") {
          return {
            name: node.name,
            path: node.path,
            absolutePath: node.absolute_path,
            isDirectory: true,
            children: globalResourcesToFileTree(node.children || []),
            meta: node.meta,
          };
        }

        return {
          name: node.name,
          path: node.path,
          absolutePath: node.absolute_path,
          isDirectory: false,
          file: globalResourceNodeToWorkspaceFile(node),
          meta: node.meta,
        };
      }),
  );
}

const runtimeStatusLabels: Record<string, string> = {
  registered: "已登记",
  ready: "可使用",
  running: "运行中",
  stopped: "已停止",
  missing: "缺失",
  unavailable: "不可用",
  error: "异常",
};

function runtimeStatusLabel(status?: string | null) {
  return status ? runtimeStatusLabels[status] ?? status : "未检测";
}

function runtimeKindLabel(kind?: WorkspaceRuntimeEnvironment["kind"] | null) {
  return kind === "registered_python" ? "已登记 Python" : "UV";
}

function selectRuntimeEnv(
  registry: WorkspaceRuntimeEnvironmentRegistry | null,
  bindingEnvId?: string | null,
): WorkspaceRuntimeEnvironment | null {
  const envs = registry?.envs ?? [];
  return (
    envs.find((env) => env.active) ??
    envs.find((env) => env.env_id === registry?.active_env_id) ??
    envs.find((env) => env.env_id === bindingEnvId) ??
    envs[0] ??
    null
  );
}

function runtimeBoolMeta(
  env: WorkspaceRuntimeEnvironment | null,
  key: string,
): boolean | null {
  const value = env?.metadata?.[key];
  return typeof value === "boolean" ? value : null;
}

function parentPath(path?: string | null): string | null {
  const text = String(path || "").trim().replace(/\\/g, "/");
  if (!text || !text.includes("/")) return null;
  return text.slice(0, text.lastIndexOf("/"));
}

function formatRuntimeEntryLabel(
  registry: WorkspaceRuntimeEnvironmentRegistry | null,
  env: WorkspaceRuntimeEnvironment | null,
  sandboxMode?: string | null,
): string {
  if (sandboxMode === "docker") {
    return "当前绑定 Docker 沙盒";
  }
  if (env) {
    const python = env.python_version ? `Python ${env.python_version}` : "Python 未锁定";
    return `${runtimeKindLabel(env.kind)} · ${python} · ${env.package_count} 个包 · ${runtimeStatusLabel(env.status)}`;
  }
  if (registry && registry.total > 0) {
    return `${registry.total} 个环境 · 未绑定`;
  }
  return "未初始化";
}

function MaterialState({ value }: { value: boolean | null }) {
  const label = value === null ? "未知" : value ? "存在" : "缺失";
  return (
    <span
      className={cn(
        "rounded-full border px-2 py-0.5 text-[11px] font-medium",
        value === true && "border-success/20 bg-success-container text-on-success-container",
        value === false && "border-warning/20 bg-warning-container text-on-warning-container",
        value === null && "border-border bg-muted text-muted-foreground",
      )}
    >
      {label}
    </span>
  );
}

function RuntimePathRow({
  label,
  value,
  onCopy,
}: {
  label: string;
  value?: string | null;
  onCopy: (value: string, label: string) => void;
}) {
  const text = String(value || "").trim();
  return (
    <div className="grid gap-1 rounded-xl border border-border bg-background px-3 py-2 md:grid-cols-[96px_minmax(0,1fr)_auto] md:items-center">
      <div className="text-[11px] font-semibold text-muted-foreground">
        {label}
      </div>
      <div
        className="min-w-0 truncate font-mono text-xs text-foreground"
        title={text || undefined}
      >
        {text || "未生成"}
      </div>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        disabled={!text}
        onClick={() => onCopy(text, label)}
        aria-label={`复制${label}`}
      >
        <Copy className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}

function RuntimeEnvControlledPreview({
  registry,
  selectedEnv,
  isLoading,
  error,
  copyMessage,
  onRefresh,
  onCopy,
  onManage,
}: {
  registry: WorkspaceRuntimeEnvironmentRegistry | null;
  selectedEnv: WorkspaceRuntimeEnvironment | null;
  isLoading: boolean;
  error: string | null;
  copyMessage: string | null;
  onRefresh: () => void;
  onCopy: (value: string, label: string) => void;
  onManage?: () => void;
}) {
  const envPath =
    selectedEnv?.material_path ?? parentPath(registry?.registry_path) ?? null;
  const packages = selectedEnv?.packages ?? [];
  const visiblePackages = packages.slice(0, 18);
  const materialFiles = [
    ["pyproject.toml", runtimeBoolMeta(selectedEnv, "pyproject_exists")],
    ["uv.lock", runtimeBoolMeta(selectedEnv, "lock_exists")],
    [".python-version", runtimeBoolMeta(selectedEnv, "python_version_file_exists")],
    [".venv", runtimeBoolMeta(selectedEnv, "venv_exists")],
  ] as const;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-border px-4 py-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <ServerCog className="h-4 w-4 text-tertiary" />
              运行环境
            </div>
            <div className="mt-1 text-xs leading-5 text-muted-foreground">
              依赖目录会以折叠节点显示，展开时按页预览。
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onRefresh}>
              <RefreshCw className={cn("h-4 w-4", isLoading && "animate-spin")} />
              刷新
            </Button>
            {onManage ? (
              <Button type="button" size="sm" onClick={onManage}>
                管理
              </Button>
            ) : null}
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <div className="space-y-4">
          {error ? (
            <div className="rounded-xl border border-error/30 bg-error-container px-3 py-2 text-sm text-on-error-container">
              {error}
            </div>
          ) : null}

          <section className="rounded-2xl border border-border bg-card px-4 py-4">
            <div className="grid gap-3 md:grid-cols-4">
              <div>
                <div className="text-[11px] font-semibold text-muted-foreground">
                  当前环境
                </div>
                <div className="mt-1 truncate text-sm font-semibold text-foreground">
                  {selectedEnv?.display_name || "未绑定"}
                </div>
              </div>
              <div>
                <div className="text-[11px] font-semibold text-muted-foreground">
                  类型
                </div>
                <div className="mt-1 text-sm font-semibold text-foreground">
                  {selectedEnv ? runtimeKindLabel(selectedEnv.kind) : "未设置"}
                </div>
              </div>
              <div>
                <div className="text-[11px] font-semibold text-muted-foreground">
                  状态
                </div>
                <div className="mt-1 text-sm font-semibold text-foreground">
                  {runtimeStatusLabel(selectedEnv?.status)}
                </div>
              </div>
              <div>
                <div className="text-[11px] font-semibold text-muted-foreground">
                  依赖包
                </div>
                <div className="mt-1 text-sm font-semibold text-foreground">
                  {selectedEnv?.package_count ?? 0} 个
                </div>
              </div>
            </div>
          </section>

          <section className="space-y-2">
            <div className="text-xs font-semibold text-muted-foreground">
              路径
            </div>
            <RuntimePathRow label=".env 目录" value={envPath} onCopy={onCopy} />
            <RuntimePathRow
              label="Python"
              value={selectedEnv?.python_executable}
              onCopy={onCopy}
            />
            <RuntimePathRow
              label="登记文件"
              value={registry?.registry_path}
              onCopy={onCopy}
            />
            {copyMessage ? (
              <div className="text-xs text-success">{copyMessage}</div>
            ) : null}
          </section>

          <section className="rounded-2xl border border-border bg-card px-4 py-4">
            <div className="text-xs font-semibold text-muted-foreground">
              材料文件
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {materialFiles.map(([name, exists]) => (
                <div
                  key={name}
                  className="flex items-center justify-between gap-3 rounded-xl border border-border bg-background px-3 py-2"
                >
                  <span className="font-mono text-xs text-foreground">{name}</span>
                  <MaterialState value={exists} />
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-2xl border border-border bg-card px-4 py-4">
            <div className="flex items-center justify-between gap-3">
              <div className="text-xs font-semibold text-muted-foreground">
                依赖包列表
              </div>
              {packages.length > visiblePackages.length ? (
                <div className="text-[11px] text-muted-foreground">
                  先显示 {visiblePackages.length} 个
                </div>
              ) : null}
            </div>
            {visiblePackages.length > 0 ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {visiblePackages.map((pkg) => (
                  <span
                    key={`${pkg.name}-${pkg.version}`}
                    className="rounded-full border border-border bg-background px-2.5 py-1 font-mono text-[11px] text-foreground"
                    title={`${pkg.name} ${pkg.version}`}
                  >
                    {pkg.name}
                    {pkg.version ? ` ${pkg.version}` : ""}
                  </span>
                ))}
              </div>
            ) : (
              <div className="mt-3 rounded-xl border border-dashed border-border bg-background px-3 py-4 text-sm text-muted-foreground">
                暂无可展示的包列表。
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

interface WorkspaceAssetPanelProps {
  scope?: AssetScope;
  files?: WorkspaceFile[];
  sessionId?: string;
  workspaceId?: string;
  workspaceSummary?: TaskWorkspaceSummary | null;
  pendingUploadedFiles?: Array<{ filename: string; file_path?: string }>;
  initialFile?: PreviewFile | null;
  onDeleteFile?: (filename: string) => Promise<boolean>;
  onDeleteFolder?: (folderPath: string) => Promise<boolean>;
  onReadFileContent?: (filename: string) => Promise<string | null>;
  onRefreshWorkspaceFiles?: () => Promise<void>;
  onMoveFile?: (source: string, target: string) => Promise<boolean>;
  onUploadFiles?: (files: File[] | FileList) => Promise<void>;
  onExportMarkdownFile?: (
    filename: string,
    format: "md" | "docx" | "pdf",
  ) => Promise<void>;
  userId?: string;
  onOpenInMainCanvas?: (file: PreviewFile) => void;
  onEditInMainCanvas?: (file: PreviewFile) => void;
  onOpenGlobalResourceInMainCanvas?: (node: GlobalResourceNode) => void;
  onOpenWorkspaceSettings?: () => void;
  surfaceMode?: "workbench" | "navigation";
}

const DEFAULT_NEW_FILE_PATH = "analysis-note.md";
const DEFAULT_CANVAS_CONTENT = '{\n  "nodes": [],\n  "edges": []\n}\n';
const DEFAULT_NEW_FOLDER_PATH = "新建文件夹";

const LazyFilePreviewPanel = lazy(() =>
  import("./preview/FilePreviewPanel").then((module) => ({
    default: module.FilePreviewPanel,
  })),
);

interface AssetHeaderActionProps {
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  testId?: string;
}

function AssetHeaderAction({
  label,
  icon,
  onClick,
  disabled,
  testId,
}: AssetHeaderActionProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          data-testid={testId}
          onClick={onClick}
          className="inline-flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-45"
          aria-label={label}
          title={label}
          disabled={disabled}
        >
          {icon}
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom">{label}</TooltipContent>
    </Tooltip>
  );
}

/** 根据文件类型自动调整后缀 */
const adjustFilePathForType = (currentPath: string, newType: "text" | "canvas" | "data_table" | "knowledge_base" | "knowledge_graph"): string => {
  // 去掉已知后缀，提取 basename
  const stripped = currentPath
    .replace(/\.graph\.db$/i, "")
    .replace(/\.table\.db$/i, "")
    .replace(/\.kb\.db$/i, "")
    .replace(/\.canvas$/i, "")
    .replace(/\.md$/i, "")
    .replace(/\.db$/i, "");
  const base = stripped || "analysis-note";
  switch (newType) {
    case "canvas":
      return `${base}.canvas`;
    case "data_table":
      return `${base}.table.db`;
    case "knowledge_base":
      return `${base}.kb.db`;
    case "knowledge_graph":
      return `${base}.graph.db`;
    default:
      return `${base}.md`;
  }
};
const PANEL_CONTEXT_MENU_WIDTH = 224;
const PANEL_CONTEXT_MENU_HEIGHT = 276;

interface FileOperationResponse {
  success: boolean;
  source?: string;
  target?: string;
}

const buildDataTableCreatePayload = (inputPath: string) => {
  const normalized = normalizeWorkspaceFolderInputPath(inputPath);
  const pathParts = normalized.split("/").filter(Boolean);
  const fileBaseName = pathParts.pop() ?? "untitled";
  const tableName = fileBaseName
    .replace(/\.table\.db$/i, "")
    .replace(/\.db$/i, "") || "untitled";
  const tableId = tableName
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9-]/g, "") || "untitled";

  return {
    name: tableName,
    id: `${tableId}-${Date.now()}`,
    directory: pathParts.join("/"),
    columns: [
      { name: "名称", type: "text", required: true },
      { name: "状态", type: "single_select", options: ["待办", "进行中", "已完成"] },
    ],
  };
};

const getResourceDisplayNameFromPath = (inputPath: string, suffixPattern: RegExp) => {
  const normalized = normalizeWorkspaceFolderInputPath(inputPath);
  const baseName = normalized.split("/").filter(Boolean).pop() ?? normalized;
  return baseName.replace(suffixPattern, "") || "untitled";
};

const buildCreatedResourcePreviewInput = (
  response: FileCreateResponse,
  workspaceId: string,
  isGlobal: boolean,
): WorkspaceFile => ({
  name: response.filename,
  size: response.size,
  mtime: new Date().toISOString(),
  resource_type:
    typeof response.meta?.resource_type === "string"
      ? response.meta.resource_type
      : undefined,
  renderer_hint:
    typeof response.meta?.renderer_hint === "string"
      ? response.meta.renderer_hint
      : undefined,
  meta: {
    ...(response.meta ?? {}),
    ...(isGlobal ? { _globalResource: true } : {}),
    workspace_id: workspaceId,
    relative_path:
      typeof response.meta?.relative_path === "string"
        ? response.meta.relative_path
        : response.filename,
    source:
      typeof response.meta?.source === "string"
        ? response.meta.source
        : isGlobal
          ? "global_workspace_asset"
          : "workspace_asset",
  },
});

interface PanelContextMenuState {
  x: number;
  y: number;
}

const WorkspaceAssetPanelComponent: React.FC<WorkspaceAssetPanelProps> = ({
  scope = "current",
  files: externalFiles = [],
  sessionId,
  workspaceId,
  workspaceSummary,
  pendingUploadedFiles = [],
  initialFile,
  onDeleteFile,
  onDeleteFolder,
  onReadFileContent,
  onRefreshWorkspaceFiles,
  onMoveFile,
  onUploadFiles,
  onExportMarkdownFile,
  userId: _userId,
  onOpenInMainCanvas,
  onEditInMainCanvas,
  onOpenGlobalResourceInMainCanvas,
  onOpenWorkspaceSettings,
  surfaceMode = "workbench",
}) => {
  const { session } = useAuthContext();
  const token = session?.token;
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const optimisticOpenFilesRef = useRef<Set<string>>(new Set());
  const lastInitialFileRef = useRef<string | null>(null);
  const isNavigationMode = surfaceMode === "navigation";
  const isGlobal = scope === "global";

  const [searchQuery, setSearchQuery] = useState<string>("");
  const [openFiles, setOpenFiles] = useState<PreviewFile[]>(
    () => (initialFile ? [initialFile] : []),
  );
  const [activeFileName, setActiveFileName] = useState<string | null>(
    initialFile?.name ?? null,
  );
  const [isUploadingFiles, setIsUploadingFiles] = useState(false);
  const [isRefreshingFiles, setIsRefreshingFiles] = useState(false);
  const isRefreshingFilesRef = useRef(false);

  const [runtimeRegistry, setRuntimeRegistry] =
    useState<WorkspaceRuntimeEnvironmentRegistry | null>(null);
  const [isRuntimeRegistryLoading, setIsRuntimeRegistryLoading] = useState(false);
  const [runtimeRegistryError, setRuntimeRegistryError] = useState<string | null>(null);
  const [isRuntimeDetailsOpen, setIsRuntimeDetailsOpen] = useState(false);
  const [runtimeCopyMessage, setRuntimeCopyMessage] = useState<string | null>(null);

  const loadRuntimeRegistry = useCallback(async () => {
    if (!workspaceId || isGlobal) {
      setRuntimeRegistry(null);
      setRuntimeRegistryError(null);
      return;
    }

    setIsRuntimeRegistryLoading(true);
    try {
      const registry = await getWorkspaceRuntimeEnvironments(workspaceId, {
        inspect: true,
      });
      setRuntimeRegistry(registry);
      setRuntimeRegistryError(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : "运行环境状态读取失败";
      setRuntimeRegistryError(message);
    } finally {
      setIsRuntimeRegistryLoading(false);
    }
  }, [workspaceId, isGlobal]);

  useEffect(() => {
    void loadRuntimeRegistry();
  }, [
    loadRuntimeRegistry,
    workspaceSummary?.runtime_binding?.env_id,
    workspaceSummary?.runtime_binding?.sandbox_mode,
  ]);

  const runtimeBinding = workspaceSummary?.runtime_binding;
  const selectedRuntimeEnv = useMemo(
    () =>
      selectRuntimeEnv(
        runtimeRegistry,
        runtimeBinding?.sandbox_mode === "local" ? runtimeBinding?.env_id : null,
      ),
    [runtimeBinding?.env_id, runtimeBinding?.sandbox_mode, runtimeRegistry],
  );
  const runtimeEnvLabel = useMemo(
    () =>
      runtimeRegistryError
        ? "状态读取失败"
        : formatRuntimeEntryLabel(
            runtimeRegistry,
            selectedRuntimeEnv,
            runtimeBinding?.sandbox_mode,
          ),
    [
      runtimeBinding?.sandbox_mode,
      runtimeRegistry,
      runtimeRegistryError,
      selectedRuntimeEnv,
    ],
  );

  const handleOpenRuntimeDetails = useCallback(() => {
    if (isNavigationMode) {
      onOpenWorkspaceSettings?.();
      return;
    }
    setIsRuntimeDetailsOpen(true);
    setRuntimeCopyMessage(null);
    void loadRuntimeRegistry();
  }, [isNavigationMode, loadRuntimeRegistry, onOpenWorkspaceSettings]);

  const handleCopyRuntimePath = useCallback(async (value: string, label: string) => {
    const result = await writeTextToClipboard(value);
    setRuntimeCopyMessage(result.ok ? `已复制${label}` : "复制失败，请手动选中文本复制");
  }, []);
  const [panelContextMenu, setPanelContextMenu] =
    useState<PanelContextMenuState | null>(null);
  const panelContextMenuRef = useRef<HTMLDivElement | null>(null);
  const [fileClipboardItem, setFileClipboardItem] =
    useState<FileTreeClipboardItem | null>(null);

  const [folderCollapseSignal, setFolderCollapseSignal] = useState(0);
  const [isCreateFileOpen, setIsCreateFileOpen] = useState(false);
  const [newFilePath, setNewFilePath] = useState(DEFAULT_NEW_FILE_PATH);
  const [createFileError, setCreateFileError] = useState<string | null>(null);
  const [isCreatingFile, setIsCreatingFile] = useState(false);
  const [createFileType, setCreateFileType] = useState<"text" | "canvas" | "data_table" | "knowledge_base" | "knowledge_graph">("text");
  const [isCreateFolderOpen, setIsCreateFolderOpen] = useState(false);
  const [newFolderPath, setNewFolderPath] = useState(DEFAULT_NEW_FOLDER_PATH);
  const [createFolderError, setCreateFolderError] = useState<string | null>(null);
  const [isCreatingFolder, setIsCreatingFolder] = useState(false);
  const [historyFile, setHistoryFile] = useState<WorkspaceFile | null>(null);

  const [fileTreeWidth, setFileTreeWidth] = useState(320);
  const [isResizingTree, setIsResizingTree] = useState(false);
  const treeResizeStartX = useRef(0);
  const treeResizeStartWidth = useRef(320);
  const treeResizeContainerRef = useRef<number>(0);

  // Global scope: fetch resources from API
  const [globalResources, setGlobalResources] = useState<GlobalResourceNode[]>([]);
  const [isLoadingGlobalResources, setIsLoadingGlobalResources] = useState(false);
  const [currentResourceTree, setCurrentResourceTree] = useState<GlobalResourceNode[]>([]);
  const [isLoadingCurrentResourceTree, setIsLoadingCurrentResourceTree] = useState(false);

  const fetchCurrentResourceTree = useCallback(async () => {
    if (!workspaceId || isGlobal) {
      setCurrentResourceTree([]);
      return;
    }
    setIsLoadingCurrentResourceTree(true);
    try {
      const res = await apiRequest<{ nodes: GlobalResourceNode[] }>(
        API_ENDPOINTS.WORKSPACE_RESOURCES_TREE(workspaceId),
        { method: "GET" },
      );
      setCurrentResourceTree(res.nodes || []);
    } catch (err) {
      if (import.meta.env.DEV) {
        console.warn("获取当前工作区资源树失败", err);
      }
      setCurrentResourceTree([]);
    } finally {
      setIsLoadingCurrentResourceTree(false);
    }
  }, [workspaceId, isGlobal]);

  const fetchGlobalResources = useCallback(async () => {
    if (!workspaceId || !token) return;
    setIsLoadingGlobalResources(true);
    try {
      const userId = getCurrentUserId();
      const res = await apiRequest<{ nodes: GlobalResourceNode[] }>(
        `${API_ENDPOINTS.GLOBAL_WORKSPACE_TREE(workspaceId)}?user_id=${userId}`,
        { method: "GET", headers: { Authorization: `Bearer ${token}` } },
      );
      setGlobalResources(res.nodes || []);
    } catch (err) {
      if (import.meta.env.DEV) {
        console.warn("获取全局工作区资源树失败", err);
      }
    } finally {
      setIsLoadingGlobalResources(false);
    }
  }, [workspaceId, token]);

  useEffect(() => {
    if (isGlobal) {
      void fetchGlobalResources();
    } else {
      void fetchCurrentResourceTree();
    }
  }, [fetchCurrentResourceTree, fetchGlobalResources, isGlobal]);

  useEffect(() => {
    if (isGlobal) {
      setGlobalResources([]);
      setSearchQuery("");
      setCreateFileError(null);
      setCreateFolderError(null);
    } else {
      setCurrentResourceTree([]);
    }
  }, [workspaceId, isGlobal]);

  // workspaceFiles 变化时同步刷新资源树（上传/删除等操作后）
  const prevFileSignatureRef = useRef("");
  useEffect(() => {
    if (isGlobal || !workspaceId || !externalFiles) return;
    const signature = externalFiles
      .map((f) => `${f.name}:${f.size}:${f.mtime || ""}`)
      .sort()
      .join("|");
    if (signature === prevFileSignatureRef.current) return;
    prevFileSignatureRef.current = signature;
    void fetchCurrentResourceTree();
  }, [externalFiles, workspaceId, isGlobal, fetchCurrentResourceTree]);

  // Build file list based on scope
  const safeFiles = useMemo(() => {
    if (isGlobal) return flattenGlobalResourcesToFiles(globalResources);
    return (externalFiles || []).filter(
      (file) => !isWorkspaceFolderMarkerFile(file.name),
    );
  }, [externalFiles, globalResources, isGlobal]);

  const fileTreeFiles = useMemo(
    () => (isGlobal ? safeFiles : externalFiles || []),
    [externalFiles, isGlobal, safeFiles],
  );
  const globalTreeData = useMemo(
    () => (isGlobal ? globalResourcesToFileTree(globalResources) : undefined),
    [globalResources, isGlobal],
  );
  const currentTreeData = useMemo(
    () => (!isGlobal ? globalResourcesToFileTree(currentResourceTree) : undefined),
    [currentResourceTree, isGlobal],
  );
  const visibleFiles = safeFiles;

  const assetCounts = useMemo(() => {
    if (isGlobal) {
      return countAssetTreeEntries(globalResources);
    }
    if (currentResourceTree.length > 0) {
      return countAssetTreeEntries(currentResourceTree);
    }
    return countWorkspaceAssetEntries(externalFiles || []);
  }, [currentResourceTree, externalFiles, globalResources, isGlobal]);

  const recentFiles = useMemo(() => {
    if (isGlobal) return [];
    return [...visibleFiles]
      .sort((left, right) => {
        const leftTime = Date.parse(left.mtime || "");
        const rightTime = Date.parse(right.mtime || "");
        return (
          (Number.isNaN(rightTime) ? 0 : rightTime) -
          (Number.isNaN(leftTime) ? 0 : leftTime)
        );
      })
      .slice(0, 8);
  }, [visibleFiles, isGlobal]);

  const pendingUploadSummary = useMemo(
    () =>
      pendingUploadedFiles
        .map((item) => item.filename.trim())
        .filter(Boolean)
        .slice(0, 3),
    [pendingUploadedFiles],
  );

  const selectedFile = useMemo(
    () => openFiles.find((file) => file.name === activeFileName) ?? null,
    [activeFileName, openFiles],
  );

  const selectedWorkspaceResourceNode = useMemo(
    () =>
      selectedFile
        ? resolveAssetResourceNodeFromWorkspaceFile(selectedFile)
        : null,
    [selectedFile],
  );

  const selectedFileName = isNavigationMode ? activeFileName : selectedFile?.name;

  // Upload handling
  const handleUploadRequest = useCallback(
    async (incomingFiles: File[] | FileList) => {
      const fileArray = Array.from(incomingFiles);
      if (fileArray.length === 0 || isUploadingFiles) return;

      setIsUploadingFiles(true);
      try {
        if (isGlobal) {
          if (!workspaceId || !token) return;
          for (const f of fileArray) {
            const formData = new FormData();
            formData.append("file", f);
            await apiRequest(
              API_ENDPOINTS.GLOBAL_WORKSPACE_UPLOAD(workspaceId),
              {
                method: "POST",
                headers: { Authorization: `Bearer ${token}` },
                body: formData,
              },
            );
          }
          await fetchGlobalResources();
        } else {
          if (!workspaceId || !onUploadFiles) return;
          await onUploadFiles(fileArray);
        }
      } finally {
        setIsUploadingFiles(false);
      }
    },
    [isGlobal, isUploadingFiles, workspaceId, token, onUploadFiles, fetchGlobalResources],
  );

  const handleFileInputChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const files = event.target.files;
      if (!files || files.length === 0) return;
      void handleUploadRequest(files);
      event.target.value = "";
    },
    [handleUploadRequest],
  );

  const handlePasteCapture = useCallback(
    (event: React.ClipboardEvent<HTMLDivElement>) => {
      const files = extractClipboardFiles(event.clipboardData);
      if (files.length === 0) return;
      event.preventDefault();
      void handleUploadRequest(files);
    },
    [handleUploadRequest],
  );

  const { isDragging, dragProps } = useDragDrop((fileList) => {
    void handleUploadRequest(fileList);
  });

  const buildPreviewFile = useCallback(
    (file: string | WorkspaceFile | PreviewFile): PreviewFile =>
      isGlobal
        ? createGlobalWorkspacePreviewFile(file, workspaceId, token)
        : createWorkspacePreviewFile(file, sessionId, token),
    [isGlobal, sessionId, token, workspaceId],
  );

  const openPreviewFile = useCallback((file: PreviewFile) => {
    setOpenFiles((current) => {
      if (current.some((item) => item.name === file.name)) return current;
      return [...current, file];
    });
    setActiveFileName(file.name);
  }, []);

  const openFileForCurrentSurface = useCallback(
    (file: PreviewFile) => {
      if (isNavigationMode && onOpenInMainCanvas) {
        setActiveFileName(file.name);
        onOpenInMainCanvas(file);
        return;
      }
      openPreviewFile(file);
    },
    [isNavigationMode, onOpenInMainCanvas, openPreviewFile],
  );

  const handleFileSelect = useCallback(
    (file: WorkspaceFile) => {
      setIsRuntimeDetailsOpen(false);
      if (isGlobal) {
        const found = findGlobalResourceNode(globalResources, file.name);
        if (found) {
          const previewFile = buildPreviewFile(file);
          const resourceNode = resolveAssetResourceNodeFromWorkspaceFile(previewFile);
          if (resourceNode && onOpenGlobalResourceInMainCanvas) {
            onOpenGlobalResourceInMainCanvas(found);
          } else {
            openFileForCurrentSurface(previewFile);
          }
        }
        return;
      }
      openFileForCurrentSurface(buildPreviewFile(file));
    },
    [isGlobal, globalResources, onOpenGlobalResourceInMainCanvas, buildPreviewFile, openFileForCurrentSurface],
  );

  const handleDeleteCurrentFile = useCallback(
    async (filename: string): Promise<boolean> => {
      const ok = await onDeleteFile?.(filename);
      if (ok) {
        await fetchCurrentResourceTree();
      }
      return ok ?? false;
    },
    [fetchCurrentResourceTree, onDeleteFile],
  );

  const handleDeleteCurrentFolder = useCallback(
    async (folderPath: string): Promise<boolean> => {
      const ok = await onDeleteFolder?.(folderPath);
      if (ok) {
        await fetchCurrentResourceTree();
      }
      return ok ?? false;
    },
    [fetchCurrentResourceTree, onDeleteFolder],
  );

  const getCopyPath = useCallback(
    (file: WorkspaceFile) => {
      const normalizedPath = normalizeLogicalFilePath(file.name);
      return isGlobal ? `/global/${normalizedPath}` : `/workspace/${normalizedPath}`;
    },
    [isGlobal],
  );

  const getFolderCopyPath = useCallback(
    (folderPath: string) => {
      const normalizedPath = normalizeLogicalFilePath(folderPath);
      return isGlobal ? `/global/${normalizedPath}` : `/workspace/${normalizedPath}`;
    },
    [isGlobal],
  );

  const existingAssetPaths = useMemo(() => {
    const paths = new Set<string>();
    const collectNodes = (nodes: FileTreeNode[]) => {
      for (const node of nodes) {
        paths.add(normalizeLogicalFilePath(node.path));
        if (node.children) collectNodes(node.children);
      }
    };
    if (isGlobal) {
      collectNodes(globalTreeData ?? []);
    } else if (currentTreeData && currentTreeData.length > 0) {
      collectNodes(currentTreeData);
    } else {
      for (const file of fileTreeFiles) {
        paths.add(normalizeLogicalFilePath(file.name));
      }
    }
    return paths;
  }, [currentTreeData, fileTreeFiles, globalTreeData, isGlobal]);

  const buildAvailableCopyTarget = useCallback(
    (targetPath: string) => {
      const normalizedTarget = normalizeLogicalFilePath(targetPath);
      if (!existingAssetPaths.has(normalizedTarget)) {
        return normalizedTarget;
      }

      const slashIndex = normalizedTarget.lastIndexOf("/");
      const directory = slashIndex >= 0 ? normalizedTarget.slice(0, slashIndex) : "";
      const name = slashIndex >= 0 ? normalizedTarget.slice(slashIndex + 1) : normalizedTarget;
      const dotIndex = name.lastIndexOf(".");
      const stem = dotIndex > 0 ? name.slice(0, dotIndex) : name;
      const extension = dotIndex > 0 ? name.slice(dotIndex) : "";

      for (let index = 1; index < 1000; index += 1) {
        const suffix = index === 1 ? " copy" : ` copy ${index}`;
        const candidateName = `${stem}${suffix}${extension}`;
        const candidate = directory ? `${directory}/${candidateName}` : candidateName;
        if (!existingAssetPaths.has(candidate)) {
          return candidate;
        }
      }

      return `${normalizedTarget}-${Date.now()}`;
    },
    [existingAssetPaths],
  );

  const handleCopyFileSystemEntry = useCallback(
    async (source: string, target: string): Promise<boolean> => {
      const normalizedSource = normalizeLogicalFilePath(source);
      const normalizedTarget = buildAvailableCopyTarget(target);
      try {
        if (isGlobal) {
          if (!workspaceId || !token) return false;
          await apiRequest<FileOperationResponse>(
            API_ENDPOINTS.GLOBAL_WORKSPACE_COPY(workspaceId),
            {
              method: "POST",
              headers: { Authorization: `Bearer ${token}` },
              body: { source: normalizedSource, target: normalizedTarget },
            },
          );
          await fetchGlobalResources();
          return true;
        }
        if (!workspaceId) return false;
        await apiRequest<FileOperationResponse>(
          API_ENDPOINTS.WORKSPACE_FILE_COPY(workspaceId),
          {
            method: "POST",
            body: { source: normalizedSource, target: normalizedTarget },
          },
        );
        await onRefreshWorkspaceFiles?.();
        await fetchCurrentResourceTree();
        return true;
      } catch (error) {
        if (import.meta.env.DEV) {
          console.warn("复制文件失败", error);
        }
        return false;
      }
    },
    [
      buildAvailableCopyTarget,
      fetchGlobalResources,
      fetchCurrentResourceTree,
      isGlobal,
      onRefreshWorkspaceFiles,
      token,
      workspaceId,
    ],
  );

  const handleMoveFileSystemEntry = useCallback(
    async (source: string, target: string): Promise<boolean> => {
      const normalizedSource = normalizeLogicalFilePath(source);
      const normalizedTarget = normalizeLogicalFilePath(target);
      if (normalizedSource === normalizedTarget) {
        return true;
      }
      if (isGlobal) {
        if (!workspaceId || !token) return false;
        try {
          await apiRequest<FileOperationResponse>(
            API_ENDPOINTS.GLOBAL_WORKSPACE_MOVE(workspaceId),
            {
              method: "PUT",
              headers: { Authorization: `Bearer ${token}` },
              body: { source: normalizedSource, target: normalizedTarget },
            },
          );
          await fetchGlobalResources();
          return true;
        } catch (error) {
          if (import.meta.env.DEV) {
            console.warn("移动全局工作区文件失败", error);
          }
          return false;
        }
      }
      const ok = await onMoveFile?.(normalizedSource, normalizedTarget);
      if (ok) {
        await fetchCurrentResourceTree();
      }
      return ok ?? false;
    },
    [fetchCurrentResourceTree, fetchGlobalResources, isGlobal, onMoveFile, token, workspaceId],
  );

  const handleOpenFileInMainCanvas = useCallback(
    (file: WorkspaceFile) => {
      onOpenInMainCanvas?.(buildPreviewFile(file));
    },
    [buildPreviewFile, onOpenInMainCanvas],
  );

  const handleEditFileInMainCanvas = useCallback(
    (file: WorkspaceFile) => {
      onEditInMainCanvas?.(buildPreviewFile(file));
    },
    [buildPreviewFile, onEditInMainCanvas],
  );

  const handleCloseOpenFile = useCallback(
    (fileName: string) => {
      const closingIndex = openFiles.findIndex((file) => file.name === fileName);
      const nextFiles = openFiles.filter((file) => file.name !== fileName);
      setOpenFiles(nextFiles);
      if (activeFileName === fileName) {
        const nextActiveFile =
          nextFiles[Math.min(closingIndex, nextFiles.length - 1)] ?? null;
        setActiveFileName(nextActiveFile?.name ?? null);
      }
    },
    [activeFileName, openFiles],
  );

  const handleGlobalDeleteFile = useCallback(
    async (filename: string): Promise<boolean> => {
      if (!workspaceId || !token) return false;
      try {
        await apiRequest(
          API_ENDPOINTS.GLOBAL_WORKSPACE_DELETE(workspaceId, filename),
          {
            method: "DELETE",
            headers: { Authorization: `Bearer ${token}` },
          },
        );
        await fetchGlobalResources();
        return true;
      } catch {
        return false;
      }
    },
    [workspaceId, token, fetchGlobalResources],
  );

  const handleDeleteGlobalFolder = useCallback(
    async (folderPath: string): Promise<boolean> => {
      if (!workspaceId || !token) return false;
      try {
        await apiRequest(
          `${API_ENDPOINTS.GLOBAL_WORKSPACE_DELETE(workspaceId, folderPath)}?recursive=true`,
          {
            method: "DELETE",
            headers: { Authorization: `Bearer ${token}` },
          },
        );
        await fetchGlobalResources();
        return true;
      } catch {
        return false;
      }
    },
    [workspaceId, token, fetchGlobalResources],
  );

  const handleRefreshFiles = useCallback(async () => {
    if (isGlobal) {
      await fetchGlobalResources();
      return;
    }
    if (!onRefreshWorkspaceFiles || isRefreshingFilesRef.current) return;
    isRefreshingFilesRef.current = true;
    setIsRefreshingFiles(true);
    try {
      await onRefreshWorkspaceFiles();
      await fetchCurrentResourceTree();
    } finally {
      isRefreshingFilesRef.current = false;
      setIsRefreshingFiles(false);
    }
  }, [fetchCurrentResourceTree, isGlobal, onRefreshWorkspaceFiles, fetchGlobalResources]);

  const historyRequestHeaders = useMemo<HeadersInit | undefined>(
    () => (isGlobal && token ? { Authorization: `Bearer ${token}` } : undefined),
    [isGlobal, token],
  );

  const handleOpenFileHistory = useCallback((file: WorkspaceFile) => {
    setHistoryFile(file);
  }, []);

  const handleOpenFileHistoryByName = useCallback((fileName: string) => {
    setHistoryFile({ name: fileName, size: 0, mtime: "" });
  }, []);

  const handleHistoryDialogOpenChange = useCallback((open: boolean) => {
    if (!open) {
      setHistoryFile(null);
    }
  }, []);

  const handleHistoryRestored = useCallback(async () => {
    await handleRefreshFiles();
  }, [handleRefreshFiles]);

  useEffect(() => {
    setHistoryFile(null);
  }, [isGlobal, workspaceId]);

  const openCreateFileDialog = useCallback(
    (folderPath?: string) => {
      const normalizedFolderPath = folderPath
        ? normalizeWorkspaceFolderInputPath(folderPath)
        : "";
      setNewFilePath(
        normalizedFolderPath
          ? `${normalizedFolderPath}/`
          : DEFAULT_NEW_FILE_PATH,
      );
      setCreateFileError(null);
      setIsCreateFileOpen(true);
    },
    [],
  );

  const openCreateFolderDialog = useCallback((folderPath?: string) => {
    const normalizedFolderPath = folderPath
      ? normalizeWorkspaceFolderInputPath(folderPath)
      : "";
    setNewFolderPath(
      normalizedFolderPath ? `${normalizedFolderPath}/` : DEFAULT_NEW_FOLDER_PATH,
    );
    setCreateFolderError(null);
    setIsCreateFolderOpen(true);
  }, []);

  const handlePanelContextMenu = useCallback(
    (event: React.MouseEvent<HTMLElement>) => {
      event.preventDefault();
      event.stopPropagation();

      const viewportWidth =
        typeof window === "undefined" ? 1024 : window.innerWidth;
      const viewportHeight =
        typeof window === "undefined" ? 768 : window.innerHeight;
      const rawX = event.clientX;
      const rawY = event.clientY;
      const x = Math.min(
        Math.max(8, rawX),
        Math.max(8, viewportWidth - PANEL_CONTEXT_MENU_WIDTH - 8),
      );
      const y = Math.min(
        Math.max(8, rawY),
        Math.max(8, viewportHeight - PANEL_CONTEXT_MENU_HEIGHT - 8),
      );

      setPanelContextMenu({ x, y });
    },
    [],
  );

  const closePanelContextMenu = useCallback(() => {
    setPanelContextMenu(null);
  }, []);

  const pasteClipboardItemToFolder = useCallback(
    async (targetFolderPath: string) => {
      if (!fileClipboardItem) return;
      const sourceName =
        fileClipboardItem.sourcePath.split("/").filter(Boolean).pop() ??
        fileClipboardItem.sourcePath;
      const normalizedTargetFolder = normalizeWorkspaceFolderInputPath(targetFolderPath);
      const target = normalizedTargetFolder
        ? `${normalizedTargetFolder}/${sourceName}`
        : sourceName;
      const ok =
        fileClipboardItem.action === "cut"
          ? await handleMoveFileSystemEntry(fileClipboardItem.sourcePath, target)
          : await handleCopyFileSystemEntry(fileClipboardItem.sourcePath, target);
      if (!ok) return;
      if (fileClipboardItem.action === "cut") {
        setFileClipboardItem(null);
      }
      await handleRefreshFiles();
      closePanelContextMenu();
    },
    [
      closePanelContextMenu,
      fileClipboardItem,
      handleCopyFileSystemEntry,
      handleMoveFileSystemEntry,
      handleRefreshFiles,
    ],
  );

  useEffect(() => {
    if (!panelContextMenu) {
      return;
    }

    const handlePointerDown = (event: PointerEvent) => {
      if (panelContextMenuRef.current?.contains(event.target as Node)) {
        return;
      }
      setPanelContextMenu(null);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setPanelContextMenu(null);
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [panelContextMenu]);

  // File tree resize
  useEffect(() => {
    if (!isResizingTree) return;
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
    treeResizeContainerRef.current =
      document.querySelector('[data-testid="workspace-asset-panel"]')
        ?.parentElement?.clientWidth || window.innerWidth;

    const handleMouseMove = (e: MouseEvent) => {
      const deltaX = e.clientX - treeResizeStartX.current;
      const containerWidth = treeResizeContainerRef.current;
      const maxWidth = Math.min(600, containerWidth * 0.65);
      const newWidth = Math.min(
        Math.max(260, treeResizeStartWidth.current + deltaX),
        maxWidth,
      );
      setFileTreeWidth(newWidth);
    };

    const handleMouseUp = () => setIsResizingTree(false);

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isResizingTree]);

  const handleTreeResizeStart = useCallback((e: React.MouseEvent) => {
    treeResizeStartX.current = e.clientX;
    treeResizeStartWidth.current = fileTreeWidth;
    setIsResizingTree(true);
  }, [fileTreeWidth]);

  const hasPreview = !isNavigationMode && !!selectedFile;
  const hasEntries = isGlobal
    ? globalResources.length > 0
    : currentResourceTree.length > 0 || fileTreeFiles.length > 0;
  const showRuntimeDetails = !isNavigationMode && isRuntimeDetailsOpen && !isGlobal;
  const showDetailsPanel = !isNavigationMode && (hasEntries || showRuntimeDetails);

  useEffect(() => {
    optimisticOpenFilesRef.current.clear();
    setOpenFiles([]);
    setActiveFileName(null);
    setSearchQuery("");
    setCreateFileError(null);
    setCreateFolderError(null);
    setPanelContextMenu(null);
    setIsRuntimeDetailsOpen(false);
  }, [sessionId]);

  useEffect(() => {
    const visibleFileNames = new Set(safeFiles.map((file) => file.name));
    visibleFileNames.forEach((fileName) => {
      optimisticOpenFilesRef.current.delete(fileName);
    });
    const nextFiles = openFiles.filter(
      (file) =>
        visibleFileNames.has(file.name) ||
        optimisticOpenFilesRef.current.has(file.name),
    );
    if (nextFiles.length === openFiles.length) return;

    setOpenFiles(nextFiles);
    if (activeFileName && isNavigationMode && !visibleFileNames.has(activeFileName)) {
      setActiveFileName(null);
      return;
    }
    if (activeFileName && !isNavigationMode && !nextFiles.some((file) => file.name === activeFileName)) {
      setActiveFileName(nextFiles[0]?.name ?? null);
    }
  }, [activeFileName, isNavigationMode, openFiles, safeFiles]);

  useEffect(() => {
    if (openFiles.length > 0 && !activeFileName) {
      setActiveFileName(openFiles[0].name);
    }
    if (!isNavigationMode && openFiles.length === 0 && activeFileName) {
      setActiveFileName(null);
    }
  }, [activeFileName, isNavigationMode, openFiles]);

  useEffect(() => {
    if (!initialFile?.name) {
      lastInitialFileRef.current = null;
      return;
    }
    if (lastInitialFileRef.current === initialFile.name) return;
    lastInitialFileRef.current = initialFile.name;
    if (isNavigationMode) {
      setActiveFileName(initialFile.name);
      return;
    }
    openPreviewFile(buildPreviewFile(initialFile));
  }, [buildPreviewFile, initialFile, isNavigationMode, openPreviewFile]);

  // Create file
  const handleCreateFile = useCallback(async () => {
    const normalizedPath = normalizeWorkspaceFileInputPath(newFilePath);
    if (!normalizedPath || isCreatingFile) return;

    setIsCreatingFile(true);
    setCreateFileError(null);
    try {
      if (createFileType === "data_table") {
        if (!workspaceId) {
          setCreateFileError("未绑定工作区，无法创建数据表");
          setIsCreatingFile(false);
          return;
        }
        const payload = buildDataTableCreatePayload(normalizedPath);
        if (isGlobal) {
          const response = await apiRequest<{ relative_path: string }>(
            API_ENDPOINTS.GLOBAL_DATA_TABLES(workspaceId),
            {
              method: "POST",
              headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
              body: payload,
            },
          );
          await fetchGlobalResources();
          if (response.relative_path) {
            openFileForCurrentSurface(
              buildPreviewFile({
                name: response.relative_path,
                size: 0,
                mtime: new Date().toISOString(),
                meta: {
                  _globalResource: true,
                  workspace_id: workspaceId,
                  relative_path: response.relative_path,
                  source: "global_workspace_asset",
                },
              }),
            );
          }
        } else {
          await apiRequest(
            API_ENDPOINTS.WORKSPACE_DATA_TABLES(workspaceId),
            {
              method: "POST",
              headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
              body: payload,
            },
          );
          await onRefreshWorkspaceFiles?.();
          await fetchCurrentResourceTree();
        }
        setIsCreateFileOpen(false);
        setNewFilePath(DEFAULT_NEW_FILE_PATH);
        setCreateFileType("text");
      } else if (createFileType === "knowledge_base") {
        const kbName = getResourceDisplayNameFromPath(normalizedPath, /\.kb\.db$/i);
        const kbPath = /\.kb\.db$/i.test(normalizedPath)
          ? normalizedPath
          : `${normalizedPath}.kb.db`;
        if (!workspaceId) {
          setCreateFileError("未绑定工作区，无法创建知识库");
          setIsCreatingFile(false);
          return;
        }
        const response = await apiRequest<FileCreateResponse>(
          isGlobal
            ? API_ENDPOINTS.GLOBAL_CREATE_KNOWLEDGE_DB(workspaceId)
            : API_ENDPOINTS.WORKSPACE_CREATE_KNOWLEDGE_DB(workspaceId),
          {
            method: "POST",
            headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
            body: {
              path: kbPath,
              name: kbName,
              description: "",
            },
          },
        );
        if (isGlobal) {
          await fetchGlobalResources();
        } else {
          await onRefreshWorkspaceFiles?.();
          await fetchCurrentResourceTree();
        }
        optimisticOpenFilesRef.current.add(response.filename);
        openFileForCurrentSurface(
          buildPreviewFile(buildCreatedResourcePreviewInput(response, workspaceId, isGlobal)),
        );
        setIsCreateFileOpen(false);
        setNewFilePath(DEFAULT_NEW_FILE_PATH);
        setCreateFileType("text");
      } else if (createFileType === "knowledge_graph") {
        const kgName = getResourceDisplayNameFromPath(normalizedPath, /\.graph\.db$/i);
        const kgPath = /\.graph\.db$/i.test(normalizedPath)
          ? normalizedPath
          : `${normalizedPath}.graph.db`;
        if (!workspaceId) {
          setCreateFileError("未绑定工作区，无法创建知识图谱");
          setIsCreatingFile(false);
          return;
        }
        const response = await apiRequest<FileCreateResponse>(
          isGlobal
            ? API_ENDPOINTS.GLOBAL_CREATE_GRAPH_DB(workspaceId)
            : API_ENDPOINTS.WORKSPACE_CREATE_GRAPH_DB(workspaceId),
          {
            method: "POST",
            headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
            body: {
              path: kgPath,
              graph_id: kgName,
              name: kgName,
              description: "",
            },
          },
        );
        if (isGlobal) {
          await fetchGlobalResources();
        } else {
          await onRefreshWorkspaceFiles?.();
          await fetchCurrentResourceTree();
        }
        optimisticOpenFilesRef.current.add(response.filename);
        openFileForCurrentSurface(
          buildPreviewFile(buildCreatedResourcePreviewInput(response, workspaceId, isGlobal)),
        );
        setIsCreateFileOpen(false);
        setNewFilePath(DEFAULT_NEW_FILE_PATH);
        setCreateFileType("text");
      } else {
        const filePath =
          createFileType === "canvas" && !normalizedPath.endsWith(".canvas")
            ? `${normalizedPath}.canvas`
            : normalizedPath;
        const initialContent =
          createFileType === "canvas" ? DEFAULT_CANVAS_CONTENT : "";
        if (isGlobal) {
          if (!workspaceId) {
            setCreateFileError("未绑定工作区，无法创建文件");
            setIsCreatingFile(false);
            return;
          }
          await apiRequest(
            API_ENDPOINTS.GLOBAL_WORKSPACE_CREATE(workspaceId),
            {
              method: "POST",
              headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
              body: {
                path: filePath,
                content: initialContent,
                overwrite: false,
              },
            },
          );
          await fetchGlobalResources();
          optimisticOpenFilesRef.current.add(filePath);
          openFileForCurrentSurface(
            buildPreviewFile({
              name: filePath,
              size: initialContent.length,
              mtime: new Date().toISOString(),
              meta: {
                _globalResource: true,
                workspace_id: workspaceId,
                relative_path: filePath,
              },
            }),
          );
          setIsCreateFileOpen(false);
          setNewFilePath(DEFAULT_NEW_FILE_PATH);
          setCreateFileType("text");
          return;
        }
        if (!workspaceId) {
          setCreateFileError("未绑定工作区，无法创建文件");
          setIsCreatingFile(false);
          return;
        }
        const response = await apiRequest<FileCreateResponse>(
          API_ENDPOINTS.WORKSPACE_FILE_CREATE(workspaceId),
          {
            method: "POST",
            body: {
              path: filePath,
              content: initialContent,
              overwrite: false,
            },
          },
        );
        await onRefreshWorkspaceFiles?.();
        await fetchCurrentResourceTree();
        optimisticOpenFilesRef.current.add(response.filename);
        openFileForCurrentSurface(buildPreviewFile(response.filename));
        setIsCreateFileOpen(false);
        setNewFilePath(DEFAULT_NEW_FILE_PATH);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "新建文件失败";
      setCreateFileError(message);
    } finally {
      setIsCreatingFile(false);
    }
  }, [
    buildPreviewFile, isCreatingFile, newFilePath, createFileType, workspaceId,
    token, onRefreshWorkspaceFiles, openFileForCurrentSurface,
    isGlobal, fetchGlobalResources, fetchCurrentResourceTree,
  ]);

  // Create folder
  const handleCreateFolder = useCallback(async () => {
    const normalizedPath = normalizeWorkspaceFolderInputPath(newFolderPath);
    if (!normalizedPath || isCreatingFolder) return;

    if (isGlobal) {
      if (!workspaceId) {
        setCreateFolderError("未绑定工作区，无法创建文件夹");
        setIsCreatingFolder(false);
        return;
      }
      setIsCreatingFolder(true);
      setCreateFolderError(null);
      try {
        await apiRequest(
          API_ENDPOINTS.GLOBAL_WORKSPACE_CREATE(workspaceId),
          {
            method: "POST",
            headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
            body: {
              path: `${normalizedPath}/${WORKSPACE_FOLDER_MARKER_FILENAME}`,
              content: "",
              overwrite: false,
            },
          },
        );
        await fetchGlobalResources();
        setIsCreateFolderOpen(false);
        setNewFolderPath(DEFAULT_NEW_FOLDER_PATH);
      } catch (error) {
        const message = error instanceof Error ? error.message : "新建文件夹失败";
        setCreateFolderError(
          message.includes("文件已存在") ? "文件夹已存在" : message,
        );
      } finally {
        setIsCreatingFolder(false);
      }
      return;
    }

    if (!workspaceId) {
      setCreateFolderError("未绑定工作区，无法创建文件夹");
      return;
    }

    setIsCreatingFolder(true);
    setCreateFolderError(null);
    try {
      await apiRequest<FileCreateResponse>(
        API_ENDPOINTS.WORKSPACE_FILE_CREATE(workspaceId),
        {
          method: "POST",
          body: {
            path: `${normalizedPath}/${WORKSPACE_FOLDER_MARKER_FILENAME}`,
            content: "",
            overwrite: false,
          },
        },
      );
      await onRefreshWorkspaceFiles?.();
      await fetchCurrentResourceTree();
      setIsCreateFolderOpen(false);
      setNewFolderPath(DEFAULT_NEW_FOLDER_PATH);
    } catch (error) {
      const message = error instanceof Error ? error.message : "新建文件夹失败";
      setCreateFolderError(
        message.includes("文件已存在") ? "文件夹已存在" : message,
      );
    } finally {
      setIsCreatingFolder(false);
    }
  }, [
    fetchGlobalResources,
    fetchCurrentResourceTree,
    isCreatingFolder,
    isGlobal,
    newFolderPath,
    onRefreshWorkspaceFiles,
    token,
    workspaceId,
  ]);

  const isRefreshing = isGlobal
    ? isLoadingGlobalResources
    : isRefreshingFiles || isLoadingCurrentResourceTree;

  // Header config based on scope
  const headerTitle = isGlobal ? "全局工作区" : "当前工作区";
  const headerDescription = isGlobal ? "跨工作区共享的资源" : "当前对话的工作区文件";
  const headerIcon = isGlobal
    ? <Globe className="h-4 w-4" />
    : <HardDrive className="h-4 w-4" />;

  const dragOverlayText = isGlobal
    ? "松开鼠标把文件加入全局工作区"
    : "松开鼠标把文件加入当前会话";
  const dragOverlayHint = isGlobal
    ? "全局工作区资源在所有任务工作区间共享。"
    : "文件会先落到工作区，再进入下一条消息的待发送附件。";

  const infoCardTitle = isGlobal
    ? "全局工作区"
    : pendingUploadedFiles.length > 0
      ? `待随下一条消息发送 ${pendingUploadedFiles.length} 个附件`
      : "支持拖拽、粘贴、按钮上传";
  const infoCardDescription = isGlobal
    ? "知识库、数据库、图谱等资源在所有任务工作区间共享。"
    : pendingUploadedFiles.length > 0
      ? pendingUploadSummary.join("、")
      : "上传后进入工作区，右键文件可操作。";

  const emptyIcon = isGlobal
    ? <Globe className="h-8 w-8 stroke-[1.5] opacity-60" />
    : <FileText className="h-8 w-8 stroke-[1.5] opacity-60" />;
  const emptyTitle = isGlobal ? "暂无全局工作区资源" : "暂无工作区文件";
  const emptyDescription = isGlobal
    ? "全局工作区资源在所有任务工作区间共享，可包含知识库、数据库、图谱等。"
    : "Agent 写出的脚本、报告、导出文件和中间产物会显示在这里。";

  return (
    <div
      className="relative flex h-full flex-col bg-background"
      data-testid={isGlobal ? "workspace-global-resources-panel" : "workspace-artifacts-panel"}
      onPasteCapture={handlePasteCapture}
      {...dragProps}
    >
      {isDragging ? (
        <div className="pointer-events-none absolute inset-0 z-20 flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-primary bg-background/90 px-6 text-center backdrop-blur-sm">
          <Upload className="mb-3 h-10 w-10 text-primary" />
          <p className="text-base font-semibold text-foreground">{dragOverlayText}</p>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{dragOverlayHint}</p>
        </div>
      ) : null}

      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        data-testid={isGlobal ? "workspace-global-resources-upload-input" : "workspace-artifacts-upload-input"}
        onChange={handleFileInputChange}
        title="上传文件"
        aria-label="上传文件"
      />

      <div className="flex-1 overflow-hidden flex">
        {/* Left: file tree */}
        <div
          className={cn(
            "flex flex-col overflow-hidden",
            isNavigationMode
              ? "w-full min-w-0"
              : "min-w-[260px] border-r border-border",
            !isNavigationMode && !isResizingTree && "transition-all duration-300",
            !isNavigationMode && !showDetailsPanel && "w-full",
          )}
          data-testid={isGlobal ? "workspace-global-resources-tree-surface" : "workspace-artifacts-tree-surface"}
          onContextMenu={handlePanelContextMenu}
          style={
            !isNavigationMode && showDetailsPanel
              ? { width: `${fileTreeWidth}px` }
              : undefined
          }
        >
          {!isGlobal ? (
            <button
              type="button"
              data-testid="workspace-runtime-env-controlled-entry"
              onClick={handleOpenRuntimeDetails}
              className={cn(
                "flex w-full items-center gap-2 border-b border-border px-3 py-1.5 text-left text-[11px] text-muted-foreground transition-colors hover:bg-muted/40",
                isRuntimeDetailsOpen && "bg-tertiary-container/50 text-on-tertiary-container",
              )}
            >
              <ServerCog className="h-3 w-3 shrink-0" />
              <span className="font-semibold text-foreground">运行环境</span>
              <span className="min-w-0 flex-1 truncate">{runtimeEnvLabel}</span>
              {isRuntimeRegistryLoading ? (
                <Loader2 className="h-3 w-3 shrink-0 animate-spin" />
              ) : null}
            </button>
          ) : null}

          <AssetTreePanelHeader
            title={headerTitle}
            description={headerDescription}
            icon={headerIcon}
            fileCount={assetCounts.fileCount}
            directoryCount={assetCounts.directoryCount}
            fileCountTestId={isGlobal ? "workspace-global-resources-file-count" : "workspace-artifacts-file-count"}
            directoryCountTestId={isGlobal ? "workspace-global-resources-directory-count" : "workspace-artifacts-directory-count"}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            searchPlaceholder={isGlobal ? "搜索全局工作区..." : undefined}
            actions={
              <div className="flex shrink-0 items-center gap-1">
                <AssetHeaderAction
                  label="新建文件"
                  onClick={() => openCreateFileDialog()}
                  disabled={!workspaceId && !isGlobal}
                  icon={<FilePlus className="h-3.5 w-3.5" />}
                />
                <AssetHeaderAction
                  label="新建文件夹"
                  onClick={() => openCreateFolderDialog()}
                  disabled={!workspaceId && !isGlobal}
                  icon={<FolderPlus className="h-3.5 w-3.5" />}
                />
                <AssetHeaderAction
                  label="上传文件"
                  testId={isGlobal ? "workspace-global-resources-upload-button" : "workspace-artifacts-upload-button"}
                  onClick={() => fileInputRef.current?.click()}
                  disabled={(!workspaceId && !isGlobal) || isUploadingFiles}
                  icon={
                    isUploadingFiles ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Upload className="h-3.5 w-3.5" />
                    )
                  }
                />
                <AssetHeaderAction
                  label="刷新"
                  onClick={() => void handleRefreshFiles()}
                  disabled={isRefreshing}
                  icon={
                    <RefreshCw
                      className={cn("h-3.5 w-3.5", isRefreshing && "animate-spin")}
                    />
                  }
                />
                <AssetHeaderAction
                  label="折叠文件夹树"
                  onClick={() => setFolderCollapseSignal((current) => current + 1)}
                  icon={<FolderTree className="h-3.5 w-3.5" />}
                />
              </div>
            }
          />

          {/* Info card */}
          <div className="flex-shrink-0 border-b border-border bg-background px-3 py-2.5">
            <div className="rounded-xl border border-border bg-muted/20 px-3 py-2.5">
              <div className="text-[11px] font-medium text-foreground">
                {infoCardTitle}
              </div>
              <div className="mt-1 truncate text-[11px] leading-5 text-muted-foreground">
                {infoCardDescription}
              </div>
            </div>
          </div>

          {/* File tree area */}
          <div className="flex-1 overflow-y-auto min-h-0">
            {hasEntries ? (
              <FileTreeView
                files={fileTreeFiles}
                treeData={isGlobal ? globalTreeData : currentTreeData}
                workspaceId={workspaceId}
                sessionId={sessionId}
                searchQuery={searchQuery}
                onFileSelect={handleFileSelect}
                selectedFileName={selectedFileName ?? undefined}
                onDeleteFile={isGlobal ? handleGlobalDeleteFile : handleDeleteCurrentFile}
                onDeleteFolder={isGlobal ? handleDeleteGlobalFolder : handleDeleteCurrentFolder}
                onOpenInMainCanvas={handleOpenFileInMainCanvas}
                onEditInMainCanvas={handleEditFileInMainCanvas}
                onOpenFileHistory={handleOpenFileHistory}
                onExportMarkdownFile={isGlobal ? undefined : onExportMarkdownFile}
                onMoveFile={handleMoveFileSystemEntry}
                onRefreshFiles={handleRefreshFiles}
                clipboardItem={fileClipboardItem}
                onClipboardItemChange={setFileClipboardItem}
                onCopyFileSystemEntry={handleCopyFileSystemEntry}
                onPasteComplete={(target) => openFileForCurrentSurface(buildPreviewFile(target))}
                getDownloadUrl={
                  isGlobal && workspaceId && token
                    ? (filename: string) => {
                        return API_ENDPOINTS.GLOBAL_WORKSPACE_DOWNLOAD(workspaceId, filename);
                      }
                    : undefined
                }
                getCopyPath={getCopyPath}
                getFolderCopyPath={getFolderCopyPath}
                collapseAllSignal={folderCollapseSignal}
                expandFirstLevel={true}
                onOpenFileCreate={openCreateFileDialog}
                onOpenFolderCreate={openCreateFolderDialog}
              />
            ) : (
              <div className="flex min-h-0 flex-1 flex-col items-center justify-center px-6 text-center text-muted-foreground/60">
                <div className="mb-3 rounded-full bg-muted/30 p-4">{emptyIcon}</div>
                <div className="space-y-1.5">
                  <p className="text-sm font-medium text-foreground/80">{emptyTitle}</p>
                  <p className="text-xs leading-5 text-muted-foreground">{emptyDescription}</p>
                </div>
              </div>
            )}
          </div>
        </div>

        {panelContextMenu ? (
          <div
            ref={panelContextMenuRef}
            role="menu"
            data-testid={isGlobal ? "workspace-global-resources-root-menu" : "workspace-artifacts-root-menu"}
            className="fixed z-[80] w-56 overflow-hidden rounded-xl border border-border bg-background p-1 text-sm text-foreground shadow-xl"
            style={{ left: `${panelContextMenu.x}px`, top: `${panelContextMenu.y}px` }}
          >
            <div className="border-b border-border px-2 py-2">
              <div className="truncate text-xs font-semibold text-foreground">
                {headerTitle}
              </div>
              <div className="mt-0.5 truncate text-[11px] text-muted-foreground">
                根目录
              </div>
            </div>
            <button
              type="button"
              role="menuitem"
              className="mt-1 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
              onClick={() => {
                openCreateFileDialog();
                closePanelContextMenu();
              }}
              disabled={!workspaceId && !isGlobal}
            >
              <FilePlus className="h-3.5 w-3.5 text-muted-foreground" />
              新建文件
            </button>
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
              onClick={() => {
                openCreateFolderDialog();
                closePanelContextMenu();
              }}
              disabled={!workspaceId && !isGlobal}
            >
              <FolderPlus className="h-3.5 w-3.5 text-muted-foreground" />
              新建文件夹
            </button>
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
              onClick={() => {
                fileInputRef.current?.click();
                closePanelContextMenu();
              }}
              disabled={((!workspaceId && !isGlobal) || isUploadingFiles)}
            >
              {isUploadingFiles ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
              ) : (
                <Upload className="h-3.5 w-3.5 text-muted-foreground" />
              )}
              上传文件
            </button>
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
              disabled={!fileClipboardItem}
              onClick={() => void pasteClipboardItemToFolder("")}
            >
              <Clipboard className="h-3.5 w-3.5 text-muted-foreground" />
              粘贴到根目录
            </button>
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
              onClick={() => {
                void handleRefreshFiles();
                closePanelContextMenu();
              }}
              disabled={isRefreshing}
            >
              <RefreshCw className={`h-3.5 w-3.5 text-muted-foreground ${isRefreshing ? "animate-spin" : ""}`} />
              刷新
            </button>
          </div>
        ) : null}

        {/* Resize handle */}
        {showDetailsPanel ? (
          <div
            className="relative z-10 w-[3px] cursor-col-resize hover:bg-primary/20 active:bg-primary/40 transition-colors"
            onMouseDown={handleTreeResizeStart}
            title="拖拽调整宽度"
          >
            <div className="absolute left-0 top-0 bottom-0 w-[1px] bg-border" />
          </div>
        ) : null}

        {/* Right: preview panel */}
        {showDetailsPanel ? (
          <div className="flex-1 overflow-hidden animate-in slide-in-from-right duration-200 flex flex-col bg-background">
            {showRuntimeDetails ? (
              <RuntimeEnvControlledPreview
                registry={runtimeRegistry}
                selectedEnv={selectedRuntimeEnv}
                isLoading={isRuntimeRegistryLoading}
                error={runtimeRegistryError}
                copyMessage={runtimeCopyMessage}
                onRefresh={() => void loadRuntimeRegistry()}
                onCopy={handleCopyRuntimePath}
                onManage={onOpenWorkspaceSettings}
              />
            ) : hasPreview ? (
              <>
                <div className="flex min-h-10 items-end gap-1 overflow-x-auto border-b border-border bg-muted/20 px-2 pt-2">
                  {openFiles.map((file) => {
                    const active = file.name === selectedFile.name;
                    return (
                      <div
                        key={file.name}
                        className={`group flex max-w-[220px] items-center gap-1 rounded-t-xl border px-2 py-1.5 text-[11px] transition-colors ${
                          active
                            ? "border-border border-b-background bg-background text-foreground shadow-sm"
                            : "border-transparent bg-transparent text-muted-foreground hover:bg-background/70 hover:text-foreground"
                        }`}
                        title={file.name}
                      >
                        <button
                          type="button"
                          onClick={() => setActiveFileName(file.name)}
                          className="flex min-w-0 flex-1 items-center gap-2 rounded px-1 py-0.5 text-left"
                        >
                          <FileText className="h-3.5 w-3.5 shrink-0" />
                          <span className="truncate font-mono">{file.name}</span>
                        </button>
                        <button
                          type="button"
                          className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-muted-foreground opacity-60 transition-colors hover:bg-muted hover:text-foreground group-hover:opacity-100"
                          title="关闭文件"
                          onClick={(event) => {
                            event.stopPropagation();
                            handleCloseOpenFile(file.name);
                          }}
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </div>
                    );
                  })}
                </div>

                <div className="border-b border-border bg-background px-3 py-2">
                  <div className="min-w-0">
                    <div
                      className="truncate text-xs font-mono text-foreground"
                      title={selectedFile.name}
                    >
                      {isGlobal ? "global" : "workspace"} / {selectedFile.name}
                    </div>
                    <div className="mt-0.5 text-[11px] text-muted-foreground">
                      已打开 {openFiles.length} 个文件
                    </div>
                  </div>
                </div>

                <div className="min-h-0 flex-1 flex flex-col overflow-hidden">
                  {(() => {
                    if (selectedWorkspaceResourceNode) {
                      const preview = renderAssetResourcePreview({
                        node: selectedWorkspaceResourceNode,
                        sessionId,
                        workspaceId,
                        onRefresh: onRefreshWorkspaceFiles ?? fetchGlobalResources,
                      });
                      if (preview) return preview;
                    }
                    return (
                      <Suspense
                        fallback={
                          <div className="flex h-full min-h-0 items-center justify-center px-6 text-sm text-muted-foreground">
                            正在加载文件预览...
                          </div>
                        }
                      >
                        <LazyFilePreviewPanel
                          file={selectedFile}
                          token={token}
                          sessionId={sessionId}
                          workspaceFiles={safeFiles}
                          onReadFileContent={onReadFileContent}
                          workspaceId={workspaceId}
                          onOpenWorkspaceFile={(fileName) =>
                            openPreviewFile(buildPreviewFile(fileName))
                          }
                          onOpenPreviewFile={openFileForCurrentSurface}
                          onEditFile={(file) => onEditInMainCanvas?.(file)}
                          onOpenFileHistory={handleOpenFileHistoryByName}
                        />
                      </Suspense>
                    );
                  })()}
                </div>
              </>
            ) : (
              <div className="flex h-full min-h-0 flex-col">
                <div className="border-b border-border px-4 py-3">
                  <div className="text-sm font-semibold text-foreground">文件浏览</div>
                  <div className="mt-1 text-xs leading-5 text-muted-foreground">
                    从左侧目录树选择文件后，这里会显示预览；未选中时先展示最近更新的文件，避免出现大片空白。
                  </div>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
                  <div className="rounded-2xl border border-border bg-muted/10 px-4 py-4">
                    <div className="text-[11px] font-medium text-muted-foreground">最近更新</div>
                    <div className="mt-3 space-y-2">
                      {recentFiles.map((file) => (
                        <button
                          key={file.name}
                          type="button"
                          onClick={() => handleFileSelect(file)}
                          className="flex w-full items-center justify-between gap-3 rounded-xl border border-border bg-background px-3 py-3 text-left transition-colors hover:border-primary/30 hover:bg-primary/5"
                        >
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium text-foreground">
                              {file.name}
                            </div>
                            <div className="mt-1 text-[11px] text-muted-foreground">
                              {file.mtime
                                ? `更新时间：${new Date(file.mtime).toLocaleString("zh-CN", { hour12: false })}`
                                : "时间未知"}
                            </div>
                          </div>
                          <span className="text-[11px] text-muted-foreground">点击预览</span>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        ) : null}
      </div>

      <Suspense fallback={null}>
        <LazyFileHistoryDialog
          open={Boolean(historyFile)}
          onOpenChange={handleHistoryDialogOpenChange}
          scope={isGlobal ? "global" : "workspace"}
          workspaceId={workspaceId}
          file={historyFile}
          headers={historyRequestHeaders}
          onRestored={handleHistoryRestored}
        />
      </Suspense>

      {/* Create file dialog */}
      <Dialog
        open={isCreateFileOpen}
        onOpenChange={(open) => {
          setIsCreateFileOpen(open);
          if (!open) setCreateFileError(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>新建文件</DialogTitle>
            <DialogDescription>
              {isGlobal
                ? "在全局工作区中创建一个新文件或数据表。"
                : "在工作区中创建一个新文件或资源。"}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="ws-new-file-type">文件类型</Label>
              <select
                id="ws-new-file-type"
                value={createFileType}
                onChange={(e) => {
                  const newType = e.target.value as "text" | "canvas" | "data_table" | "knowledge_base" | "knowledge_graph";
                  setCreateFileType(newType);
                  setNewFilePath((prev) => adjustFilePathForType(prev, newType));
                  setCreateFileError(null);
                }}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary"
              >
                <option value="text">普通文件</option>
                <option value="canvas">Canvas (.canvas)</option>
                <option value="data_table">多维表格 (.table.db)</option>
                <option value="knowledge_base">知识库 (.kb.db)</option>
                <option value="knowledge_graph">知识图谱 (.graph.db)</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-file-path">
                {createFileType === "data_table"
                  ? "数据表名称"
                  : createFileType === "canvas"
                    ? "Canvas 路径"
                  : createFileType === "knowledge_base"
                    ? "知识库名称"
                    : createFileType === "knowledge_graph"
                      ? "知识图谱名称"
                      : "文件路径"}
              </Label>
              <Input
                id="new-file-path"
                value={newFilePath}
                onChange={(event) => {
                  setNewFilePath(event.target.value);
                  setCreateFileError(null);
                }}
                placeholder={
                  createFileType === "data_table"
                    ? "销售跟踪"
                    : createFileType === "canvas"
                      ? "research/views/research.canvas"
                    : createFileType === "knowledge_base"
                      ? "产品文档库"
                      : createFileType === "knowledge_graph"
                        ? "产品实体图谱"
                        : "reports/analysis-note.md"
                }
              />
              <p className="text-xs leading-5 text-muted-foreground">
                {createFileType === "data_table"
                  ? "输入名称后会自动创建 .table.db 文件。"
                  : createFileType === "canvas"
                    ? "可以输入相对路径、/workspace 或 /global 路径，也可以粘贴 AIASys 文件链接。未带 .canvas 后缀时会自动补齐。"
                  : createFileType === "knowledge_base"
                    ? "创建后可在知识库管理中查看和上传文档。"
                  : createFileType === "knowledge_graph"
                    ? "创建后可在知识图谱管理中导入实体和关系。"
                  : isNavigationMode
                        ? "可以输入相对路径、/workspace 或 /global 路径，也可以粘贴 AIASys 文件链接。文件创建后会在中间编辑区打开。"
                        : "可以输入相对路径、/workspace 或 /global 路径，也可以粘贴 AIASys 文件链接。文件创建后会在右侧标签页打开。"}
              </p>
            </div>
            {createFileError ? (
              <div className="rounded-md border border-error/20 bg-error-container px-3 py-2 text-xs text-error">
                {createFileError}
              </div>
            ) : null}
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setIsCreateFileOpen(false)}
              disabled={isCreatingFile}
            >
              取消
            </Button>
            <Button
              type="button"
              onClick={() => void handleCreateFile()}
              disabled={isCreatingFile || !newFilePath.trim()}
            >
              {isCreatingFile ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : null}
              创建并打开
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create folder dialog */}
      <Dialog
        open={isCreateFolderOpen}
        onOpenChange={(open) => {
          setIsCreateFolderOpen(open);
          if (!open) setCreateFolderError(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>新建文件夹</DialogTitle>
            <DialogDescription>
              {isGlobal
                ? "在全局工作区中创建一个新文件夹。"
                : "在工作区中创建一个新文件夹。"}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="new-folder-path">文件夹路径</Label>
              <Input
                id="new-folder-path"
                value={newFolderPath}
                onChange={(event) => {
                  setNewFolderPath(event.target.value);
                  setCreateFolderError(null);
                }}
                placeholder="reports/2026"
              />
              <p className="text-xs leading-5 text-muted-foreground">
                可以输入相对路径、/workspace 或 /global 路径，也可以粘贴 AIASys 文件链接。空文件夹会用一个内部标记文件保留。
              </p>
            </div>
            {createFolderError ? (
              <div className="rounded-md border border-error/20 bg-error-container px-3 py-2 text-xs text-error">
                {createFolderError}
              </div>
            ) : null}
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setIsCreateFolderOpen(false)}
              disabled={isCreatingFolder}
            >
              取消
            </Button>
            <Button
              type="button"
              onClick={() => void handleCreateFolder()}
              disabled={isCreatingFolder || !newFolderPath.trim()}
            >
              {isCreatingFolder ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : null}
              创建文件夹
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export const WorkspaceAssetPanel = React.memo(WorkspaceAssetPanelComponent);
