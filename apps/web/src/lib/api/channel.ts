import { API_ENDPOINTS } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";
import type {
  Channel,
  ChannelEnabledResult,
  ChannelPlatformCatalogItem,
  CreateChannelPayload,
  DeleteChannelResult,
  UpdateChannelEnabledPayload,
  UpdateChannelPayload,
} from "@/types/channel";

export function listChannelPlatforms() {
  return apiRequest<ChannelPlatformCatalogItem[]>(API_ENDPOINTS.CHANNEL_PLATFORMS, {
    cache: "no-store",
  });
}

export function listChannels() {
  return apiRequest<Channel[]>(API_ENDPOINTS.CHANNELS, {
    cache: "no-store",
  });
}

export function getChannel(channelId: string) {
  return apiRequest<Channel>(API_ENDPOINTS.CHANNEL(channelId), {
    cache: "no-store",
  });
}

export function createChannel(payload: CreateChannelPayload) {
  return apiRequest<Channel>(API_ENDPOINTS.CHANNELS, {
    method: "POST",
    body: payload,
  });
}

export function updateChannel(channelId: string, payload: UpdateChannelPayload) {
  return apiRequest<Channel>(API_ENDPOINTS.CHANNEL(channelId), {
    method: "PATCH",
    body: payload,
  });
}

export function updateChannelEnabled(
  channelId: string,
  payload: UpdateChannelEnabledPayload,
) {
  return apiRequest<ChannelEnabledResult>(API_ENDPOINTS.CHANNEL_ENABLED(channelId), {
    method: "PATCH",
    body: payload,
  });
}

export function deleteChannel(channelId: string) {
  return apiRequest<DeleteChannelResult>(API_ENDPOINTS.CHANNEL(channelId), {
    method: "DELETE",
  });
}
