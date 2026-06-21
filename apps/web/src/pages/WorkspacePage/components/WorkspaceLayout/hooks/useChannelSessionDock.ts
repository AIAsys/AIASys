import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  clearSessionClawBinding,
  dispatchSessionClawLastReply,
  getClawErrorMessage,
  getSessionClawBinding,
  getSessionClawOutboundPreview,
  pollClawQrLogin,
  saveSessionClawBinding,
  startClawQrLogin,
  startSessionClawLink,
  stopSessionClawLink,
} from "@/lib/api/claw";
import {
  createChannel,
  deleteChannel,
  listChannelPlatforms,
  listChannels,
  updateChannelEnabled,
} from "@/lib/api/channel";
import type {
  Channel,
  ChannelPlatformCatalogItem,
  CreateChannelPayload,
} from "@/types/channel";
import type {
  ClawDispatchResult,
  ClawOutboundPreview,
  ClawQrLoginSession,
  SessionClawBinding,
  UpdateSessionClawBindingPayload,
} from "@/types/claw";

interface UseChannelSessionDockParams {
  sessionId?: string | null;
  enabled?: boolean;
}

export function useChannelSessionDock({
  sessionId,
  enabled = true,
}: UseChannelSessionDockParams) {
  const [platforms, setPlatforms] = useState<ChannelPlatformCatalogItem[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [binding, setBinding] = useState<SessionClawBinding | null>(null);
  const [preview, setPreview] = useState<ClawOutboundPreview | null>(null);
  const [qrLogin, setQrLogin] = useState<ClawQrLoginSession | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isMutating, setIsMutating] = useState(false);
  const [isDispatching, setIsDispatching] = useState(false);
  const [isQrLoginStarting, setIsQrLoginStarting] = useState(false);
  const [isQrLoginPolling, setIsQrLoginPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const qrLoginPollingLockRef = useRef(false);

  const clearState = useCallback(() => {
    setPlatforms([]);
    setChannels([]);
    setBinding(null);
    setPreview(null);
    setQrLogin(null);
    setError(null);
    setNotice(null);
  }, []);

  const reload = useCallback(async () => {
    if (!enabled) {
      clearState();
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const [nextPlatforms, nextChannels] = await Promise.all([
        listChannelPlatforms(),
        listChannels(),
      ]);
      setPlatforms(nextPlatforms);
      setChannels(nextChannels);

      if (sessionId) {
        const [nextBinding, nextPreview] = await Promise.all([
          getSessionClawBinding(sessionId),
          getSessionClawOutboundPreview(sessionId),
        ]);
        setBinding(nextBinding);
        setPreview(nextPreview);
      } else {
        setBinding(null);
        setPreview(null);
      }
    } catch (err) {
      setError(getClawErrorMessage(err, "加载频道状态失败"));
    } finally {
      setIsLoading(false);
    }
  }, [clearState, enabled, sessionId]);

  useEffect(() => {
    if (!enabled) {
      clearState();
      return;
    }
    void reload();
  }, [clearState, enabled, reload]);

  useEffect(() => {
    setQrLogin(null);
  }, [sessionId]);

  useEffect(() => {
    if (!enabled || !sessionId) {
      return;
    }
    const shouldPollRuntime =
      binding?.link_status === "running" || Boolean(binding?.runtime_active);
    if (!shouldPollRuntime) {
      return;
    }
    const intervalMs = binding?.runtime_active ? 5000 : 2000;
    const intervalId = window.setInterval(() => {
      void reload();
    }, intervalMs);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [
    binding?.link_status,
    binding?.runtime_active,
    enabled,
    reload,
    sessionId,
  ]);

  const handleCreateChannel = useCallback(
    async (payload: CreateChannelPayload) => {
      setIsMutating(true);
      setError(null);
      setNotice(null);
      try {
        await createChannel(payload);
        setNotice("频道已保存。");
        await reload();
      } catch (err) {
        setError(getClawErrorMessage(err, "保存频道失败"));
      } finally {
        setIsMutating(false);
      }
    },
    [reload],
  );

  const handleDeleteChannel = useCallback(
    async (channelId: string) => {
      setIsMutating(true);
      setError(null);
      setNotice(null);
      try {
        await deleteChannel(channelId);
        setNotice("频道已删除。");
        await reload();
      } catch (err) {
        setError(getClawErrorMessage(err, "删除频道失败"));
      } finally {
        setIsMutating(false);
      }
    },
    [reload],
  );

  const handleUpdateChannelEnabled = useCallback(
    async (channelId: string, enabled: boolean) => {
      setIsMutating(true);
      setError(null);
      setNotice(null);
      try {
        await updateChannelEnabled(channelId, { enabled });
        setNotice(`频道已${enabled ? "启用" : "禁用"}。`);
        await reload();
      } catch (err) {
        setError(getClawErrorMessage(err, "更新频道状态失败"));
      } finally {
        setIsMutating(false);
      }
    },
    [reload],
  );

  const handleSaveBinding = useCallback(
    async (payload: UpdateSessionClawBindingPayload) => {
      if (!sessionId) {
        return;
      }
      setIsMutating(true);
      setError(null);
      setNotice(null);
      try {
        const nextBinding = await saveSessionClawBinding(sessionId, payload);
        setBinding(nextBinding);
        setNotice("当前会话的频道绑定已保存。");
        setPreview(await getSessionClawOutboundPreview(sessionId));
      } catch (err) {
        setError(getClawErrorMessage(err, "保存频道绑定失败"));
      } finally {
        setIsMutating(false);
      }
    },
    [sessionId],
  );

  const handleClearBinding = useCallback(async () => {
    if (!sessionId) {
      return;
    }
    setIsMutating(true);
    setError(null);
    setNotice(null);
    try {
      const nextBinding = await clearSessionClawBinding(sessionId);
      setBinding(nextBinding);
      setPreview(await getSessionClawOutboundPreview(sessionId));
      setNotice("当前会话的频道绑定已清除。");
    } catch (err) {
      setError(getClawErrorMessage(err, "清除频道绑定失败"));
    } finally {
      setIsMutating(false);
    }
  }, [sessionId]);

  const handleStartLink = useCallback(async () => {
    if (!sessionId) {
      return;
    }
    setIsMutating(true);
    setError(null);
    setNotice(null);
    try {
      const nextBinding = await startSessionClawLink(sessionId);
      setBinding(nextBinding);
      setNotice("频道链接已启动。");
    } catch (err) {
      setError(getClawErrorMessage(err, "启动频道链接失败"));
    } finally {
      setIsMutating(false);
    }
  }, [sessionId]);

  const handleStopLink = useCallback(async () => {
    if (!sessionId) {
      return;
    }
    setIsMutating(true);
    setError(null);
    setNotice(null);
    try {
      const nextBinding = await stopSessionClawLink(sessionId);
      setBinding(nextBinding);
      setNotice("频道链接已停止。");
    } catch (err) {
      setError(getClawErrorMessage(err, "停止频道链接失败"));
    } finally {
      setIsMutating(false);
    }
  }, [sessionId]);

  const handleDispatchLastReply = useCallback(
    async (
      options?: {
        force?: boolean;
        silentDuplicate?: boolean;
        autoTriggered?: boolean;
      },
    ): Promise<ClawDispatchResult | null> => {
      if (!sessionId) {
        return null;
      }
      setIsDispatching(true);
      setError(null);
      if (!options?.autoTriggered) {
        setNotice(null);
      }
      try {
        const result = await dispatchSessionClawLastReply(sessionId, {
          force: options?.force ?? false,
        });
        setBinding(result.binding);
        setPreview(result.preview);
        if (result.dispatched) {
          setNotice("最近回复已同步到远端会话。");
        } else if (!(options?.silentDuplicate && result.reason)) {
          setNotice(result.reason || "当前没有新的可同步回复。");
        }
        return result;
      } catch (err) {
        setError(getClawErrorMessage(err, "同步最近回复失败"));
        return null;
      } finally {
        setIsDispatching(false);
      }
    },
    [sessionId],
  );

  const handleStartQrLogin = useCallback(
    async (platform: string): Promise<ClawQrLoginSession | null> => {
      setIsQrLoginStarting(true);
      setError(null);
      setNotice(null);
      try {
        const result = await startClawQrLogin({
          platform: platform as "weixin" | "feishu" | "dingtalk",
          bot_type: "3",
        });
        setQrLogin(result);
        setNotice(`${platform} 扫码链接已生成，页面会自动检查状态。`);
        return result;
      } catch (err) {
        setError(getClawErrorMessage(err, `创建 ${platform} 扫码链接失败`));
        return null;
      } finally {
        setIsQrLoginStarting(false);
      }
    },
    [],
  );

  const handlePollQrLogin = useCallback(
    async (platform: string): Promise<ClawQrLoginSession | null> => {
      if (!qrLogin?.flow_id || qrLoginPollingLockRef.current) {
        return qrLogin;
      }
      qrLoginPollingLockRef.current = true;
      setIsQrLoginPolling(true);
      setError(null);
      try {
        const result = await pollClawQrLogin(platform, qrLogin.flow_id);
        setQrLogin(result);
        if (result.status === "confirmed") {
          let autoStarted = false;
          const resultChannelId =
            result.connector?.channel_id || result.connector?.connector_id;
          if (
            sessionId &&
            resultChannelId &&
            !(binding?.channel_id || binding?.connector_id)
          ) {
            const nextBinding = await saveSessionClawBinding(sessionId, {
              channel_id: resultChannelId,
              connector_id: resultChannelId,
              chat_id: null,
              chat_label: null,
            });
            setBinding(nextBinding);
            const startedBinding = await startSessionClawLink(sessionId);
            setBinding(startedBinding);
            autoStarted = true;
          }
          await reload();
          setNotice(
            autoStarted
              ? `${platform} 扫码已确认，当前会话已开始监听；第一条消息会自动绑定到这个会话。`
              : result.message || `${platform} 扫码已确认，连接已保存。`,
          );
        } else if (
          result.status === "expired" ||
          Boolean(result.message && result.message.includes("刷新"))
        ) {
          setNotice(result.message || "二维码状态已更新。");
        }
        return result;
      } catch (err) {
        setError(getClawErrorMessage(err, `轮询 ${platform} 扫码状态失败`));
        return null;
      } finally {
        qrLoginPollingLockRef.current = false;
        setIsQrLoginPolling(false);
      }
    },
    [binding?.channel_id, binding?.connector_id, qrLogin, reload, sessionId],
  );

  // 兼容旧名
  const handleClearQrLogin = useCallback(() => {
    setQrLogin(null);
  }, []);

  const handleStartWeixinQrLogin = useCallback(
    async (): Promise<ClawQrLoginSession | null> => handleStartQrLogin("weixin"),
    [handleStartQrLogin],
  );
  const handlePollWeixinQrLogin = useCallback(
    async (): Promise<ClawQrLoginSession | null> => handlePollQrLogin("weixin"),
    [handlePollQrLogin],
  );

  const statusLabel = useMemo(() => {
    switch (binding?.link_status) {
      case "running":
        return binding?.chat_id ? "运行中" : "等待首聊";
      case "error":
        return "异常";
      case "stopped":
        return "已配置";
      case "unconfigured":
      default:
        return "未绑定";
    }
  }, [binding?.link_status, binding?.chat_id]);

  return {
    platforms,
    channels,
    binding,
    preview,
    isLoading,
    isMutating,
    isDispatching,
    qrLogin,
    isQrLoginStarting,
    isQrLoginPolling,
    error,
    notice,
    statusLabel,
    reload,
    handleCreateChannel,
    handleDeleteChannel,
    handleUpdateChannelEnabled,
    handleSaveBinding,
    handleClearBinding,
    handleStartLink,
    handleStopLink,
    handleDispatchLastReply,
    handleStartQrLogin,
    handlePollQrLogin,
    handleClearQrLogin,
    handleStartWeixinQrLogin,
    handlePollWeixinQrLogin,
  };
}
