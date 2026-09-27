"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight, ArrowUpRight, CheckCircle2, ChevronLeft, KeyRound, Loader2, ShieldCheck, XCircle } from "lucide-react";
import { providerApi, type ProviderCatalogItem, type ProviderConfig, type VerifyResult } from "@/lib/authApi";
import { ApiError } from "@/lib/tokenVault";
import { Button } from "@/components/ui/primitives";
import { cn, EASE_CURVE } from "@/lib/utils";
import { StepTitle } from "./shared";

function ProviderSetup({
  provider, configured, onBack, onConnected,
}: {
  provider: ProviderCatalogItem;
  configured?: ProviderConfig;
  onBack: () => void;
  onConnected: () => void;
}) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [error, setError] = useState<string | null>(null);

  const verify = async () => {
    if (!key.trim() && !configured?.has_key) {
      setError("Enter an API key to connect this provider.");
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      if (key.trim()) {
        await providerApi.saveKey(provider.id, { api_key: key.trim() });
        setKey(""); // the key is never retained after its one-time POST
      }
      const check = await providerApi.verify(provider.id);
      setResult(check);
      if (!check.connected) return;
      const catalog = await providerApi.models(provider.id, "text");
      setModels(catalog.available);
      setSelectedModel(check.verification_model ?? catalog.default ?? catalog.available[0] ?? "");
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not verify this provider. Check the backend and retry.";
      setError(message);
      setResult({ provider: provider.id, connected: false, detail: message, models: [] });
    } finally {
      setBusy(false);
    }
  };

  const useModel = async () => {
    if (!selectedModel) return;
    setBusy(true);
    setError(null);
    try {
      await providerApi.saveKey(provider.id, { model: selectedModel });
      const check = await providerApi.verify(provider.id);
      setResult(check);
      if (!check.connected) setError(check.detail || "The selected model failed its text capability check.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not verify the selected model.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <button onClick={onBack} className="mb-4 inline-flex items-center gap-1.5 text-[11px] text-faint transition-colors hover:text-gold-bright">
        <ChevronLeft className="h-3.5 w-3.5" /> All providers
      </button>
      <StepTitle kicker="Provider setup" title={provider.label} sub={provider.blurb} />
      <div className="mx-auto max-w-xl space-y-4">
        <motion.a
          href={provider.key_url} target="_blank" rel="noreferrer"
          className="glass group flex items-center justify-between rounded-2xl px-5 py-4 transition-colors hover:border-gold/35 hover:bg-gold/[0.04]"
          initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
        >
          <span className="flex items-center gap-3">
            <KeyRound className="h-4 w-4 text-gold" />
            <span className="text-sm font-semibold text-cream">Get an API key from {provider.label}</span>
          </span>
          <ArrowUpRight className="h-4 w-4 text-gold-bright transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
        </motion.a>

        <div className="glass rounded-2xl p-5">
          <label htmlFor="provider-key" className="mb-3 block text-sm font-semibold text-cream">
            {configured?.has_key ? "Replace saved key (optional)" : "Paste your API key"}
          </label>
          <input
            id="provider-key"
            type="password"
            value={key}
            onChange={(event) => setKey(event.target.value)}
            placeholder={configured?.has_key ? "Leave blank to use the saved key" : "API key"}
            autoComplete="off"
            spellCheck={false}
            className="glass h-11 w-full rounded-xl px-3.5 font-mono text-sm text-cream placeholder:text-faint focus:border-gold/40 focus:outline-none"
          />
          <p className="mt-3 flex items-start gap-2 text-[11px] leading-snug text-faint">
            <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gold" />
            The key is sent once to this backend, encrypted at rest, and never returned to the browser or stored in browser storage.
          </p>
          <div className="mt-4 flex justify-end">
            <Button variant="primary" onClick={() => void verify()} disabled={busy || (!key.trim() && !configured?.has_key)}>
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <>Save securely & verify <ArrowRight className="h-4 w-4" /></>}
            </Button>
          </div>
        </div>

        {error && <p role="alert" className="text-center text-[12px] text-[#f49a96]">{error}</p>}

        {result && (
          <div className={cn("glass-strong rounded-2xl p-5", result.connected && "border-emerald-400/35")}>
            <div className="flex items-start gap-3">
              {result.connected
                ? <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-400" />
                : <XCircle className="mt-0.5 h-5 w-5 shrink-0 text-[#f0746e]" />}
              <div className="min-w-0 flex-1">
                <p className={cn("font-display text-base font-bold", result.connected ? "text-emerald-300" : "text-[#f49a96]")}>
                  {result.connected ? "Key and model verified" : "Provider check failed"}
                </p>
                <p className="mt-1 break-words text-[12px] leading-snug text-muted">
                  {result.connected ? `Live text generation succeeded with ${result.verification_model}.` : result.detail}
                </p>
              </div>
            </div>
            {result.connected && models.length > 0 && (
              <div className="mt-4 space-y-3">
                <label htmlFor="provider-model" className="block text-[11px] font-semibold uppercase tracking-[0.16em] text-faint">
                  Live-validated text models
                </label>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <select
                    id="provider-model"
                    value={selectedModel}
                    onChange={(event) => setSelectedModel(event.target.value)}
                    className="glass min-w-0 flex-1 rounded-xl px-3 py-2.5 text-sm text-cream outline-none [&>option]:bg-charcoal"
                  >
                    {models.map((model) => <option key={model} value={model}>{model}</option>)}
                  </select>
                  <Button variant="subtle" onClick={() => void useModel()} disabled={busy || !selectedModel || selectedModel === result.verification_model}>
                    {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Verify selection"}
                  </Button>
                </div>
                <p className="text-[11px] text-faint">Only models that passed a real text-generation check are listed as usable.</p>
              </div>
            )}
            {result.connected && (
              <div className="mt-4 flex justify-end">
                <Button variant="primary" onClick={() => void onConnected()}>
                  Continue <ArrowRight className="h-4 w-4" />
                </Button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function ProviderWizard({ onDone, onExit }: { onDone: () => void; onExit: () => void }) {
  const [catalog, setCatalog] = useState<ProviderCatalogItem[]>([]);
  const [configured, setConfigured] = useState<ProviderConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState<ProviderCatalogItem | null>(null);

  useEffect(() => {
    void Promise.all([providerApi.catalog(), providerApi.configured()])
      .then(([providers, configs]) => {
        setCatalog(providers.providers);
        setConfigured(configs.providers);
      })
      .catch(() => setCatalog([]))
      .finally(() => setLoading(false));
  }, []);

  if (active) {
    return <ProviderSetup
      provider={active}
      configured={configured.find((item) => item.provider === active.id)}
      onBack={() => setActive(null)}
      onConnected={onDone}
    />;
  }

  return (
    <div>
      <button onClick={onExit} className="mb-4 text-[11px] text-faint transition-colors hover:text-gold-bright">
        ← Back to welcome
      </button>
      <StepTitle kicker="Secure provider setup" title="Choose an AI provider" sub="Connect Gemini or Groq with a server-encrypted key. Model lists come from official live APIs and are checked before use." />
      {loading ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-gold" /></div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {catalog.map((provider, index) => (
            <motion.button
              key={provider.id}
              onClick={() => setActive(provider)}
              className="glass group flex min-h-40 flex-col items-start gap-3 rounded-2xl p-5 text-left transition-colors hover:border-gold/35 hover:bg-gold/[0.04]"
              initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 + index * 0.08, duration: 0.45, ease: EASE_CURVE }}
              whileHover={{ y: -2 }} whileTap={{ scale: 0.985 }}
            >
              <span className="flex w-full items-center justify-between">
                <span className="flex h-11 w-11 items-center justify-center rounded-xl border border-gold/30 bg-gold/10 font-display text-lg font-extrabold text-gold-bright">
                  {provider.label.replace(/[^a-z]/gi, "").slice(0, 1).toUpperCase()}
                </span>
                <span className={cn("rounded-full border px-2.5 py-1 text-[10px]", configured.some((row) => row.provider === provider.id && row.verified)
                  ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-300"
                  : "border-white/10 bg-white/[0.03] text-faint")}>
                  {configured.some((row) => row.provider === provider.id && row.verified) ? "Verified" : "Needs setup"}
                </span>
              </span>
              <span>
                <span className="block font-display text-base font-bold text-cream">{provider.label}</span>
                <span className="mt-1 block text-[11px] leading-snug text-faint">{provider.blurb}</span>
              </span>
            </motion.button>
          ))}
        </div>
      )}
      <div className="mt-8 flex justify-end">
        <Button variant="ghost" onClick={() => void onDone()}>Skip for now <ArrowRight className="h-4 w-4" /></Button>
      </div>
    </div>
  );
}
