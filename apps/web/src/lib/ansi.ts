const ANSI_COLORS: Record<number, { color?: string; bold?: boolean }> = {
  0: {},
  1: { bold: true },
  30: { color: "#1f2937" },
  31: { color: "#ef4444" },
  32: { color: "#22c55e" },
  33: { color: "#eab308" },
  34: { color: "#3b82f6" },
  35: { color: "#a855f7" },
  36: { color: "#06b6d4" },
  37: { color: "#f3f4f6" },
  90: { color: "#6b7280" },
  91: { color: "#fca5a5" },
  92: { color: "#86efac" },
  93: { color: "#fde047" },
  94: { color: "#93c5fd" },
  95: { color: "#d8b4fe" },
  96: { color: "#67e8f9" },
  97: { color: "#f9fafb" },
};

// ANSI SGR escape sequence.
// eslint-disable-next-line no-control-regex
const ANSI_ESCAPE_RE = /\x1b\[([0-9;]*)m/g;

function resolveStyle(codes: number[]): { className?: string; color?: string; bold?: boolean } {
  let className: string | undefined;
  let color: string | undefined;
  let bold: boolean | undefined;

  for (const code of codes) {
    if (code === 0) {
      return {};
    }
    const style = ANSI_COLORS[code];
    if (style) {
      if (style.bold) {
        bold = true;
        className = "font-bold";
      }
      if (style.color) {
        color = style.color;
      }
    }
  }
  return { className, color, bold };
}

export interface AnsiElement {
  text: string;
  className?: string;
  color?: string;
  bold?: boolean;
}

export function parseAnsiToElements(text: string): AnsiElement[] {
  const parts: AnsiElement[] = [];
  let lastIndex = 0;
  let current: { className?: string; color?: string; bold?: boolean } = {};

  ANSI_ESCAPE_RE.lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = ANSI_ESCAPE_RE.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push({
        text: text.slice(lastIndex, match.index),
        ...current,
      });
    }

    const codes = match[1] ? match[1].split(";").map(Number) : [0];
    current = resolveStyle(codes);

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    parts.push({
      text: text.slice(lastIndex),
      ...current,
    });
  }

  return parts;
}
