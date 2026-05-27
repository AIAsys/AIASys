import type { JsonRecord } from "./types";
import { deepMerge, isJsonRecord } from "./utils";

export function buildInteractionOption(
  interaction: JsonRecord | undefined,
  currentOption: JsonRecord,
): JsonRecord {
  if (!interaction) {
    return currentOption;
  }

  let nextOption = { ...currentOption };
  const dataZoom = interaction.dataZoom;
  if (isJsonRecord(dataZoom) && dataZoom.enabled) {
    const zoomConfig: JsonRecord = {};
    for (const [key, value] of Object.entries(dataZoom)) {
      if (!["enabled", "inside", "slider"].includes(key)) {
        zoomConfig[key] = value;
      }
    }

    const dataZoomItems: JsonRecord[] = [];
    if (dataZoom.inside) {
      dataZoomItems.push({ type: "inside", ...zoomConfig });
    }
    if (dataZoom.slider) {
      dataZoomItems.push({ type: "slider", ...zoomConfig });
    }
    if (dataZoomItems.length > 0) {
      nextOption = {
        ...nextOption,
        dataZoom: dataZoomItems,
      };
    }
  }

  const axisPointer = interaction.axisPointer;
  if (isJsonRecord(axisPointer) && axisPointer.enabled) {
    const axisPointerConfig: JsonRecord = {};
    for (const [key, value] of Object.entries(axisPointer)) {
      if (key !== "enabled") {
        axisPointerConfig[key] = value;
      }
    }

    nextOption = {
      ...nextOption,
      axisPointer: isJsonRecord(nextOption.axisPointer)
        ? deepMerge(nextOption.axisPointer, axisPointerConfig)
        : axisPointerConfig,
    };
  }

  return nextOption;
}
