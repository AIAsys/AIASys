import { API_ENDPOINTS } from "@/config/api";
import { apiRequest, ApiRequestError } from "@/lib/api/httpClient";
import type {
  ChannelBindingsResponse,
  ClawDispatchResult,
  ClawGatewaySession,
  ClawOutboundPreview,
  ClawPlatformCatalogItem,
  ClawQrLoginSession,
  DispatchClawReplyPayload,
  SessionClawBinding,
  StartClawQrLoginPayload,
  UpdateSessionClawBindingPayload,
} from "@/types/claw";

export function getClawErrorMessage(error: unknown, actionLabel?: string): string {
  let message = "请求失败";
  if (error instanceof ApiRequestError) {
    message = error.message;
  } else if (error instanceof Error && error.message) {
    message = error.message;
  } else if (
    error &&
    typeof error === "object" &&
    "message" in error &&
    typeof (error as { message?: unknown }).message === "string"
  ) {
    message = (error as { message: string }).message;
  } else {
    message = String(error);
  }
  return actionLabel ? `${actionLabel}：${message}` : message;
}

export function listClawGatewaySessions() {
  return apiRequest<ClawGatewaySession[]>(API_ENDPOINTS.CLAW_GATEWAY_SESSIONS, {
    cache: "no-store",
  });
}

export function listClawPlatforms() {
  return apiRequest<ClawPlatformCatalogItem[]>(API_ENDPOINTS.CLAW_PLATFORMS, {
    cache: "no-store",
  });
}

export function startClawQrLogin(payload: StartClawQrLoginPayload) {
  return apiRequest<ClawQrLoginSession>(
    API_ENDPOINTS.CLAW_QR_LOGIN_START(payload.platform),
    {
      method: "POST",
      body: payload,
    },
  );
}

export function pollClawQrLogin(platform: string, flowId: string) {
  return apiRequest<ClawQrLoginSession>(
    API_ENDPOINTS.CLAW_QR_LOGIN_POLL(platform, flowId),
    {
      method: "POST",
    },
  );
}

// 兼容旧名
export function startClawWeixinQrLogin(payload: StartClawQrLoginPayload = { platform: "weixin" }) {
  return startClawQrLogin(payload);
}

export function pollClawWeixinQrLogin(flowId: string) {
  return pollClawQrLogin("weixin", flowId);
}

export function getSessionClawBinding(sessionId: string) {
  return apiRequest<SessionClawBinding>(API_ENDPOINTS.CLAW_SESSION_BINDING(sessionId), {
    cache: "no-store",
  });
}

export function saveSessionClawBinding(
  sessionId: string,
  payload: UpdateSessionClawBindingPayload,
) {
  return apiRequest<SessionClawBinding>(API_ENDPOINTS.CLAW_SESSION_BINDING(sessionId), {
    method: "PUT",
    body: payload,
  });
}

export function clearSessionClawBinding(sessionId: string) {
  return apiRequest<SessionClawBinding>(API_ENDPOINTS.CLAW_SESSION_BINDING(sessionId), {
    method: "DELETE",
  });
}

export function startSessionClawLink(sessionId: string) {
  return apiRequest<SessionClawBinding>(API_ENDPOINTS.CLAW_SESSION_START(sessionId), {
    method: "POST",
  });
}

export function stopSessionClawLink(sessionId: string) {
  return apiRequest<SessionClawBinding>(API_ENDPOINTS.CLAW_SESSION_STOP(sessionId), {
    method: "POST",
  });
}

export function getSessionClawOutboundPreview(sessionId: string) {
  return apiRequest<ClawOutboundPreview>(API_ENDPOINTS.CLAW_SESSION_OUTBOUND_PREVIEW(sessionId), {
    cache: "no-store",
  });
}

export function dispatchSessionClawLastReply(
  sessionId: string,
  payload: DispatchClawReplyPayload = {},
) {
  return apiRequest<ClawDispatchResult>(
    API_ENDPOINTS.CLAW_SESSION_DISPATCH_LAST_REPLY(sessionId),
    {
      method: "POST",
      body: payload,
    },
  );
}

export function getChannelClawBindings(channelId: string) {
  return apiRequest<ChannelBindingsResponse>(
    API_ENDPOINTS.CLAW_CHANNEL_BINDINGS(channelId),
    {
      cache: "no-store",
    },
  );
}
