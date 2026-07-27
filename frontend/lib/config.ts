/**
 * Shared runtime configuration — pulled out of api.ts so the token vault and
 * the REST client can both read endpoints without an import cycle.
 */

// Host-derived API base: if the app is opened as localhost:3000 the backend
// is localhost:8000; as 127.0.0.1:3000 → 127.0.0.1:8000. Same-host matters
// since Phase 7: the auth refresh cookie is SameSite=Lax, and "localhost" vs
// "127.0.0.1" are DIFFERENT sites — only a same-host pairing lets the cookie
// flow. NEXT_PUBLIC_API_BASE still overrides everything (real deployments).
const _host = typeof window !== "undefined" ? window.location.hostname : "127.0.0.1";
const _loopback = _host === "localhost" || _host === "127.0.0.1";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? (_loopback ? `http://${_host}:8000` : "http://127.0.0.1:8000");

export const WS_URL =
  process.env.NEXT_PUBLIC_WS_BASE ??
  (_loopback ? `ws://${_host}:8000/ws/chat` : "ws://127.0.0.1:8000/ws/chat");
