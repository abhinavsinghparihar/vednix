# Running Vednix AI with Docker

```bash
# minimal stack: backend + frontend (Ollama runs on the host as usual — see below)
docker compose up --build

# + internet search (SearXNG on :8080, backend auto-targets http://searxng:8080)
docker compose --profile research up --build

# + Postgres & Redis services (swap URLs via env to actually use them)
VEDNIX_DATABASE_URL=postgresql+asyncpg://vednix:vednix@postgres:5432/vednix \
VEDNIX_REDIS_URL=redis://redis:6379/0 \
docker compose --profile scale up --build
```

## Why Ollama is not a compose service

The official `ollama/ollama` image needs per-machine GPU flags (`--gpus all`,
`/dev/kfd` …). Keeping it outside means the default compose file works
everywhere: run `ollama serve` on the host, the backend reaches it via
`host.docker.internal:11434` (compose sets `extra_hosts: host-gateway`).
Linux users who prefer the container can add it themselves with their GPU flags.

## What gets persisted

| Volume        | Contents                                   |
|---------------|--------------------------------------------|
| `vednix-data` | SQLite DB (or uploads) under `/app/data`   |
| `pg-data`     | Postgres data dir (scale profile)          |
| `searxng-config` | SearXNG settings (research profile)     |

## Environment switches (compose substitutes into the backend)

- `VEDNIX_LLM_PROVIDER=openrouter` + `VEDNIX_OPENROUTER_API_KEY` → cloud provider
- `VEDNIX_AUTH_TOKEN=<secret>` → bearer-gates every `/api/*` and `/ws/chat`
  (frontend: append `?token=<secret>` on the WS URL / send the header for REST)
- `VEDNIX_SEARXNG_URL` — with the research profile this just works; without it
  point at any reachable instance (default `http://localhost:8080`)

The frontend image bakes `NEXT_PUBLIC_API_BASE=http://localhost:8000` (browser →
host port mapping) — correct for the standard local compose layout.
