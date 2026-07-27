/**
 * CloudWizard — bring-your-own-key setup: a grid of provider cards (from the
 * backend catalog), each opening a guided flow: what this provider is → get
 * the key (official console button) → paste (never echoed back) → verify
 * (real API round-trip, green animation or the provider's own error) → done.
 */

"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  ArrowRight, ArrowUpRight, CheckCircle2, ChevronLeft, KeyRound, Loader2, ShieldCheck, XCircle,
} from "lucide-react";
import { providerApi, type ProviderCatalogItem } from "@/lib/authApi";
import { ApiError } from "@/lib/tokenVault";
import { Button } from "@/components/ui/primitives";
import { cn, EASE_CURVE } from "@/lib/utils";
import { StatusDot, StepTitle } from "./shared";

/** Monogram badge — trademark-safe (no copied logos): the provider's initial
 * in the shared gold-glass chip style. */
function Monogram({ label }: { label: string }) {
  return (
    <span className="flex h-11 w-11 items-center justify-center rounded-xl border border-gold/30 bg-gradient-to-br from-gold/15 to-gold/[0.04] font-display text-lg font-extrabold text-gold-bright">
      {label.replace(/[^a-zA-Z]/g, "").slice(0, 1).toUpperCase()}
    </span>
  );
}

function ProviderSetup({
  provider, onBack, onConnected,
}: {
  provider: ProviderCatalogItem;
  onBack: () => void;
  onConnected: () => void;
}) {
  const [key, setKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [busy, setBusy] = useState<"save" | "verify" | null>(null);
  const [result, setResult] = useState<{ ok: boolean; detail: string; models: string[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isCustom = provider.kind === "custom";

  const save = async () => {
    setBusy("save");
    setError(null);
    setResult(null);
    try {
      await providerApi.saveKey(provider.id, {
        api_key: key, ...(isCustom ? { base_url: baseUrl } : {}),
      });
      setKey("");
      return true;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save — retry?");
      return false;
    } finally {
      setBusy(null);
    }
  };

  const verify = async () => {
    if (!(await save())) return;
    setBusy("verify");
    try {
      const r = await providerApi.verify(provider.id);
      setResult({ ok: r.connected, detail: r.detail, models: r.models });
    } catch (err) {
      setResult({ ok: false, detail: err instanceof ApiError ? err.message : "verify failed", models: [] });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div>
      <button onClick={onBack} className="mb-4 inline-flex items-center gap-1.5 text-[11px] text-faint transition-colors hover:text-gold-bright">
        <ChevronLeft className="h-3.5 w-3.5" /> all providers
      </button>

      <StepTitle
        kicker="Cloud mode"
        title={provider.label}
        sub={provider.blurb}
      />

      <div className="mx-auto max-w-lg space-y-4">
        {provider.key_url && (
          <motion.a
            href={provider.key_url} target="_blank" rel="noreferrer"
            className="glass group flex items-center justify-between rounded-2xl px-5 py-4 transition-colors duration-200 hover:border-gold/35 hover:bg-gold/[0.04]"
            initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
          >
            <span className="flex items-center gap-3">
              <KeyRound className="h-4 w-4 text-gold" />
              <span className="text-sm font-semibold text-cream">1 · Create your API key</span>
            </span>
            <span className="inline-flex items-center gap-1 text-[12px] text-gold-bright">
              official console <ArrowUpRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
            </span>
          </motion.a>
        )}

        <motion.div
          className="glass rounded-2xl p-5"
          initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}
        >
          <p className="mb-3 text-sm font-semibold text-cream">
            {provider.key_url ? "2" : "1"} · {isCustom ? "Point at your endpoint" : "Paste the key here"}
          </p>
          <div className="space-y-3">
            {isCustom && (
              <input
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="http://localhost:1234/v1"
                aria-label="Base URL"
                className="glass h-11 w-full rounded-xl px-3.5 font-mono text-sm text-cream placeholder:text-faint focus:border-gold/40 focus:outline-none"
              />
            )}
            {(provider.needs_key || isCustom) && (
              <input
                type="password"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder={isCustom ? "API key (if your endpoint needs one)" : "sk-… (stored encrypted, shown once)"}
                aria-label="API key"
                autoComplete="off"
                className="glass h-11 w-full rounded-xl px-3.5 font-mono text-sm text-cream placeholder:text-faint focus:border-gold/40 focus:outline-none"
              />
            )}
            <p className="flex items-center gap-2 text-[11px] leading-snug text-faint">
              <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-gold" />
              Keys are encrypted on disk and never leave this backend. Vednix
              shows only the last 4 characters afterwards.
            </p>
          </div>
        </motion.div>

        {error && <p className="text-center text-[12px] text-[#f49a96]">{error}</p>}

        {result && (
          <motion.div
            className={cn(
              "glass-strong rounded-2xl p-5 text-center",
              result.ok && "border-emerald-400/40 shadow-[inset_0_0_0_1px_rgba(52,211,153,0.25)]",
            )}
            initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }}
          >
            {result.ok ? (
              <>
                <CheckCircle2 className="mx-auto mb-2 h-8 w-8 text-emerald-400" />
                <p className="font-display text-lg font-bold text-emerald-300">Connected</p>
                {result.models.length > 0 && (
                  <p className="mt-1 font-mono text-[10px] text-faint">
                    {result.models.slice(0, 3).join(" · ")}{result.models.length > 3 ? ` +${result.models.length - 3} more` : ""}
                  </p>
                )}
                <Button variant="primary" className="mt-4" onClick={onConnected}>
                  Continue <ArrowRight className="h-4 w-4" />
                </Button>
              </>
            ) : (
              <>
                <XCircle className="mx-auto mb-2 h-8 w-8 text-[#f0746e]" />
                <p className="font-display text-lg font-bold text-[#f49a96]">Not connecting</p>
                <p className="mx-auto mt-1 max-w-sm text-[12px] leading-snug text-muted">{result.detail}</p>
              </>
            )}
          </motion.div>
        )}

        <div className="flex items-center justify-between pt-2">
          <Button variant="ghost" onClick={onBack}><ChevronLeft className="h-4 w-4" /> Back</Button>
          <div className="flex gap-2">
            <Button variant="subtle" onClick={() => void verify()}
              disabled={busy !== null || (provider.needs_key && !key.trim() && !result?.ok) || (isCustom && !baseUrl.trim())}>
              {busy === "verify" ? <Loader2 className="h-4 w-4 animate-spin" /> : "Test connection"}
            </Button>
            <Button variant="ghost" onClick={onConnected}>Skip for now</Button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function CloudWizard({ onDone, onExit }: { onDone: () => void; onExit: () => void }) {
  const [catalog, setCatalog] = useState<ProviderCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState<ProviderCatalogItem | null>(null);

  useEffect(() => {
    void providerApi.catalog()
      .then((r) => setCatalog(r.providers.filter((p) => p.id !== "ollama")))
      .catch(() => setCatalog([]))
      .finally(() => setLoading(false));
  }, []);

  if (active) {
    return <ProviderSetup provider={active} onBack={() => setActive(null)} onConnected={onDone} />;
  }

  return (
    <div>
      <button onClick={onExit} className="mb-4 text-[11px] text-faint transition-colors hover:text-gold-bright">
        ← choose a different mode
      </button>
      <StepTitle
        kicker="Cloud mode"
        title="Pick your provider"
        sub="One guided setup each: official console, paste key, live connection test. Add more later in Settings."
      />
      {loading ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-gold" /></div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {catalog.map((p, i) => (
            <motion.button
              key={p.id}
              onClick={() => setActive(p)}
              className="glass group flex flex-col items-start gap-3 rounded-2xl p-5 text-left transition-colors duration-200 hover:border-gold/35 hover:bg-gold/[0.04]"
              initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 + i * 0.06, duration: 0.45, ease: EASE_CURVE }}
              whileHover={{ y: -2 }}
              whileTap={{ scale: 0.985 }}
            >
              <span className="flex w-full items-center justify-between">
                <Monogram label={p.label} />
                <StatusDot tone="idle" />
              </span>
              <span>
                <span className="block font-display text-base font-bold text-cream">{p.label}</span>
                <span className="mt-0.5 block text-[11px] leading-snug text-faint">{p.blurb}</span>
              </span>
              <span className="mt-auto font-mono text-[9px] uppercase tracking-[0.2em] text-faint/80 group-hover:text-gold-bright">
                {p.needs_key ? "needs API key" : "endpoint URL"}
              </span>
            </motion.button>
          ))}
        </div>
      )}
      <div className="mt-8 flex justify-end">
        <Button variant="ghost" onClick={onDone}>Skip — set up later in Settings <ArrowRight className="h-4 w-4" /></Button>
      </div>
    </div>
  );
}
