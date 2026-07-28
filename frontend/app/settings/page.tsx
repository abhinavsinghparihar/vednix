/**
 * /settings — the system preferences of the Vednix OS. Left tab rail,
 * eleven panels, every control wired to something real:
 *
 *   General      — backend health, mode, quick links
 *   Appearance   — Obsidian/Ivory/System theme
 *   Language     — default reply language (account pref; guests: local)
 *   Voice        — speak replies + speed + test (shared chat store state)
 *   AI Models    — default model per the ACTIVE provider (live-applied)
 *   Engine       — connection, installed models, pull guides, specs
 *   API Keys     — the provider manager: add/verify/toggle/remove/priority
 *   Memory       — counts, open view, context budget note
 *   Privacy      — local-first explainer + destructive actions
 *   Experimental — internet search + multi-agent feature switches
 *   About        — version, stack, creator signature
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowDown, ArrowLeft, ArrowUp, Bot, CheckCircle2, ChevronDown, Cloud, Cpu, Database,
  FlaskConical, Globe, HardDrive, Info, KeyRound, Languages, Loader2, MemoryStick,
  Mic, MonitorSmartphone, Palette, RefreshCw, Settings2, ShieldCheck, Sparkles, Trash2, Users, Volume2,
} from "lucide-react";
import {
  adminApi, authApi, onboardingApi, providerApi, systemApi,
  type AdminUser, type OnboardingStatus, type ProviderCatalogItem, type ProviderConfig, type SystemStatus,
} from "@/lib/authApi";
import { ApiError } from "@/lib/tokenVault";
import { api } from "@/lib/api";
import { useAuth } from "@/store/auth";
import { useChat } from "@/store/chat";
import { useRouteGuard } from "@/lib/useGuard";
import { NeuralBackground } from "@/components/background/NeuralBackground";
import { MouseGlow } from "@/components/background/MouseGlow";
import { Signature } from "@/components/brand/Signature";
import { ThemeToggle } from "@/components/brand/ThemeToggle";
import { Button, Segmented, Slider, Switch } from "@/components/ui/primitives";
import { CopyChip, StatusDot } from "@/components/onboarding/shared";
import { applyTheme, currentTheme } from "@/lib/theme";
import { tts } from "@/lib/tts";
import { PasswordField } from "@/components/auth/fields";
import { cn, EASE_CURVE } from "@/lib/utils";
import type { Language } from "@/lib/ws";

/* ---------------------------------------------------------------- shell --- */

const TABS = [
  { id: "general", label: "General", icon: Settings2 },
  { id: "appearance", label: "Appearance", icon: Palette },
  { id: "language", label: "Language", icon: Languages },
  { id: "voice", label: "Voice", icon: Volume2 },
  { id: "models", label: "AI Models", icon: Bot },
  { id: "engine", label: "Engine", icon: Cpu },
  { id: "keys", label: "API Keys", icon: KeyRound },
  { id: "memory", label: "Memory", icon: MemoryStick },
  { id: "privacy", label: "Privacy", icon: ShieldCheck },
  { id: "admin", label: "Admin", icon: Users },
  { id: "experimental", label: "Experimental", icon: FlaskConical },
  { id: "about", label: "About", icon: Info },
] as const;

type TabId = (typeof TABS)[number]["id"];

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      className="space-y-4"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.35, ease: EASE_CURVE }}
    >
      {children}
    </motion.div>
  );
}

function Card({ title, children, icon: Icon }: { title: string; children: React.ReactNode; icon?: typeof Cpu }) {
  return (
    <div className="glass-strong rounded-2xl p-5">
      <h3 className="mb-3 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.22em] text-faint">
        {Icon && <Icon className="h-3.5 w-3.5 text-gold" />} {title}
      </h3>
      {children}
    </div>
  );
}

/* ------------------------------------------------------------ main page --- */

export default function SettingsPage() {
  // NO SIGNUP, NO ENTRY → anyone without a session goes to /login?next=/settings
  const guard = useRouteGuard({ requireAuth: true });
  const me = useAuth((s) => s.user);
  const tabs = TABS.filter((t) => t.id !== "admin" || me?.role === "owner");
  const [tab, setTab] = useState<TabId>("general");
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [sys, setSys] = useState<SystemStatus | null>(null);

  const load = useCallback(async () => {
    try {
      setStatus(await onboardingApi.status());
    } catch { /* offline */ }
    try {
      setSys(await systemApi.status());
    } catch { /* offline */ }
  }, []);

  useEffect(() => {
    if (guard === "ok") void load();
  }, [guard, load]);

  if (guard === "loading") {
    return (
      <main className="flex min-h-dvh items-center justify-center bg-void">
        <Loader2 className="h-6 w-6 animate-spin text-gold" />
      </main>
    );
  }

  return (
    <main className="relative min-h-dvh overflow-hidden bg-void text-cream">
      <NeuralBackground />
      <MouseGlow />
      <div className="absolute right-5 top-5 z-20"><ThemeToggle /></div>

      <div className="relative z-10 mx-auto flex max-w-5xl gap-6 px-5 pb-16 pt-8">
        {/* tab rail */}
        <aside className="sticky top-8 hidden h-fit w-48 shrink-0 flex-col gap-1 md:flex">
          <Link href="/chat" className="mb-4 inline-flex items-center gap-2 px-2 text-xs text-faint transition-colors hover:text-gold-bright">
            <ArrowLeft className="h-3.5 w-3.5" /> Workspace
          </Link>
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              aria-current={tab === t.id ? "page" : undefined}
              className={cn(
                "flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-left text-[13px] transition-all duration-200",
                tab === t.id
                  ? "bg-gold/[0.12] font-semibold text-gold-bright shadow-[inset_0_0_0_1px_rgba(227,184,87,0.3)]"
                  : "text-muted hover:bg-white/[0.04] hover:text-cream",
              )}
            >
              <t.icon className="h-4 w-4 shrink-0" /> {t.label}
            </button>
          ))}
        </aside>

        {/* mobile tab bar */}
        <div className="fixed inset-x-0 bottom-0 z-30 flex gap-1 overflow-x-auto border-t border-white/[0.06] bg-void/90 p-2 backdrop-blur-lg md:hidden">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              aria-label={t.label}
              className={cn(
                "flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-[11px]",
                tab === t.id ? "bg-gold/[0.12] text-gold-bright" : "text-muted",
              )}
            >
              <t.icon className="h-3.5 w-3.5" /> {t.label}
            </button>
          ))}
        </div>

        <div className="min-w-0 flex-1 pb-16 md:pb-0">
          <div className="mb-6 md:hidden">
            <Link href="/chat" className="inline-flex items-center gap-2 text-xs text-faint">
              <ArrowLeft className="h-3.5 w-3.5" /> Workspace
            </Link>
          </div>
          <AnimatePresence mode="wait">
            <div key={tab}>
              {tab === "general" && <GeneralPanel status={status} sys={sys} reload={load} />}
              {tab === "appearance" && <AppearancePanel />}
              {tab === "language" && <LanguagePanel />}
              {tab === "voice" && <VoicePanel />}
              {tab === "models" && <ModelsPanel sys={sys} reload={load} />}
              {tab === "engine" && <OllamaPanel sys={sys} />}
              {tab === "keys" && <ApiKeysPanel />}
              {tab === "memory" && <MemoryPanel sys={sys} />}
              {tab === "privacy" && <PrivacyPanel reload={load} />}
              {tab === "admin" && <AdminPanel />}
              {tab === "experimental" && <ExperimentalPanel />}
              {tab === "about" && <AboutPanel />}
            </div>
          </AnimatePresence>
          <footer className="mt-12 text-center"><Signature framed /></footer>
        </div>
      </div>
    </main>
  );
}

/* ---------------------------------------------------------------- panels --- */

function GeneralPanel({ status, sys, reload }: { status: OnboardingStatus | null; sys: SystemStatus | null; reload: () => Promise<void> }) {
  const [waking, setWaking] = useState(false);
  return (
    <Panel>
      <Card title="System" icon={Cpu}>
        <div className="flex flex-wrap items-center gap-3 text-[13px]">
          <span className="flex items-center gap-2">
            <StatusDot tone={status ? "ok" : "fail"} pulse={!!status} />
            Backend {status ? "live" : "unreachable"}
          </span>
          <span className="flex items-center gap-2 text-muted">
            <StatusDot tone={status?.ollama_running ? "ok" : "idle"} />
            Engine {status?.ollama_running ? "running" : "stopped"}
          </span>
          <span className="text-muted">Provider · <b className="text-cream">{status?.active_provider ?? "—"}</b></span>
          <Button
            variant="ghost" size="sm" className="ml-auto"
            disabled={waking}
            onClick={() => {
              setWaking(true);
              void reload().finally(() => setWaking(false));
            }}
          >
            <RefreshCw className={cn("h-3.5 w-3.5", waking && "animate-spin")} /> Re-check
          </Button>
        </div>
      </Card>
      <Card title="Run mode" icon={Sparkles}>
        <p className="mb-3 text-[13px] text-muted">
          This machine runs in <b className="text-cream">{status?.mode ?? "unset"}</b> mode.
          Re-run the first-time ceremony anytime:
        </p>
        <div className="flex flex-wrap gap-2">
          <Link href="/onboarding"><Button variant="subtle" size="sm"><Sparkles className="h-3.5 w-3.5" /> Open setup ceremony</Button></Link>
          <Link href="/profile"><Button variant="subtle" size="sm">Profile & devices</Button></Link>
        </div>
      </Card>
      <Card title="Usage" icon={Database}>
        <div className="grid grid-cols-2 gap-2 text-[13px] sm:grid-cols-4">
          <span>Chats · <b className="text-cream">{sys?.counts.conversations ?? "—"}</b></span>
          <span>Messages · <b className="text-cream">{sys?.counts.messages ?? "—"}</b></span>
          <span>Memories · <b className="text-cream">{sys?.counts.memories ?? "—"}</b></span>
          <span>DB size · <b className="text-cream">{sys ? `${(sys.db_bytes / 1024).toFixed(0)} KB` : "—"}</b></span>
        </div>
      </Card>
    </Panel>
  );
}

function AppearancePanel() {
  const [mode, setMode] = useState<"dark" | "light" | "system">(() =>
    typeof window !== "undefined" && !localStorage.getItem("vednix.theme") ? "system" : currentTheme(),
  );
  const choose = (m: "dark" | "light" | "system") => {
    setMode(m);
    if (m === "system") {
      localStorage.removeItem("vednix.theme");
      applyTheme(window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
    } else {
      applyTheme(m);
    }
  };
  return (
    <Panel>
      <Card title="Theme" icon={Palette}>
        <Segmented<"dark" | "light" | "system">
          value={mode}
          onChange={choose}
          options={[
            { value: "dark", label: "Obsidian" },
            { value: "light", label: "Ivory" },
            { value: "system", label: "System" },
          ]}
        />
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          <div className="rounded-xl border border-white/10 bg-[#050505] p-4">
            <p className="font-display text-sm font-bold text-[#f5f0e6]">Obsidian</p>
            <p className="text-[11px] text-[#9a8d74]">deep black · gold light</p>
          </div>
          <div className="rounded-xl border border-[#221b0e]/10 bg-[#f4f0e6] p-4">
            <p className="font-display text-sm font-bold text-[#221b0e]">Ivory</p>
            <p className="text-[11px] text-[#6e6350]">paper white · bronze ink</p>
          </div>
        </div>
        <p className="mt-3 text-[11px] text-faint">
          Instant swap, no reload — every glass panel, gradient and skeleton re-skins live.
        </p>
      </Card>
    </Panel>
  );
}

function LanguagePanel() {
  const user = useAuth((s) => s.user);
  const setUser = useAuth((s) => s.setUser);
  const [lang, setLang] = useState<Language>(() =>
    (typeof window !== "undefined" && (localStorage.getItem("vednix.lang") as Language)) || "auto",
  );
  const [saved, setSaved] = useState(false);
  const choose = async (v: Language) => {
    setLang(v);
    setSaved(false);
    localStorage.setItem("vednix.lang", v);
    if (user) {
      try {
        setUser(await authApi.updateMe({ language: v }));
      } catch { /* keep local choice anyway */ }
    }
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };
  return (
    <Panel>
      <Card title="Default reply language" icon={Languages}>
        <Segmented<Language>
          value={lang}
          onChange={(v) => void choose(v)}
          options={[
            { value: "auto", label: "Auto" },
            { value: "hi", label: "हिंदी" },
            { value: "hinglish", label: "Hinglish" },
            { value: "en", label: "English" },
          ]}
        />
        <p className="mt-3 flex items-center gap-2 text-[11px] text-faint">
          {saved ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" /> : null}
          Auto mirrors your message language. Individual chats can override this
          from the Studio panel — this is your default.
          {user ? " Saved to your account." : " Saved on this device (account syncs it after sign-in)."}
        </p>
      </Card>
    </Panel>
  );
}

function VoicePanel() {
  const voiceReplies = useChat((s) => s.voiceReplies);
  const setVoiceReplies = useChat((s) => s.setVoiceReplies);
  const voiceRate = useChat((s) => s.voiceRate);
  const setVoiceRate = useChat((s) => s.setVoiceRate);
  const [testing, setTesting] = useState(false);
  return (
    <Panel>
      <Card title="Speak replies" icon={Volume2}>
        <Switch checked={voiceReplies} onCheckedChange={setVoiceReplies} label="Read assistant replies aloud (on-device OS voices)" />
        <div className="mt-4">
          <Slider
            value={voiceRate} min={0.5} max={2} step={0.05}
            onChange={(e) => setVoiceRate(parseFloat(e.target.value))}
            aria-label={`Speed · ${voiceRate.toFixed(2)}×`}
          />
          <div className="mt-1 text-[11px] text-faint">Speed · {voiceRate.toFixed(2)}×</div>
        </div>
        <Button
          variant="subtle" size="sm" className="mt-3"
          disabled={testing}
          onClick={() => {
            setTesting(true);
            tts.rate = voiceRate;
            const off = tts.onSpeakingChange((speaking) => {
              if (!speaking) { off(); setTesting(false); }
            });
            tts.speak("नमस्ते — this is Vednix speaking from your machine. Everything you hear is generated locally.", "hi-IN");
            setTimeout(() => { off(); setTesting(false); }, 9000);
          }}
        >
          <Volume2 className="h-3.5 w-3.5" /> {testing ? "Speaking…" : "Test voice"}
        </Button>
      </Card>
      <Card title="Dictation" icon={Mic}>
        <p className="text-[12px] leading-relaxed text-muted">
          The composer's mic uses the Web Speech API (Chrome/Edge). Mic language
          follows each conversation — <b className="text-cream">hi-IN</b> handles
          हिंदी and Hinglish in one stream.
        </p>
      </Card>
    </Panel>
  );
}

function ModelsPanel({ sys, reload }: { sys: SystemStatus | null; reload: () => Promise<void> }) {
  const [models, setModels] = useState<string[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    void api.models().then((r) => {
      setModels(r.available ?? []);
      setSelected(r.default ?? "");
    }).catch(() => setModels([]));
  }, []);

  const save = async () => {
    if (!selected) return;
    setSaving(true);
    setNote(null);
    try {
      await systemApi.setDefaultModel(selected);
      await reload();
      setNote(`Default model saved — ${selected} answers from now on.`);
    } catch (err) {
      setNote(err instanceof ApiError ? `${err.message} (default model applies to the Engine; cloud models are set per provider in API Keys)` : "Could not save.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Panel>
      <Card title="Active provider" icon={Bot}>
        <p className="text-[13px] text-muted">
          <b className="text-cream">{sys?.active_provider ?? "—"}</b> is answering right now.
          The priority chain lives in <b>API Keys</b> — Engine first, cloud as fallback.
        </p>
      </Card>
      <Card title="Default model" icon={Cpu}>
        {models.length === 0 ? (
          <p className="text-[12px] text-faint">No models listed — start the Engine or verify a cloud key, then re-check.</p>
        ) : (
          <>
            <div className="relative">
              <select
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
                aria-label="Default model"
                className="glass h-11 w-full appearance-none rounded-xl px-3.5 font-mono text-sm text-cream focus:border-gold/40 focus:outline-none"
              >
                {models.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
              <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
            </div>
            <div className="mt-3 flex items-center gap-3">
              <Button variant="primary" size="sm" onClick={() => void save()} disabled={saving || !selected}>
                {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save default"}
              </Button>
              {note && <span className="text-[11px] leading-snug text-faint">{note}</span>}
            </div>
          </>
        )}
      </Card>
    </Panel>
  );
}

function OllamaPanel({ sys }: { sys: SystemStatus | null }) {
  const [st, setSt] = useState<{ running: boolean; models: string[]; detail: string } | null>(null);
  const [loading, setLoading] = useState(true);

  const check = useCallback(async () => {
    setLoading(true);
    try {
      setSt(await providerApi.ollamaStatus());
    } catch {
      setSt({ running: false, models: [], detail: "backend unreachable" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void check();
  }, [check]);

  return (
    <Panel>
      <Card title="Connection" icon={Cpu}>
        <div className="flex flex-wrap items-center gap-3 text-[13px]">
          <StatusDot tone={loading ? "warn" : st?.running ? "ok" : "fail"} pulse={!!st?.running} />
          <span className="text-cream">{loading ? "Checking…" : st?.running ? "Connected · localhost:11434" : "Not running"}</span>
          <Button variant="ghost" size="sm" className="ml-auto" onClick={() => void check()}>
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} /> Retry
          </Button>
        </div>
        {st && !st.running && (
          <div className="mt-3 space-y-2">
            <CopyChip text="ollama serve" />
            {st.detail && <p className="font-mono text-[10px] text-faint/70">{st.detail}</p>}
          </div>
        )}
        {sys?.ollama.models_running && sys.ollama.models_running.length > 0 && (
          <p className="mt-3 text-[11px] text-faint">
            Loaded now: {sys.ollama.models_running.map((m) => m.name).join(", ")}
          </p>
        )}
      </Card>
      <Card title={`Installed models ${st ? `(${st.models.length})` : ""}`} icon={HardDrive}>
        {st?.models.length ? (
          <div className="flex flex-wrap gap-2">
            {st.models.map((m) => (
              <span key={m} className="glass rounded-lg px-3 py-1.5 font-mono text-[12px] text-gold-bright">{m}</span>
            ))}
          </div>
        ) : (
          <p className="text-[12px] text-faint">None yet. Pull a starter:</p>
        )}
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <CopyChip text="ollama pull qwen2.5:7b" label="balanced · 5GB" />
          <CopyChip text="ollama pull qwen2.5:3b" label="tiny · 2GB" />
          <CopyChip text="ollama pull llama3.1:8b" label="llama · 5GB" />
          <CopyChip text="ollama pull gemma3:4b" label="gemma · 3GB" />
        </div>
        <p className="mt-3 text-[11px] text-faint">
          Any installed model works — Qwen, Llama, Gemma, Mistral, DeepSeek,
          Phi, TinyLlama, CodeLlama. Pick the default in <b>AI Models</b>.
        </p>
      </Card>
    </Panel>
  );
}

function ApiKeysPanel() {
  const [catalog, setCatalog] = useState<ProviderCatalogItem[]>([]);
  const [rows, setRows] = useState<ProviderConfig[]>([]);
  const [priority, setPriority] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, { key: string; baseUrl: string }>>({});
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [cat, conf] = await Promise.all([providerApi.catalog(), providerApi.configured()]);
      setCatalog(cat.providers.filter((p) => p.id !== "ollama"));
      setRows(conf.providers);
      setPriority(conf.priority.filter((p) => p !== "ollama"));
    } catch { /* offline */ }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const rowFor = (id: string) => rows.find((r) => r.provider === id);

  const save = async (id: string, andVerify: boolean) => {
    const d = draft[id] ?? { key: "", baseUrl: "" };
    setBusy(id);
    setNotice(null);
    try {
      await providerApi.saveKey(id, {
        ...(d.key.trim() ? { api_key: d.key } : {}),
        ...(d.baseUrl.trim() ? { base_url: d.baseUrl } : {}),
      });
      setDraft((s) => ({ ...s, [id]: { key: "", baseUrl: "" } }));
      if (andVerify) {
        const r = await providerApi.verify(id);
        setNotice(r.connected ? `${id}: connected ✓` : `${id}: ${r.detail}`);
      }
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "Save failed.");
    } finally {
      setBusy(null);
    }
  };

  const verify = async (id: string) => {
    setBusy(id);
    try {
      const r = await providerApi.verify(id);
      setNotice(r.connected ? `${id}: connected ✓` : `${id}: ${r.detail}`);
      await load();
    } finally {
      setBusy(null);
    }
  };

  const toggle = async (id: string, enabled: boolean) => {
    await providerApi.toggle(id, enabled).catch(() => undefined);
    await load();
  };

  const remove = async (id: string) => {
    setBusy(id);
    try {
      await providerApi.removeKey(id);
      setNotice(`${id}: key removed from this machine.`);
      await load();
    } finally {
      setBusy(null);
    }
  };

  const move = async (id: string, dir: -1 | 1) => {
    const order = ["ollama", ...priority];
    const i = order.indexOf(id);
    const j = i + dir;
    if (i < 1 || j < 1 || j >= order.length) return; // ollama stays pinned at #1 unless user moves it below explicitly
    [order[i], order[j]] = [order[j], order[i]];
    const r = await providerApi.setPriority(order).catch(() => null);
    if (r) setPriority(r.priority.filter((p) => p !== "ollama"));
  };

  return (
    <Panel>
      <Card title="How keys live here" icon={ShieldCheck}>
        <p className="text-[12px] leading-relaxed text-muted">
          Keys are encrypted on disk (Fernet, machine-bound secret), never
          logged, and only ever readable by this backend. You always see the
          last 4 characters — nothing more, not even here.
        </p>
      </Card>

      <Card title="Failover priority" icon={Cloud}>
        <p className="mb-2 text-[11px] text-faint">
          If a provider dies mid-session, the next one answers before the first
          token — with a visible handoff line in the chat.
        </p>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="glass flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-semibold text-gold-bright">
            1 · Engine
          </span>
          {priority.filter((id) => rowFor(id)?.enabled && rowFor(id)?.has_key).map((id, i) => (
            <span key={id} className="glass rounded-lg px-2.5 py-1.5 text-[11px] text-muted">{i + 2} · {id}</span>
          ))}
        </div>
      </Card>

      {notice && (
        <p className="glass rounded-xl px-4 py-2.5 text-center text-[12px] text-gold-bright">{notice}</p>
      )}

      <div className="space-y-3">
        {catalog.map((p, idx) => {
          const row = rowFor(p.id);
          const d = draft[p.id] ?? { key: "", baseUrl: "" };
          const statusTone = !row ? "idle" : row.status === "connected" ? "ok" : row.status === "failed" ? "fail" : "warn";
          return (
            <motion.div
              key={p.id}
              className={cn("glass-strong rounded-2xl p-5", row && !row.enabled && "opacity-60")}
              initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.04, duration: 0.35 }}
            >
              <div className="flex flex-wrap items-center gap-3">
                <StatusDot tone={statusTone} pulse={row?.status === "connected"} />
                <span className="font-display text-base font-bold text-cream">{p.label}</span>
                {row?.key_hint && (
                  <code className="rounded-md bg-white/[0.06] px-2 py-0.5 font-mono text-[11px] text-muted">{row.key_hint}</code>
                )}
                {row && (
                  <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-faint">
                    {row.enabled ? (row.status === "connected" ? "connected" : row.status) : "disabled"}
                  </span>
                )}
                <span className="ml-auto flex items-center gap-1">
                  <button onClick={() => void move(p.id, -1)} aria-label="Raise priority" className="rounded-md p-1.5 text-faint hover:text-gold-bright"><ArrowUp className="h-3.5 w-3.5" /></button>
                  <button onClick={() => void move(p.id, 1)} aria-label="Lower priority" className="rounded-md p-1.5 text-faint hover:text-gold-bright"><ArrowDown className="h-3.5 w-3.5" /></button>
                </span>
              </div>

              <p className="mt-1.5 text-[11px] text-faint">{p.blurb}</p>

              <div className="mt-3 flex flex-col gap-2">
                <div className="flex flex-wrap gap-2">
                  {(p.needs_key || p.kind === "custom") && (
                    <input
                      type="password"
                      value={d.key}
                      onChange={(e) => setDraft((s) => ({ ...s, [p.id]: { ...d, key: e.target.value } }))}
                      placeholder={row?.has_key ? "Replace key (sk-…)" : "Paste API key (sk-…)"}
                      aria-label={`${p.label} API key`}
                      autoComplete="off"
                      className="glass h-10 min-w-0 flex-1 rounded-xl px-3 font-mono text-sm text-cream placeholder:text-faint focus:border-gold/40 focus:outline-none"
                    />
                  )}
                  {p.kind === "custom" && (
                    <input
                      value={d.baseUrl}
                      onChange={(e) => setDraft((s) => ({ ...s, [p.id]: { ...d, baseUrl: e.target.value } }))}
                      placeholder="http://localhost:1234/v1"
                      aria-label="Base URL"
                      className="glass h-10 min-w-0 flex-1 rounded-xl px-3 font-mono text-sm text-cream placeholder:text-faint focus:border-gold/40 focus:outline-none"
                    />
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button variant="primary" size="sm" onClick={() => void save(p.id, true)}
                    disabled={busy === p.id || (!d.key.trim() && !d.baseUrl.trim() && !row?.has_key)}>
                    {busy === p.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : row?.has_key ? "Update & test" : "Save & test"}
                  </Button>
                  {row?.has_key && (
                    <>
                      <Button variant="subtle" size="sm" onClick={() => void verify(p.id)} disabled={busy === p.id}>
                        Test
                      </Button>
                      <Button variant="subtle" size="sm" onClick={() => void toggle(p.id, !row.enabled)}>
                        {row.enabled ? "Disable" : "Enable"}
                      </Button>
                      <Button variant="danger" size="sm" onClick={() => void remove(p.id)} disabled={busy === p.id}>
                        <Trash2 className="h-3.5 w-3.5" /> Remove
                      </Button>
                    </>
                  )}
                  {p.key_url && (
                    <a href={p.key_url} target="_blank" rel="noreferrer" className="ml-auto text-[11px] text-gold-bright hover:underline">
                      get a key ↗
                    </a>
                  )}
                </div>
                {row?.status === "failed" && row.status_detail && (
                  <p className="text-[11px] leading-snug text-[#f49a96]">{row.status_detail}</p>
                )}
              </div>
            </motion.div>
          );
        })}
      </div>
    </Panel>
  );
}

function MemoryPanel({ sys }: { sys: SystemStatus | null }) {
  return (
    <Panel>
      <Card title="Long-term memory" icon={MemoryStick}>
        <p className="mb-3 text-[13px] text-muted">
          <b className="text-cream">{sys?.counts.memories ?? "—"}</b> facts stored
          on this machine. The top 5 ride into the system prompt of every
          conversation — Hindi, Hinglish or English.
        </p>
        <Link href="/chat?view=memory">
          <Button variant="subtle" size="sm">Open the Memory view</Button>
        </Link>
      </Card>
      <Card title="Knowledge base" icon={Database}>
        <p className="mb-3 text-[13px] text-muted">
          Documents are chunked + FTS5-indexed on-device and cited into answers.
          Manage them in the Knowledge view.
        </p>
        <Link href="/chat?view=knowledge">
          <Button variant="subtle" size="sm">Open the Knowledge view</Button>
        </Link>
      </Card>
    </Panel>
  );
}

function PrivacyPanel({ reload }: { reload: () => Promise<void> }) {
  const [state, setState] = useState<"idle" | "busy" | "ok">("idle");
  const [detail, setDetail] = useState<string | null>(null);
  const chatWipe = useChat((s) => s.conversations.length);
  const bootstrap = useChat((s) => s.bootstrap);

  const wipe = async () => {
    setState("busy");
    setDetail(null);
    try {
      const r = await onboardingApi.wipeData();
      setDetail(`Wiped ${r.conversations_deleted} conversations and ${r.memories_deleted} memories from this machine.`);
      setState("ok");
      await reload();
      await bootstrap();
    } catch (err) {
      setDetail(err instanceof ApiError ? err.message : "Wipe failed.");
      setState("idle");
    }
  };

  return (
    <Panel>
      <Card title="Local-first, in numbers" icon={ShieldCheck}>
        <ul className="space-y-1.5 text-[12px] leading-relaxed text-muted">
          <li>· <b className="text-cream">0</b> telemetry events, ever — there is no analytics code to disable</li>
          <li>· Network calls happen only <i>when you make them</i>: the Vednix Engine on localhost, plus any cloud provider you personally configure</li>
          <li>· Passwords are PBKDF2 digests; API keys are Fernet-encrypted with a machine-bound secret</li>
          <li>· The whole app keeps answering even when the internet doesn't (cloud providers excluded, obviously)</li>
        </ul>
      </Card>
      <Card title="Danger zone" icon={Trash2}>
        <p className="mb-3 text-[12px] leading-relaxed text-muted">
          Wipes every conversation ({chatWipe}) and long-term memory from this
          machine. Uploaded files and knowledge documents stay (clear them in
          their views — they were added file-by-file, on purpose).
        </p>
        <Button variant="danger" size="sm" onClick={() => void wipe()} disabled={state === "busy"}>
          {state === "busy" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
          Wipe chats & memories
        </Button>
        {detail && <p className="mt-3 text-[11px] leading-snug text-faint">{detail}</p>}
      </Card>
    </Panel>
  );
}

function ExperimentalPanel() {
  const internet = useChat((s) => s.internet);
  const setInternet = useChat((s) => s.setInternet);
  const multiAgent = useChat((s) => s.multiAgent);
  const setMultiAgent = useChat((s) => s.setMultiAgent);
  return (
    <Panel>
      <Card title="Web research" icon={Globe}>
        <Switch checked={internet} onCheckedChange={setInternet} label="Internet search before answers (SearXNG · cited sources)" />
        <p className="mt-2 text-[11px] leading-snug text-faint">
          Needs a reachable SearXNG instance (self-hostable:
          docker run -p 8080:8080 searxng/searxng). Without one you get an
          honest "research unavailable" note, never a fake search.
        </p>
      </Card>
      <Card title="Multi-agent mode" icon={Bot}>
        <Switch checked={multiAgent} onCheckedChange={setMultiAgent} label="Planner → researcher → critic deep-research loop" />
        <p className="mt-2 text-[11px] leading-snug text-faint">
          Slower and deeper — implies web research. The live agent trace stacks
          above the reply while the swarm works.
        </p>
      </Card>
    </Panel>
  );
}

function AboutPanel() {
  return (
    <Panel>
      <Card title="Vednix AI" icon={Sparkles}>
        <p className="text-[13px] leading-relaxed text-muted">
          The AI Operating System — private-first, multilingual, premium by
          default. Next.js 15 + FastAPI + SQLAlchemy + LangGraph research, all
          orchestrated around an 8-state neural core.
        </p>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {["131 tests green", "8 neural states", "0 telemetry", "हिंदी · Hinglish · English"].map((t) => (
            <span key={t} className="glass rounded-lg px-2.5 py-1.5 font-mono text-[10px] text-muted">{t}</span>
          ))}
        </div>
      </Card>
      <Card title="Credits" icon={Info}>
        <div className="flex flex-col items-center gap-3 py-4">
          <Signature framed />
          <p className="text-center text-[11px] leading-relaxed text-faint">
            Designed and engineered with an obsession for local-first AI.
          </p>
        </div>
      </Card>
    </Panel>
  );
}

/* --- Admin (owner console) ------------------------------------------------ */

function AdminPanel() {
  const me = useAuth((s) => s.user);
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [resetId, setResetId] = useState<string | null>(null);
  const [resetPw, setResetPw] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setUsers((await adminApi.users()).users);
    } catch {
      setUsers([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const act = async (id: string, fn: () => Promise<unknown>, msg: string) => {
    setBusy(id);
    setNotice(null);
    try {
      await fn();
      setNotice(msg);
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "Action failed.");
    } finally {
      setBusy(null);
    }
  };

  const owners = users?.filter((u) => u.role === "owner").length ?? 0;

  return (
    <Panel>
      <Card title="Owner console" icon={Users}>
        <p className="text-[12px] leading-relaxed text-muted">
          You own this machine. Every account answers to you — reset a
          password, sign a user out everywhere, or remove them entirely.
          The last owner can never be removed (the door would brick itself).
        </p>
      </Card>

      {notice && (
        <p className="glass rounded-xl px-4 py-2.5 text-center text-[12px] text-gold-bright">{notice}</p>
      )}

      <div className="space-y-3">
        {(users ?? []).map((u, idx) => {
          const self = u.id === me?.id;
          const immortal = u.role === "owner" && owners <= 1;
          return (
            <motion.div
              key={u.id}
              className="glass-strong rounded-2xl p-5"
              initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.05, duration: 0.35 }}
            >
              <div className="flex flex-wrap items-center gap-3">
                <span className="flex h-11 w-11 items-center justify-center rounded-2xl border border-gold/30 bg-gold/[0.12] font-display text-base font-bold text-gold-bright">
                  {u.display_name.slice(0, 1).toUpperCase()}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2">
                    <span className="truncate font-semibold text-cream">{u.display_name}</span>
                    <span className={cn(
                      "rounded-md px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.16em]",
                      u.role === "owner" ? "bg-gold/20 text-gold-bright" : "bg-white/[0.06] text-muted",
                    )}>
                      {u.role}
                    </span>
                    {self && (
                      <span className="rounded-md bg-emerald-400/10 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.16em] text-emerald-300">
                        you
                      </span>
                    )}
                  </p>
                  <p className="mt-0.5 truncate text-[11px] text-faint">
                    @{u.username}{u.email ? ` · ${u.email}` : ""} · {u.live_sessions} live session{u.live_sessions === 1 ? "" : "s"}
                  </p>
                </div>
                <span className="flex items-center gap-1.5">
                  <Button variant="subtle" size="sm" disabled={busy === u.id}
                    onClick={() => { setResetId(resetId === u.id ? null : u.id); setResetPw(""); setConfirmDeleteId(null); }}>
                    <KeyRound className="h-3.5 w-3.5" /> Reset
                  </Button>
                  <Button variant="subtle" size="sm" disabled={busy === u.id}
                    onClick={() => void act(u.id, () => adminApi.revokeSessions(u.id), `${u.username}: signed out everywhere.`)}>
                    <MonitorSmartphone className="h-3.5 w-3.5" /> Sign out
                  </Button>
                  {self || immortal ? (
                    <span className="px-2 font-mono text-[9px] uppercase tracking-[0.16em] text-faint" title={self ? "You can't delete yourself" : "The last owner is immortal"}>
                      {self ? "you" : "last owner"}
                    </span>
                  ) : confirmDeleteId === u.id ? (
                    <>
                      <Button variant="danger" size="sm" disabled={busy === u.id}
                        onClick={() => void act(u.id, () => adminApi.deleteUser(u.id), `${u.username}: account removed.`).then(() => setConfirmDeleteId(null))}>
                        Sure?
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => setConfirmDeleteId(null)}>Keep</Button>
                    </>
                  ) : (
                    <Button variant="danger" size="sm" disabled={busy === u.id}
                      onClick={() => { setConfirmDeleteId(u.id); setResetId(null); }}>
                      <Trash2 className="h-3.5 w-3.5" /> Remove
                    </Button>
                  )}
                </span>
              </div>

              {resetId === u.id && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
                  className="mt-3 flex flex-wrap items-end gap-2 border-t border-white/[0.06] pt-3"
                >
                  <div className="min-w-52 flex-1">
                    <PasswordField
                      label={`New password for ${u.username} (8+)`}
                      value={resetPw}
                      onChange={(e) => setResetPw(e.target.value)}
                      autoComplete="new-password"
                    />
                  </div>
                  <Button
                    variant="primary" size="sm" className="h-10"
                    disabled={resetPw.length < 8 || busy === u.id}
                    onClick={() => void act(u.id, () => adminApi.resetPassword(u.id, resetPw),
                      `${u.username}: password reset, all devices signed out.`).then(() => { setResetId(null); setResetPw(""); })}
                  >
                    {busy === u.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <KeyRound className="h-3.5 w-3.5" />}
                    Set password
                  </Button>
                </motion.div>
              )}
            </motion.div>
          );
        })}
        {users && users.length === 0 && (
          <p className="text-center text-[12px] text-faint">No accounts found.</p>
        )}
      </div>
    </Panel>
  );
}
