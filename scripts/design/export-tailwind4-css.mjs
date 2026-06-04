#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(scriptDir, "../..");

const args = process.argv.slice(2);
const outputArg = args.find((arg) => !arg.startsWith("--"));
const outputPath = resolve(
  projectRoot,
  outputArg ?? "archive/design/aiasys-design-md-poc/tailwind4-theme-draft.css",
);
const designPath = resolve(projectRoot, "DESIGN.md");

function runDesignExport() {
  const output = execFileSync(
    "npx",
    ["-y", "@google/design.md", "export", "--format", "tailwind", designPath],
    {
      cwd: projectRoot,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "inherit"],
    },
  );
  return JSON.parse(output);
}

function cssName(name) {
  return String(name).replace(/[^a-zA-Z0-9-]/g, "-").toLowerCase();
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

function section(lines, title, entries) {
  if (!entries.length) {
    return;
  }
  lines.push(`  /* ${title} */`);
  lines.push(...entries);
  lines.push("");
}

function buildThemeInline(theme) {
  const lines = ["@theme inline {"];

  section(
    lines,
    "Colors",
    Object.keys(theme.colors ?? {}).map(
      (name) => `  --color-aiasys-${cssName(name)}: var(--aiasys-color-${cssName(name)});`,
    ),
  );

  section(
    lines,
    "Radii",
    Object.keys(theme.borderRadius ?? {}).map(
      (name) => `  --radius-aiasys-${cssName(name)}: var(--aiasys-radius-${cssName(name)});`,
    ),
  );

  section(
    lines,
    "Spacing",
    Object.keys(theme.spacing ?? {}).map(
      (name) => `  --spacing-aiasys-${cssName(name)}: var(--aiasys-spacing-${cssName(name)});`,
    ),
  );

  section(
    lines,
    "Typography",
    Object.keys(theme.fontSize ?? {}).flatMap((name) => [
      `  --text-aiasys-${cssName(name)}: var(--aiasys-text-${cssName(name)});`,
      `  --text-aiasys-${cssName(name)}--line-height: var(--aiasys-text-${cssName(name)}-line-height);`,
    ]),
  );

  section(
    lines,
    "Fonts",
    Object.keys(theme.fontFamily ?? {}).map(
      (name) => `  --font-aiasys-${cssName(name)}: var(--aiasys-font-${cssName(name)});`,
    ),
  );

  lines.push("}");
  return lines.join("\n");
}

function buildRoot(theme) {
  const lines = [":root {"];

  section(
    lines,
    "Colors",
    Object.entries(theme.colors ?? {}).map(
      ([name, value]) => `  --aiasys-color-${cssName(name)}: ${cssString(value)};`,
    ),
  );

  section(
    lines,
    "Radii",
    Object.entries(theme.borderRadius ?? {}).map(
      ([name, value]) => `  --aiasys-radius-${cssName(name)}: ${cssString(value)};`,
    ),
  );

  section(
    lines,
    "Spacing",
    Object.entries(theme.spacing ?? {}).map(
      ([name, value]) => `  --aiasys-spacing-${cssName(name)}: ${cssString(value)};`,
    ),
  );

  section(
    lines,
    "Fonts",
    Object.entries(theme.fontFamily ?? {}).map(([name, value]) => {
      const families = Array.isArray(value) ? value.map(cssFontFamily).join(", ") : cssFontFamily(value);
      return `  --aiasys-font-${cssName(name)}: ${families};`;
    }),
  );

  section(
    lines,
    "Typography",
    Object.entries(theme.fontSize ?? {}).flatMap(([name, value]) => {
      const [fontSize, meta = {}] = Array.isArray(value) ? value : [value, {}];
      const key = cssName(name);
      const typography = [
        `  --aiasys-text-${key}: ${cssString(fontSize)};`,
      ];
      if (meta.lineHeight) {
        typography.push(`  --aiasys-text-${key}-line-height: ${cssString(meta.lineHeight)};`);
      }
      if (meta.fontWeight) {
        typography.push(`  --aiasys-text-${key}-font-weight: ${cssString(meta.fontWeight)};`);
      }
      if (meta.letterSpacing) {
        typography.push(`  --aiasys-text-${key}-letter-spacing: ${cssString(meta.letterSpacing)};`);
      }
      return typography;
    }),
  );

  lines.push("}");
  return lines.join("\n");
}

function buildCompatibilityNotes() {
  return [
    "/*",
    "  Current apps/web/src/index.css uses shadcn-style runtime variables such as",
    "  --background, --foreground, --card, --primary and --sidebar.",
    "",
    "  This draft deliberately emits namespaced variables. Review the mapping before",
    "  moving anything into apps/web/src/index.css.",
    "",
    "  Suggested review pairs:",
    "  --background           <= --aiasys-color-background",
    "  --foreground           <= --aiasys-color-on-background",
    "  --card                 <= --aiasys-color-surface",
    "  --card-foreground      <= --aiasys-color-on-surface",
    "  --primary              <= --aiasys-color-primary",
    "  --primary-foreground   <= --aiasys-color-on-primary",
    "  --secondary            <= --aiasys-color-secondary-container",
    "  --secondary-foreground <= --aiasys-color-on-secondary-container",
    "  --accent               <= --aiasys-color-tertiary-container",
    "  --accent-foreground    <= --aiasys-color-on-tertiary-container",
    "  --destructive          <= --aiasys-color-error",
    "  --border               <= --aiasys-color-outline",
    "  --input                <= --aiasys-color-outline-variant",
    "  --ring                 <= --aiasys-color-focus",
    "*/",
  ].join("\n");
}

const exported = runDesignExport();
const theme = exported.theme?.extend;

if (!theme) {
  throw new Error("Invalid @google/design.md tailwind export: missing theme.extend");
}

const css = [
  "/*",
  "  Generated draft from DESIGN.md.",
  "  Command: ./dev.sh design-export-css",
  "",
  "  This file is for review only. Do not import it into the runtime until the",
  "  mapping into apps/web/src/index.css has been reviewed.",
  "*/",
  "",
  buildThemeInline(theme),
  "",
  buildRoot(theme),
  "",
  buildCompatibilityNotes(),
  "",
].join("\n");

mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(outputPath, css, "utf8");

console.log(`Wrote ${outputPath}`);
