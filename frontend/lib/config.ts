/**
 * Shared browser API configuration.
 *
 * Local browser development pairs its host with backend :8000. Production must
 * set NEXT_PUBLIC_API_BASE to the Render service URL; the old production
 * fallback pointed Vercel browsers at their own localhost and could never work.
 */

const host = typeof window !== "undefined" ? window.location.hostname : "";
const isLoopback = host === "localhost" || host === "127.0.0.1";
const configuredApiBase = process.env.NEXT_PUBLIC_API_BASE?.trim().replace(/\/$/, "") ?? "";

export const API_BASE = configuredApiBase || (isLoopback ? `http://${host}:8000` : "");
export const API_BASE_CONFIGURED = Boolean(configuredApiBase || isLoopback);

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

export const WS_URL =
  process.env.NEXT_PUBLIC_WS_BASE?.trim() || deriveWebSocketUrl(API_BASE);
