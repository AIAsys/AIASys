import CodeMirror from "@uiw/react-codemirror";
import type { Extension } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { css } from "@codemirror/lang-css";
import { html } from "@codemirror/lang-html";
import { javascript } from "@codemirror/lang-javascript";
import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import { python } from "@codemirror/lang-python";
import { sql } from "@codemirror/lang-sql";
import { xml } from "@codemirror/lang-xml";
import { yaml } from "@codemirror/lang-yaml";
import { oneDark } from "@codemirror/theme-one-dark";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { tags } from "@lezer/highlight";
import { cn } from "@/lib/utils";
import type { WorkspaceEditorLanguage } from "@/utils/workspaceFileEditing";

export interface CodeMirrorEditorProps {
  value: string;
  onChange?: (value: string) => void;
  language?: WorkspaceEditorLanguage;
  readOnly?: boolean;
  theme?: "dark" | "light";
  className?: string;
  ariaLabel?: string;
}

/* ─── 编辑器外观（浅色） ─── */
const lightEditorTheme = EditorView.theme({
  "&": {
    color: "#1f2937",
    backgroundColor: "#ffffff",
  },
  ".cm-content": {
    caretColor: "#2563eb",
  },
  ".cm-cursor, .cm-dropCursor": {
    borderLeftColor: "#2563eb",
  },
  "&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection":
    {
      backgroundColor: "#bfdbfe",
    },
  ".cm-activeLine": {
    backgroundColor: "#f3f4f6",
  },
  ".cm-gutters": {
    backgroundColor: "#f9fafb",
    color: "#9ca3af",
    borderRight: "1px solid #e5e7eb",
  },
  ".cm-activeLineGutter": {
    backgroundColor: "#f3f4f6",
  },
});

/* ─── 语法高亮（浅色背景上的高对比度配色） ─── */
const lightHighlightStyle = HighlightStyle.define([
  { tag: tags.keyword, color: "#7c3aed" },
  { tag: [tags.name, tags.deleted, tags.character, tags.propertyName, tags.macroName], color: "#2563eb" },
  { tag: [tags.function(tags.variableName), tags.labelName], color: "#2563eb" },
  { tag: [tags.color, tags.constant(tags.name), tags.standard(tags.name)], color: "#b45309" },
  { tag: [tags.definition(tags.name), tags.separator], color: "#1f2937" },
  { tag: [tags.typeName, tags.className, tags.number, tags.changed, tags.annotation, tags.modifier, tags.self, tags.namespace], color: "#059669" },
  { tag: [tags.operator, tags.operatorKeyword, tags.url, tags.escape, tags.regexp, tags.link, tags.special(tags.string)], color: "#dc2626" },
  { tag: [tags.meta, tags.comment], color: "#6b7280", fontStyle: "italic" },
  { tag: tags.strong, fontWeight: "bold" },
  { tag: tags.emphasis, fontStyle: "italic" },
  { tag: tags.strikethrough, textDecoration: "line-through" },
  { tag: tags.link, color: "#2563eb", textDecoration: "underline" },
  { tag: tags.heading, fontWeight: "bold", color: "#1f2937" },
  { tag: [tags.atom, tags.bool, tags.special(tags.variableName)], color: "#b45309" },
  { tag: [tags.processingInstruction, tags.string, tags.inserted], color: "#b45309" },
  { tag: tags.invalid, color: "#dc2626" },
  /* 括号 / 标点 —— 这是之前对比度不足的重点 */
  { tag: tags.punctuation, color: "#1f2937" },
  { tag: tags.bracket, color: "#1f2937" },
]);

const aiasysLight = [lightEditorTheme, syntaxHighlighting(lightHighlightStyle)];

const editorSurfaceTheme = EditorView.theme({
  "&": {
    height: "100%",
    minHeight: "100%",
    display: "flex",
    flexDirection: "column",
  },
  ".cm-scroller": {
    fontFamily:
      '"JetBrains Mono", "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace',
    overflow: "auto",
    flex: "1 1 auto",
  },
  ".cm-content": {
    padding: "16px 0",
  },
  ".cm-line": {
    padding: "0 16px",
  },
  ".cm-gutters": {
    borderRightWidth: "1px",
  },
  ".cm-focused": {
    outline: "none",
  },
});

function resolveLanguageExtension(
  language: WorkspaceEditorLanguage | undefined,
): Extension | null {
  switch (language) {
    case "css":
      return css();
    case "html":
      return html();
    case "javascript":
      return javascript();
    case "jsx":
      return javascript({ jsx: true });
    case "json":
      return json();
    case "markdown":
      return markdown();
    case "python":
      return python();
    case "sql":
      return sql();
    case "tsx":
      return javascript({ jsx: true, typescript: true });
    case "typescript":
      return javascript({ typescript: true });
    case "xml":
      return xml();
    case "yaml":
      return yaml();
    default:
      return null;
  }
}

export function CodeMirrorEditor({
  value,
  onChange,
  language = "text",
  readOnly = false,
  theme = "light",
  className,
  ariaLabel = "代码编辑器",
}: CodeMirrorEditorProps) {
  const languageExtension = resolveLanguageExtension(language);
  const extensions = languageExtension
    ? [editorSurfaceTheme, languageExtension]
    : [editorSurfaceTheme];

  return (
    <div
      className={cn(
        "flex h-full min-h-0 flex-col overflow-hidden text-[13px]",
        "[&_.cm-editor]:h-full [&_.cm-scroller]:overflow-auto",
        "[&>div]:flex [&>div]:h-full [&>div]:min-h-0 [&>div]:flex-col",
        className,
      )}
      data-testid="workspace-code-editor"
    >
      <CodeMirror
        value={value}
        height="100%"
        basicSetup={{
          lineNumbers: true,
          foldGutter: true,
          highlightActiveLine: true,
          highlightActiveLineGutter: true,
          autocompletion: true,
          bracketMatching: true,
          closeBrackets: true,
          searchKeymap: true,
        }}
        extensions={extensions}
        editable={!readOnly}
        readOnly={readOnly}
        theme={theme === "dark" ? oneDark : aiasysLight}
        onChange={onChange}
        aria-label={ariaLabel}
      />
    </div>
  );
}

export default CodeMirrorEditor;
