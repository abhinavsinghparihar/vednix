# Vercel + Render deployment

This guide uses the production origins reserved for Vednix:

- Frontend: `https://vednix.vercel.app`
- Backend API: `https://vednix.onrender.com`
- Backend WebSocket: `wss://vednix.onrender.com/ws/chat`

## Vercel

Set these frontend build-time environment variables for Production (and Preview only if the preview backend is intentionally configured for that origin):

```text
NEXT_PUBLIC_API_BASE=https://vednix.onrender.com
NEXT_PUBLIC_WS_BASE=wss://vednix.onrender.com/ws/chat
```

The Next.js client reads these at build time. Redeploy after changing them. Never place provider API keys, backend auth secrets, or any other credential in `NEXT_PUBLIC_*`.

## Render backend

Create a Python web service using `backend/` as its root directory.

- Build command: `pip install -r requirements.txt`
- Start command: `python -m uvicorn main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/api/health`

Set an explicit credentialed CORS allowlist. Origins contain scheme and host only—no wildcard and no path:

```text
VEDNIX_CORS_ORIGINS=https://vednix.vercel.app,http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001
```

The application adds those local origins and the production Vercel origin to its validated allowlist. If the frontend domain changes, update the backend configuration and redeploy. WebSocket origins are checked against the same list.

Use persistent storage for the database, upload directory, and server secret. The current backend dependencies include SQLite support by default; a Render-managed PostgreSQL database also requires installing the matching async SQLAlchemy driver before setting `VEDNIX_DATABASE_URL`. The default SQLite database and local upload directory are suitable for development or a persistent disk; ephemeral filesystem deployments can lose local files between restarts. Set `VEDNIX_UPLOAD_DIR` to a persistent mount when uploads must survive restarts.

Optional backend settings include `VEDNIX_REDIS_URL` for shared rate limiting, `VEDNIX_AUTH_TOKEN` for an additional bearer-token gate, SearXNG settings for research, and SMTP settings for email login. "Stay signed in" device sessions use `VEDNIX_SESSION_DAYS` (default `3650`), and the keyless free tier is configured with `VEDNIX_FREE_USE_ENABLED`, `VEDNIX_FREE_USE_BASE_URL`, `VEDNIX_FREE_USE_MODELS`, `VEDNIX_FREE_USE_REQUESTS_PER_HOUR` and the optional `VEDNIX_FREE_USE_API_KEY`; set `VEDNIX_FREE_USE_ENABLED=false` to offer paid providers only. Use Render's secret environment variable facility for credentials. Provider keys are deliberately entered in the authenticated Vednix Settings UI and encrypted by the backend; do not add them to Vercel variables or commit them.

## Verify after deployment

1. Open `https://vednix.onrender.com/api/health` and confirm the service is healthy.
2. In the browser Network panel, confirm API and WebSocket requests target the configured Render origins—not `localhost`.
3. Sign in, add a provider key in **Settings → AI Providers**, and require a successful provider check before enabling it.
4. Refresh **Settings → AI Models** to discover current models and run the task-specific validation.
5. Test a text reply, then image routing only with a validated vision-capable model.

No live provider verification can be claimed until a real user key passes the provider's check.

## Fast entry and sessions that survive closing the browser

`/chat` checks the refresh cookie before loading the workspace, models or
WebSocket. A new visitor is sent to login without onboarding/provider requests.
A returning device restores its in-memory access token from the **httpOnly**
refresh cookie; credentials are not put in localStorage. A temporary network
failure leaves entry pending and retries, rather than signing the device out.
The cinematic boot overlay only plays on the landing page, not login/workspace.

For production persistence, use **one** of these setups:

- **SQLite + persistent disk:** mount a durable disk (for example `/var/data`),
  set `VEDNIX_DATA_DIR=/var/data`, and leave the default database URL so the
  settings resolver places SQLite inside that directory. Keep uploads and
  `secret.key` on that disk too. Do not share SQLite across multiple replicas.
- **Managed PostgreSQL:** install `asyncpg` alongside `requirements.txt` and set
  `VEDNIX_DATABASE_URL` to the database connection URL in the hosting dashboard
  (not in source control). Set a strong, stable `VEDNIX_SECRET_KEY` on every
  replica. Upload files still need their own persistent storage.

No additional database is needed for local use: SQLite is already configured.
However, cookies alone cannot restore a session whose server-side database was
lost on an ephemeral filesystem. A fixed secret alone cannot recover lost rows.
Keep the same signing/encryption secret across deployments; changing it also
invalidates access tokens and prevents decrypting existing provider keys.

Keep browser HTTP requests same-origin through the Next.js `/api` proxy
(`NEXT_PUBLIC_DIRECT_API` unset/false). Third-party cookie blocking in direct
cross-site mode can prevent session restoration. Do not clear site cookies on
exit; private browsing only remembers a session while its private window lives.

A sleeping/cold backend can still delay the first session check. If that remains
slow after these changes, use an always-on backend rather than adding artificial
frontend delays or periodic keep-alive traffic.

After deploying both frontend and backend, sign in with **Stay signed in on
this device** checked, close and reopen the browser, and test again after a
backend restart. Explicit logout and revoked sessions must still require login.

## Private administrator provisioning

Public signup **always** creates a `member`, including the very first account.
Existing owners remain owners; this update does not sign them out or change
their identity. No public screen contains an admin username, default password,
or an admin-account shortcut. Admin routes check the stored role on every
request, and API responses are marked `Cache-Control: no-store`.

To assign the intended administrator on a new database, first register that
person's own account, then run this **only in the backend server's trusted shell**:

```sh
cd backend
python scripts/grant_admin.py <your-username>
```

The command revokes that account's pre-promotion sessions, requiring a fresh
sign-in once. Running it for an existing owner leaves sessions untouched. There
is intentionally no browser/API endpoint for granting admin. Do not use a
shared admin login on other people's browsers. A normal signup, forged `role`
field, or copied admin URL cannot grant admin access.
