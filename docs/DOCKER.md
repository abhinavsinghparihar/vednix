# Docker

The Compose stack runs the Vednix backend and frontend. Gemini/Groq API keys are entered through the application and stored encrypted by the backend; they are not passed to the frontend container.

```bash
# Local workspace
 docker compose up --build
```

Open `http://localhost:3000`. Compose sets the browser-facing frontend base URLs to the backend on `http://localhost:8000` and `ws://localhost:8000/ws/chat`.

Optional profiles:

```bash
# Add SearXNG for the Studio's web-research feature
 docker compose --profile research up --build

# Add optional PostgreSQL and Redis services
 docker compose --profile scale up --build
```

The backend container persists its data in the `vednix-data` volume. If using a non-SQLite database, configure a SQLAlchemy async URL and ensure the corresponding database driver is installed. For non-local frontends, configure `VEDNIX_CORS_ORIGINS` with exact origins; wildcard CORS is rejected. See [deployment notes](DEPLOY_FREE.md) for Vercel/Render configuration.
