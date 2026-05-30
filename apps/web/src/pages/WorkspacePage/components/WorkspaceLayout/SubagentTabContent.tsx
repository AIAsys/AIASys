import { useState, useEffect, useCallback, useRef } from "react";
import { apiRequest } from "@/lib/api/httpClient";
import { Loader2 } from "lucide-react";
import { SubAgentDetailDrawer } from "@/components/layout/WorkspaceSidebar/SubAgentDetailDrawer";
import type { SubAgentDetail } from "@/hooks/useExecutionTree";

interface SubagentTabContentProps {
  subagentId: string;
  userId?: string;
  sessionId?: string;
}

export function SubagentTabContent({ subagentId, userId, sessionId }: SubagentTabContentProps) {
  const [detail, setDetail] = useState<SubAgentDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const abortRef = useRef<AbortController | null>(null);

  const fetchDetail = useCallback(async () => {
    if (!userId || !sessionId) return;
    // 取消旧请求
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    setIsLoading(true);
    try {
      const data = await apiRequest<SubAgentDetail>(
        `/api/sessions/${userId}/${sessionId}/subagents/${subagentId}`,
        { signal: controller.signal },
      );
      setDetail(data);
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      console.error("加载 Sub Agent 详情失败:", err);
    } finally {
      setIsLoading(false);
    }
  }, [subagentId, userId, sessionId]);

  useEffect(() => {
    fetchDetail();
    return () => {
      if (abortRef.current) {
        abortRef.current.abort();
      }
    };
  }, [fetchDetail]);

  if (!userId || !sessionId) {
    return (
      <div className="flex flex-1 items-center justify-center px-6 text-sm text-muted-foreground">
        缺少会话信息
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center gap-2 px-6 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        正在加载协作节点详情...
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="flex flex-1 items-center justify-center px-6 text-sm text-muted-foreground">
        无法加载协作节点详情
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col min-h-0 overflow-hidden">
      <SubAgentDetailDrawer
        subagent={detail}
        inline
        isLoading={false}
        userId={userId}
        sessionId={sessionId}
      />
    </div>
  );
}
