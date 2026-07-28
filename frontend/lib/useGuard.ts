/**
 * useRouteGuard — the single routing law of Phase 8:
 *
 *   backend unreachable              → allow (workspace shows its offline state)
 *   setup NOT complete               → /onboarding (except when already there)
 *   /profile, /settings, (any page) without a session
 *                                    → /login?next=… — NO SIGNUP, NO ENTRY:
 *                                      a zero-account machine ("anon") is treated
 *                                      exactly like a locked one
 *   everything else                  → allow (signed-in users roam free)
 *
 * Returns "loading" | "ok" ("loading" also covers in-flight redirects so the
 * page can render a minimal splash instead of flashing protected content).
 */

"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/store/auth";

export function useRouteGuard(opts: { requireAuth: boolean }): "loading" | "ok" {
  const router = useRouter();
  const pathname = usePathname();
  const bootstrap = useAuth((s) => s.bootstrap);
  const [state, setState] = useState<"loading" | "ok">("loading");

  useEffect(() => {
    let live = true;
    void (async () => {
      const status = await bootstrap();
      if (!live) return;
      // unreachable backend sentinel (see store/auth.bootstrap)
      const unreachable = status.active_provider === "Vednix Engine" && !useAuth.getState().onboarding;
      if (unreachable) {
        setState("ok");
        return;
      }
      if (!status.setup_complete && pathname !== "/onboarding") {
        router.replace("/onboarding");
        return;
      }
      const { session } = useAuth.getState();
      const signedIn = session === "authed";
      if (opts.requireAuth && !signedIn) {
        router.replace(`/login?next=${encodeURIComponent(pathname)}`);
        return;
      }
      // no-signup-no-entry: anywhere but the door trio, anon/locked → /login
      if (!signedIn && pathname !== "/login" && pathname !== "/signup" && pathname !== "/onboarding") {
        router.replace("/login");
        return;
      }
      setState("ok");
    })();
    return () => {
      live = false;
    };
    // bootstrap identity is stable (zustand); opts are literals per page
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  return state;
}
