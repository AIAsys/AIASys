export type PreviewFileType =
  | "image"
  | "csv"
  | "xlsx"
  | "word"
  | "presentation"
  | "code"
  | "notebook"
  | "chart"
  | "pdf"
  | "markdown"
  | "canvas"
  | "database"
  | "video"
  | "audio"
  | "html"
  | "unknown";

export type WorkspaceRenderableFileType =
  | "image"
  | "csv"
  | "echarts"
  | "pdf"
  | "markdown"
  | "word"
  | "presentation";

export interface PreviewFile {
  name: string;
  url: string;
  downloadUrl?: string;
  size?: number;
  mtime?: string;
  absolute_path?: string | null;
  resource_type?: "knowledge" | "database" | "graph" | string;
  schema_kind?: string;
  preview_kind?: string;
  renderer_hint?: string;
  meta?: Record<string, unknown>;
  type: PreviewFileType;
}

type PreviewCategory = "analysis" | "report" | "canvas" | "asset";

interface FilePreviewDefinition {
  type: PreviewFileType;
  label: string;
  category: PreviewCategory;
  extensions?: readonly string[];
  filenamePatterns?: readonly RegExp[];
  declaredTypes?: readonly string[];
  workspaceType?: WorkspaceRenderableFileType;
  readsTextContent?: boolean;
  prefersInlineResponse?: boolean;
}

const FILE_PREVIEW_DEFINITIONS = [
  {
    type: "chart",
    label: "图表",
    category: "analysis",
    filenamePatterns: [/\.chart\.echarts\.json$/i, /\.echarts\.json$/i],
    declaredTypes: ["echarts", "chart"],
    workspaceType: "echarts",
    readsTextContent: true,
  },
  {
    type: "image",
    label: "图片",
    category: "report",
    extensions: ["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp"],
    declaredTypes: ["image"],
    workspaceType: "image",
  },
  {
    type: "csv",
    label: "CSV",
    category: "analysis",
    extensions: ["csv"],
    declaredTypes: ["csv", "text/csv"],
    workspaceType: "csv",
  },
  {
    type: "xlsx",
    label: "表格",
    category: "analysis",
    extensions: ["xlsx", "xls", "xlsb"],
    declaredTypes: [
      "xlsx",
      "xls",
      "xlsb",
      "spreadsheet",
      "excel",
      "application/vnd.ms-excel",
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ],
  },
  {
    type: "word",
    label: "Word",
    category: "report",
    extensions: ["docx", "doc"],
    declaredTypes: [
      "word",
      "doc",
      "docx",
      "application/msword",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ],
    workspaceType: "word",
  },
  {
    type: "presentation",
    label: "PPT",
    category: "report",
    extensions: ["pptx", "ppt"],
    declaredTypes: [
      "presentation",
      "powerpoint",
      "ppt",
      "pptx",
      "application/vnd.ms-powerpoint",
      "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ],
    workspaceType: "presentation",
  },
  {
    type: "pdf",
    label: "PDF",
    category: "report",
    extensions: ["pdf"],
    declaredTypes: ["pdf", "application/pdf"],
    workspaceType: "pdf",
    prefersInlineResponse: true,
  },
  {
    type: "markdown",
    label: "Markdown",
    category: "report",
    extensions: ["md", "markdown"],
    declaredTypes: ["markdown", "md", "text/markdown"],
    workspaceType: "markdown",
    readsTextContent: true,
  },
  {
    type: "notebook",
    label: "Notebook",
    category: "analysis",
    extensions: ["ipynb"],
    readsTextContent: true,
  },
  {
    type: "canvas",
    label: "画布",
    category: "canvas",
    extensions: ["canvas"],
    readsTextContent: true,
  },
  {
    type: "database",
    label: "数据库",
    category: "analysis",
    extensions: ["db", "sqlite", "sqlite3", "duckdb"],
    declaredTypes: ["database", "sqlite", "duckdb"],
  },
  {
    type: "video",
    label: "视频",
    category: "asset",
    extensions: ["mp4", "webm", "ogg", "mov", "mkv", "avi"],
    declaredTypes: [
      "video",
      "video/mp4",
      "video/webm",
      "video/ogg",
      "video/quicktime",
    ],
  },
  {
    type: "audio",
    label: "音频",
    category: "asset",
    extensions: ["mp3", "wav", "ogg", "aac", "flac", "m4a", "wma"],
    declaredTypes: [
      "audio",
      "audio/mpeg",
      "audio/wav",
      "audio/ogg",
      "audio/aac",
      "audio/flac",
      "audio/mp4",
    ],
  },
  {
    type: "html",
    label: "HTML",
    category: "asset",
    extensions: ["html", "htm"],
    declaredTypes: ["html", "text/html"],
    readsTextContent: true,
  },
  {
    type: "code",
    label: "代码",
    category: "asset",
    extensions: [
      "py",
      "js",
      "ts",
      "tsx",
      "jsx",
      "css",
      "json",
      "txt",
      "yml",
      "yaml",
      "xml",
      "sql",
      "sh",
      "bat",
      "log",
      "env",
      "toml",
      "ini",
      "gitignore",
    ],
    readsTextContent: true,
  },
] as const satisfies readonly FilePreviewDefinition[];

const PREVIEW_DEFINITIONS: readonly FilePreviewDefinition[] =
  FILE_PREVIEW_DEFINITIONS;

const UNKNOWN_PREVIEW_DEFINITION: FilePreviewDefinition = {
  type: "unknown",
  label: "文件",
  category: "asset",
};

const CATEGORY_LABELS: Record<PreviewCategory, string> = {
  analysis: "数据",
  report: "文档",
  canvas: "画布",
  asset: "文件",
};

const SUPPORTED_PREVIEW_HINT =
  "支持 PDF / Word / PPT / 图片 / CSV / Excel / Notebook / 图表 / 工作区视图 / 代码 / 文本";

function normalizeLookupValue(value?: string | null) {
  return (value || "").trim().toLowerCase();
}

function stripQueryAndHash(value: string) {
  return value.split("?")[0]?.split("#")[0] ?? value;
}

function getFileExtension(fileName: string) {
  const normalizedName = stripQueryAndHash(normalizeLookupValue(fileName));
  const baseName =
    normalizedName.split("/").filter(Boolean).pop() ?? normalizedName;
  const dotIndex = baseName.lastIndexOf(".");
  return dotIndex >= 0 ? baseName.slice(dotIndex + 1) : "";
}

function findPreviewDefinition(type: PreviewFileType) {
  return (
    PREVIEW_DEFINITIONS.find((definition) => definition.type === type) ??
    UNKNOWN_PREVIEW_DEFINITION
  );
}

function findPreviewDefinitionByDeclaredType(declaredType?: string | null) {
  const normalizedType = normalizeLookupValue(declaredType);
  if (!normalizedType) {
    return undefined;
  }

  return PREVIEW_DEFINITIONS.find((definition) =>
    definition.declaredTypes?.includes(normalizedType),
  );
}

export function getPreviewType(fileName: string): PreviewFileType {
  const normalizedName = stripQueryAndHash(normalizeLookupValue(fileName));
  const patternMatch = PREVIEW_DEFINITIONS.find((definition) =>
    definition.filenamePatterns?.some((pattern) => pattern.test(normalizedName)),
  );

  if (patternMatch) {
    return patternMatch.type;
  }

  const extension = getFileExtension(normalizedName);
  const extensionMatch = PREVIEW_DEFINITIONS.find((definition) =>
    definition.extensions?.includes(extension),
  );

  return extensionMatch?.type ?? "unknown";
}

export function inferPreviewType(
  fileName: string,
  declaredType?: string | null,
): PreviewFileType {
  return (
    findPreviewDefinitionByDeclaredType(declaredType)?.type ??
    getPreviewType(fileName)
  );
}

export function getPreviewTypeLabel(type: PreviewFileType) {
  return findPreviewDefinition(type).label;
}

export function getPreviewCategoryLabel(type: PreviewFileType) {
  return CATEGORY_LABELS[findPreviewDefinition(type).category];
}

export function shouldReadPreviewTextContent(type?: PreviewFileType) {
  if (!type) {
    return false;
  }
  return findPreviewDefinition(type).readsTextContent === true;
}

export function getSupportedPreviewHint() {
  return SUPPORTED_PREVIEW_HINT;
}

export function getPreviewUrlOptions(type: PreviewFileType): {
  disposition: "attachment" | "inline";
  preferDirectBackend: boolean;
} {
  const prefersInlineResponse =
    findPreviewDefinition(type).prefersInlineResponse === true;

  return {
    disposition: prefersInlineResponse ? "inline" : "attachment",
    preferDirectBackend: prefersInlineResponse,
  };
}

export function inferWorkspaceRenderableFileType(
  path: string,
  declaredType?: string,
): WorkspaceRenderableFileType | null {
  const typeMatch = findPreviewDefinitionByDeclaredType(declaredType);

  if (typeMatch?.workspaceType) {
    return typeMatch.workspaceType;
  }

  const previewType = getPreviewType(path);
  return findPreviewDefinition(previewType).workspaceType ?? null;
}
