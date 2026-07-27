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

import { API_BASE } from "./config";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

let accessToken: string | null = null;
let refreshFlight: Promise<RefreshResult> | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

/** The CSRF cookie is deliberately not httpOnly — the SPA mirrors its value
 * into the X-CSRF-Token header on cookie-bearing calls (double-submit). */
export function csrfToken(): string | null {
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
}

/** Single-flight refresh: concurrent callers share one network attempt. */
export function tryRefresh(): Promise<RefreshResult> {
  refreshFlight ??= (async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers: {
          "content-type": "application/json",
          ...(csrfToken() ? { "X-CSRF-Token": csrfToken()! } : {}),
        },
      });
      if (!resp.ok) {
        setAccessToken(null);
        return { ok: false };
      }
      const body = await resp.json();
      setAccessToken(body.access_token);
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
