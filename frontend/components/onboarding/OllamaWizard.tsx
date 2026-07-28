/**
 * OllamaWizard — the guided local-AI setup, in five premium steps:
 *   1. What/why (honest pros, cons, hardware math, model catalog with specs)
 *   2. Download (official site, per-OS cards — browsers can't auto-install)
 *   3. Install guide (animated steps + copy chips: ollama serve, ollama pull)
 *   4. Connect (auto-detect @ localhost:11434, green-check animation, model
 *      picker persisted via /api/providers/ollama/default-model)
 *   5. Done (AI Ready → Launch Workspace)
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Apple, ArrowRight, CheckCircle2, ChevronLeft, Cpu, Download, Info,
  Laptop, Loader2, Lock, RefreshCw, ShieldCheck, TerminalSquare, WifiOff,
} from "lucide-react";
import {
  onboardingApi, providerApi, systemApi, type LocalModelRec, type OnboardingStatus,
} from "@/lib/authApi";
import { ApiError } from "@/lib/tokenVault";
import { Button } from "@/components/ui/primitives";
import { cn, EASE_CURVE } from "@/lib/utils";
import { CopyChip, SpecChip, StatusDot, StepTitle, usePoller } from "./shared";

const OLLAMA_URL = "https://ollama.com/download";

const OS_CARDS = [
  { os: "Windows", icon: Laptop, note: "Installer .exe — runs in the tray after setup" },
  { os: "macOS", icon: Apple, note: ".dmg — drag to Applications, menu-bar app" },
  { os: "Linux", icon: TerminalSquare, note: "One line: curl -fsSL https://ollama.com/install.sh | sh" },
];

const PROS = [
  { icon: Lock, text: "100% private — prompts never leave this machine" },
  { icon: WifiOff, text: "No internet needed once models are installed" },
  { icon: ShieldCheck, text: "Free & unlimited — no keys, no quotas, no bills" },
  { icon: Cpu, text: "Qwen · Llama · Gemma · Mistral · DeepSeek · Phi — your pick" },
];

const CONS = [
  "Uses your RAM (4–16GB depending on the model you pick)",
  "Uses disk (2–10GB per model)",
  "Slower than the biggest cloud models on old hardware",
];

/* --- step 1: explain --------------------------------------------------------- */

function ExplainStep({ next, models }: { next: () => void; models: LocalModelRec[] }) {
  return (
    <div>
      <StepTitle
        kicker="Local mode · step 1 of 4"
        title="Meet the Vednix Engine"
        sub="A tiny engine that runs open AI models right on this computer (built on the open Ollama runtime). Vednix talks to it, you own everything."
      />

      <div className="grid gap-3 sm:grid-cols-2">
        {PROS.map((p, i) => (
          <motion.div
            key={p.text}
            className="glass flex items-start gap-3 rounded-2xl p-4"
            initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 + i * 0.08, duration: 0.5, ease: EASE_CURVE }}
          >
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-gold/25 bg-gold/[0.08] text-gold">
              <p.icon className="h-4 w-4" />
            </span>
            <p className="text-[13px] leading-snug text-cream/90">{p.text}</p>
          </motion.div>
        ))}
      </div>

      <div className="glass mt-4 rounded-2xl p-4">
        <p className="mb-2 flex items-center gap-2 text-[12px] font-semibold text-muted">
          <Info className="h-3.5 w-3.5 text-gold" /> The honest trade-offs
        </p>
        <ul className="space-y-1 text-[12px] text-faint">
          {CONS.map((c) => <li key={c}>· {c}</li>)}
        </ul>
      </div>

      <p className="mb-3 mt-8 text-center font-mono text-[10px] uppercase tracking-[0.25em] text-faint">
        Recommended models — pick by your hardware
      </p>
      <div className="space-y-2">
        {models.slice(0, 4).map((m, i) => (
          <motion.div
            key={m.tag}
            className={cn(
              "glass flex flex-wrap items-center gap-2.5 rounded-2xl p-4",
              m.tier === "Balanced" && "border-gold/40 shadow-[inset_0_0_0_1px_rgba(227,184,87,0.25)]",
            )}
            initial={{ opacity: 0, x: -14 }} animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.35 + i * 0.07, duration: 0.45, ease: EASE_CURVE }}
          >
            <span className={cn(
              "rounded-md px-2 py-1 font-mono text-[9px] uppercase tracking-[0.15em]",
              m.tier === "Balanced" ? "bg-gold/20 text-gold-bright" : "bg-white/[0.06] text-muted",
            )}>
              {m.tier}
            </span>
            <code className="text-sm font-semibold text-cream">{m.tag}</code>
            <span className="text-[11px] text-faint">{m.best_for}</span>
            <span className="ml-auto flex flex-wrap gap-1.5">
              <SpecChip label="RAM" value={`${m.ram_gb}GB`} />
              <SpecChip label="Disk" value={`${m.disk_gb}GB`} />
              <SpecChip label="Speed" value={m.speed} />
              <SpecChip label="Quality" value={m.quality} />
            </span>
          </motion.div>
        ))}
      </div>

      <div className="mt-8 flex justify-end">
        <Button variant="primary" onClick={next}>
          Continue <ArrowRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

/* --- step 2: download ------------------------------------------------------------ */

function DownloadStep({ next, back }: { next: () => void; back: () => void }) {
  return (
    <div>
      <StepTitle
        kicker="Local mode · step 2 of 4"
        title="Download the Engine"
        sub="Browsers can't silently install software (a good thing) — so this step is one honest click on the official engine download page."
      />

      <div className="grid gap-3 sm:grid-cols-3">
        {OS_CARDS.map((c, i) => (
          <motion.a
            key={c.os}
            href={OLLAMA_URL}
            target="_blank"
            rel="noreferrer"
            className="glass group flex flex-col items-center gap-3 rounded-2xl p-6 text-center transition-colors duration-200 hover:border-gold/35 hover:bg-gold/[0.04]"
            initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 + i * 0.1, duration: 0.5, ease: EASE_CURVE }}
            whileHover={{ y: -3 }}
          >
            <c.icon className="h-8 w-8 text-gold" />
            <span className="font-display text-lg font-bold text-cream">{c.os}</span>
            <span className="text-[11px] leading-snug text-faint">{c.note}</span>
            <span className="mt-1 inline-flex items-center gap-1.5 text-[11px] font-semibold text-gold-bright">
              <Download className="h-3.5 w-3.5" /> ollama.com/download
            </span>
          </motion.a>
        ))}
      </div>

      <p className="mt-6 text-center text-[12px] text-faint">
        Installed already? Continue — Vednix auto-detects in the next step.
      </p>

      <div className="mt-8 flex items-center justify-between">
        <Button variant="ghost" onClick={back}><ChevronLeft className="h-4 w-4" /> Back</Button>
        <Button variant="primary" onClick={next}>Continue <ArrowRight className="h-4 w-4" /></Button>
      </div>
    </div>
  );
}

/* --- step 3: install guide --------------------------------------------------------- */

function InstallStep({ next, back, selectedModel }: { next: () => void; back: () => void; selectedModel: string }) {
  const steps = [
    { n: "01", title: "Install the Engine", body: "Run the installer you downloaded. On Windows/Mac it lives in the tray and starts itself." },
    { n: "02", title: "Start the engine", body: "Terminal/command prompt (only needed if it isn't already running):", cmd: "ollama serve" },
    { n: "03", title: "Fetch your model", body: "One download, then it's on your machine forever:", cmd: `ollama pull ${selectedModel}` },
  ];
  return (
    <div>
      <StepTitle
        kicker="Local mode · step 3 of 4"
        title="Three tiny moves"
        sub="Copy buttons included — no terminal knowledge required, just paste and press Enter."
      />
      <div className="space-y-3">
        {steps.map((s, i) => (
          <motion.div
            key={s.n}
            className="glass flex items-start gap-4 rounded-2xl p-5"
            initial={{ opacity: 0, x: -18 }} animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.15 + i * 0.12, duration: 0.5, ease: EASE_CURVE }}
          >
            <span className="font-mono text-[11px] text-gold/70">{s.n}</span>
            <div className="min-w-0 flex-1 space-y-2">
              <p className="text-sm font-semibold text-cream">{s.title}</p>
              <p className="text-[12px] leading-snug text-faint">{s.body}</p>
              {s.cmd && <CopyChip text={s.cmd} label="click to copy" />}
            </div>
          </motion.div>
        ))}
      </div>

      <div className="mt-8 flex items-center justify-between">
        <Button variant="ghost" onClick={back}><ChevronLeft className="h-4 w-4" /> Back</Button>
        <Button variant="primary" onClick={next}>Verify connection <ArrowRight className="h-4 w-4" /></Button>
      </div>
    </div>
  );
}

/* --- step 4: connect (auto-detect + model select) ---------------------------------------- */

function ConnectStep({
  next, back, status, setStatus, selectedModel, setSelectedModel,
}: {
  next: () => void;
  back: () => void;
  status: OnboardingStatus | null;
  setStatus: (s: OnboardingStatus) => void;
  selectedModel: string;
  setSelectedModel: (m: string) => void;
}) {
  const [models, setModels] = useState<string[]>([]);
  const [checking, setChecking] = useState(true);
  const [detail, setDetail] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const probe = useCallback(async () => {
    try {
      const res = await providerApi.ollamaStatus();
      setChecking(false);
      setDetail(res.detail);
      setModels(res.models);
      if (res.running && res.models.length && !res.models.includes(selectedModel)) {
        setSelectedModel(res.models[0]);
      }
      const ob = await onboardingApi.status();
      setStatus(ob);
    } catch {
      setChecking(false);
      setModels([]);
      setDetail("backend unreachable");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedModel]);

  usePoller(probe, 2500);
  const running = models.length > 0 || (status?.ollama_running ?? false);

  const saveAndContinue = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      await systemApi.setDefaultModel(selectedModel);
      next();
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "Could not save — retry?");
      setSaving(false);
    }
  };

  return (
    <div>
      <StepTitle
        kicker="Local mode · step 4 of 4"
        title="Connecting…"
        sub="Vednix probes localhost:11434 every few seconds — install the Engine and this card turns green by itself."
      />

      <motion.div
        className={cn(
          "glass-strong rounded-3xl p-7 text-center transition-all duration-500",
          running && "border-emerald-400/40 shadow-[inset_0_0_0_1px_rgba(52,211,153,0.25),0_0_40px_-10px_rgba(52,211,153,0.3)]",
        )}
        animate={running ? { scale: [1, 1.015, 1] } : {}}
        transition={{ duration: 0.6 }}
      >
        <div className="mb-4 flex items-center justify-center gap-2.5">
          {checking && !running ? (
            <Loader2 className="h-5 w-5 animate-spin text-gold" />
          ) : (
            <StatusDot tone={running ? "ok" : "fail"} pulse={running} />
          )}
          <span className={cn("font-display text-xl font-bold", running ? "text-emerald-300" : "text-cream")}>
            {running ? "Connected" : checking ? "Looking for the engine…" : "Not detected yet"}
          </span>
        </div>

        {running ? (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
            <CheckCircle2 className="mx-auto h-10 w-10 text-emerald-400" />
            {models.length > 0 ? (
              <div>
                <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.25em] text-faint">
                  Choose your default model
                </p>
                <div className="mx-auto flex max-w-md flex-wrap justify-center gap-2">
                  {models.map((m) => (
                    <button
                      key={m}
                      onClick={() => setSelectedModel(m)}
                      className={cn(
                        "rounded-xl border px-3.5 py-2 font-mono text-[12px] transition-all duration-200",
                        m === selectedModel
                          ? "border-gold/60 bg-gold/15 text-gold-bright shadow-[0_0_12px_rgba(227,184,87,0.25)]"
                          : "border-white/10 bg-white/[0.03] text-muted hover:border-gold/30 hover:text-cream",
                      )}
                    >
                      {m}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-[13px] text-muted">The engine is up, but no model is installed yet. Run:</p>
                <div className="mx-auto max-w-xs"><CopyChip text={`ollama pull ${selectedModel}`} /></div>
              </div>
            )}
          </motion.div>
        ) : (
          <div className="space-y-3">
            <p className="text-[13px] text-muted">
              {checking ? "Give it a few seconds after ollama serve…" : "Troubleshooting"}
            </p>
            {!checking && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mx-auto max-w-sm space-y-2 text-left">
                <CopyChip text="ollama serve" label="start the engine" />
                <CopyChip text={`ollama pull ${selectedModel}`} label="fetch the model" />
                {detail && <p className="text-center font-mono text-[10px] text-faint/70">{detail}</p>}
              </motion.div>
            )}
            <div className="flex justify-center gap-2">
              <Button variant="subtle" size="sm" onClick={() => { setChecking(true); void probe(); }}>
                <RefreshCw className="h-3.5 w-3.5" /> Retry now
              </Button>
            </div>
          </div>
        )}
      </motion.div>

      {saveError && <p className="mt-3 text-center text-[12px] text-[#f49a96]">{saveError}</p>}

      <div className="mt-8 flex items-center justify-between">
        <Button variant="ghost" onClick={back}><ChevronLeft className="h-4 w-4" /> Back</Button>
        <Button variant="primary" onClick={() => void saveAndContinue()} disabled={!running || saving}>
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <>Save & finish <ArrowRight className="h-4 w-4" /></>}
        </Button>
      </div>
    </div>
  );
}

/* --- orchestrator ------------------------------------------------------------------- */

export function OllamaWizard({
  status, setStatus, onDone, onExit,
}: {
  status: OnboardingStatus | null;
  setStatus: (s: OnboardingStatus) => void;
  onDone: () => void;
  onExit: () => void;
}) {
  const [step, setStep] = useState(0);
  const [recs, setRecs] = useState<LocalModelRec[]>([]);
  const [selectedModel, setSelectedModel] = useState("qwen2.5:7b");

  useEffect(() => {
    void onboardingApi.localModels().then((r) => setRecs(r.models)).catch(() => setRecs([]));
  }, []);

  const steps = [
    <ExplainStep key="explain" models={recs} next={() => setStep(1)} />,
    <DownloadStep key="download" next={() => setStep(2)} back={() => setStep(0)} />,
    <InstallStep key="install" next={() => setStep(3)} back={() => setStep(1)} selectedModel={selectedModel} />,
    <ConnectStep
      key="connect" status={status} setStatus={setStatus}
      selectedModel={selectedModel} setSelectedModel={setSelectedModel}
      next={onDone} back={() => setStep(2)}
    />,
  ];
  return (
    <div>
      <button onClick={onExit} className="mb-4 text-[11px] text-faint transition-colors hover:text-gold-bright">
        ← choose a different mode
      </button>
      {steps[step]}
    </div>
  );
}
