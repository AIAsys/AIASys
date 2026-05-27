import {
  useCallback,
  useDeferredValue,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  getExternalMCPMarketDetail,
  getExternalMCPMarketItems,
  getExternalMCPMarketSources,
  importExternalMCPMarketItem,
} from "@/lib/api/externalMCPMarket";
import type {
  ExternalMCPMarketDetailResponse,
  ExternalMCPMarketItem,
  ExternalMCPMarketSource,
} from "@/types/externalMCPMarket";

interface UseExternalMCPMarketReturn {
  sources: ExternalMCPMarketSource[];
  selectedSourceId: string | null;
  setSelectedSourceId: (sourceId: string) => void;
  items: ExternalMCPMarketItem[];
  totalCount: number;
  loadedCount: number;
  currentPage: number;
  hasMore: boolean;
  loadingSources: boolean;
  loadingItems: boolean;
  loadingMore: boolean;
  loadingDetail: boolean;
  importingItemId: string | null;
  error: Error | null;
  detail: ExternalMCPMarketDetailResponse | null;
  loadDetail: (
    sourceId: string,
    itemId: string,
  ) => Promise<ExternalMCPMarketDetailResponse | null>;
  refreshItems: () => Promise<void>;
  loadMore: () => Promise<void>;
  setSearchQuery: (value: string) => void;
  searchQuery: string;
  importItem: (params: {
    sourceId: string;
    itemId: string;
    envOverrides?: Record<string, string>;
    enabled?: boolean;
  }) => Promise<boolean>;
}

const PAGE_SIZE = 24;

export function useExternalMCPMarket(): UseExternalMCPMarketReturn {
  const [sources, setSources] = useState<ExternalMCPMarketSource[]>([]);
  const [selectedSourceId, setSelectedSourceIdState] = useState<string | null>(
    null,
  );
  const [items, setItems] = useState<ExternalMCPMarketItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState("");
  const [detail, setDetail] = useState<ExternalMCPMarketDetailResponse | null>(
    null,
  );
  const [loadingSources, setLoadingSources] = useState(true);
  const [loadingItems, setLoadingItems] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [importingItemId, setImportingItemId] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const deferredSearchQuery = useDeferredValue(searchQuery);
  const itemRequestIdRef = useRef(0);

  const loadSources = useCallback(async () => {
    setLoadingSources(true);
    setError(null);
    try {
      const nextSources = await getExternalMCPMarketSources();
      setSources(nextSources);
      if (!selectedSourceId && nextSources.length > 0) {
        setSelectedSourceIdState(nextSources[0].source_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoadingSources(false);
    }
  }, [selectedSourceId]);

  const loadItems = useCallback(
    async ({ pageNumber, append }: { pageNumber: number; append: boolean }) => {
      if (!selectedSourceId) {
        setItems([]);
        setTotalCount(0);
        setCurrentPage(1);
        return;
      }

      if (append) {
        setLoadingMore(true);
      } else {
        setLoadingItems(true);
      }
      setError(null);
      const requestId = ++itemRequestIdRef.current;
      try {
        const response = await getExternalMCPMarketItems({
          sourceId: selectedSourceId,
          search: deferredSearchQuery,
          pageNumber,
          pageSize: PAGE_SIZE,
        });
        if (requestId !== itemRequestIdRef.current) {
          return;
        }
        setItems((previous) =>
          append ? [...previous, ...response.items] : response.items,
        );
        setTotalCount(response.total_count);
        setCurrentPage(response.page_number);
      } catch (err) {
        if (requestId !== itemRequestIdRef.current) {
          return;
        }
        setError(err instanceof Error ? err : new Error(String(err)));
      } finally {
        if (requestId === itemRequestIdRef.current) {
          if (append) {
            setLoadingMore(false);
          } else {
            setLoadingItems(false);
          }
        }
      }
    },
    [deferredSearchQuery, selectedSourceId],
  );

  const refreshItems = useCallback(async () => {
    if (!selectedSourceId) {
      setItems([]);
      setTotalCount(0);
      setCurrentPage(1);
      return;
    }
    await loadItems({ pageNumber: 1, append: false });
  }, [loadItems, selectedSourceId]);

  useEffect(() => {
    void loadSources();
  }, [loadSources]);

  useEffect(() => {
    void refreshItems();
  }, [refreshItems]);

  const hasMore = items.length < totalCount;

  const loadMore = useCallback(async () => {
    if (!selectedSourceId || loadingItems || loadingMore || !hasMore) {
      return;
    }
    await loadItems({ pageNumber: currentPage + 1, append: true });
  }, [
    currentPage,
    hasMore,
    loadItems,
    loadingItems,
    loadingMore,
    selectedSourceId,
  ]);

  const setSelectedSourceId = (sourceId: string) => {
    setSelectedSourceIdState(sourceId);
    setDetail(null);
    setItems([]);
    setTotalCount(0);
    setCurrentPage(1);
  };

  const loadDetail = useCallback(async (sourceId: string, itemId: string) => {
    setLoadingDetail(true);
    setError(null);
    try {
      const response = await getExternalMCPMarketDetail({ sourceId, itemId });
      setDetail(response);
      return response;
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      return null;
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  const importItem = useCallback(
    async (params: {
      sourceId: string;
      itemId: string;
      envOverrides?: Record<string, string>;
      enabled?: boolean;
    }) => {
      setImportingItemId(params.itemId);
      setError(null);
      try {
        await importExternalMCPMarketItem({
          source_id: params.sourceId,
          item_id: params.itemId,
          env_overrides: params.envOverrides || {},
          enabled: params.enabled ?? true,
        });
        return true;
      } catch (err) {
        setError(err instanceof Error ? err : new Error(String(err)));
        return false;
      } finally {
        setImportingItemId(null);
      }
    },
    [],
  );

  return {
    sources,
    selectedSourceId,
    setSelectedSourceId,
    items,
    totalCount,
    loadedCount: items.length,
    currentPage,
    hasMore,
    loadingSources,
    loadingItems,
    loadingMore,
    loadingDetail,
    importingItemId,
    error,
    detail,
    loadDetail,
    refreshItems,
    loadMore,
    setSearchQuery,
    searchQuery,
    importItem,
  };
}
