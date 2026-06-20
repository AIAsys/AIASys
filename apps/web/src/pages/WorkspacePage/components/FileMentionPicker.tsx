import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { Folder, FileText, Hash } from "lucide-react";
import { API_ENDPOINTS, getCurrentUserId } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";
import { cn } from "@/lib/utils";
import type { FileInfo } from "@/types/api";
import type { GlobalResourceNode } from "@/components/layout/WorkspaceSidebar/assetPreviewFactory";

interface MentionCandidate {
  scope: "current" | "global";
  path: string;
  name: string;
  isDirectory: boolean;
  insertText: string;
}

interface FileMentionPickerProps {
  workspaceId?: string;
  inputValue: string;
  onInputChange: (value: string) => void;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  disabled?: boolean;
}

export interface FileMentionPickerRef {
  isOpen: () => boolean;
  handleKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => boolean;
}

const MAX_CANDIDATES = 50;

function collectGlobalCandidates(nodes: GlobalResourceNode[]): MentionCandidate[] {
  const results: MentionCandidate[] = [];
  for (const node of nodes) {
    if (node.node_type === "directory" && node.children) {
      results.push(...collectGlobalCandidates(node.children));
    } else if (node.node_type === "resource") {
      const nodePath = node.path || node.name;
      results.push({
        scope: "global",
        path: nodePath,
        name: node.name,
        isDirectory: false,
        insertText: `@/global/${nodePath}`,
      });
    }
  }
  return results;
}

export const FileMentionPicker = forwardRef<FileMentionPickerRef, FileMentionPickerProps>(
  function FileMentionPicker({ workspaceId, inputValue, onInputChange, textareaRef, disabled }, ref) {
    const [isOpen, setIsOpen] = useState(false);
    const [query, setQuery] = useState("");
    const [candidates, setCandidates] = useState<MentionCandidate[]>([]);
    const [filtered, setFiltered] = useState<MentionCandidate[]>([]);
    const [selectedIndex, setSelectedIndex] = useState(0);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const mentionStartRef = useRef<number | null>(null);
    const loadingRef = useRef(false);
    const [skipNextDetection, setSkipNextDetection] = useState(false);

    const loadCandidates = useCallback(async () => {
      if (!workspaceId) {
        setError("工作区未就绪");
        return;
      }
      if (loadingRef.current) return;
      loadingRef.current = true;
      setLoading(true);
      setError(null);
      if (import.meta.env.DEV) console.log("[FileMentionPicker] 开始加载候选文件, workspaceId=", workspaceId);
      try {
        const userId = getCurrentUserId();

        const currentPromise = apiRequest<{ files: FileInfo[] }>(
          API_ENDPOINTS.WORKSPACE_FILE_LIST(workspaceId, { recursive: true, limit: 500 }),
          { query: { user_id: userId } },
        )
          .then((res) => {
            const mapped = (res.files || []).map((f) => ({
              scope: "current" as const,
              path: f.name,
              name: f.name.split("/").pop() || f.name,
              isDirectory: false,
              insertText: `@/workspace/${f.name}`,
            }));
            if (import.meta.env.DEV) console.log("[FileMentionPicker] 当前工作区文件:", mapped.length);
            return mapped;
          })
          .catch((err) => {
            if (import.meta.env.DEV) console.error("[FileMentionPicker] 加载当前工作区文件失败:", err);
            return [];
          });

        const globalPromise = apiRequest<{ nodes: GlobalResourceNode[] }>(
          API_ENDPOINTS.GLOBAL_WORKSPACE_TREE(workspaceId),
          { query: { user_id: userId } },
        )
          .then((res) => {
            const mapped = collectGlobalCandidates(res.nodes || []);
            if (import.meta.env.DEV) console.log("[FileMentionPicker] 全局工作区资源:", mapped.length);
            return mapped;
          })
          .catch((err) => {
            if (import.meta.env.DEV) console.error("[FileMentionPicker] 加载全局工作区资源失败:", err);
            return [];
          });

        const [current, global] = await Promise.all([currentPromise, globalPromise]);
        const merged = [...current, ...global];
        if (import.meta.env.DEV) console.log("[FileMentionPicker] 候选文件总数:", merged.length);
        setCandidates(merged);
        if (merged.length === 0) {
          setError("工作区暂无可用文件");
        }
      } catch (err) {
        if (import.meta.env.DEV) console.error("[FileMentionPicker] 加载候选文件失败:", err);
        setCandidates([]);
        setError("加载文件列表失败");
      } finally {
        loadingRef.current = false;
        setLoading(false);
      }
    }, [workspaceId]);

    // 工作区切换时清空候选，避免显示旧工作区文件
    useEffect(() => {
      setCandidates([]);
      setFiltered([]);
      setError(null);
    }, [workspaceId]);

    // 检测 @ 触发
    useEffect(() => {
      if (disabled || !textareaRef.current) {
        setIsOpen(false);
        return;
      }

      // 刚完成文件引用插入，跳过本次检测，避免 picker 重新打开
      if (skipNextDetection) {
        setSkipNextDetection(false);
        setIsOpen(false);
        mentionStartRef.current = null;
        return;
      }

      const textarea = textareaRef.current;
      const cursor = textarea.selectionStart ?? inputValue.length;
      const textBeforeCursor = inputValue.slice(0, cursor);

      // 从光标位置向前找最近的 @，且 @ 到光标之间没有空白字符
      const lastAt = textBeforeCursor.lastIndexOf("@");
      if (lastAt === -1) {
        setIsOpen(false);
        mentionStartRef.current = null;
        return;
      }

      const textBetween = textBeforeCursor.slice(lastAt + 1);
      if (/\s/.test(textBetween)) {
        setIsOpen(false);
        mentionStartRef.current = null;
        return;
      }

      mentionStartRef.current = lastAt;
      setQuery(textBetween);
      setIsOpen(true);
      setSelectedIndex(0);

      if (candidates.length === 0 && workspaceId) {
        void loadCandidates();
      }
    }, [inputValue, disabled, textareaRef, candidates.length, workspaceId, loadCandidates, skipNextDetection]);

    // 过滤候选
    useEffect(() => {
      if (!query) {
        setFiltered(candidates.slice(0, MAX_CANDIDATES));
        return;
      }
      const lowerQuery = query.toLowerCase();
      const scored = candidates
        .filter((c) => c.path.toLowerCase().includes(lowerQuery) || c.name.toLowerCase().includes(lowerQuery))
        .sort((a, b) => {
          // 名字以 query 开头的优先
          const aNameMatch = a.name.toLowerCase().startsWith(lowerQuery) ? 2 : 0;
          const bNameMatch = b.name.toLowerCase().startsWith(lowerQuery) ? 2 : 0;
          const aPathMatch = a.path.toLowerCase().startsWith(lowerQuery) ? 1 : 0;
          const bPathMatch = b.path.toLowerCase().startsWith(lowerQuery) ? 1 : 0;
          return bNameMatch + bPathMatch - (aNameMatch + aPathMatch);
        })
        .slice(0, MAX_CANDIDATES);
      setFiltered(scored);
      setSelectedIndex(0);
    }, [query, candidates]);

    const insertMention = useCallback(
      (candidate: MentionCandidate) => {
        const textarea = textareaRef.current;
        const start = mentionStartRef.current ?? 0;
        const end = textarea?.selectionEnd ?? inputValue.length;
        const before = inputValue.slice(0, start);
        const after = inputValue.slice(end);
        const needsLeadingSpace = before.length > 0 && !/\s$/.test(before);
        // 在输入框末尾插入时也追加尾部空格，确保 picker 不会把 /workspace/... 继续当成 @ 查询
        const needsTrailingSpace = !/^\s/.test(after);
        const inserted =
          (needsLeadingSpace ? " " : "") + candidate.insertText + (needsTrailingSpace ? " " : "");
        const newValue = before + inserted + after;
        onInputChange(newValue);
        setIsOpen(false);
        setSkipNextDetection(true);
        mentionStartRef.current = null;
        requestAnimationFrame(() => {
          textarea?.focus();
          const newCursor = start + inserted.length;
          textarea?.setSelectionRange(newCursor, newCursor);
        });
      },
      [inputValue, onInputChange, textareaRef],
    );

    const handleKeyDown = useCallback(
      (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (!isOpen) return false;

        if (e.key === "Escape") {
          setIsOpen(false);
          e.preventDefault();
          e.stopPropagation();
          return true;
        }

        if (e.key === "ArrowDown") {
          e.preventDefault();
          e.stopPropagation();
          setSelectedIndex((prev) => (prev + 1) % Math.max(filtered.length, 1));
          return true;
        }

        if (e.key === "ArrowUp") {
          e.preventDefault();
          e.stopPropagation();
          setSelectedIndex((prev) =>
            prev <= 0 ? Math.max(filtered.length - 1, 0) : prev - 1,
          );
          return true;
        }

        if (e.key === "Enter" || e.key === "Tab") {
          const candidate = filtered[selectedIndex];
          if (candidate) {
            e.preventDefault();
            e.stopPropagation();
            insertMention(candidate);
            return true;
          }
        }

        return false;
      },
      [isOpen, filtered, selectedIndex, insertMention],
    );

    useImperativeHandle(ref, () => ({
      isOpen: () => isOpen,
      handleKeyDown,
    }));

    // 点击外部关闭
    useEffect(() => {
      if (!isOpen) return;
      const handleClickOutside = (event: MouseEvent) => {
        const target = event.target as Node;
        if (
          textareaRef.current &&
          !textareaRef.current.contains(target) &&
          !document.getElementById("file-mention-picker")?.contains(target)
        ) {
          setIsOpen(false);
        }
      };
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }, [isOpen, textareaRef]);

    if (!isOpen || !workspaceId) return null;

    return (
      <div
        id="file-mention-picker"
        className="absolute left-0 right-0 bottom-full mb-2 max-h-64 overflow-y-auto rounded-lg border border-border bg-popover shadow-lg z-20"
      >
        {(loading || loadingRef.current) && filtered.length === 0 ? (
          <div className="px-3 py-2 text-xs text-muted-foreground">正在加载文件...</div>
        ) : error && filtered.length === 0 ? (
          <div className="px-3 py-2 text-xs text-destructive">{error}</div>
        ) : filtered.length === 0 ? (
          <div className="px-3 py-2 text-xs text-muted-foreground">未找到匹配文件</div>
        ) : (
          <ul className="py-1">
            {filtered.map((candidate, idx) => (
              <li
                key={`${candidate.scope}:${candidate.path}`}
                className={cn(
                  "px-3 py-2 flex items-center gap-2 cursor-pointer text-sm",
                  idx === selectedIndex ? "bg-accent text-accent-foreground" : "text-foreground hover:bg-accent/50",
                )}
                onMouseEnter={() => setSelectedIndex(idx)}
                onClick={() => insertMention(candidate)}
              >
                {candidate.scope === "current" ? (
                  candidate.isDirectory ? (
                    <Folder size={14} className="text-muted-foreground flex-shrink-0" />
                  ) : (
                    <FileText size={14} className="text-muted-foreground flex-shrink-0" />
                  )
                ) : (
                  <Hash size={14} className="text-muted-foreground flex-shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                  <div className="truncate font-medium">{candidate.name}</div>
                  <div className="truncate text-[10px] text-muted-foreground">
                    {candidate.scope === "current" ? "当前工作区" : "全局工作区"} · {candidate.path}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  },
);
