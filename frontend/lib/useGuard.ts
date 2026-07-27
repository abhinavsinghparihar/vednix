/**
 * useRouteGuard — the single routing law of Phase 7:
 *
 *   backend unreachable              → allow (workspace shows offline UI)
 *   setup NOT complete               → /onboarding (except when already there)
 *   /profile, /settings without auth → /login?next=… (guest may NOT pass)
 *   accounts exist, no session       → locked → /login (for guarded routes)
 *   everything else                  → allow (guests can roam /chat & /onboarding)
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
      const unreachable = status.active_provider === "Ollama" && !useAuth.getState().onboarding;
      if (unreachable) {
        setState("ok");
        return;
      }
      if (!status.setup_complete && pathname !== "/onboarding") {
        router.replace("/onboarding");
        return;
      }
      const { session } = useAuth.getState();
      if (opts.requireAuth && session === "locked") {
        router.replace(`/login?next=${encodeURIComponent(pathname)}`);
        return;
      }
      if (session === "locked" && pathname !== "/login" && pathname !== "/signup" && pathname !== "/chat" && pathname !== "/onboarding") {
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
