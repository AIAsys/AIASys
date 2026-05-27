import type { ChartArtifact, JsonRecord } from "./types";

export const OPTION_FRAGMENT_EXCLUDES = new Set([
  "chartType",
  "mapResourceId",
  "nameField",
  "valueField",
  "datasetMapping",
  "seriesLayout",
  "rendererHint",
  "theme",
  "height",
  "option",
]);

export function isJsonRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

export function normalizeJsonText(value: string): string {
  const trimmed = value.trim();
  const codeBlockMatch = trimmed.match(/^```[\w-]*\s*([\s\S]*?)\s*```$/);
  return codeBlockMatch ? codeBlockMatch[1].trim() : trimmed;
}

export function deepMerge(target: JsonRecord, source: JsonRecord): JsonRecord {
  const merged: JsonRecord = { ...target };

  for (const [key, value] of Object.entries(source)) {
    const previous = merged[key];
    if (isJsonRecord(previous) && isJsonRecord(value)) {
      merged[key] = deepMerge(previous, value);
      continue;
    }
    merged[key] = value;
  }

  return merged;
}

export function extractOptionFragment(source: unknown): JsonRecord {
  if (!isJsonRecord(source)) {
    return {};
  }

  const fragment: JsonRecord = {};
  for (const [key, value] of Object.entries(source)) {
    if (!OPTION_FRAGMENT_EXCLUDES.has(key)) {
      fragment[key] = value;
    }
  }
  return fragment;
}

export function parseCsvRow(line: string): string[] {
  const cells: string[] = [];
  let current = "";
  let inQuotes = false;

  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    const nextChar = line[index + 1];

    if (char === '"') {
      if (inQuotes && nextChar === '"') {
        current += '"';
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }

    if (char === "," && !inQuotes) {
      cells.push(current.trim());
      current = "";
      continue;
    }

    current += char;
  }

  cells.push(current.trim());
  return cells;
}

export function coerceCsvValue(value: string): string | number {
  if (value === "") {
    return "";
  }

  const numericValue = Number(value);
  if (!Number.isNaN(numericValue) && value.trim() !== "") {
    return numericValue;
  }

  return value;
}

export function parseCsvContent(raw: string): JsonRecord[] {
  const lines = raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (lines.length < 2) {
    return [];
  }

  const headers = parseCsvRow(lines[0]);
  return lines.slice(1).map((line) => {
    const values = parseCsvRow(line);
    const row: JsonRecord = {};

    headers.forEach((header, index) => {
      row[header] = coerceCsvValue(values[index] ?? "");
    });

    return row;
  });
}

export function looksLikeRawEChartsOption(raw: unknown): raw is JsonRecord {
  if (!isJsonRecord(raw)) {
    return false;
  }

  return Boolean(
    raw.series ||
      raw.xAxis ||
      raw.yAxis ||
      raw.tooltip ||
      raw.legend ||
      raw.grid ||
      raw.visualMap,
  );
}

export function getChartTitle(artifact: ChartArtifact): string | undefined {
  const metaTitle = artifact.meta?.title;
  if (isNonEmptyString(metaTitle)) {
    return metaTitle;
  }

  const payloadTitle = artifact.payload?.title;
  if (isJsonRecord(payloadTitle) && isNonEmptyString(payloadTitle.text)) {
    return payloadTitle.text;
  }

  const viewTitle = artifact.view?.title;
  if (isJsonRecord(viewTitle) && isNonEmptyString(viewTitle.text)) {
    return viewTitle.text;
  }

  return undefined;
}

export function getChartDescription(artifact: ChartArtifact): string | undefined {
  const description = artifact.meta?.description;
  return isNonEmptyString(description) ? description : undefined;
}

export function getArtifactDisplayName(path?: string): string {
  if (!path) {
    return "内嵌图表资产";
  }

  const normalizedPath = path.replace(/\\/g, "/");
  const basename = normalizedPath.split("/").pop() || normalizedPath;

  return basename.replace(/\.chart\.echarts\.json$/i, "") || basename;
}

export function getRendererHint(artifact: ChartArtifact): "canvas" | "svg" {
  const rendererHint = artifact.view?.rendererHint;
  return rendererHint === "svg" ? "svg" : "canvas";
}
