/**
 * /onboarding — the first-run ceremony. Four movements:
 *   welcome   → the manifesto (Create. Research. Code. Think.)
 *   mode      → how do you want to run AI? (Local free · Cloud keys · Guest · demo link)
 *   flow      → OllamaWizard | CloudWizard
 *   done      → AI Ready → Launch Workspace
 *
 * Choices persist server-side the moment they're made (/api/onboarding/mode),
 * so closing the tab mid-wizard resumes honestly. Once setup is complete the
 * page still re-runs on demand (Settings links back here).
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Cloud, Cpu, Loader2, Rocket, UserRound, Eye, ArrowRight } from "lucide-react";
import { WizardShell, StepTitle } from "@/components/onboarding/shared";
import { OllamaWizard } from "@/components/onboarding/OllamaWizard";
import { CloudWizard } from "@/components/onboarding/CloudWizard";
import { onboardingApi, type OnboardingStatus } from "@/lib/authApi";
import { Orb } from "@/components/orb/Orb";
import { Button } from "@/components/ui/primitives";
import { cn, EASE_CURVE } from "@/lib/utils";

type Stage = "welcome" | "mode" | "wizard" | "done";

const VERBS = ["Create.", "Research.", "Code.", "Think."];

const MODES = [
  {
    id: "free" as const, icon: Cpu, title: "Free · Offline · Unlimited", tag: "RECOMMENDED",
    lines: ["100% private — nothing leaves this machine", "Powered by Ollama", "Guided 3-minute setup"],
  },
  {
    id: "cloud" as const, icon: Cloud, title: "Cloud AI", tag: null,
    lines: ["Fastest models on earth", "Works anywhere, even weak hardware", "Requires an API key (guided)"],
  },
  {
    id: "guest" as const, icon: UserRound, title: "Continue as Guest", tag: null,
    lines: ["No account, no setup walls", "Chat on local Ollama", "Temporary history — clear anytime"],
  },
];

export default function OnboardingPage() {
  const router = useRouter();
  const [stage, setStage] = useState<Stage>("welcome");
  const [flow, setFlow] = useState<"free" | "cloud" | null>(null);
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [busyMode, setBusyMode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void onboardingApi.status().then(setStatus).catch(() => setStatus(null));
  }, []);

  const pick = useCallback(async (mode: "free" | "cloud" | "guest" | "demo") => {
    setBusyMode(mode);
    setError(null);
    try {
      setStatus(await onboardingApi.chooseMode(mode));
      if (mode === "free") {
        setFlow("free");
        setStage("wizard");
      } else if (mode === "cloud") {
        setFlow("cloud");
        setStage("wizard");
      } else if (mode === "demo") {
        router.replace("/chat");
      } else {
        router.replace("/chat");
      }
    } catch {
      setError("Backend unreachable — start Vednix's backend and retry.");
    } finally {
      setBusyMode(null);
    }
  }, [router]);

  const stepIndex = stage === "welcome" ? 0 : stage === "mode" ? 1 : stage === "wizard" ? 2 : 3;
  const stepLabel = ["Welcome", "Mode", "Setup", "Ready"][stepIndex];

  return (
    <WizardShell step={stepIndex} total={4} stepLabel={stepLabel}>
      {stage === "welcome" && (
        <div className="flex flex-col items-center pt-6 text-center">
          <motion.div
            initial={{ opacity: 0, scale: 0.85 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.9, ease: EASE_CURVE }}
          >
            <Orb state="LISTENING" size={170} />
          </motion.div>
          <motion.h1
            className="mt-8 font-display text-6xl font-extrabold tracking-tight sm:text-7xl"
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25, duration: 0.7, ease: EASE_CURVE }}
          >
            <span className="text-gold-gradient">Vednix AI</span>
          </motion.h1>
          <motion.p
            className="mt-2 font-mono text-[11px] uppercase tracking-[0.35em] text-faint"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.45 }}
          >
            The AI Operating System
          </motion.p>
          <div className="mt-10 flex flex-wrap justify-center gap-x-8 gap-y-2">
            {VERBS.map((v, i) => (
              <motion.span
                key={v}
                className="font-display text-2xl font-bold text-cream/90"
                initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.6 + i * 0.14, duration: 0.55, ease: EASE_CURVE }}
              >
                {v}
              </motion.span>
            ))}
          </div>
          <motion.div
            initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 1.3, duration: 0.55 }}
            className="mt-14"
          >
            <Button variant="primary" size="md" className="h-12 rounded-2xl px-8 text-base" onClick={() => setStage("mode")}>
              Begin <ArrowRight className="h-4 w-4" />
            </Button>
          </motion.div>
        </div>
      )}

      {stage === "mode" && (
        <div>
          <StepTitle
            kicker="One question"
            title="How do you want to run AI?"
            sub="You're never locked in — switch modes anytime from Settings → AI Providers."
          />
          {error && <p className="mb-4 text-center text-[13px] text-[#f49a96]">{error}</p>}
          <div className="grid gap-4 lg:grid-cols-3">
            {MODES.map((m, i) => (
              <motion.button
                key={m.id}
                onClick={() => void pick(m.id)}
                disabled={busyMode !== null}
                className={cn(
                  "glass-strong group relative flex min-h-[240px] flex-col items-start gap-4 rounded-3xl p-6 text-left",
                  "transition-all duration-300 hover:border-gold/40 hover:shadow-[0_0_50px_-12px_rgba(227,184,87,0.35)]",
                )}
                initial={{ opacity: 0, y: 26 }} animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.15 + i * 0.12, duration: 0.6, ease: EASE_CURVE }}
                whileHover={{ y: -4 }}
                whileTap={{ scale: 0.985 }}
              >
                {m.tag && (
                  <span className="absolute right-4 top-4 rounded-md bg-gold/20 px-2 py-1 font-mono text-[8px] uppercase tracking-[0.18em] text-gold-bright">
                    {m.tag}
                  </span>
                )}
                <span className="flex h-12 w-12 items-center justify-center rounded-2xl border border-gold/30 bg-gradient-to-br from-gold/15 to-gold/[0.04] text-gold transition-transform duration-300 group-hover:scale-110">
                  {busyMode === m.id ? <Loader2 className="h-5 w-5 animate-spin" /> : <m.icon className="h-5 w-5" />}
                </span>
                <span className="font-display text-lg font-bold leading-tight text-cream">{m.title}</span>
                <ul className="space-y-1.5 text-[12px] leading-snug text-muted">
                  {m.lines.map((l) => <li key={l}>· {l}</li>)}
                </ul>
                <span className="mt-auto inline-flex items-center gap-1.5 text-[12px] font-semibold text-gold-bright opacity-0 transition-opacity duration-300 group-hover:opacity-100">
                  Continue <ArrowRight className="h-3.5 w-3.5" />
                </span>
              </motion.button>
            ))}
          </div>
          <motion.p
            className="mt-6 text-center"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.6 }}
          >
            <button
              onClick={() => void pick("demo")}
              disabled={busyMode !== null}
              className="inline-flex items-center gap-2 text-[12px] text-faint transition-colors hover:text-gold-bright"
            >
              <Eye className="h-3.5 w-3.5" />
              Just exploring? Take the no-AI demo tour instead
            </button>
          </motion.p>
        </div>
      )}

      {stage === "wizard" && flow === "free" && (
        <OllamaWizard
          status={status}
          setStatus={setStatus}
          onDone={() => setStage("done")}
          onExit={() => setStage("mode")}
        />
      )}
      {stage === "wizard" && flow === "cloud" && (
        <CloudWizard onDone={() => setStage("done")} onExit={() => setStage("mode")} />
      )}

      {stage === "done" && (
        <div className="flex flex-col items-center pt-8 text-center">
          <motion.div
            initial={{ scale: 0.7, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: "spring", stiffness: 180, damping: 16 }}
          >
            <Orb state="SPEAKING" size={150} />
          </motion.div>
          <motion.h1
            className="mt-6 font-display text-5xl font-extrabold tracking-tight"
            initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
          >
            <span className="text-gold-gradient">AI Ready.</span>
          </motion.h1>
          <motion.p
            className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-muted"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.35 }}
          >
            {status?.active_provider
              ? `${status.active_provider} is live. Your workspace — dashboard, chat, knowledge, memory — is standing by.`
              : "Your workspace — dashboard, chat, knowledge, memory — is standing by."}
          </motion.p>
          <motion.div
            initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }}
            className="mt-10"
          >
            <Button
              variant="primary" size="md"
              className="h-12 rounded-2xl px-8 text-base"
              onClick={() => {
                void onboardingApi.status().catch(() => status);
                router.replace("/chat");
              }}
            >
              <Rocket className="h-4 w-4" /> Launch Workspace
            </Button>
          </motion.div>
        </div>
      )}
    </WizardShell>
  );
}
