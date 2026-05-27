import {
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  getExternalSkillMarketDetail,
  getExternalSkillMarketItems,
  getExternalSkillMarketSources,
  installExternalSkillMarketItem,
} from "@/lib/api/externalSkillMarket";
import type {
  ExternalSkillMarketDetailResponse,
  ExternalSkillMarketItem,
  ExternalSkillMarketSource,
} from "@/types/externalSkillMarket";

type SkillMarketSortBy = "recommended" | "downloads" | "stars";

interface UseExternalSkillMarketReturn {
  sources: ExternalSkillMarketSource[];
  selectedSourceId: string | null;
  setSelectedSourceId: (sourceId: string) => void;
  items: ExternalSkillMarketItem[];
  availableCategories: string[];
  totalCount: number;
  hasMoreItems: boolean;
  loadingSources: boolean;
  loadingItems: boolean;
  loadingMoreItems: boolean;
  loadingDetail: boolean;
  installingItemId: string | null;
  error: Error | null;
  detail: ExternalSkillMarketDetailResponse | null;
  loadDetail: (
    sourceId: string,
    itemId: string,
  ) => Promise<ExternalSkillMarketDetailResponse | null>;
  refreshItems: () => Promise<void>;
  loadNextPage: () => Promise<void>;
  searchQuery: string;
  setSearchQuery: (value: string) => void;
  selectedCategory: string | null;
  setSelectedCategory: (value: string | null) => void;
  sortBy: SkillMarketSortBy;
  setSortBy: (value: SkillMarketSortBy) => void;
  installItem: (params: {
    workspaceId: string;
    sourceId: string;
    itemId: string;
    force?: boolean;
  }) => Promise<boolean>;
}

export function useExternalSkillMarket(): UseExternalSkillMarketReturn {
  const pageSize = 24;
  const [sources, setSources] = useState<ExternalSkillMarketSource[]>([]);
  const [selectedSourceId, setSelectedSourceIdState] = useState<string | null>(
    null,
  );
  const [items, setItems] = useState<ExternalSkillMarketItem[]>([]);
  const [availableCategories, setAvailableCategories] = useState<string[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [pageNumber, setPageNumber] = useState(1);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<SkillMarketSortBy>("recommended");
  const [detail, setDetail] = useState<ExternalSkillMarketDetailResponse | null>(
    null,
  );
  const [loadingSources, setLoadingSources] = useState(true);
  const [loadingItems, setLoadingItems] = useState(false);
  const [loadingMoreItems, setLoadingMoreItems] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [installingItemId, setInstallingItemId] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const deferredSearchQuery = useDeferredValue(searchQuery);
  const requestVersionRef = useRef(0);
  const queryKey = useMemo(
    () =>
      JSON.stringify({
        selectedSourceId,
        deferredSearchQuery,
        selectedCategory,
        sortBy,
      }),
    [deferredSearchQuery, selectedCategory, selectedSourceId, sortBy],
  );
  const hasMoreItems = items.length < totalCount;

  const loadSources = useCallback(async () => {
    setLoadingSources(true);
    setError(null);
    try {
      const nextSources = await getExternalSkillMarketSources();
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

  const loadItemsPage = useCallback(async (nextPageNumber: number) => {
    if (!selectedSourceId) {
      setItems([]);
      setAvailableCategories([]);
      setTotalCount(0);
      return;
    }

    const isAppending = nextPageNumber > 1;
    const requestVersion = ++requestVersionRef.current;
    if (isAppending) {
      setLoadingMoreItems(true);
    } else {
      setLoadingItems(true);
      setItems([]);
    }
    setError(null);
    try {
      const response = await getExternalSkillMarketItems({
        sourceId: selectedSourceId,
        search: deferredSearchQuery,
        category: selectedCategory || undefined,
        sortBy,
        pageNumber: nextPageNumber,
        pageSize,
      });
      if (requestVersion !== requestVersionRef.current) {
        return;
      }
      setItems((prevItems) => {
        if (!isAppending) {
          return response.items;
        }
        const merged = new Map<string, ExternalSkillMarketItem>();
        for (const item of prevItems) {
          merged.set(`${item.source_id}:${item.item_id}`, item);
        }
        for (const item of response.items) {
          merged.set(`${item.source_id}:${item.item_id}`, item);
        }
        return Array.from(merged.values());
      });
      setAvailableCategories(response.available_categories);
      setTotalCount(response.total_count);
      setPageNumber(response.page_number);
    } catch (err) {
      if (requestVersion === requestVersionRef.current) {
        setError(err instanceof Error ? err : new Error(String(err)));
      }
    } finally {
      if (requestVersion === requestVersionRef.current) {
        setLoadingItems(false);
        setLoadingMoreItems(false);
      }
    }
  }, [deferredSearchQuery, pageSize, selectedCategory, selectedSourceId, sortBy]);

  const refreshItems = useCallback(async () => {
    await loadItemsPage(1);
  }, [loadItemsPage]);

  const loadNextPage = useCallback(async () => {
    if (
      !selectedSourceId ||
      loadingItems ||
      loadingMoreItems ||
      items.length >= totalCount
    ) {
      return;
    }
    await loadItemsPage(pageNumber + 1);
  }, [
    items.length,
    loadItemsPage,
    loadingItems,
    loadingMoreItems,
    pageNumber,
    selectedSourceId,
    totalCount,
  ]);

  useEffect(() => {
    void loadSources();
  }, [loadSources]);

  useEffect(() => {
    setPageNumber(1);
    setTotalCount(0);
    setItems([]);
    setAvailableCategories([]);
    void refreshItems();
  }, [queryKey, refreshItems]);

  const setSelectedSourceId = (sourceId: string) => {
    setSelectedSourceIdState(sourceId);
    setSelectedCategory(null);
    setDetail(null);
  };

  const loadDetail = useCallback(async (sourceId: string, itemId: string) => {
    setDetail(null);
    setLoadingDetail(true);
    setError(null);
    try {
      const response = await getExternalSkillMarketDetail({ sourceId, itemId });
      setDetail(response);
      return response;
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      return null;
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  const installItem = useCallback(
    async (params: {
      workspaceId: string;
      sourceId: string;
      itemId: string;
      force?: boolean;
    }) => {
      setInstallingItemId(params.itemId);
      setError(null);
      try {
        await installExternalSkillMarketItem({
          workspaceId: params.workspaceId,
          payload: {
            source_id: params.sourceId,
            item_id: params.itemId,
            force: params.force ?? false,
          },
        });
        return true;
      } catch (err) {
        setError(err instanceof Error ? err : new Error(String(err)));
        return false;
      } finally {
        setInstallingItemId(null);
      }
    },
    [],
  );

  return {
    sources,
    selectedSourceId,
    setSelectedSourceId,
    items,
    availableCategories,
    totalCount,
    hasMoreItems,
    loadingSources,
    loadingItems,
    loadingMoreItems,
    loadingDetail,
    installingItemId,
    error,
    detail,
    loadDetail,
    refreshItems,
    loadNextPage,
    searchQuery,
    setSearchQuery,
    selectedCategory,
    setSelectedCategory,
    sortBy,
    setSortBy,
    installItem,
  };
}
