import type { ChartArtifact, JsonRecord, RenderPlan } from "./types";
import {
  deepMerge,
  extractOptionFragment,
  getChartDescription,
  getChartTitle,
  getRendererHint,
  isJsonRecord,
  isNonEmptyString,
  looksLikeRawEChartsOption,
  normalizeJsonText,
  parseCsvContent,
} from "./utils";
import { buildInteractionOption } from "./interactionBuilder";

export async function resolveDatasetSource(
  artifact: ChartArtifact,
  readTextFile: (path: string) => Promise<string>,
): Promise<unknown | undefined> {
  const dataset = artifact.dataset;
  if (!dataset) {
    return undefined;
  }

  const datasetMode = dataset.mode ?? dataset.type;
  if (datasetMode === "inline") {
    return dataset.source;
  }

  if (datasetMode === "file_ref" && dataset.fileRef) {
    const lowerPath = dataset.fileRef.toLowerCase();
    if (lowerPath.endsWith(".parquet")) {
      throw new Error("当前 MVP 暂不支持 parquet 图表数据文件预览");
    }

    const raw = await readTextFile(dataset.fileRef);
    if (lowerPath.endsWith(".csv")) {
      return parseCsvContent(raw);
    }

    if (lowerPath.endsWith(".json")) {
      try {
        return JSON.parse(normalizeJsonText(raw));
      } catch {
        throw new Error(`JSON 数据文件格式错误: ${dataset.fileRef}`);
      }
    }

    throw new Error(`暂不支持的数据文件类型: ${dataset.fileRef}`);
  }

  return undefined;
}

function buildGenericSafeSpecOption(
  artifact: ChartArtifact,
  datasetSource: unknown,
): JsonRecord {
  const payloadOption = artifact.payload?.option;
  if (isJsonRecord(payloadOption)) {
    return buildInteractionOption(
      artifact.interaction,
      deepMerge(extractOptionFragment(artifact.view), payloadOption),
    );
  }

  let option = deepMerge(
    extractOptionFragment(artifact.view),
    extractOptionFragment(artifact.payload),
  );

  if (!option.title && getChartTitle(artifact)) {
    option.title = { text: getChartTitle(artifact) };
  }

  if (datasetSource !== undefined) {
    const currentDataset = isJsonRecord(option.dataset) ? option.dataset : {};
    option.dataset = {
      ...currentDataset,
      source: datasetSource,
    };
  }

  option = buildInteractionOption(artifact.interaction, option);
  option = materializePieSeriesData(option, datasetSource);
  return option;
}

function normalizeDatasetRows(source: unknown): JsonRecord[] {
  if (!Array.isArray(source)) {
    return [];
  }

  return source.filter(isJsonRecord);
}

function cloneSeriesItems(option: JsonRecord): JsonRecord[] {
  if (!Array.isArray(option.series)) {
    return [];
  }

  return option.series.filter(isJsonRecord).map((item) => ({ ...item }));
}

function resolveEncodeField(
  encode: unknown,
  key: "itemName" | "value",
): string | undefined {
  if (!isJsonRecord(encode)) {
    return undefined;
  }

  const rawValue = encode[key];
  if (isNonEmptyString(rawValue)) {
    return rawValue;
  }

  if (Array.isArray(rawValue)) {
    const first = rawValue.find(isNonEmptyString);
    return first;
  }

  return undefined;
}

function materializePieSeriesData(
  option: JsonRecord,
  datasetSource: unknown,
): JsonRecord {
  const rows = normalizeDatasetRows(datasetSource);
  if (rows.length === 0) {
    return option;
  }

  const seriesItems = cloneSeriesItems(option);
  if (seriesItems.length === 0) {
    return option;
  }

  let hasPieSeries = false;
  const nextSeries = seriesItems.map((seriesItem) => {
    if (seriesItem.type !== "pie") {
      return seriesItem;
    }

    hasPieSeries = true;
    const itemNameField = resolveEncodeField(seriesItem.encode, "itemName");
    const valueField = resolveEncodeField(seriesItem.encode, "value");
    if (!itemNameField || !valueField) {
      return seriesItem;
    }

    const data = rows
      .map((row) => ({
        name: row[itemNameField],
        value: row[valueField],
      }))
      .filter(
        (item) =>
          (isNonEmptyString(item.name) || typeof item.name === "number") &&
          (typeof item.value === "number" || isNonEmptyString(item.value)),
      );

    const nextSeriesItem: JsonRecord = {
      ...seriesItem,
      data,
    };
    delete nextSeriesItem.encode;
    return nextSeriesItem;
  });

  if (!hasPieSeries) {
    return option;
  }

  const nextOption: JsonRecord = {
    ...option,
    series: nextSeries,
  };
  delete nextOption.dataset;
  return nextOption;
}

async function buildMapRenderPlan(
  artifact: ChartArtifact,
  datasetSource: unknown,
  readTextFile: (path: string) => Promise<string>,
): Promise<RenderPlan> {
  const payload = artifact.payload ?? {};
  const resourceId =
    (isNonEmptyString(payload.mapResourceId) ? payload.mapResourceId : undefined) ??
    artifact.resources?.find((item) => isNonEmptyString(item.resourceId))
      ?.resourceId;

  const resource = artifact.resources?.find(
    (item) => item.resourceId === resourceId || item.fileRef,
  );

  if (!resource?.fileRef || !resourceId) {
    throw new Error("地图图表缺少可用的地图资源");
  }

  const geoJsonRaw = await readTextFile(resource.fileRef);
  let geoJson: unknown;
  try {
    geoJson = JSON.parse(normalizeJsonText(geoJsonRaw));
  } catch {
    throw new Error("地图 GeoJSON 数据格式错误");
  }
  const rows = normalizeDatasetRows(datasetSource);
  const nameField = isNonEmptyString(payload.nameField)
    ? payload.nameField
    : "name";
  const valueField = isNonEmptyString(payload.valueField)
    ? payload.valueField
    : "value";

  const optionBase = deepMerge(
    extractOptionFragment(artifact.view),
    extractOptionFragment(payload),
  );
  const data = rows
    .map((row) => ({
      name: row[nameField],
      value: row[valueField],
    }))
    .filter(
      (item) =>
        isNonEmptyString(item.name) ||
        typeof item.name === "number" ||
        typeof item.value === "number",
    );

  const rawSeries = Array.isArray(optionBase.series) ? optionBase.series : [];
  const seriesTemplates = rawSeries.length > 0 ? rawSeries : [{ type: "map" }];
  const interaction = artifact.interaction ?? {};

  delete optionBase.series;

  const series = seriesTemplates.map((seriesItem) => {
    const baseSeries = isJsonRecord(seriesItem) ? seriesItem : {};
    const nextSeries: JsonRecord = {
      ...baseSeries,
      type: "map",
      map: resourceId,
      data,
    };

    if (typeof interaction.roam === "boolean") {
      nextSeries.roam = interaction.roam;
    }

    return nextSeries;
  });

  const option = buildInteractionOption(artifact.interaction, {
    ...optionBase,
    series,
  });

  return {
    option,
    mapRegistrations: [{ mapName: resourceId, geoJson }],
    renderer: getRendererHint(artifact),
    title: getChartTitle(artifact),
    description: getChartDescription(artifact),
  };
}

export function normalizeArtifact(raw: unknown): ChartArtifact {
  if (!isJsonRecord(raw)) {
    throw new Error("图表文件内容不是合法的 JSON 对象");
  }

  const dataset = isJsonRecord(raw.dataset) ? raw.dataset : undefined;
  const payload = isJsonRecord(raw.payload)
    ? raw.payload
    : isJsonRecord(raw.spec)
      ? raw.spec
      : undefined;

  return {
    kind:
      (isNonEmptyString(raw.kind) ? raw.kind : undefined) ??
      (isNonEmptyString(raw.type) ? raw.type : undefined),
    type: isNonEmptyString(raw.type) ? raw.type : undefined,
    version: typeof raw.version === "number" ? raw.version : undefined,
    engine: isNonEmptyString(raw.engine) ? raw.engine : undefined,
    mode: isNonEmptyString(raw.mode) ? raw.mode : undefined,
    meta: isJsonRecord(raw.meta) ? raw.meta : undefined,
    view: isJsonRecord(raw.view) ? raw.view : undefined,
    dataset: dataset
      ? {
          ...dataset,
          mode:
            (isNonEmptyString(dataset.mode) ? dataset.mode : undefined) ??
            (isNonEmptyString(dataset.type) ? dataset.type : undefined),
          fileRef:
            (isNonEmptyString(dataset.fileRef) ? dataset.fileRef : undefined) ??
            (isNonEmptyString(dataset.uri) ? dataset.uri : undefined),
        }
      : undefined,
    resources: Array.isArray(raw.resources)
      ? raw.resources.filter(isJsonRecord).map((resource) => ({
          resourceId: isNonEmptyString(resource.resourceId)
            ? resource.resourceId
            : undefined,
          kind: isNonEmptyString(resource.kind) ? resource.kind : undefined,
          fileRef:
            (isNonEmptyString(resource.fileRef)
              ? resource.fileRef
              : undefined) ??
            (isNonEmptyString(resource.uri) ? resource.uri : undefined),
        }))
      : [],
    interaction: isJsonRecord(raw.interaction) ? raw.interaction : undefined,
    payload,
    spec: isJsonRecord(raw.spec) ? raw.spec : undefined,
    fallback: isJsonRecord(raw.fallback) ? raw.fallback : undefined,
  };
}

export async function buildRenderPlan(
  rawContent: string,
  readTextFile: (path: string) => Promise<string>,
): Promise<RenderPlan> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(normalizeJsonText(rawContent));
  } catch {
    throw new Error("图表内容 JSON 格式错误");
  }

  if (looksLikeRawEChartsOption(parsed)) {
    return {
      option: parsed,
      mapRegistrations: [],
      renderer: "canvas",
      title: undefined,
      description: undefined,
    };
  }

  const artifact = normalizeArtifact(parsed);

  if (artifact.kind !== "aiasys.chart" || artifact.engine !== "echarts") {
    throw new Error("文件不是受支持的 ECharts 图表资产");
  }

  if (artifact.mode === "native_option") {
    const payload = artifact.payload ?? {};
    const option = payload.option;
    if (!isJsonRecord(option)) {
      throw new Error("native_option 缺少 payload.option");
    }
    return {
      option,
      mapRegistrations: [],
      renderer: getRendererHint(artifact),
      title: getChartTitle(artifact),
      description: getChartDescription(artifact),
    };
  }

  const datasetSource = await resolveDatasetSource(artifact, readTextFile);
  const chartType =
    (isNonEmptyString(artifact.payload?.chartType)
      ? artifact.payload?.chartType
      : undefined) ??
    (isNonEmptyString(artifact.meta?.chartType)
      ? artifact.meta?.chartType
      : undefined);

  if (chartType === "map") {
    return await buildMapRenderPlan(artifact, datasetSource, readTextFile);
  }

  return {
    option: buildGenericSafeSpecOption(artifact, datasetSource),
    mapRegistrations: [],
    renderer: getRendererHint(artifact),
    title: getChartTitle(artifact),
    description: getChartDescription(artifact),
  };
}
