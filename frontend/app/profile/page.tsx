/**
 * /profile — who you are on this machine: avatar monogram, username, email,
 * membership (owner/member), the AI provider & local model currently live,
 * honest machine stats (db/uploads bytes, counts, CPU, Engine VRAM residency),
 * signed-in devices with revoke, password change, and sign-out.
 * No signup, no entry — this page only exists behind a session.
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  Activity, ArrowLeft, CheckCircle2, Cpu, Database, HardDrive, KeyRound, Loader2, LogOut,
  MonitorSmartphone, ShieldCheck, Trash2, XCircle,
} from "lucide-react";
import {
  authApi, systemApi, type SessionInfo, type SystemStatus,
} from "@/lib/authApi";
import { ApiError } from "@/lib/tokenVault";
import { useAuth } from "@/store/auth";
import { useRouteGuard } from "@/lib/useGuard";
import { NeuralBackground } from "@/components/background/NeuralBackground";
import { MouseGlow } from "@/components/background/MouseGlow";
import { Signature } from "@/components/brand/Signature";
import { ThemeToggle } from "@/components/brand/ThemeToggle";
import { AuthError, AuthSubmit, PasswordField } from "@/components/auth/fields";
import { Button } from "@/components/ui/primitives";
import { cn, EASE_CURVE } from "@/lib/utils";

function humanBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}

function Section({ title, icon: Icon, children, delay = 0 }: {
  title: string; icon: typeof Cpu; children: React.ReactNode; delay?: number;
}) {
  return (
    <motion.section
      className="glass-strong rounded-3xl p-6"
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.55, ease: EASE_CURVE }}
    >
      <h2 className="mb-4 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.25em] text-faint">
        <Icon className="h-3.5 w-3.5 text-gold" /> {title}
      </h2>
      {children}
    </motion.section>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="glass rounded-2xl p-4">
      <p className="font-mono text-[9px] uppercase tracking-[0.2em] text-faint">{label}</p>
      <p className="mt-1.5 font-display text-xl font-bold text-cream">{value}</p>
      {sub && <p className="mt-0.5 text-[11px] text-faint">{sub}</p>}
    </div>
  );
}

function ProfileInner() {
  const router = useRouter();
  const user = useAuth((s) => s.user);
  const onboarding = useAuth((s) => s.onboarding);
  const signOut = useAuth((s) => s.signOut);

  const [sys, setSys] = useState<SystemStatus | null>(null);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [pw, setPw] = useState({ current: "", next: "", confirm: "" });
  const [pwState, setPwState] = useState<"idle" | "busy" | "ok" | "err">("idle");
  const [pwError, setPwError] = useState<string | null>(null);
  const [signingOut, setSigningOut] = useState(false);

  const load = useCallback(async () => {
    try {
      setSys(await systemApi.status());
    } catch { /* offline */ }
    if (useAuth.getState().user) {
      try {
        setSessions(await authApi.sessions());
      } catch { /* locked */ }
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const changePassword = async () => {
    if (pw.next !== pw.confirm) {
      setPwError("New passwords don't match.");
      return;
    }
    setPwState("busy");
    setPwError(null);
    try {
      await authApi.changePassword(pw.current, pw.next);
      setPwState("ok");
      // every device incl. this one was revoked — return to the lock screen
      setTimeout(() => router.replace("/login"), 1200);
    } catch (err) {
      setPwError(err instanceof ApiError ? err.message : "Could not change password.");
      setPwState("err");
    }
  };

  const revoke = async (id: string) => {
    try {
      await authApi.revokeSession(id);
      setSessions((s) => s.filter((x) => x.id !== id));
    } catch { /* keep list */ }
  };

  const doSignOut = async () => {
    setSigningOut(true);
    await signOut();
    router.replace(useAuth.getState().session === "locked" ? "/login" : "/chat");
  };

  const counts = sys?.counts;
  return (
    <main className="relative min-h-dvh overflow-hidden bg-void text-cream">
      <NeuralBackground />
      <MouseGlow />
      <div className="absolute right-5 top-5 z-20"><ThemeToggle /></div>

      <div className="relative z-10 mx-auto max-w-3xl px-5 pb-16 pt-8">
        <Link href="/chat" className="mb-6 inline-flex items-center gap-2 text-xs text-faint transition-colors hover:text-gold-bright">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to workspace
        </Link>

        {/* --- identity hero ------------------------------------------------ */}
        <motion.header
          className="glass-strong mb-5 flex flex-wrap items-center gap-5 rounded-3xl p-7"
          initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: EASE_CURVE }}
        >
          <span className="flex h-20 w-20 items-center justify-center rounded-3xl border border-gold/40 bg-gradient-to-br from-gold/25 to-ember/10 font-display text-3xl font-extrabold text-gold-bright shadow-glow-gold">
            {(user?.display_name ?? "V").slice(0, 1).toUpperCase()}
          </span>
          <div className="min-w-0">
            <h1 className="truncate font-display text-3xl font-extrabold tracking-tight text-cream">
              {user?.display_name ?? "…"}
            </h1>
            <p className="text-sm text-muted">
              {user ? `@${user.username}${user.email ? ` · ${user.email}` : ""}` : "Loading your identity…"}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className={cn(
                "rounded-md px-2 py-1 font-mono text-[9px] uppercase tracking-[0.18em]",
                user?.role === "owner" ? "bg-gold/20 text-gold-bright" : "bg-white/[0.06] text-muted",
              )}>
                {user ? (user.role === "owner" ? "Owner membership" : "Member") : "…"}
              </span>
              <span className="rounded-md bg-white/[0.06] px-2 py-1 font-mono text-[9px] uppercase tracking-[0.18em] text-muted">
                {sys?.active_provider ?? onboarding?.active_provider ?? "Vednix Engine"}
              </span>
              <span className="rounded-md bg-white/[0.06] px-2 py-1 font-mono text-[9px] uppercase tracking-[0.18em] text-muted">
                model · {sys?.default_model ?? "—"}
              </span>
            </div>
          </div>
          <div className="ml-auto">
            <Button variant="subtle" onClick={() => void doSignOut()} disabled={signingOut}>
              {signingOut ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogOut className="h-4 w-4" />}
              Sign out
            </Button>
          </div>
        </motion.header>

        {/* --- machine stats ------------------------------------------------- */}
        <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { label: "Conversations", value: String(counts?.conversations ?? "—"), icon: Activity },
            { label: "Memories", value: String(counts?.memories ?? "—"), icon: ShieldCheck },
            { label: "Database", value: sys ? humanBytes(sys.db_bytes) : "—", icon: Database },
            { label: "Files stored", value: sys ? humanBytes(sys.uploads_bytes) : "—", icon: HardDrive },
          ].map((s, i) => (
            <motion.div key={s.label} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 + i * 0.07, duration: 0.5 }}>
              <Stat label={s.label} value={s.value} sub={undefined} />
            </motion.div>
          ))}
        </div>

        <div className="space-y-5">
          <Section title="Compute" icon={Cpu} delay={0.2}>
            <div className="flex flex-wrap items-center gap-3 text-[13px] text-muted">
              <span className="glass rounded-xl px-3 py-2">
                CPU · <b className="text-cream">{sys?.cpu.cores ?? "—"} cores</b>
                {sys?.cpu.load1 != null && <span className="text-faint"> · load {sys.cpu.load1}</span>}
              </span>
              {sys?.ollama.models_running.map((m) => (
                <span key={m.name} className="glass rounded-xl px-3 py-2">
                  <b className="font-mono text-[12px] text-gold-bright">{m.name}</b>
                  <span className="text-faint"> · {humanBytes(m.size)} · {m.size_vram > 0 ? `${humanBytes(m.size_vram)} on GPU` : "on CPU"}</span>
                </span>
              ))}
              {sys && !sys.ollama.running && (
                <span className="flex items-center gap-2 text-[12px] text-faint">
                  <XCircle className="h-3.5 w-3.5 text-[#f0746e]" /> Engine stopped — no local models loaded
                </span>
              )}
            </div>
          </Section>

          {(
            <>
              <Section title="Devices" icon={MonitorSmartphone} delay={0.25}>
                {sessions.length === 0 ? (
                  <p className="text-[13px] text-faint">No active sessions found.</p>
                ) : (
                  <ul className="space-y-2">
                    {sessions.map((s) => (
                      <li key={s.id} className="glass flex items-center gap-3 rounded-xl px-4 py-3">
                        <MonitorSmartphone className="h-4 w-4 shrink-0 text-gold" />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-[13px] font-semibold text-cream">
                            {s.device_label}
                            {s.current && <span className="ml-2 rounded bg-emerald-400/15 px-1.5 py-0.5 text-[10px] text-emerald-300">this device</span>}
                          </p>
                          <p className="text-[11px] text-faint">
                            signed in {new Date(s.created_at).toLocaleDateString()} · {s.remember ? "remembered" : "session only"}
                          </p>
                        </div>
                        {!s.current && (
                          <Button variant="danger" size="sm" onClick={() => void revoke(s.id)}>
                            <Trash2 className="h-3.5 w-3.5" /> Revoke
                          </Button>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </Section>

              <Section title="Change password" icon={KeyRound} delay={0.3}>
                <form onSubmit={(e) => { e.preventDefault(); void changePassword(); }}>
                <div className="grid gap-3 sm:grid-cols-3">
                  <PasswordField label="Current" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} autoComplete="current-password" />
                  <PasswordField label="New (8+)" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} autoComplete="new-password" />
                  <PasswordField label="Confirm new" value={pw.confirm} onChange={(e) => setPw({ ...pw, confirm: e.target.value })} autoComplete="new-password" />
                </div>
                <div className="mt-3">
                  <AuthError message={pwError} />
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  <div className="w-44">
                    <AuthSubmit loading={pwState === "busy"} disabled={!pw.current || pw.next.length < 8 || !pw.confirm}>
                      Update password
                    </AuthSubmit>
                  </div>
                  {pwState === "ok" && (
                    <span className="flex items-center gap-1.5 text-[12px] text-emerald-300">
                      <CheckCircle2 className="h-4 w-4" /> Updated — all devices signed out. Back to login…
                    </span>
                  )}
                  <span className="text-[11px] text-faint">Changing it revokes every session, everywhere.</span>
                </div>
                </form>
              </Section>
            </>
          )}
        </div>

        <footer className="mt-12 text-center"><Signature framed /></footer>
      </div>
    </main>
  );
}

export default function ProfilePage() {
  // no signup, no entry: anonymous visitors — with OR without accounts on the
  // machine — are rerouted to /login by the single routing law.
  const state = useRouteGuard({ requireAuth: true });
  if (state === "loading") {
    return (
      <main className="flex min-h-dvh items-center justify-center bg-void">
        <Loader2 className="h-6 w-6 animate-spin text-gold" />
      </main>
    );
  }
  return <ProfileInner />;
}
