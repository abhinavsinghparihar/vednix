/** First-run ceremony: Vednix identity → provider setup → workspace ready. */

"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowRight, Rocket } from "lucide-react";
import { WizardShell } from "@/components/onboarding/shared";
import { ProviderWizard } from "@/components/onboarding/ProviderWizard";
import { onboardingApi, type OnboardingStatus } from "@/lib/authApi";
import { Orb } from "@/components/orb/Orb";
import { Button } from "@/components/ui/primitives";
import { EASE_CURVE } from "@/lib/utils";

type Stage = "welcome" | "setup" | "done";
const VERBS = ["Create.", "Research.", "Code.", "Think."];

export default function OnboardingPage() {
  const router = useRouter();
  const [stage, setStage] = useState<Stage>("welcome");
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void onboardingApi.status().then(setStatus).catch(() => setStatus(null));
  }, []);

  const finishSetup = useCallback(async () => {
    setError(null);
    try {
      await onboardingApi.chooseMode("cloud");
      setStatus(await onboardingApi.status());
    } catch {
      setError("The backend could not save onboarding state. You can still continue, then retry in Settings.");
    }
    setStage("done");
  }, []);

  const step = stage === "welcome" ? 0 : stage === "setup" ? 1 : 2;
  const stepLabel = ["Welcome", "Providers", "Ready"][step];

  return (
    <WizardShell step={step} total={3} stepLabel={stepLabel}>
      {stage === "welcome" && (
        <div className="flex flex-col items-center pt-6 text-center">
          <motion.div initial={{ opacity: 0, scale: 0.85 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.9, ease: EASE_CURVE }}>
            <Orb state="LISTENING" size={170} />
          </motion.div>
          <motion.h1
            className="mt-8 font-display text-6xl font-extrabold tracking-tight sm:text-7xl"
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25, duration: 0.7, ease: EASE_CURVE }}
          >
            <span className="text-gold-gradient">Vednix AI</span>
          </motion.h1>
          <motion.p className="mt-2 font-mono text-[11px] uppercase tracking-[0.35em] text-faint" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.45 }}>
            The AI Operating System
          </motion.p>
          <div className="mt-10 flex flex-wrap justify-center gap-x-8 gap-y-2">
            {VERBS.map((verb, index) => (
              <motion.span key={verb} className="font-display text-2xl font-bold text-cream/90" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.6 + index * 0.14, duration: 0.55, ease: EASE_CURVE }}>
                {verb}
              </motion.span>
            ))}
          </div>
          <motion.div className="mt-14" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1.0, duration: 0.55 }}>
            <Button variant="primary" size="md" className="h-12 rounded-2xl px-8 text-base" onClick={() => setStage("setup")}>
              Begin <ArrowRight className="h-4 w-4" />
            </Button>
          </motion.div>
        </div>
      )}

      {stage === "setup" && (
        <ProviderWizard onDone={() => void finishSetup()} onExit={() => setStage("welcome")} />
      )}

      {stage === "done" && (
        <div className="flex flex-col items-center pt-8 text-center">
          <Orb state="SPEAKING" size={150} />
          <h1 className="mt-6 font-display text-5xl font-extrabold tracking-tight"><span className="text-gold-gradient">AI Ready.</span></h1>
          <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-muted">
            {status?.active_provider && status.active_provider !== "unavailable"
              ? `${status.active_provider} is live. Your workspace — chat, knowledge, and memory — is standing by.`
              : "No chat provider is connected yet. You can configure Gemini or Groq anytime in Settings → AI Providers."}
          </p>
          {error && <p className="mt-3 max-w-md text-[12px] text-[#f49a96]">{error}</p>}
          <div className="mt-10">
            <Button
              variant="primary" size="md" className="h-12 rounded-2xl px-8 text-base"
              onClick={() => router.replace(status?.auth_enabled ? "/chat" : "/signup")}
            >
              <Rocket className="h-4 w-4" />
              {status?.auth_enabled ? "Launch Workspace" : "Create your account"}
            </Button>
          </div>
        </div>
      )}
    </WizardShell>
  );
}
