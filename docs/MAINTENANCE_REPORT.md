# Maintenance notes

This file records current maintenance guidance for the Vednix provider migration and workspace.

## Provider boundary

Gemini and Groq are supported through provider adapters and a server-side router. Official APIs supply model candidates. Task capabilities are confirmed by real, operation-specific requests before a model can be selected. API keys remain encrypted on the backend, and error/status payloads never include saved secrets.

## Operational checks

```bash
# backend (from backend/)
pytest -q

# frontend (from frontend/)
npm run typecheck
npm run build
```

Mock transport tests are deterministic provider-boundary tests; they do not prove a live key or upstream service is available. A real provider verification needs a valid key and successful external call.

## Deployment reminders

- Vercel frontend variables: `NEXT_PUBLIC_API_BASE=https://vednix.onrender.com` and `NEXT_PUBLIC_WS_BASE=wss://vednix.onrender.com/ws/chat`.
- Render CORS must allow `https://vednix.vercel.app` and explicit development origins; do not configure wildcard origins.
- Use Render secret variables for backend secrets, persistent storage for database/uploads, and the Settings UI for Gemini/Groq keys.
- Keep provider keys out of frontend bundles, logs, URLs, and repository files.

See [deployment](DEPLOY_FREE.md), [architecture](ARCHITECTURE.md), and [API](API.md) for details.
