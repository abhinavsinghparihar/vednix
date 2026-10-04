/**
 * Shared browser API configuration.
 *
 * Browser HTTP requests default to same-origin `/api/*` (proxied by Next.js
 * rewrites) so session refresh cookies remain first-party and are not dropped
 * by third-party cookie restrictions. WebSockets connect to the configured
 * backend origin with an authenticated token query parameter.
 */

const host = typeof window !== "undefined" ? window.location.hostname : "";
function isLoopbackHost(hostname: string): boolean {
  const normalized = hostname.replace(/^\[|\]$/g, "").toLowerCase();
  return normalized === "localhost" || normalized === "127.0.0.1" || normalized === "::1";
}
const isLoopback = host ? isLoopbackHost(host) : process.env.NODE_ENV === "development";
const apiHost = host.includes(":") && !host.startsWith("[") ? `[${host}]` : host || "localhost";
const rawApiBase = process.env.NEXT_PUBLIC_API_BASE?.trim().replace(/\/$/, "") ?? "";
const PRODUCTION_API_BASE = "https://vednix.onrender.com";
const PRODUCTION_WS_BASE = "wss://vednix.onrender.com/ws/chat";

function isSafeApiBase(value: string): boolean {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol)
      && (isLoopback || !isLoopbackHost(url.hostname));
  } catch {
    return false;
  }
}

const configuredApiBase = isSafeApiBase(rawApiBase) ? rawApiBase : "";
export const DIRECT_API_BASE = configuredApiBase || (isLoopback ? `http://${apiHost}:8000` : PRODUCTION_API_BASE);
const useDirectApi = process.env.NEXT_PUBLIC_DIRECT_API === "true";

// Empty string in the browser routes `/api/*` through Next.js's same-origin proxy.
export const API_BASE = typeof window !== "undefined" && !useDirectApi ? "" : DIRECT_API_BASE;
export const API_BASE_CONFIGURED = Boolean(DIRECT_API_BASE);

function deriveWebSocketUrl(apiBase: string): string {
  if (!apiBase) return "";
  try {
    const url = new URL(apiBase);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    url.pathname = `${url.pathname.replace(/\/$/, "")}/ws/chat`;
    url.search = "";
    url.hash = "";
    return url.toString();
  } catch {
    return "";
  }
}

const rawWsBase = process.env.NEXT_PUBLIC_WS_BASE?.trim() ?? "";
function isSafeWebSocketBase(value: string): boolean {
  try {
    const url = new URL(value);
    return ["ws:", "wss:"].includes(url.protocol)
      && (isLoopback || !isLoopbackHost(url.hostname));
  } catch {
    return false;
  }
}
const configuredWsBase = isSafeWebSocketBase(rawWsBase) ? rawWsBase : "";
export const WS_URL = configuredWsBase || (
  configuredApiBase || isLoopback ? deriveWebSocketUrl(DIRECT_API_BASE) : PRODUCTION_WS_BASE
);
