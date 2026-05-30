import { useCallback, useEffect, useState } from "react";

import {
  diffNotebookVersions,
  getNotebookArtifacts,
  getNotebookExecutionRecords,
  getNotebookOutline,
  getNotebookVariables,
  searchNotebookCells,
} from "@/lib/api/notebooks";
import type {
  NotebookArtifactSummary,
  NotebookDiffCellChange,
  NotebookExecutionRecord,
  NotebookOutlineItem,
  NotebookSearchMatch,
  NotebookVariableSummary,
} from "@/types/notebook";

import type {
  NotebookInspectorTab,
  UseNotebookInspectorOptions,
  UseNotebookInspectorResult,
} from "../types";

export function useNotebookInspector({
  sessionId,
  notebookPath,
  lastExecutionRecordId,
  refreshVersion,
}: UseNotebookInspectorOptions): UseNotebookInspectorResult {
  const [inspectorTab, setInspectorTab] = useState<NotebookInspectorTab | null>("variables");
  const [inspectorLoading, setInspectorLoading] = useState(false);
  const [inspectorError, setInspectorError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<NotebookSearchMatch[]>([]);
  const [outlineItems, setOutlineItems] = useState<NotebookOutlineItem[]>([]);
  const [variables, setVariables] = useState<NotebookVariableSummary[]>([]);
  const [artifacts, setArtifacts] = useState<NotebookArtifactSummary[]>([]);
  const [executionRecords, setExecutionRecords] = useState<NotebookExecutionRecord[]>([]);
  const [diffChanges, setDiffChanges] = useState<NotebookDiffCellChange[]>([]);
  const [diffMetadataChanged, setDiffMetadataChanged] = useState(false);

  const loadInspectorData = useCallback(async (tab: NotebookInspectorTab): Promise<void> => {
    if (!sessionId || !notebookPath) {
      return;
    }
    setInspectorLoading(true);
    setInspectorError(null);
    try {
      switch (tab) {
        case "outline": {
          const response = await getNotebookOutline(sessionId, notebookPath);
          setOutlineItems(response.items);
          break;
        }
        case "variables": {
          const response = await getNotebookVariables(sessionId, notebookPath);
          setVariables(response.variables);
          break;
        }
        case "artifacts": {
          const response = await getNotebookArtifacts(sessionId, notebookPath);
          setArtifacts(response.artifacts);
          break;
        }
        case "runs": {
          const response = await getNotebookExecutionRecords(sessionId, notebookPath, 30);
          setExecutionRecords(response.records);
          break;
        }
        case "diff": {
          const response = await diffNotebookVersions(sessionId, notebookPath);
          setDiffChanges(response.changed_cells);
          setDiffMetadataChanged(response.metadata_changed);
          break;
        }
        case "search":
        default:
          break;
      }
    } catch (err) {
      setInspectorError(err instanceof Error ? err.message : "读取 notebook 面板数据失败");
    } finally {
      setInspectorLoading(false);
    }
  }, [sessionId, notebookPath]);

  useEffect(() => {
    if (!sessionId || !notebookPath || !inspectorTab || inspectorTab === "search") {
      return;
    }
    void loadInspectorData(inspectorTab);
  }, [inspectorTab, lastExecutionRecordId, notebookPath, refreshVersion, sessionId, loadInspectorData]);

  async function refreshInspectorData(): Promise<void> {
    if (!inspectorTab) {
      return;
    }
    await loadInspectorData(inspectorTab);
  }

  function toggleInspectorTab(tab: NotebookInspectorTab): void {
    setInspectorTab((prev) => (prev === tab ? null : tab));
  }

  function closeInspector(): void {
    setInspectorTab(null);
  }

  async function handleSearch(): Promise<void> {
    if (!sessionId || !notebookPath || !searchQuery.trim()) {
      setSearchResults([]);
      return;
    }
    setInspectorLoading(true);
    setInspectorError(null);
    try {
      const response = await searchNotebookCells(sessionId, {
        notebook_path: notebookPath,
        query: searchQuery.trim(),
        max_results: 50,
      });
      setSearchResults(response.matches);
    } catch (err) {
      setInspectorError(err instanceof Error ? err.message : "搜索 notebook 失败");
    } finally {
      setInspectorLoading(false);
    }
  }

  return {
    inspectorTab,
    inspectorLoading,
    inspectorError,
    searchQuery,
    setSearchQuery,
    searchResults,
    outlineItems,
    variables,
    artifacts,
    executionRecords,
    diffChanges,
    diffMetadataChanged,
    toggleInspectorTab,
    closeInspector,
    handleSearch,
    refreshInspectorData,
  };
}
