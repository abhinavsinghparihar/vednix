# API key audit — the 50 keys supplied for review

Date: 2026-10-31 · Scope: 50 `sk-…` values pasted in the project chat
Method: `backend/core/key_validation.py` (format fingerprints, repeated-block
detection, alphabet entropy, placeholder vocabulary) plus an independent
entropy/periodicity pass.

**Verdict: 50 of 50 are hand-typed examples, not provider credentials.**
None is usable, none was added to the codebase, and none was needed to be —
implementing them would have weakened the project, not improved it.

## Why they are not real keys

| Property | Observed in these 50 | What real keys look like |
|---|---|---|
| Alphabet | only `abcd…uvwx` letter blocks and `1234/5678` digit blocks | base62/base64url, uniformly random |
| Repetition | 12/50 are one block repeated exactly; 35/50 paste the same block ≥2× | no repeated structure |
| Shannon entropy | 3.09 – 4.62 bits/char | ≈ 5.0 – 6.0 bits/char |
| Length | 41 or 43 chars | 48 (legacy OpenAI), 51+ (`sk-proj-`), or provider-specific |
| Provider shape | all match the generic `sk-` shape only — ambiguous between OpenAI and DeepSeek | one documented prefix + length |
| Duplicates | 47 unique values (3 duplicates) | — |

Every value was rejected by the importer, with a specific reason:

* 35 × *repeated block* — the same 8–16 character block pasted more than once;
* 12 × *periodic block* — one unit repeated for the whole key;
* 3 × *abc/123 alphabet* — built only from `abcd/efgh/…/1234/5678` groups.

## Full result set (masked)

Only the first six and last four characters are shown; full values are not
reproduced anywhere in this repository.

| # | Masked | Length | Entropy (bits/char) | Importer verdict |
|---|---|---|---|---|
| 1 | `sk-abc…ef12` | 43 | 4.17 | repeated block |
| 2 | `sk-123…5678` | 43 | 4.17 | repeated block |
| 3 | `sk-abc…ef12` | 41 | 3.09 | repeated block |
| 4 | `sk-789…abcd` | 41 | 3.56 | repeated block |
| 5 | `sk-123…abcd` | 43 | 3.27 | periodic block |
| 6 | `sk-abc…1234` | 43 | 3.27 | periodic block |
| 7 | `sk-567…efgh` | 43 | 3.27 | periodic block |
| 8 | `sk-efg…5678` | 43 | 3.27 | periodic block |
| 9 | `sk-ijk…1234` | 43 | 3.18 | periodic block |
| 10 | `sk-mno…5678` | 43 | 3.27 | periodic block |
| 11 | `sk-qrs…1234` | 43 | 3.18 | periodic block |
| 12 | `sk-uvw…5678` | 43 | 3.27 | periodic block |
| 13 | `sk-123…ijkl` | 43 | 3.18 | periodic block |
| 14 | `sk-567…mnop` | 43 | 3.27 | periodic block |
| 15 | `sk-qrs…5678` | 43 | 3.18 | periodic block |
| 16 | `sk-uvw…1234` | 43 | 3.27 | periodic block |
| 17 | `sk-123…abcd` | 43 | 4.17 | repeated block |
| 18 | `sk-567…ijkl` | 43 | 4.09 | repeated block |
| 19 | `sk-abc…qrst` | 43 | 4.09 | repeated block |
| 20 | `sk-ijk…mnop` | 43 | 4.03 | repeated block |
| 21 | `sk-123…uvwx` | 43 | 4.17 | repeated block |
| 22 | `sk-efg…mnop` | 43 | 4.62 | abc/123 alphabet |
| 23 | `sk-mno…qrst` | 43 | 4.09 | repeated block |
| 24 | `sk-ijk…mnop` | 43 | 4.03 | repeated block |
| 25 | `sk-abc…1234` | 43 | 4.17 | repeated block |
| 26 | `sk-123…5678` | 43 | 4.09 | abc/123 alphabet |
| 27 | `sk-qrs…efgh` | 43 | 4.09 | repeated block |
| 28 | `sk-uvw…ijkl` | 43 | 4.09 | repeated block |
| 29 | `sk-abc…5678` | 43 | 4.17 | repeated block |
| 30 | `sk-ijk…mnop` | 43 | 4.03 | repeated block |
| 31 | `sk-123…qrst` | 43 | 4.09 | repeated block |
| 32 | `sk-efg…ijkl` | 43 | 4.09 | repeated block |
| 33 | `sk-mno…abcd` | 43 | 4.17 | repeated block |
| 34 | `sk-ijk…qrst` | 43 | 4.02 | repeated block |
| 35 | `sk-123…ijkl` | 43 | 4.09 | repeated block |
| 36 | `sk-abc…qrst` | 43 | 4.09 | repeated block |
| 37 | `sk-ijk…mnop` | 43 | 4.09 | repeated block |
| 38 | `sk-efg…5678` | 43 | 4.17 | repeated block |
| 39 | `sk-mno…qrst` | 43 | 4.03 | repeated block |
| 40 | `sk-123…5678` | 43 | 4.17 | abc/123 alphabet |
| 41 | `sk-ijk…mnop` | 43 | 4.09 | repeated block |
| 42 | `sk-abc…1234` | 43 | 4.11 | repeated block |
| 43 | `sk-123…efgh` | 43 | 4.11 | repeated block |
| 44 | `sk-567…mnop` | 43 | 4.11 | repeated block |
| 45 | `sk-abc…ijkl` | 43 | 4.09 | repeated block |
| 46 | `sk-ijk…mnop` | 43 | 4.09 | repeated block |
| 47 | `sk-123…efgh` | 43 | 4.11 | repeated block |
| 48 | `sk-567…ijkl` | 43 | 4.09 | repeated block |
| 49 | `sk-abc…1234` | 43 | 4.17 | repeated block |
| 50 | `sk-ijk…mnop` | 43 | 4.03 | repeated block |

## Threat assessment

| Scenario | Risk | Result |
|---|---|---|
| Committing these values to source | **High** — every pattern the scanner looks for; a single real key in a fork stays valid forever | Would have been blocked by CI (`scripts/scan_secrets.py`) |
| Using them as provider keys | None — they cannot authenticate anywhere | Rejected before they reach the encrypted vault |
| Salting the project with a "shared free key" | **High** — shared secrets are unrevocable once exposed and can be abused by anyone | Not implemented; free use is keyless instead |
| Passing them through the vault anyway | Low, but dishonest: the UI would claim a provider exists | Importer refuses them |

The real threat was never the values themselves — it was the *habit* of moving
credentials through chat, source files, and READMEs. That is the risk this
change removes.

## What was implemented instead

1. **No key in code, ever.** `backend/scripts/import_keys.py` is the only
   supported batch path: it validates, encrypts with the machine secret, and
   stores keys as Fernet ciphertext in the database. Plaintext is never printed,
   logged, or written to disk.
2. **A leak fails the build.** `scripts/scan_secrets.py` runs in CI on every
   push and fails when a credential-shaped string appears in a tracked file
   (deliberate `mock`/`test`/`example` fixtures stay allowed).
3. **Free use with no key at all.** The "Free use" option next to the API-key
   field uses a keyless shared tier (`VEDNIX_FREE_USE_*`), verified live before
   it can answer, budgeted per hour, and always last in routing so a real key
   wins.

## What to do with the real keys

```bash
cd backend
python scripts/import_keys.py --stdin      # paste `provider=key` lines, Ctrl-D
python scripts/import_keys.py --file ~/vednix-keys.txt --verify
```

Then delete the temp file. The Settings screen shows the same `…a1b2`
fingerprint for each stored key — that hint is the only fragment the server
will ever echo back.
