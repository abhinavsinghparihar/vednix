"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/store/auth";

// Guests never download/mount the chat, model discovery or WebSocket client.
const Workspace = dynamic(() => import("@/components/workspace/Workspace"), {
  loading: () => <EntryStatus />,
});

function EntryStatus() {
  return <div role="status" className="flex min-h-dvh items-center justify-center bg-void text-muted">Opening your workspace…</div>;
}

export default function Page() {
  const router = useRouter();
  const session = useAuth((s) => s.session);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let retry: ReturnType<typeof setTimeout>;
    const enter = async () => {
      const status = await useAuth.getState().bootstrap();
      if (cancelled) return;
      const current = useAuth.getState().session;
      if (current === "locked" || current === "anon") {
        router.replace("/login?next=/chat");
      } else if (current === "authed") {
        if (!status.setup_complete) router.replace("/onboarding");
        else setReady(true);
      } else {
        // Cold starts/offline networks are not expired sessions.
        retry = setTimeout(() => void enter(), 3000);
      }
    };
    void enter();
    return () => { cancelled = true; clearTimeout(retry); };
  }, [router]);

  useEffect(() => {
    if (ready && (session === "locked" || session === "anon")) {
      router.replace("/login?next=/chat");
    }
  }, [ready, session, router]);

  if (!ready || session !== "authed") return <EntryStatus />;
  return <Workspace />;
}
