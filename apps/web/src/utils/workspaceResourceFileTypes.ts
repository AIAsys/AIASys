export type WorkspaceResourceFileType = "knowledge" | "database" | "graph" | "memory" | "data_table";

export interface WorkspaceResourceFileLike {
  name: string;
  resource_type?: string;
  schema_kind?: string;
  preview_kind?: string;
  renderer_hint?: string;
  meta?: Record<string, unknown>;
}

export function normalizeWorkspaceResourcePath(path: string): string {
  return path.replace(/\\/g, "/").replace(/^\/+/, "").replace(/\/+$/, "").trim();
}

export function getWorkspaceResourceBaseName(path: string): string {
  const normalizedPath = normalizeWorkspaceResourcePath(path);
  return normalizedPath.split("/").filter(Boolean).pop() ?? normalizedPath;
}

function getStringValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function asWorkspaceResourceFileType(value: unknown): WorkspaceResourceFileType | null {
  if (value === "knowledge" || value === "database" || value === "graph" || value === "memory" || value === "data_table") {
    return value;
  }
  return null;
}

function inferFromHints(
  previewKind?: string,
  schemaKind?: string,
  rendererHint?: string,
): WorkspaceResourceFileType | null {
  const hints = [previewKind, schemaKind, rendererHint]
    .map((item) => item?.toLowerCase().trim())
    .filter((item): item is string => Boolean(item));

  if (
    hints.some(
      (hint) =>
        hint === "knowledge_base" ||
        hint === "knowledge_base_preview" ||
        hint.includes("knowledge_base") ||
        hint.includes("knowledge-base"),
    )
  ) {
    return "knowledge";
  }

  if (
    hints.some(
      (hint) =>
        hint === "knowledge_graph" ||
        hint === "knowledge_graph_preview" ||
        hint.includes("knowledge_graph") ||
        hint.includes("knowledge-graph"),
    )
  ) {
    return "graph";
  }

  if (
    hints.some(
      (hint) =>
        hint === "database" ||
        hint === "database_preview" ||
        hint.includes("database") ||
        hint.includes("duckdb") ||
        hint.includes("sqlite"),
    )
  ) {
    return "database";
  }

  return null;
}

function hasPathSegment(pathSegments: string[], values: string[]) {
  return pathSegments.some((segment) => values.includes(segment));
}

function isMemoryFile(baseName: string, pathSegments: string[]): boolean {
  const aiasysIndex = pathSegments.indexOf(".aiasys");
  const isAiasysMemoryPath =
    aiasysIndex >= 0 &&
    (pathSegments[aiasysIndex + 1] === "memory" ||
      pathSegments[aiasysIndex + 1] === ".memory");
  const isTopLevelMemoryPath =
    pathSegments[0] === "memory" || pathSegments[0] === ".memory";

  if ((isAiasysMemoryPath || isTopLevelMemoryPath) && /\.(md|jsonl)$/i.test(baseName)) {
    return true;
  }

  if (
    hasPathSegment(pathSegments, [
      "rollout_summaries",
      "rollout-summaries",
    ]) &&
    /\.(md|jsonl)$/i.test(baseName)
  ) {
    return true;
  }

  return [
    "memory.md",
    "memory_summary.md",
    "memory-summary.md",
    "raw_memories.md",
    "raw-memories.md",
    "workspace_memory.md",
    "workspace-memory.md",
  ].includes(baseName);
}

export function isKnowledgeBaseDirectory(path: string): boolean {
  const normalizedPath = normalizeWorkspaceResourcePath(path).toLowerCase();
  const segments = normalizedPath.split("/").filter(Boolean);
  const baseName = getWorkspaceResourceBaseName(normalizedPath);
  return (
    hasPathSegment(segments, [
      "knowledge",
      "knowledge-base",
      "knowledge-bases",
      "knowledge_base",
      "knowledge_bases",
      "kb",
      "知识库",
    ]) ||
    /(^|[._-])(knowledge|kb|knowledge-base|knowledge_base)([._-]|$)/i.test(
      baseName,
    )
  );
}

export function inferWorkspaceResourceFileType(
  file: WorkspaceResourceFileLike,
  options?: { isDirectory?: boolean },
): WorkspaceResourceFileType | null {
  const meta = file.meta ?? {};
  const explicitType =
    asWorkspaceResourceFileType(file.resource_type) ||
    asWorkspaceResourceFileType(meta.resource_type);
  if (explicitType) {
    return explicitType;
  }

  const hintType = inferFromHints(
    getStringValue(file.preview_kind || meta.preview_kind),
    getStringValue(file.schema_kind || meta.schema_kind),
    getStringValue(file.renderer_hint || meta.renderer_hint),
  );
  if (hintType) {
    return hintType;
  }

  const normalizedPath = normalizeWorkspaceResourcePath(file.name);
  const baseName = getWorkspaceResourceBaseName(normalizedPath).toLowerCase();
  const pathSegments = normalizedPath.toLowerCase().split("/").filter(Boolean);

  if (options?.isDirectory) {
    return isKnowledgeBaseDirectory(normalizedPath) ? "knowledge" : null;
  }

  if (isMemoryFile(baseName, pathSegments)) {
    return "memory";
  }

  if (baseName.endsWith(".kg")) {
    return "graph";
  }

  if (/\.(db|sqlite|sqlite3|duckdb)$/i.test(baseName)) {
    // 数据表：文件名包含 .table. 后缀
    if (/[._-]table\.(db|sqlite|sqlite3|duckdb)$/i.test(baseName)) {
      return "data_table";
    }

    if (
      hasPathSegment(pathSegments, [
        "graphs",
        "graph",
        "knowledge-graphs",
        "knowledge_graphs",
      ]) ||
      /(^|[._-])(graph|kg|knowledge-graph|knowledge_graph)([._-]|$)/i.test(
        baseName,
      )
    ) {
      return "graph";
    }

    if (isKnowledgeBaseDirectory(normalizedPath)) {
      return "knowledge";
    }

    return "database";
  }

  return null;
}
