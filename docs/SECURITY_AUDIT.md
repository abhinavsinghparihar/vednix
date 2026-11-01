# Vednix AI — Security Audit & Hardening Report

**Date:** 2026-10-11
**Scope:** Full stack — FastAPI backend (`backend/`), Next.js frontend (`frontend/`), container/deploy configuration, dependency tree, and git history.
**Method:** Line-by-line review of every authentication, authorization, input-handling, storage and configuration path; live end-to-end probing of a running instance; `pip-audit` and `npm audit` against the resolved dependency trees; secret-pattern scan of the complete git history.

**Result:** every requested control is in place and verified. No known vulnerabilities remain in either dependency tree. No credentials were ever committed to git history.

---

## 1. What was verified (and was already correct)

These controls were reviewed and confirmed working — they are listed so the audit is complete, not because they changed.

| Area | Control | Status |
|---|---|---|
| Secret storage | Provider API keys encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256), key derived from a machine-local secret; a stolen database alone reveals nothing | ✅ verified (`core/crypto.py`) |
| Secret storage | Machine secret written `0600`, persisted in the DB so container restarts don't invalidate sessions/keys | ✅ verified |
| Secret exposure | Keys are never returned by any endpoint — only a `…a1b2` fingerprint; status/error text is redacted through `_SECRET_PATTERNS` before reaching a client | ✅ verified live |
| Authentication | Access tokens: HS256 JWT, 20-minute TTL, constant-time signature comparison, carried **only** in the `Authorization` header (never a cookie, never `localStorage`) | ✅ verified |
| Authentication | Refresh tokens: 48 random bytes, only a SHA-256 digest stored, rotated on every use, reuse ⇒ the whole session chain is treated as stolen | ✅ verified |
| Authentication | CSRF: double-submit token on the two cookie-bearing endpoints; API writes are CSRF-immune by construction (header-only bearer tokens) | ✅ verified |
| Authorization | `SessionMiddleware` (ASGI, so it also covers WebSocket scopes) locks every `/api/*` and `/ws/*` route once one account exists | ✅ verified live |
| Authorization | Admin console (`/api/admin/*`) re-checks the current database role (`owner`) — a member gets 403, an anonymous request 401 | ✅ verified live |
| Authorization | Public signup always creates members; owners are explicitly provisioned from the trusted server console | ✅ verified |
| Brute force | Per-IP login lockout (5 failures ⇒ 5-minute lockout) plus a dedicated 10/min credential-endpoint bucket, separate from the 120/min global limiter | ✅ verified |
| Input handling | Uploads validated by extension, declared-vs-detected MIME, size and content before touching disk; message length bounded; NUL bytes stripped | ✅ verified |
| Input handling | Raw exception text is never echoed to clients (`safe_error_message`), and provider-key validation errors strip the echoed input | ✅ verified |
| Database | SQLAlchemy ORM/parameterized queries only; WAL journal mode; foreign keys enforced | ✅ verified |
| WebSocket | Origin checked against the exact CORS allow-list before `accept()`; unauthenticated upgrade closed with 4401; per-connection token bucket (8 msgs / 20 s) | ✅ verified |
| XSS | `react-markdown` **without** `rehype-raw` — raw HTML in model output is never parsed as HTML | ✅ verified |
| XSS | Mermaid diagrams render at `securityLevel: "strict"` | ✅ verified |
| CORS | Exact credentialed origins only — wildcards, URL paths, userinfo and fragments are rejected by a settings validator | ✅ verified |
| Debug | `dev_reload` defaults to off; no stack traces or debug payloads in responses | ✅ verified |

---

## 2. Findings fixed in this pass

### 2.1 Security response headers (backend) — **added**
`SecurityHeadersMiddleware` (`backend/main.py`) now attaches to **every** response — including the 401/403/429 short-circuits produced by the inner middlewares:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Content-Security-Policy: default-src 'self'; … frame-ancestors 'none'; base-uri 'none'; form-action 'self'`
- `Permissions-Policy: camera=(self), microphone=(self), geolocation=(), payment=(), usb=(), interest-cohort=()`
- `Cross-Origin-Opener-Policy: same-origin-allow-popups` (keeps OAuth-style redirects working)
- `X-Permitted-Cross-Domain-Policies: none`
- `Strict-Transport-Security: max-age=63072000; includeSubDomains` — **only on HTTPS requests**, so local development is never pinned to https.

### 2.2 Security response headers (frontend) — **added**
`frontend/next.config.ts` now emits the same baseline plus a CSP built for this app: `connect-src` allows the same-origin `/api` proxy **and** the backend origin in both `http(s)` and `ws(s)` form (the chat WebSocket connects to the backend directly), `img-src 'self' data: blob:` for attachments, `object-src 'none'`, `frame-ancestors 'none'`. HSTS is emitted only for production builds. Extra origins can be allowed with `NEXT_PUBLIC_CSP_CONNECT_EXTRA` if a deployment splits the API and WebSocket hosts.

> **Known trade-off:** `script-src`/`style-src` keep `'unsafe-inline'` because Next.js injects inline bootstrap/hydration scripts; a nonce-based CSP would require request middleware plus nonce propagation into the RSC payload. The application renders no user-supplied HTML (see §1), so the residual exposure is dependency-level, not application-level. Verified live: all headers present on `/` and on the 401 rejection path.

### 2.3 Interactive API docs exposed — **fixed**
`/docs`, `/redoc` and `/openapi.json` were publicly readable — a free map of every endpoint. They are now **off by default** (`docs_url`/`redoc_url`/`openapi_url` set to `None`) and can be enabled deliberately with `VEDNIX_API_DOCS=1` for local development. Verified live: all three return 404.

### 2.4 Password hashing strength — **raised**
PBKDF2-HMAC-SHA256 iterations raised **200,000 → 600,000** (the OWASP Password Storage Cheat Sheet figure). The stored format is self-describing (`pbkdf2$iters$salt$hash`), so existing hashes at the old iteration count still verify — no forced password resets.

### 2.5 Access-token hardening — **added**
`verify_access_token` (`backend/core/tokens.py`) now enforces, in order:

1. exactly three segments, valid base64url in each;
2. the HMAC signature is checked **before** any claim is trusted (constant time);
3. the JOSE header must be exactly `{"alg":"HS256","typ":"JWT"}` — an unpinned header is how `alg:none` and algorithm-confusion attacks begin;
4. `exp` must be in the future (`<=`, not `<`) and `iat` must not be more than 60 s in the future;
5. `sub`, `username`, `role` and the new `sid` claim must all be present.

### 2.6 Session revocation actually revokes — **fixed**
Access tokens now carry a `sid` claim naming the refresh session they were minted from, and `SessionMiddleware` verifies that session is still live (exists, unrevoked, unexpired) on **every** request. Previously a logout or an admin "revoke sessions" action only killed the refresh cookie, leaving a stolen access token usable for up to 20 minutes. Verified live: after `POST /api/auth/logout`, the previously valid access token returns 401 immediately.

### 2.7 Secrets in Docker images — **closed**
`.dockerignore` now excludes `.env`/`.env.*`, `*.patch`, `*.pem`, `*.key`, `secret.key`, `*.sqlite3*`, `*.db` and `logs/`. A developer's local `backend/.env` (real keys) could previously be baked into an image layer by `COPY . .`. The app reads configuration from the container environment, so nothing needed at build/run time was excluded.

### 2.8 Dependency vulnerabilities — **fixed**
- **Python:** `pip-audit -r requirements.txt -r requirements-dev.txt` → **no known vulnerabilities**. All packages are at their current releases.
- **npm:** `npm audit` went from **8 vulnerabilities (1 critical, 4 high, 2 moderate, 1 low)** to **0**. Fixed by upgrading `next` 15.3 → **16.4.0** (critical: unauthenticated RCE in the Image Optimization API with AVIF input, RCE on Windows-hosted servers, SSG/ISR cache poisoning) and `mermaid` 11 → **12.1.0**, then an `overrides` entry pinning transitive `katex` to `^0.19.0` (prototype pollution). Typecheck and production build were re-run green after the upgrade, including the tsconfig changes Next 16 requires.
- **CI** now runs `pip-audit` and `npm audit --audit-level=high` on every push so regressions fail the build instead of silently shipping.

### 2.9 Gemini provider removed — **fixed**
The Gemini option was broken for end users and is no longer viable:

- Google shut down Gemini 2.0 Flash/Flash-Lite on 2026-06-01; since 2026-09-18 the 2.5 models are served **only to projects that already used them** and new projects are pointed at newer models; `gemini-3.7-flash` was deprecated 2026-10-08. The adapter reached Gemini through its OpenAI-compatibility layer, so its live model catalog is largely retired.
- It was removed from the provider registry, the two client adapters, the model-normalization helpers, all user-facing copy and the documentation. **11 providers remain** — Groq, OpenAI, Mistral, DeepSeek, OpenRouter, Together, xAI, Cerebras, SambaNova, NVIDIA NIM, Perplexity — all through their official OpenAI-compatible APIs.
- While removing it, two latent inconsistencies were fixed for *every* provider: verification now actually falls back to another listed text model when the selected one fails (the status message already promised this), and a transient catalog failure no longer disables an already-verified provider.

### 2.10 Configuration documentation — **added**
`backend/.env.example` documents `VEDNIX_API_DOCS` and keeps every secret commented out with generation guidance. No real value is present in any tracked file.

---

## 3. Checks that came back clean

- **Git history (44 commits, full history fetched and scanned):** no `.env` file was ever committed — only `.env.example` templates. Secret-pattern scan of every added line in history found only obvious test fixtures (`gsk_mock_key_for_provider_tests`, `AIzaMockKeyForTests…`, `sk-super-secret-key-1234`, …). No credential, private key or token has ever been committed. Nothing needs rotation or history rewriting.
- **Working tree:** no untracked `.env` files, no credentials on disk.
- **Dependencies:** every declared dependency is imported by application code; no unused packages, and no unused source modules. Nothing needed removing beyond the Gemini adapter.
- **Exposed files:** no static file mounts, no directory listing, no backup/temp artefacts in the image context, `.git` and `docs` excluded from images.

---

## 4. Accepted, documented trade-offs

1. **Rate-limit keys use the connection's peer address.** Behind a reverse proxy every request can share one bucket — this fails *closed* (more limiting, never less). Honouring `X-Forwarded-For` instead would let any client spoof its bucket key and bypass limits, so the peer address is kept deliberately. Redis-backed shared limiting is already supported via `VEDNIX_REDIS_URL` for multi-instance deployments.
2. **Access tokens are verified statelessly, then checked against their session row.** That is one indexed primary-key lookup per authenticated request — negligible for this app, and it is what makes revocation immediate (§2.6).
3. **`script-src 'unsafe-inline'`** in the frontend CSP, for the Next.js inline-bootstrap reason in §2.2.
4. **Login lockout is keyed per IP**, so an attacker who knows a victim's address can make that address fail closed for 5 minutes. The alternative (per-account lockout) turns the same knowledge into an account-denial tool; per-IP was chosen as the lesser evil and the window is short.
5. **`/api/health` is unauthenticated by design** (load-balancer probes). It exposes provider/model readiness and the configured creator identity — no user data, no secrets.

---

## 5. How to re-verify

```bash
# backend: full suite (136 tests) + dependency audit
cd backend && python -m pytest -q
pip-audit -r requirements.txt -r requirements-dev.txt

# frontend: types, build, dependency audit
cd frontend && npm run typecheck && npm run build
npm audit --audit-level=high

# live checks against a running backend
curl -I http://127.0.0.1:8000/api/health          # security headers present
curl -o /dev/null -w '%{http_code}' .../docs      # 404
curl -o /dev/null -w '%{http_code}' .../api/conversations            # 401
curl .../api/conversations -H "Authorization: Bearer $TOKEN"         # 200
curl -X POST .../api/auth/logout -b jar -H "X-CSRF-Token: $CSRF"     # then 401
```

## 6. Deployment checklist

- [ ] Set `VEDNIX_SECRET_KEY` to a long random value (`python -c "import secrets; print(secrets.token_urlsafe(48))"`) so restarts never invalidate sessions or encrypted keys.
- [ ] Set `VEDNIX_CORS_ORIGINS` to the exact deployed origins — never `*`.
- [ ] Leave `VEDNIX_API_DOCS` unset (docs stay off) in production.
- [ ] Optionally set `VEDNIX_AUTH_TOKEN` for an additional bearer-token gate in front of the whole API.
- [ ] Optionally set `VEDNIX_REDIS_URL` to share rate-limit state across instances.
- [ ] Keep provider keys in the Settings UI (encrypted at rest) — never in `NEXT_PUBLIC_*` variables, never committed.
