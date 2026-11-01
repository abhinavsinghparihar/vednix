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
  /** The backend was unreachable or hiccuped — this is NOT a sign-out. */
  transient?: boolean;
}

type AttemptResult = RefreshResult & { retryable?: boolean; authFailed?: boolean };

async function performRefresh(): Promise<AttemptResult> {
  try {
    // Re-read the shared cookie's nonce, not a stale module-memory copy
    // from before another tab rotated it. Also avoid two failing refreshes
    // (and the retry delay) for a genuinely new visitor.
    const bootstrap = await fetch(`${API_BASE}/api/auth/csrf`, {
      credentials: "include", cache: "no-store", signal: AbortSignal.timeout(10000),
    });
    if (!bootstrap.ok) return { ok: false, transient: true };
    const csrfBody = await bootstrap.json();
    if (csrfBody.has_session === false) return { ok: false, authFailed: true };
    const csrf = typeof csrfBody.csrf_token === "string" ? csrfBody.csrf_token : null;
    setCsrfToken(csrf);
    if (!csrf) return { ok: false, transient: true };
    const resp = await fetch(`${API_BASE}/api/auth/refresh`, {
      method: "POST",
      credentials: "include",
      signal: AbortSignal.timeout(10000),
      headers: {
        "content-type": "application/json",
        "X-CSRF-Token": csrf,
      },
    });
    if (resp.status === 401) {
      // The session itself is gone — but a second tab may have rotated the
      // shared cookie microseconds ago, so retrying once is always worth it.
      return { ok: false, retryable: true, authFailed: true };
    }
    if (!resp.ok) {
      // 403 here is usually a stale CSRF mirror, 429/5xx a throttled or
      // restarting backend. None of those mean "signed out".
      return { ok: false, retryable: true, transient: true };
    }
    const body = await resp.json();
    setAccessToken(body.access_token);
    if (typeof body.csrf_token === "string") setCsrfToken(body.csrf_token);
    return { ok: true, user: body.user, expiresIn: body.expires_in };
  } catch {
    return { ok: false, transient: true };
  }
}

/**
 * Single-flight refresh: concurrent callers share one network attempt.
 *
 * "Stay signed in" needs one guarantee from this function: only a real 401
 * (after one retry, which absorbs a rotation made by another tab) may clear
 * the session. A network blip, a 5xx, or a stale CSRF mirror is reported as
 * `transient` and leaves the stored session untouched, so the UI keeps the
 * device signed in instead of bouncing the user to the lock screen.
 */
export function tryRefresh(): Promise<RefreshResult> {
  if (!API_BASE_CONFIGURED) return Promise.resolve({ ok: false });
  const refresh = async (): Promise<RefreshResult> => {
    try {
      let result = await performRefresh();
      if (!result.ok && result.retryable) {
        // Give the cookie jar a beat: another tab's rotation may be landing.
        await new Promise((resolve) => setTimeout(resolve, 400));
        result = await performRefresh();
      }
      if (!result.ok && result.authFailed) {
        setAccessToken(null);
        setCsrfToken(null);
        return { ok: false };
      }
      if (!result.ok) return { ok: false, transient: true };
      return result;
    } finally {
      setTimeout(() => {
        refreshFlight = null;
      }, 0);
    }
  };
  // The cookie jar is shared by tabs. Serialize rotations across tabs too,
  // otherwise the slower response can overwrite a newer refresh credential.
  refreshFlight ??= (async () => {
    if (typeof navigator !== "undefined" && navigator.locks) {
      return await navigator.locks.request("vednix.session-refresh", refresh);
    }
    return await refresh();
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
      cache: "no-store",
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
