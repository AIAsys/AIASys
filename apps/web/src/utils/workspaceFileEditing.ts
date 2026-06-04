/**
 * 通用文本编辑文件扩展名白名单。
 *
 * 这些文件可以通过 Monaco/CodeMirror 等通用文本编辑器打开和编辑。
 * 注意：`.canvas` 不在此列表中 —— 它有自己的 CanvasEditor 专用编辑器。
 *
 * ## 与后端的一致性
 * 后端 `apps/backend/app/api/routes/files_utils.py` 中的 `EDITABLE_EXTENSIONS`
 * 额外包含 `.canvas`（用于确定 `FileContentResponse.editable` 字段），
 * 但前端通过资源类型路由到 CanvasEditor，无需将 `.canvas` 视为泛用文本编辑。
 */
export const GENERIC_TEXT_EDIT_EXTENSIONS = [
  ".md",
  ".markdown",
  ".mdx",
  ".txt",
  ".json",
  ".jsonl",
  ".yaml",
  ".yml",
  ".csv",
  ".tsv",
  ".xml",
  ".ini",
  ".conf",
  ".cfg",
  ".toml",
  ".log",
  ".properties",
  ".py",
  ".js",
  ".ts",
  ".tsx",
  ".jsx",
  ".html",
  ".css",
  ".scss",
  ".sql",
  ".sh",
  ".bash",
  ".zsh",
] as const;

export function isGenericallyEditable(filename: string): boolean {
  return GENERIC_TEXT_EDIT_EXTENSIONS.includes(
    getWorkspaceFileExtension(
      filename,
    ) as (typeof GENERIC_TEXT_EDIT_EXTENSIONS)[number],
  );
}

export type WorkspaceEditorLanguage =
  | "bash"
  | "css"
  | "html"
  | "javascript"
  | "json"
  | "jsx"
  | "markdown"
  | "python"
  | "sql"
  | "text"
  | "tsx"
  | "typescript"
  | "xml"
  | "yaml";

export function getWorkspaceFileExtension(filename: string): string {
  const dotIndex = filename.lastIndexOf(".");
  return dotIndex >= 0 ? filename.slice(dotIndex).toLowerCase() : "";
}

export function getWorkspaceEditorLanguage(
  filename: string,
): WorkspaceEditorLanguage {
  const extension = getWorkspaceFileExtension(filename);

  switch (extension) {
    case ".bash":
    case ".sh":
    case ".zsh":
      return "bash";
    case ".css":
    case ".scss":
      return "css";
    case ".html":
      return "html";
    case ".js":
      return "javascript";
    case ".jsx":
      return "jsx";
    case ".json":
    case ".jsonl":
    case ".ipynb":
      return "json";
    case ".md":
    case ".markdown":
    case ".mdx":
      return "markdown";
    case ".py":
      return "python";
    case ".sql":
      return "sql";
    case ".ts":
      return "typescript";
    case ".tsx":
      return "tsx";
    case ".xml":
      return "xml";
    case ".yaml":
    case ".yml":
      return "yaml";
    default:
      return "text";
  }
}
