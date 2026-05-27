import { useState, useCallback, useEffect } from "react";
import {
  listTemplateMarketSources,
  listTemplateMarketItems,
  getTemplateMarketDetail,
  installTemplateMarketItem,
} from "@/lib/api/templateMarket";
import type {
  ExternalTemplateMarketSource,
  ExternalTemplateMarketItem,
  ExternalTemplateMarketDetailResponse,
} from "@/types/templateMarket";

export function useTemplateMarket() {
  const [sources, setSources] = useState<ExternalTemplateMarketSource[]>([]);
  const [selectedSourceId, setSelectedSourceId] = useState<string>("");
  const [items, setItems] = useState<ExternalTemplateMarketItem[]>([]);
  const [availableCategories, setAvailableCategories] = useState<string[]>([]);
  const [totalCount, setTotalCount] = useState(0);

  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("");

  const [loadingSources, setLoadingSources] = useState(false);
  const [loadingItems, setLoadingItems] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [installingItemId, setInstallingItemId] = useState<string | null>(null);

  const [detail, setDetail] = useState<ExternalTemplateMarketDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 加载市场源
  const loadSources = useCallback(async () => {
    setLoadingSources(true);
    setError(null);
    try {
      const data = await listTemplateMarketSources();
      setSources(data);
      if (data.length > 0 && !selectedSourceId) {
        setSelectedSourceId(data[0].source_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载市场源失败");
    } finally {
      setLoadingSources(false);
    }
  }, [selectedSourceId]);

  // 加载条目列表
  const loadItems = useCallback(async () => {
    if (!selectedSourceId) return;
    setLoadingItems(true);
    setError(null);
    try {
      const data = await listTemplateMarketItems(
        selectedSourceId,
        searchQuery || undefined,
        selectedCategory || undefined,
      );
      setItems(data.items);
      setAvailableCategories(data.available_categories);
      setTotalCount(data.total_count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载模板列表失败");
    } finally {
      setLoadingItems(false);
    }
  }, [selectedSourceId, searchQuery, selectedCategory]);

  // 加载详情
  const loadDetail = useCallback(
    async (itemId: string) => {
      if (!selectedSourceId) return;
      setLoadingDetail(true);
      setError(null);
      try {
        const data = await getTemplateMarketDetail(selectedSourceId, itemId);
        setDetail(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载模板详情失败");
      } finally {
        setLoadingDetail(false);
      }
    },
    [selectedSourceId],
  );

  // 安装模板
  const installItem = useCallback(
    async (itemId: string) => {
      if (!selectedSourceId) return { installed: false, template_id: "" };
      setInstallingItemId(itemId);
      setError(null);
      try {
        const result = await installTemplateMarketItem({
          source_id: selectedSourceId,
          item_id: itemId,
        });
        // 更新本地安装状态
        setItems((prev) =>
          prev.map((item) =>
            item.item_id === itemId ? { ...item, is_installed: true } : item,
          ),
        );
        if (detail && detail.item.item_id === itemId) {
          setDetail({
            ...detail,
            item: { ...detail.item, is_installed: true },
            can_install: false,
            install_disabled_reason: "该模板已安装到您的模板目录",
          });
        }
        return result;
      } catch (err) {
        setError(err instanceof Error ? err.message : "安装模板失败");
        return { installed: false, template_id: "" };
      } finally {
        setInstallingItemId(null);
      }
    },
    [selectedSourceId, detail],
  );

  // 初始加载源
  useEffect(() => {
    void loadSources();
  }, [loadSources]);

  // 源或过滤条件变化时加载条目
  useEffect(() => {
    void loadItems();
  }, [loadItems]);

  return {
    sources,
    selectedSourceId,
    setSelectedSourceId,
    items,
    availableCategories,
    totalCount,
    searchQuery,
    setSearchQuery,
    selectedCategory,
    setSelectedCategory,
    loadingSources,
    loadingItems,
    loadingDetail,
    installingItemId,
    detail,
    loadDetail,
    installItem,
    refreshItems: loadItems,
    error,
  };
}
