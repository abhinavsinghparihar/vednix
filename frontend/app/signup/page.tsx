/**
 * /signup — create the machine's account. Name, email, password (live
 * strength meter), confirm, terms. Username is derived transparently from
 * the email (shown live), so the form stays human-shaped while the backend
 * keeps its canonical usernames. Register logs straight in; first-run then
 * hands off to /onboarding.
 */

"use client";

import { useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { AtSign, CheckCircle2, XCircle } from "lucide-react";
import { AuthShell } from "@/components/auth/AuthShell";
import { AuthCheck, AuthError, AuthField, AuthSubmit, PasswordField } from "@/components/auth/fields";
import { authApi, onboardingApi } from "@/lib/authApi";
import { ApiError } from "@/lib/tokenVault";
import { useAuth } from "@/store/auth";
import { cn } from "@/lib/utils";

function scorePassword(pw: string): { score: 0 | 1 | 2 | 3 | 4; label: string; color: string } {
  if (!pw) return { score: 0, label: "Start typing", color: "bg-white/10" };
  let pts = 0;
  if (pw.length >= 8) pts++;
  if (pw.length >= 12) pts++;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) pts++;
  if (/\d/.test(pw)) pts++;
  if (/[^a-zA-Z0-9]/.test(pw)) pts++;
  if (/^(.)\1+$/.test(pw) || /^(123|qwerty|password)/i.test(pw)) pts = Math.min(pts, 1);
  const clamped = Math.min(4, pts) as 0 | 1 | 2 | 3 | 4;
  const levels: { score: 0 | 1 | 2 | 3 | 4; label: string; color: string }[] = [
    { score: 0, label: "Start typing", color: "bg-white/10" },
    { score: 1, label: "Weak", color: "bg-[#f0746e]" },
    { score: 2, label: "Okay", color: "bg-ember" },
    { score: 3, label: "Strong", color: "bg-gold" },
    { score: 4, label: "Excellent", color: "bg-emerald-400" },
  ];
  return levels[clamped];
}

function deriveUsername(email: string, name: string): string {
  const local = email.split("@")[0] || "";
  const base = (local || name).toLowerCase().replace(/[^a-z0-9_.-]+/g, "-").replace(/^-+|-+$/g, "");
  return base.length >= 3 ? base.slice(0, 32) : `${base || "vednix"}-user`;
}

export default function SignupPage() {
  const router = useRouter();
  const setUser = useAuth((s) => s.setUser);

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [terms, setTerms] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const strength = useMemo(() => scorePassword(password), [password]);
  const usernameHint = useMemo(() => deriveUsername(email, name), [email, name]);
  const emailOk = useMemo(() => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email), [email]);
  const match = confirm.length > 0 && confirm === password;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (loading) return;
    if (!name.trim()) return setError("Tell us your name.");
    if (!emailOk) return setError("That email address doesn't look right.");
    if (password.length < 8) return setError("Password needs at least 8 characters.");
    if (password !== confirm) return setError("Passwords don't match.");
    if (!terms) return setError("Please accept the local-first terms to continue.");

    setLoading(true);
    setError(null);
    try {
      const user = await authApi.register({
        username: usernameHint,
        password,
        display_name: name.trim(),
        email: email.trim().toLowerCase(),
      });
      setUser(user);
      let status = null;
      try {
        status = await onboardingApi.status();
      } catch {
        /* offline → workspace handles it */
      }
      router.replace(status && !status.setup_complete ? "/onboarding" : "/chat");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Backend unreachable — is Vednix running?");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell
      title="Create your account"
      subtitle="The first account owns this machine — it can lock the workspace, manage sessions, and control AI providers."
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        <AuthField
          label="Full name"
          autoComplete="name"
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Abhinav Singh"
          invalid={!!error && !name.trim()}
          disabled={loading}
        />

        <div className="space-y-1.5">
          <AuthField
            label="Email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="abhinav@vednix.ai"
            invalid={!!email && !emailOk}
            disabled={loading}
            trailing={email ? (emailOk
              ? <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              : <XCircle className="h-4 w-4 text-[#f0746e]" />) : undefined}
          />
          <motion.p
            className="flex items-center gap-1.5 text-[11px] text-faint"
            animate={{ opacity: usernameHint ? 1 : 0 }}
          >
            <AtSign className="h-3 w-3" />
            your sign-in id:&nbsp;<span className="font-mono text-gold-bright">{usernameHint}</span>
          </motion.p>
        </div>

        <div className="space-y-1.5">
          <PasswordField
            label="Password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="8+ characters"
            disabled={loading}
          />
          <div className="flex items-center gap-2 pt-1" aria-live="polite">
            <div className="flex h-1 flex-1 gap-1">
              {[1, 2, 3, 4].map((seg) => (
                <motion.span
                  key={seg}
                  className={cn("h-full flex-1 rounded-full", seg <= strength.score ? strength.color : "bg-white/[0.07]")}
                  layout
                  transition={{ duration: 0.25 }}
                />
              ))}
            </div>
            <span className="w-16 text-right font-mono text-[10px] uppercase tracking-wider text-faint">
              {strength.label}
            </span>
          </div>
        </div>

        <PasswordField
          label="Confirm password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          placeholder="Once more"
          invalid={confirm.length > 0 && !match}
          hint={confirm ? (match ? "✓ matches" : "doesn't match yet") : undefined}
          disabled={loading}
        />

        <AuthCheck id="terms" checked={terms} onChange={setTerms}>
          I understand Vednix is local-first — my data, keys and memories live
          on this machine, and owning them is my responsibility.
        </AuthCheck>

        <AuthError message={error} />
        <AuthSubmit loading={loading}>Create account</AuthSubmit>
      </form>

      <p className="mt-4 text-center text-xs text-faint">
        Already have an account?{" "}
        <Link href="/login" className="text-gold-bright underline-offset-4 transition-colors hover:underline">
          Sign in
        </Link>
      </p>
    </AuthShell>
  );
}
