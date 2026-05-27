#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(scriptDir, "../..");
const outputDir = resolve(projectRoot, "archive/design/aiasys-design-md-poc");
const designPath = resolve(projectRoot, "DESIGN.md");

const mappedRuntimeVars = [
  { runtime: "background", token: "background", note: "页面主背景" },
  { runtime: "foreground", token: "on-background", note: "全局前景文本" },
  { runtime: "card", token: "surface", note: "主卡片表面" },
  { runtime: "card-foreground", token: "on-surface", note: "卡片正文文本" },
  { runtime: "popover", token: "surface-overlay", note: "浮层背景" },
  { runtime: "popover-foreground", token: "on-surface", note: "浮层前景文本" },
  { runtime: "primary", token: "primary", note: "主操作色" },
  { runtime: "primary-foreground", token: "on-primary", note: "主操作前景文本" },
  { runtime: "secondary", token: "secondary-container", note: "次级容器色" },
  { runtime: "secondary-foreground", token: "on-secondary-container", note: "次级容器前景文本" },
  { runtime: "muted", token: "muted", note: "弱背景层" },
  { runtime: "muted-foreground", token: "on-muted", note: "弱前景文本" },
  { runtime: "accent", token: "tertiary-container", note: "轻强调容器" },
  { runtime: "accent-foreground", token: "on-tertiary-container", note: "轻强调前景文本" },
  { runtime: "destructive", token: "error", note: "破坏性操作色" },
  { runtime: "border", token: "outline", note: "标准边界色" },
  { runtime: "input", token: "outline-variant", note: "输入边界色" },
  { runtime: "ring", token: "focus", note: "聚焦环" },
  { runtime: "sidebar", token: "sidebar", note: "侧栏背景" },
  { runtime: "sidebar-foreground", token: "on-sidebar", note: "侧栏前景文本" },
  { runtime: "sidebar-primary", token: "primary", note: "侧栏主操作色" },
  { runtime: "sidebar-primary-foreground", token: "on-primary", note: "侧栏主操作前景文本" },
  { runtime: "sidebar-accent", token: "secondary-container", note: "侧栏轻强调背景" },
  { runtime: "sidebar-accent-foreground", token: "on-secondary-container", note: "侧栏轻强调前景" },
  { runtime: "sidebar-border", token: "outline", note: "侧栏边界色" },
  { runtime: "sidebar-ring", token: "focus", note: "侧栏聚焦环" },
];

const preservedRuntimeVars = [
  { runtime: "chart-1..5", reason: "当前 DESIGN.md 未定义图表调色板" },
  { runtime: "scrollbar-thumb / scrollbar-thumb-hover", reason: "当前 DESIGN.md 未覆盖滚动条皮肤" },
  { runtime: "image-zoom-*", reason: "图片预览层仍是当前运行时私有变量组" },
  { runtime: ".dark block", reason: "当前 DESIGN.md 没有暗色主题轴，继续保留现状" },
];

function runTailwindExport() {
  const output = execFileSync(
    "npx",
    ["-y", "@google/design.md", "export", "--format", "tailwind", designPath],
    {
      cwd: projectRoot,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "inherit"],
    },
  );
  const parsed = JSON.parse(output);
  const theme = parsed.theme?.extend;
  if (!theme) {
    throw new Error("Invalid tailwind export: missing theme.extend");
  }
  return theme;
}

function cssString(value) {
  const text = String(value);
  if (/^[-_a-zA-Z0-9. #%()/,]+$/.test(text)) {
    return text;
  }
  return JSON.stringify(text);
}

function cssFontFamily(value) {
  const text = String(value);
  if (/\s/.test(text)) {
    return JSON.stringify(text);
  }
  return cssString(text);
}

function getToken(theme, group, token) {
  const value = theme[group]?.[token];
  if (value === undefined) {
    throw new Error(`Missing DESIGN.md token for ${group}.${token}`);
  }
  return value;
}

function getFontStack(theme, token, fallback) {
  const families = theme.fontFamily?.[token];
  if (!Array.isArray(families) || families.length === 0) {
    throw new Error(`Missing DESIGN.md font token: ${token}`);
  }
  return [families[0], ...fallback];
}

function buildCandidateCss(theme) {
  const radius = getToken(theme, "borderRadius", "md");
  const fontSans = getFontStack(theme, "body-md", ["Noto Sans SC", "system-ui", "-apple-system", "sans-serif"]);
  const fontMono = getFontStack(theme, "code-sm", ["ui-monospace", "Cascadia Code", "monospace"]);

  const lines = [
    "/*",
    "  Generated runtime candidate from DESIGN.md.",
    "  Command: ./dev.sh design-export-runtime",
    "",
    "  This file is for review only.",
    "  It mirrors the current apps/web/src/index.css runtime variables without",
    "  touching the live theme file.",
    "*/",
    "",
    ":root {",
    `  --radius: ${cssString(radius)};`,
    `  --font-sans: ${fontSans.map(cssFontFamily).join(", ")};`,
    `  --font-mono: ${fontMono.map(cssFontFamily).join(", ")};`,
    "",
    "  /* Mapped from DESIGN.md */",
  ];

  for (const entry of mappedRuntimeVars) {
    const value = getToken(theme, "colors", entry.token);
    lines.push(`  --${entry.runtime}: ${cssString(value)};`);
  }

  lines.push("");
  lines.push("  /* Preserved current runtime vars: review separately before any replacement */");
  for (const entry of preservedRuntimeVars) {
    lines.push(`  /* ${entry.runtime}: ${entry.reason} */`);
  }
  lines.push("}");
  lines.push("");
  lines.push("/*");
  lines.push("  .dark is intentionally omitted.");
  lines.push("  Current DESIGN.md has a single token set and does not yet describe a dark theme axis.");
  lines.push("*/");

  return lines.join("\n");
}

function buildMappingMarkdown(theme) {
  const lines = [
    "# DESIGN.md 运行时变量映射草案",
    "",
    "本文件用于审查 `DESIGN.md` 到 `apps/web/src/index.css` 当前运行时变量体系的建议映射。",
    "",
    "## 输出文件",
    "",
    "- `tailwind4-theme-draft.css`：命名空间化 Tailwind 4 草案",
    "- `runtime-theme-candidate.css`：当前运行时变量候选片段",
    "- `runtime-theme-mapping.md`：映射说明和保留项",
    "",
    "## 已映射变量",
    "",
    "| 当前运行时变量 | DESIGN.md token | 候选值 | 说明 |",
    "|------|------|------|------|",
  ];

  for (const entry of mappedRuntimeVars) {
    const value = getToken(theme, "colors", entry.token);
    lines.push(`| \`--${entry.runtime}\` | \`${entry.token}\` | \`${value}\` | ${entry.note} |`);
  }

  lines.push("");
  lines.push("## 保留现状");
  lines.push("");
  lines.push("| 变量组 | 原因 |");
  lines.push("|------|------|");
  for (const entry of preservedRuntimeVars) {
    lines.push(`| \`${entry.runtime}\` | ${entry.reason} |`);
  }

  lines.push("");
  lines.push("## 额外说明");
  lines.push("");
  lines.push(`- \`--radius\` 候选值使用 \`${getToken(theme, "borderRadius", "md")}\`，以保持当前输入框和按钮的紧凑半径。`);
  lines.push(`- \`--font-sans\` 候选值以 \`${getFontStack(theme, "body-md", []).join(", ")}\` 为主，并保留当前运行时的中文与系统回退栈。`);
  lines.push(`- \`--font-mono\` 候选值以 \`${getFontStack(theme, "code-sm", []).join(", ")}\` 为主，并保留当前运行时的等宽回退栈。`);
  lines.push("- `.dark` 相关变量本轮不自动生成，继续保留当前 `index.css` 的实现。");
  lines.push("- 当前候选片段默认不导入运行时，只放在 `archive/design/aiasys-design-md-poc/` 供审查。");
  lines.push("");
  lines.push("## 接入建议");
  lines.push("");
  lines.push("1. 先审查 `runtime-theme-candidate.css` 和 `apps/web/src/index.css` 的差异。");
  lines.push("2. 若浅色主题映射通过，再考虑把映射后的 `:root` 变量分批迁入主线。");
  lines.push("3. 暗色主题、图表色和图片预览变量单独开下一轮，不在本轮混入。");

  return lines.join("\n");
}

const theme = runTailwindExport();
const css = buildCandidateCss(theme);
const mapping = buildMappingMarkdown(theme);

mkdirSync(outputDir, { recursive: true });
writeFileSync(resolve(outputDir, "runtime-theme-candidate.css"), css, "utf8");
writeFileSync(resolve(outputDir, "runtime-theme-mapping.md"), mapping, "utf8");

console.log(`Wrote ${resolve(outputDir, "runtime-theme-candidate.css")}`);
console.log(`Wrote ${resolve(outputDir, "runtime-theme-mapping.md")}`);
