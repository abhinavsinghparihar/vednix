/**
 * Token vault — the ONLY place the access token lives (SPA memory; never
 * localStorage, so a fresh tab means silent /refresh via the httpOnly cookie,
 * and an XSS finding can't exfiltrate a long-lived credential from storage).
 *
 * Responsibilities:
 *  - hold/clear the access token
 *  - single-flight silent refresh (five parallel 401s → ONE /refresh call)
 *  - credentialed apiFetch: Authorization header + cookies + one 401 retry
 *  - CSRF mirror read for the double-submit cookie pair
 */

import { API_BASE, API_BASE_CONFIGURED } from "./config";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

let accessToken: string | null = null;
let csrfAccessToken: string | null = null;
let refreshFlight: Promise<RefreshResult> | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

/** Keep the CSRF nonce in memory for cross-origin SPAs; it is never a login
 * credential and never persisted to localStorage. */
export function setCsrfToken(token: string | null): void {
  csrfAccessToken = token;
}

/** Locally the readable cookie is available; for Vercel → Render, use the
 * nonce returned by the credentialed /api/auth/csrf or auth response. */
export function csrfToken(): string | null {
  if (csrfAccessToken) return csrfAccessToken;
  if (typeof document === "undefined") return null;
  const row = document.cookie.split("; ").find((c) => c.startsWith("vednix_csrf="));
  return row ? decodeURIComponent(row.split("=")[1]) : null;
}

async function parseError(resp: Response): Promise<ApiError> {
  let message = resp.statusText;
  try {
    const body = await resp.json();
    message = body.detail ?? message;
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(resp.status, message);
}

export interface RefreshResult {
  ok: boolean;
  user?: Record<string, unknown>;
  expiresIn?: number;
  csrfToken?: string;
}

/** Single-flight refresh: concurrent callers share one network attempt. */
export function tryRefresh(): Promise<RefreshResult> {
  if (!API_BASE_CONFIGURED) return Promise.resolve({ ok: false });
  refreshFlight ??= (async () => {
    try {
      let csrf = csrfToken();
      if (!csrf) {
        const bootstrap = await fetch(`${API_BASE}/api/auth/csrf`, { credentials: "include" });
        if (!bootstrap.ok) return { ok: false };
        const csrfBody = await bootstrap.json();
        csrf = typeof csrfBody.csrf_token === "string" ? csrfBody.csrf_token : null;
        setCsrfToken(csrf);
      }
      if (!csrf) return { ok: false };
      const resp = await fetch(`${API_BASE}/api/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers: {
          "content-type": "application/json",
          "X-CSRF-Token": csrf,
        },
      });
      if (!resp.ok) {
        setAccessToken(null);
        setCsrfToken(null);
        return { ok: false };
      }
      const body = await resp.json();
      setAccessToken(body.access_token);
      if (typeof body.csrf_token === "string") setCsrfToken(body.csrf_token);
      return { ok: true, user: body.user, expiresIn: body.expires_in };
    } catch {
      return { ok: false };
    } finally {
      setTimeout(() => {
        refreshFlight = null;
      }, 0);
    }
  })();
  return refreshFlight;
}

export async function clearSession(): Promise<void> {
  if (!API_BASE_CONFIGURED) {
    setAccessToken(null);
    setCsrfToken(null);
    return;
  }
  try {
    await fetch(`${API_BASE}/api/auth/logout`, {
      method: "POST",
      credentials: "include",
      headers: {
        "content-type": "application/json",
        ...(csrfToken() ? { "X-CSRF-Token": csrfToken()! } : {}),
      },
    });
  } finally {
    setAccessToken(null);
    setCsrfToken(null);
  }
}

/**
 * Credentialed fetch for every authed API call. On a single 401 it attempts
 * one silent refresh and retries; auth endpoints themselves are exempt
 * (their 401s ARE the answer, not a stale token).
 */
export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
  opts: { retryOn401?: boolean } = {},
): Promise<T> {
  if (!API_BASE_CONFIGURED) {
    throw new ApiError(0, "Backend URL is not configured. Set NEXT_PUBLIC_API_BASE to the Render backend URL and redeploy the frontend.");
  }
  const retry = opts.retryOn401 !== false && !path.startsWith("/api/auth/login")
    && !path.startsWith("/api/auth/register") && !path.startsWith("/api/auth/refresh");

  const make = (): Promise<Response> =>
    fetch(`${API_BASE}${path}`, {
      credentials: "include",
      ...init,
      headers: {
        "content-type": "application/json",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...init.headers,
      },
    });

  let resp = await make();
  if (resp.status === 401 && retry) {
    const r = await tryRefresh();
    if (r.ok) resp = await make();
  }
  if (!resp.ok) throw await parseError(resp);
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}
