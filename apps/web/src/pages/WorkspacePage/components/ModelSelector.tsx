import { Check, ChevronDown, Key, Search, Sparkles } from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  getProviders,
  type LLMModelConfig,
  type LLMProviderConfigWithMeta,
} from "@/lib/api/llm";
import { Settings2Icon } from "./chatShellIcons";

const PROVIDER_GRADIENTS: Record<string, { gradient: string; initial: string }> = {
  openai: { gradient: "from-foreground to-muted-foreground", initial: "O" },
  anthropic: { gradient: "from-foreground to-muted-foreground", initial: "A" },
  deepseek: { gradient: "from-foreground to-muted-foreground", initial: "D" },
  google: { gradient: "from-foreground to-muted-foreground", initial: "G" },
  gemini: { gradient: "from-foreground to-muted-foreground", initial: "G" },
  kimi: { gradient: "from-foreground to-muted-foreground", initial: "K" },
  vertexai: { gradient: "from-foreground to-muted-foreground", initial: "V" },
};

const FALLBACK_GRADIENT_PALETTE = [
  "from-foreground to-muted-foreground",
  "from-muted-foreground to-foreground",
  "from-foreground to-muted-foreground",
  "from-muted-foreground to-foreground",
  "from-foreground to-muted-foreground",
  "from-muted-foreground to-foreground",
];

const RECENT_MODELS_KEY = "aia-recent-models";
const MAX_RECENT = 3;


function getProviderGradient(providerName: string): string {
  const key = providerName.toLowerCase();
  if (PROVIDER_GRADIENTS[key]) return PROVIDER_GRADIENTS[key].gradient;
  let hash = 0;
  for (let i = 0; i < key.length; i++) {
    hash = (hash * 31 + key.charCodeAt(i)) | 0;
  }
  return FALLBACK_GRADIENT_PALETTE[Math.abs(hash) % FALLBACK_GRADIENT_PALETTE.length];
}

function getProviderInitial(providerName: string): string {
  const key = providerName.toLowerCase();
  if (PROVIDER_GRADIENTS[key]) return PROVIDER_GRADIENTS[key].initial;
  return providerName.charAt(0).toUpperCase() || "?";
}

function getRecentModelIds(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_MODELS_KEY);
    if (!raw) return [];
    const ids = JSON.parse(raw);
    return Array.isArray(ids) ? ids.slice(0, MAX_RECENT) : [];
  } catch {
    return [];
  }
}

function addRecentModel(id: string): void {
  const ids = getRecentModelIds().filter((value) => value !== id);
  ids.unshift(id);
  try {
    localStorage.setItem(RECENT_MODELS_KEY, JSON.stringify(ids.slice(0, MAX_RECENT)));
  } catch {
    // ignore
  }
}

interface ModelSelectorProps {
  userModels: LLMModelConfig[];
  selectedModelId?: string;
  effectiveModelDisplayName?: string | null;
  onSelectModel?: (modelId: string) => Promise<void> | void;
  thinkingEnabled?: boolean;
  thinkingEffort?: "low" | "medium" | "high";
  setThinkingEnabled?: (enabled: boolean) => void;
  setThinkingEffort?: (effort: "low" | "medium" | "high") => void;
  selectedModelSupportsThinking?: boolean;
  onOpenConfig?: () => void;
  disabled?: boolean;
}

export function ModelSelector({
  userModels,
  selectedModelId,
  effectiveModelDisplayName,
  onSelectModel,
  thinkingEnabled = false,
  thinkingEffort = "high",
  setThinkingEnabled,
  setThinkingEffort,
  selectedModelSupportsThinking = false,
  onOpenConfig,
  disabled,
}: ModelSelectorProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [providers, setProviders] = useState<LLMProviderConfigWithMeta[]>([]);
  const [recentIds, setRecentIds] = useState<string[]>(getRecentModelIds);
  const selectorRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [panelPos, setPanelPos] = useState<{ bottom: number; left: number } | null>(
    null,
  );

  useEffect(() => {
    getProviders(true)
      .then((res) => setProviders(res.providers))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!open) return;
    const handler = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        selectorRef.current &&
        !selectorRef.current.contains(target) &&
        panelRef.current &&
        !panelRef.current.contains(target)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handler = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        setOpen(false);
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  useEffect(() => {
    if (!open || !triggerRef.current) {
      setPanelPos(null);
      setSearch("");
      return;
    }
    const updatePos = () => {
      if (!triggerRef.current) return;
      const rect = triggerRef.current.getBoundingClientRect();
      setPanelPos({
        bottom: window.innerHeight - rect.top + 4,
        left: rect.left,
      });
    };
    updatePos();
    requestAnimationFrame(() => searchInputRef.current?.focus());
    window.addEventListener("resize", updatePos);
    window.addEventListener("scroll", updatePos, true);
    return () => {
      window.removeEventListener("resize", updatePos);
      window.removeEventListener("scroll", updatePos, true);
    };
  }, [open]);

  const providerMap = useMemo(() => {
    const map = new Map<string, LLMProviderConfigWithMeta>();
    for (const provider of providers) {
      map.set(provider.id, provider);
    }
    return map;
  }, [providers]);

  const getProviderName = useCallback(
    (providerId: string) => providerMap.get(providerId)?.name ?? providerId,
    [providerMap],
  );

  const getProviderGradientById = useCallback(
    (providerId: string) =>
      getProviderGradient(providerMap.get(providerId)?.name ?? providerId),
    [providerMap],
  );

  const getProviderInitialById = useCallback(
    (providerId: string) =>
      getProviderInitial(providerMap.get(providerId)?.name ?? providerId),
    [providerMap],
  );

  const filteredModels = useMemo(() => {
    if (!search.trim()) return userModels;
    const query = search.toLowerCase();
    return userModels.filter(
      (model) =>
        model.name.toLowerCase().includes(query) ||
        model.model.toLowerCase().includes(query) ||
        getProviderName(model.provider).toLowerCase().includes(query),
    );
  }, [getProviderName, search, userModels]);

  const groupedModels = useMemo(() => {
    const groups = new Map<string, LLMModelConfig[]>();
    for (const model of filteredModels) {
      const list = groups.get(model.provider) ?? [];
      list.push(model);
      groups.set(model.provider, list);
    }
    return groups;
  }, [filteredModels]);

  const recentModels = useMemo(() => {
    if (search.trim()) return [];
    return recentIds
      .map((id) => userModels.find((model) => model.id === id))
      .filter((model): model is LLMModelConfig => model != null);
  }, [recentIds, search, userModels]);
  const current = useMemo(() => {
    if (!selectedModelId || selectedModelId === "system") {
      return {
        name: effectiveModelDisplayName?.trim() || "默认模型",
        providerId: null,
      };
    }
    const model = userModels.find((item) => item.id === selectedModelId);
    if (model) return { name: model.name, providerId: model.provider };
    return {
      name: effectiveModelDisplayName?.trim() || selectedModelId,
      providerId: null,
    };
  }, [effectiveModelDisplayName, selectedModelId, userModels]);

  const handleSelect = (modelId: string) => {
    if (onSelectModel) {
      void Promise.resolve(onSelectModel(modelId)).catch((error) => {
        console.error("Failed to update session model selection:", error);
      });
    }
    addRecentModel(modelId);
    setRecentIds(getRecentModelIds());
    setOpen(false);
  };

  const isSelected = (modelId: string) => selectedModelId === modelId;

  const renderModelItem = (model: LLMModelConfig, badge?: string) => {
    const gradient = getProviderGradientById(model.provider);
    const initial = getProviderInitialById(model.provider);
    const selected = isSelected(model.id);

    return (
      <button
        key={model.id + (badge ?? "")}
        type="button"
        onClick={() => handleSelect(model.id)}
        className={`w-full flex items-center gap-2.5 px-2.5 py-2 text-left hover:bg-accent rounded-[10px] transition-colors ${selected ? "bg-primary/10" : ""}`}
      >
        <span
          className={`w-7 h-7 rounded-full bg-gradient-to-br ${gradient} flex items-center justify-center text-white text-xs font-bold flex-shrink-0`}
        >
          {initial}
        </span>
        <span className="flex-1 min-w-0 text-[13px] font-medium truncate">
          {model.name}
        </span>
        {badge ? (
          <span className="text-[10px] px-1 py-0.5 rounded bg-muted text-muted-foreground flex-shrink-0">
            {badge}
          </span>
        ) : null}
        {selected ? <Check size={16} className="text-primary flex-shrink-0" /> : null}
      </button>
    );
  };

  const panelContent =
    open && panelPos
      ? createPortal(
          <div
            ref={panelRef}
            className="fixed z-[9999] w-[300px] bg-popover border border-border rounded-2xl shadow-lg overflow-hidden"
            style={{ bottom: panelPos.bottom, left: panelPos.left }}
          >
            <div className="p-3 border-b border-border">
              <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-muted">
                <Search size={14} className="text-muted-foreground flex-shrink-0" />
                <input
                  ref={searchInputRef}
                  type="text"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="搜索模型..."
                  className="flex-1 bg-transparent text-[13px] outline-none placeholder:text-muted-foreground"
                />
              </div>
            </div>

            <div className="max-h-[360px] overflow-y-auto p-1.5">
              {!search.trim() ? (
                <div className="px-2.5 pt-2 pb-1 text-[11px] leading-5 text-muted-foreground">
                  这里只显示当前已配置并启用的模型。更多服务商或模型，请去设置里补充。
                </div>
              ) : null}

              {recentModels.length > 0 ? (
                <div className="mb-1">
                  <div className="px-2.5 pt-2 pb-1 text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">
                    最近使用
                  </div>
                  {recentModels.map((model) => renderModelItem(model, "最近"))}
                </div>
              ) : null}

              {Array.from(groupedModels.entries()).map(([providerId, models]) => (
                <div key={providerId} className="mb-1">
                  <div className="px-2.5 pt-2 pb-1 text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">
                    {getProviderName(providerId)}
                  </div>
                  {models.map((model) => renderModelItem(model))}
                </div>
              ))}

              {filteredModels.length === 0 && search.trim() ? (
                <div className="px-3 py-4 text-center text-sm text-muted-foreground">
                  无匹配模型
                </div>
              ) : null}
            </div>

            {selectedModelSupportsThinking && setThinkingEnabled ? (
              <div className="border-t border-border p-2.5">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[13px] font-medium">深度思考</span>
                  <button
                    type="button"
                    onClick={() => setThinkingEnabled(!thinkingEnabled)}
                    className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                      thinkingEnabled ? "bg-primary" : "bg-muted-foreground/30"
                    }`}
                  >
                    <span
                      className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                        thinkingEnabled ? "translate-x-4.5" : "translate-x-0.5"
                      }`}
                    />
                  </button>
                </div>
                {thinkingEnabled && setThinkingEffort ? (
                  <div className="flex items-center gap-1">
                    {(["low", "medium", "high"] as const).map((level) => (
                      <button
                        key={level}
                        type="button"
                        onClick={() => setThinkingEffort(level)}
                        className={`flex-1 text-[11px] py-1 rounded-md transition-colors ${
                          thinkingEffort === level
                            ? "bg-primary/10 text-primary font-medium"
                            : "bg-muted text-muted-foreground hover:bg-accent"
                        }`}
                      >
                        {level === "low" ? "低" : level === "medium" ? "中" : "高"}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}

            <div className="border-t border-border p-1.5">
              <button
                type="button"
                onClick={() => {
                  onOpenConfig?.();
                  setOpen(false);
                }}
                className="w-full flex items-center gap-2 px-2.5 py-2 text-left hover:bg-accent rounded-[10px] transition-colors text-muted-foreground"
              >
                <Settings2Icon className="h-3.5 w-3.5" />
                <span className="text-[13px]">配置更多服务商和模型...</span>
              </button>
            </div>
          </div>,
          document.body,
        )
      : null;

  return (
    <div ref={selectorRef} className="relative">
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            ref={triggerRef}
            type="button"
            disabled={disabled}
            onClick={() => setOpen(!open)}
            className="flex-shrink-0 flex items-center gap-1 p-2 rounded-md bg-secondary text-secondary-foreground text-xs hover:bg-secondary/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {current.providerId ? <Key size={14} /> : <Sparkles size={14} />}
            <span className="max-w-[80px] truncate hidden sm:inline">
              {current.name}
            </span>
            <ChevronDown size={12} className="opacity-60" />
          </button>
        </TooltipTrigger>
        <TooltipContent side="top">{current.name}</TooltipContent>
      </Tooltip>
      {panelContent}
    </div>
  );
}
