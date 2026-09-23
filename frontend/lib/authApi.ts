/**
 * Typed client for the Phase-7 APIs: auth sessions, onboarding, providers,
 * and machine status. All requests ride the token vault (memory-held access
 * token, single-flight refresh, credentialed fetch, CSRF mirror).
 */

import { API_BASE, API_BASE_CONFIGURED } from "./config";
import { apiFetch, csrfToken, setAccessToken, setCsrfToken } from "./tokenVault";

// ---------------------------------------------------------------------------
// Types (mirror backend/api schemas)
// ---------------------------------------------------------------------------

export interface UserOut {
  id: string;
  username: string;
  display_name: string;
  email: string | null;
  role: string;
  avatar_color: string;
  theme: string;
  language: string;
  created_at: string;
}

export interface SessionInfo {
  id: string;
  device_label: string;
  remember: boolean;
  current: boolean;
  last_seen_at: string;
  created_at: string;
}

export interface OnboardingStatus {
  setup_complete: boolean;
  mode: "free" | "cloud" | null;
  auth_enabled: boolean;
  ollama_running: boolean;
  active_provider: string;
}

export interface LocalModelRec {
  tag: string;
  tier: string;
  best_for: string;
  ram_gb: number;
  disk_gb: number;
  speed: string;
  quality: string;
  pull: string;
}

export interface ProviderCatalogItem {
  id: string;
  label: string;
  kind: string;
  needs_key: boolean;
  default_model: string;
  key_url: string;
  docs_url: string;
  vision: boolean;
  models: string[];
  blurb: string;
  base_url: string;
}

export interface ProviderConfig {
  provider: string;
  label: string;
  enabled: boolean;
  configured?: boolean;
  has_key: boolean;
  key_hint: string | null;
  verified?: boolean;
  status: "unverified" | "connected" | "failed" | "unavailable";
  status_detail: string | null;
  model_override: string | null;
  base_url_override: string | null;
  priority: number | null;
  verified_at: string | null;
}

export interface VerifyResult {
  provider: string;
  connected: boolean;
  enabled?: boolean;
  verified?: boolean;
  verification_model?: string | null;
  model_available?: boolean;
  running?: boolean | null;
  detail: string;
  models: string[];
}

export interface SystemStatus {
  db_bytes: number;
  uploads_bytes: number;
  counts: { conversations: number; messages: number; memories: number };
  cpu: { cores: number; load1: number | null };
  backend_online?: boolean;
  chat_available?: boolean;
  provider_configured?: boolean;
  provider_verified?: boolean;
  model_available?: boolean;
  providers?: {
    provider: string; label: string; configured: boolean; verified: boolean;
    enabled: boolean; status: string; status_detail: string | null;
    model: string; model_available: boolean; chat_available: boolean;
  }[];
  ollama: {
    running: boolean;
    models_running: { name: string; size: number; size_vram: number }[];
    host: string;
    models?: string[];
    default_model?: string;
    model_available?: boolean;
    chat_available?: boolean;
  };
  active_provider: string;
  default_model: string;
}

// ---------------------------------------------------------------------------
// auth
// ---------------------------------------------------------------------------

interface TokenPayload {
  access_token: string;
  expires_in: number;
  csrf_token?: string;
  user: UserOut;
}

export const authApi = {
  async register(input: { username: string; password: string; display_name?: string; email?: string }): Promise<UserOut> {
    const body = await apiFetch<TokenPayload>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(input),
    });
    setAccessToken(body.access_token);
    if (typeof body.csrf_token === "string") setCsrfToken(body.csrf_token);
    return body.user;
  },

  async login(input: { username: string; password: string; remember: boolean; device_label?: string }): Promise<UserOut> {
    const body = await apiFetch<TokenPayload>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(input),
    });
    setAccessToken(body.access_token);
    if (typeof body.csrf_token === "string") setCsrfToken(body.csrf_token);
    return body.user;
  },

  async requestEmailOtp(email: string): Promise<{ ok: boolean; message: string }> {
    return apiFetch<{ ok: boolean; message: string }>("/api/auth/email/request", {
      method: "POST", body: JSON.stringify({ email }),
    }, { retryOn401: false });
  },

  async verifyEmailOtp(email: string, code: string, remember = true): Promise<UserOut> {
    const body = await apiFetch<TokenPayload>("/api/auth/email/verify", {
      method: "POST", body: JSON.stringify({ email, code, remember }),
    }, { retryOn401: false });
    setAccessToken(body.access_token);
    if (typeof body.csrf_token === "string") setCsrfToken(body.csrf_token);
    return body.user;
  },

  me: () => apiFetch<UserOut>("/api/auth/me"),

  updateMe: (patch: Partial<Pick<UserOut, "display_name" | "avatar_color" | "theme" | "language">>) =>
    apiFetch<UserOut>("/api/auth/me", { method: "PATCH", body: JSON.stringify(patch) }),

  changePassword: (current_password: string, new_password: string) =>
    apiFetch<void>("/api/auth/me/password", {
      method: "POST",
      body: JSON.stringify({ current_password, new_password }),
    }),

  sessions: () => apiFetch<SessionInfo[]>("/api/auth/sessions"),

  revokeSession: (id: string) => apiFetch<void>(`/api/auth/sessions/${id}`, { method: "DELETE" }),

  async logout(): Promise<void> {
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
  },
};

// ---------------------------------------------------------------------------
// onboarding + system + providers
// ---------------------------------------------------------------------------

export const onboardingApi = {
  status: () => apiFetch<OnboardingStatus>("/api/onboarding/status", {}, { retryOn401: false }),
  chooseMode: (mode: "free" | "cloud") =>
    apiFetch<OnboardingStatus>("/api/onboarding/mode", { method: "POST", body: JSON.stringify({ mode }) }),
  localModels: () => apiFetch<{ models: LocalModelRec[] }>("/api/onboarding/local-models"),
  wipeData: () =>
    apiFetch<{ conversations_deleted: number; memories_deleted: number }>(
      "/api/onboarding/wipe-data", { method: "POST" },
    ),
};

export const systemApi = {
  status: () => apiFetch<SystemStatus>("/api/system/status"),
  defaultModel: () => apiFetch<{ model: string; saved: boolean }>("/api/providers/ollama/default-model"),
  setDefaultModel: (model: string) =>
    apiFetch<{ model: string; saved: boolean }>("/api/providers/ollama/default-model", {
      method: "PUT",
      body: JSON.stringify({ model }),
    }),
};

export interface AdminUser {
  id: string;
  username: string;
  display_name: string;
  email: string | null;
  role: "owner" | "member";
  theme: string;
  language: string;
  created_at: string | null;
  live_sessions: number;
}

export const adminApi = {
  users: () => apiFetch<{ users: AdminUser[] }>("/api/admin/users"),
  resetPassword: (id: string, password: string) =>
    apiFetch<{ ok: boolean }>(`/api/admin/users/${id}/password`, {
      method: "POST", body: JSON.stringify({ password }),
    }),
  revokeSessions: (id: string) =>
    apiFetch<{ revoked: number }>(`/api/admin/users/${id}/revoke-sessions`, { method: "POST" }),
  deleteUser: (id: string) =>
    apiFetch<{ ok: boolean }>(`/api/admin/users/${id}`, { method: "DELETE" }),
};

export const providerApi = {
  catalog: () => apiFetch<{ providers: ProviderCatalogItem[] }>("/api/providers/catalog"),
  configured: () => apiFetch<{ providers: ProviderConfig[]; priority: string[] }>("/api/providers"),
  saveKey: (provider: string, input: { api_key?: string; base_url?: string; model?: string }) =>
    apiFetch<ProviderConfig>(`/api/providers/${provider}/key`, {
      method: "PUT",
      body: JSON.stringify(input),
    }),
  removeKey: (provider: string) => apiFetch<void>(`/api/providers/${provider}/key`, { method: "DELETE" }),
  verify: (provider: string) => apiFetch<VerifyResult>(`/api/providers/${provider}/verify`, { method: "POST" }),
  toggle: (provider: string, enabled: boolean) =>
    apiFetch(`/api/providers/${provider}/toggle`, { method: "POST", body: JSON.stringify({ enabled }) }),
  setPriority: (order: string[]) =>
    apiFetch<{ priority: string[] }>("/api/providers/priority", { method: "PUT", body: JSON.stringify({ order }) }),
  ollamaStatus: () =>
    apiFetch<{ running: boolean; models: string[]; default_model: string; model_available: boolean; chat_available: boolean; detail: string }>("/api/providers/ollama/status"),
};
