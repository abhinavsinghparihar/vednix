/**
 * Auth & entry-state store — ONE place answering three questions:
 *   1. Has this machine finished first-run setup?      (onboarding)
 *   2. Is anyone signed in, must anyone be?            (auth enabled + user)
 *   3. Which run mode is the shell in?                 (free|cloud|guest|demo)
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

type SessionState = "unknown" | "guest" | "authed" | "locked";
//   unknown : not bootstrapped yet
//   guest   : no account needed & none signed in (open machine, or guest mode)
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
        setup_complete: true, mode: null, demo_active: false,
        auth_enabled: false, ollama_running: false, active_provider: "Ollama",
      };
    }
    let session: SessionState = "guest";
    let user: UserOut | null = null;
    if (status.auth_enabled) {
      if (getAccessToken()) {
        try {
          user = await authApi.me();
        } catch {
          user = null;
        }
      }
      if (!user) {
        const r = await tryRefresh();
        user = r.ok ? ((r.user as unknown as UserOut) ?? null) : null;
      }
      session = user ? "authed" : "locked";
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
    set({ user: null, session: authEnabled ? "locked" : "guest" });
  },
}));
