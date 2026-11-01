/**
 * Auth & entry-state store — ONE place answering three questions:
 *   1. Has this machine finished first-run setup?      (onboarding)
 *   2. Is anyone signed in, must anyone be?            (auth enabled + user)
 *   3. Which workspace mode is the shell in?            (provider-backed cloud)
 *
 * Route guards consume `bootstrap()`; pages consume the flags. The access
 * token itself never lives here — it lives in the tokenVault (module memory).
 */

"use client";

import { create } from "zustand";
import {
  authApi,
  onboardingApi,
  type OnboardingStatus,
  type UserOut,
} from "@/lib/authApi";
import { ApiError, getAccessToken, tryRefresh } from "@/lib/tokenVault";

type SessionState = "unknown" | "anon" | "authed" | "locked";
//   unknown : not bootstrapped yet (or the silent refresh hiccuped — the
//             device stays signed in and the guard retries instead of
//             treating a network blip as a sign-out)
//   anon    : zero accounts on this machine & nobody signed in — treated
//             like locked for protected routes (NO SIGNUP, NO ENTRY)
//   authed  : signed in
//   locked  : accounts exist AND no valid session → route to /login

interface AuthState {
  user: UserOut | null;
  session: SessionState;
  onboarding: OnboardingStatus | null;
  checked: boolean; // bootstrap ran at least once
  bootstrap: () => Promise<OnboardingStatus>;
  refreshOnboarding: () => Promise<void>;
  setUser: (user: UserOut | null) => void;
  signOut: () => Promise<void>;
}

let bootstrapFlight: Promise<OnboardingStatus> | null = null;

export const useAuth = create<AuthState>((set, get) => ({
  user: null,
  session: "unknown",
  onboarding: null,
  checked: false,

  bootstrap: () => {
    if (bootstrapFlight) return bootstrapFlight;
    bootstrapFlight = (async () => {
      const fallback: OnboardingStatus = get().onboarding ?? {
        setup_complete: true, mode: null,
        auth_enabled: true, providers: [], active_provider: "unavailable", chat_available: false,
      };
      let user = getAccessToken() ? get().user : null;
      let transient = false;
      if (!user && getAccessToken()) {
        try {
          user = await authApi.me();
        } catch (error) {
          transient = !(error instanceof ApiError && error.status === 401);
        }
      }
      if (!user && !transient) {
        const result = await tryRefresh();
        if (result.ok) user = (result.user as unknown as UserOut) ?? null;
        else transient = Boolean(result.transient);
      }
      // Resolve the session before onboarding/provider work. No session means
      // the login screen can open without waiting for the workspace services.
      set({ user, session: user ? "authed" : transient ? "unknown" : "locked", checked: true });
      if (!user) return fallback;
      try {
        const status = await onboardingApi.status();
        set({ onboarding: status });
        return status;
      } catch {
        // A valid session survives an unavailable onboarding endpoint.
        return fallback;
      }
    })().finally(() => { bootstrapFlight = null; });
    return bootstrapFlight;
  },

  refreshOnboarding: async () => {
    try {
      set({ onboarding: await onboardingApi.status() });
    } catch {
      /* offline: keep stale flags */
    }
  },

  setUser: (user) => set({ user, session: user ? "authed" : get().session }),

  signOut: async () => {
    await authApi.logout();
    const authEnabled = get().onboarding?.auth_enabled ?? false;
    set({ user: null, session: authEnabled ? "locked" : "anon" });
  },
}));
