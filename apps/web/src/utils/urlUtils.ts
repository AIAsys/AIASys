import { API_BASE_URL } from "@/config/api";

const DEFAULT_LOCALHOST_API = "http://localhost:13001";
const PLACEHOLDER_ACCESS_TOKENS = new Set(["local-jwt-token", "none-mode-token"]);

function isUsableAccessToken(token?: string): token is string {
  if (!token) {
    return false;
  }

  return !PLACEHOLDER_ACCESS_TOKENS.has(token.trim());
}

/**
 * Appends the access token to the URL as a query parameter if it's an API URL.
 *
 * @param url The URL to append the token to.
 * @param token The access token.
 * @returns The URL with the access token appended if applicable.
 */
export const appendAccessToken = (url: string, token?: string): string => {
  if (!isUsableAccessToken(token) || !url) return url;

  // Check if it's an API URL (starts with /api/files or absolute URL to API)
  // Adjust logic based on your specific API URL patterns
  const isApiUrl = url.startsWith("/api/files") || url.includes("/api/files");

  if (!isApiUrl) return url;

  try {
    // Handle relative URLs by providing a base
    const urlObj = new URL(url, window.location.origin);

    // Only append if not already present
    if (!urlObj.searchParams.has("access_token")) {
      urlObj.searchParams.set("access_token", token);
    }

    // Return relative path if it was relative, otherwise full URL
    if (url.startsWith("/")) {
      return urlObj.pathname + urlObj.search + urlObj.hash;
    }
    return urlObj.toString();
  } catch {
    // If URL parsing fails, return original
    return url;
  }
};

/**
 * Helper to strip the base URL from a full URL if it matches.
 * Useful for ensuring requests go through the proxy when we have absolute URLs.
 */
export function stripApiBaseUrl(url: string): string {
  if (!url) return "";

  if (url.startsWith(DEFAULT_LOCALHOST_API)) {
    return url.replace(DEFAULT_LOCALHOST_API, "");
  }

  if (API_BASE_URL && url.startsWith(API_BASE_URL)) {
    return url.replace(API_BASE_URL, "");
  }
  return url;
}
