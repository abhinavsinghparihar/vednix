/**
 * /login — the OS lock screen, cinematic edition. Email-or-username +
 * password, remember-me, animated validation and errors, forgot-password
 * recovery (honest local recovery — a machine-only app can't promise SMTP).
 * Rule of the house: NO SIGNUP, NO ENTRY — this screen is the only door.
 *
 * Keyboard: Enter/⌘↵ submits; Esc exits the forgot view.
 */

"use client";

import { Suspense, useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { TerminalSquare, Copy, Check, ArrowLeft } from "lucide-react";
import { AuthShell } from "@/components/auth/AuthShell";
import { AuthCheck, AuthError, AuthField, AuthSubmit, PasswordField } from "@/components/auth/fields";
import { authApi, onboardingApi } from "@/lib/authApi";
import { ApiError } from "@/lib/tokenVault";
import { useAuth } from "@/store/auth";

type View = "login" | "forgot";

function LoginInner() {
  const router = useRouter();
  const params = useSearchParams();
  const setUser = useAuth((s) => s.setUser);
  const refreshOnboarding = useAuth((s) => s.refreshOnboarding);

  const [view, setView] = useState<View>("login");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shake, setShake] = useState(0);
  const [copied, setCopied] = useState(false);

  const fail = useCallback((msg: string) => {
    setError(msg);
    setShake((s) => s + 1);
  }, []);

  const goAfterAuth = useCallback(async () => {
    let status = null;
    try {
      status = await onboardingApi.status();
    } catch {
      /* offline → workspace shows its own offline UI */
    }
    const next = params.get("next");
    if (next && next.startsWith("/")) router.replace(next);
    else if (status && !status.setup_complete) router.replace("/onboarding");
    else router.replace("/chat");
  }, [params, router]);

  const submit = async (e?: FormEvent) => {
    e?.preventDefault();
    if (loading) return;
    if (!identifier.trim() || !password) {
      fail("Enter your username (or email) and password.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const user = await authApi.login({ username: identifier.trim(), password, remember });
      setUser(user);
      await refreshOnboarding();
      await goAfterAuth();
    } catch (err) {
      fail(err instanceof ApiError ? err.message : "Backend unreachable — is Vednix running?");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && view === "forgot") setView("login");
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") void submit();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (view === "forgot") {
    return (
      <AuthShell title="Recover access" subtitle="Local-first means your machine is the recovery channel.">
        <button
          onClick={() => setView("login")}
          className="mb-5 inline-flex items-center gap-1.5 text-xs text-faint transition-colors hover:text-gold-bright"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Back to sign in
        </button>

        <div className="space-y-4 text-[13px] leading-relaxed text-muted">
          <div className="glass rounded-xl p-4">
            <p className="mb-2 flex items-center gap-2 font-semibold text-cream">
              <TerminalSquare className="h-4 w-4 text-gold" /> On this machine
            </p>
            <p className="mb-3">Run Vednix's reset helper — it sets a new password and revokes every session:</p>
            <div className="flex items-center gap-2">
              <code className="glass flex-1 truncate rounded-lg px-3 py-2 font-mono text-[11px] text-gold-bright">
                python scripts/reset_password.py your-username
              </code>
              <button
                aria-label="Copy reset command"
                onClick={() => {
                  void navigator.clipboard?.writeText("python scripts/reset_password.py your-username");
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1600);
                }}
                className="rounded-lg p-2 text-faint transition-colors hover:bg-white/[0.05] hover:text-gold-bright"
              >
                {copied ? <Check className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
              </button>
            </div>
          </div>
          <p>
            Email-based reset isn't offered because an app that lives wholly on
            this machine can't promise SMTP. If you run Vednix behind a mail relay later, this
            screen grows a real email flow off the same seam.
          </p>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Welcome back"
      subtitle="Sign in to your Vednix workspace — your models, memories and settings, exactly as you left them."
    >
      <form onSubmit={submit} className="space-y-4" key={shake} noValidate={false}>
        <AuthField
          label="Username or Email"
          autoComplete="username"
          autoFocus
          value={identifier}
          onChange={(e) => setIdentifier(e.target.value)}
          placeholder="abhinav · abhinav@vednix.ai"
          invalid={!!error}
          disabled={loading}
        />
        <PasswordField
          label="Password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
          invalid={!!error}
          disabled={loading}
        />

        <div className="flex items-center justify-between pt-0.5">
          <AuthCheck id="remember" checked={remember} onChange={setRemember}>
            Keep me signed in for 30 days
          </AuthCheck>
          <button
            type="button"
            onClick={() => setView("forgot")}
            className="text-xs text-faint transition-colors hover:text-gold-bright"
          >
            Forgot password?
          </button>
        </div>

        <AuthError message={error} />
        <AuthSubmit loading={loading}>Sign in</AuthSubmit>
      </form>

      <p className="mt-4 text-center text-xs text-faint">
        New to Vednix?{" "}
        <Link href="/signup" className="text-gold-bright underline-offset-4 transition-colors hover:underline">
          Create an account
        </Link>
      </p>

      <p className="mt-5 text-center font-mono text-[9px] uppercase tracking-[0.22em] text-faint/70">
        Enter submits · ⌘↵ anywhere
      </p>
    </AuthShell>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginInner />
    </Suspense>
  );
}
