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
import { getAccessToken, tryRefresh } from "@/lib/tokenVault";

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

export const useAuth = create<AuthState>((set, get) => ({
  user: null,
  session: "unknown",
  onboarding: null,
  checked: false,

  bootstrap: async () => {
    let status: OnboardingStatus;
    try {
      status = await onboardingApi.status();
    } catch {
      // backend unreachable: stay "unknown", the workspace shows its own
      // backend-offline UI — a wrong redirect would be worse
      set({ checked: true });
      return {
        setup_complete: true, mode: null,
        auth_enabled: false, providers: [], active_provider: "unavailable", chat_available: false,
      };
    }
    let session: SessionState = "anon";
    let user: UserOut | null = null;
    if (status.auth_enabled) {
      let transient = false;
      if (getAccessToken()) {
        try {
          user = await authApi.me();
        } catch {
          user = null;
        }
      }
      if (!user) {
        const r = await tryRefresh();
        if (r.ok) user = (r.user as unknown as UserOut) ?? null;
        else if (r.transient) transient = true;
      }
      // A transient failure is never a sign-out: stay "unknown" so the route
      // guard retries while the device's long-lived session is still valid.
      session = user ? "authed" : transient ? "unknown" : "locked";
    }
    set({ onboarding: status, session, user, checked: true });
    return status;
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
