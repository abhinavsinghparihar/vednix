# Secret handling in Vednix

Rule zero: **no credential is ever stored in source.** Not in a Python file, a
TypeScript constant, a test fixture, a README, a Docker image, or an environment
variable baked into a frontend build. A key in a tracked file is a leaked key,
because Git remembers it even after a later commit deletes the line.

This document describes where secrets *may* live, how they get there, and how
they leave.

## The three legal homes

| Secret | Where it lives | How it gets there |
|---|---|---|
| Provider API keys (Groq, OpenAI, …) | Encrypted in the app database (`provider_keys.key_ciphertext`, Fernet / AES-CBC + HMAC-SHA256) | Settings → API Keys, or `backend/scripts/import_keys.py` |
| Machine secret (signs sessions, derives the key-encryption key) | `data/secret.key` (mode `0600`) and/or `VEDNIX_SECRET_KEY` | Generated on first boot, or supplied by the operator |
| Deployment secrets (SMTP password, optional operator token for the free tier, `VEDNIX_AUTH_TOKEN`) | Backend environment / platform secret store | Operator, at deploy time |

Provider keys are **never** put in `NEXT_PUBLIC_*`, browser storage, URLs, API
responses, or logs. The only value the browser ever sees is a non-reversible
fingerprint such as `…a1b2`.

## Adding provider keys

### Interactive (recommended for one or two keys)

Settings → **API Keys** → paste the key → *Save key & verify*. The key is POSTed
once, encrypted, and never returned. The card then shows the fingerprint and the
live verification state.

### Batch import (recommended for several keys)

```bash
cd backend
python scripts/import_keys.py --stdin          # paste `provider=key` lines, then Ctrl-D
python scripts/import_keys.py --file ~/vednix-keys.txt
python scripts/import_keys.py --file ~/vednix-keys.txt --verify   # also run a live check
```

The importer:

* accepts `provider=key`, `provider,key`, `provider:key`, or a bare key whose
  provider can be identified unambiguously;
* rejects documentation placeholders, typed examples (`abcd1234…` blocks,
  periodic values, low-entropy strings) and wrong-format values **before**
  writing anything;
* refuses to store the same credential under two providers;
* prints only fingerprints, never the key;
* stores every imported key as `unverified` and disabled — the live capability
  probe in the UI is still the gate that makes a provider usable;
* writes only ciphertext, so `vednix.db` alone reveals nothing.

`--dry-run` validates without touching the vault. Delete the temporary key file
as soon as the import finishes; `*.keys.txt`, `*keys*.txt` and `vednix-keys*`
are already git-ignored as a second line of defence.

### Rotation and removal

* **Rotate:** import the new key for the same provider; prior verification is
  discarded and the provider must be verified again.
* **Remove:** Settings → API Keys → *Remove*, or
  `DELETE /api/providers/{provider}/key`. Both delete the ciphertext and every
  cached model validation for that provider.
* **Nuclear reset:** delete `data/secret.key`. Every stored key becomes
  undecryptable and every session is invalidated. Re-import the keys you still
  trust.

## Free use: the zero-secret path

"Free use" (next to the API-key field in Settings and in onboarding) needs no
account and stores no credential. It talks to a shared, keyless endpoint that
the operator configures with environment variables:

```text
VEDNIX_FREE_USE_ENABLED=true
VEDNIX_FREE_USE_BASE_URL=https://text.pollinations.ai/openai   # operator-chosen endpoint
VEDNIX_FREE_USE_MODELS=openai,mistral
VEDNIX_FREE_USE_REQUESTS_PER_HOUR=120
# VEDNIX_FREE_USE_API_KEY=…   # only if your endpoint requires an operator token
```

If `VEDNIX_FREE_USE_API_KEY` is set it stays in the process environment: it is
never written to the database, never returned by an API, and is scrubbed from
every error detail string. Free use is last in automatic routing, so a verified
provider key always wins, and the hourly budget is enforced server-side.

## Preventing the next leak

`scripts/scan_secrets.py` scans every tracked file for credential shapes
(Groq `gsk_`, OpenAI `sk-`/`sk-proj-`, OpenRouter, Anthropic, xAI, NVIDIA,
Perplexity, Cerebras, Google) and fails on a hit. CI runs it on every push and
pull request:

```bash
python scripts/scan_secrets.py     # exit 0 = clean, 1 = leak found
```

Deliberate fakes in tests must announce themselves with `mock`, `test`, `fake`,
`example`, `placeholder`, `dummy`, `sample`, or `redacted` — otherwise the scan
treats them as real.

## If a key does leak

1. **Rotate it at the provider first** — assume it is already in use.
2. Remove it from the working tree *and* rewrite history if the commit was
   public (`git filter-repo`); a force-push alone does not un-leak a fork.
3. Import the replacement with `backend/scripts/import_keys.py`.
4. If the leaked secret was `VEDNIX_SECRET_KEY` or `data/secret.key`, treat it as
   a full reset as described above.

## Sessions ("stay signed in")

A device that signs in with *Stay signed in on this device* receives an
httpOnly refresh cookie whose server-side session slides forward on every use
(`VEDNIX_SESSION_DAYS`, default 3650 days). It does not expire from inactivity
alone. It **does** end immediately on:

* *Sign out* on that device,
* *Revoke* from Profile → Devices,
* a password change (all other sessions are revoked),
* an owner action in Settings → Admin, or
* deletion of `data/secret.key`.

A network blip is explicitly *not* a sign-out: the client retries a failed silent
refresh and only clears local state on a real `401` from `/api/auth/refresh`.
