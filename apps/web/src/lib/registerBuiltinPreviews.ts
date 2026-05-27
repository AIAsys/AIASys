/**
 * 内置预览组件注册
 *
 * 在应用启动时调用一次，将所有内置的资源预览组件注册到 ExtensionRegistry。
 * 外部扩展可在此之后追加注册新的预览类型。
 */

import { lazy } from "react";
import { extensionRegistry } from "./extensionRegistry";

const LazyKnowledgeBasePreviewPanel = lazy(() =>
  import("@/components/layout/WorkspaceSidebar/KnowledgeBasePreviewPanel").then(
    (module) => ({ default: module.KnowledgeBasePreviewPanel }),
  ),
);

const LazyDatabasePreviewPanel = lazy(() =>
  import("@/components/layout/WorkspaceSidebar/DatabasePreviewPanel").then(
    (module) => ({ default: module.DatabasePreviewPanel }),
  ),
);

const LazyGraphPreviewPanel = lazy(() =>
  import("@/components/layout/WorkspaceSidebar/GraphPreviewPanel").then(
    (module) => ({ default: module.GraphPreviewPanel }),
  ),
);

const LazyMemoryPreviewPanel = lazy(() =>
  import("@/components/layout/WorkspaceSidebar/preview/MemoryPreviewPanel").then(
    (module) => ({ default: module.MemoryPreviewPanel }),
  ),
);

const LazyDataTablePreviewPanel = lazy(() =>
  import("@/components/layout/WorkspaceSidebar/DataTablePreviewPanel").then(
    (module) => ({ default: module.DataTablePreviewPanel }),
  ),
);

let _initialized = false;

export function ensureBuiltinPreviewsRegistered(): void {
  if (_initialized) return;
  _initialized = true;

  extensionRegistry.registerPreview("knowledge", LazyKnowledgeBasePreviewPanel, "知识库");
  extensionRegistry.registerPreview("database", LazyDatabasePreviewPanel, "数据库");
  extensionRegistry.registerPreview("graph", LazyGraphPreviewPanel, "知识图谱");
  extensionRegistry.registerPreview("memory", LazyMemoryPreviewPanel, "记忆");
  extensionRegistry.registerPreview("data_table", LazyDataTablePreviewPanel, "数据表");
}
