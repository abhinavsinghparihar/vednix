# SaaS upgrade audit and release blockers

This repository is still a **single-workspace application**, not an isolated
multi-tenant SaaS. Do not deploy it to unrelated users or treat this change as
a complete SaaS/security upgrade. This document records the actual state, not
claims of production readiness.

## Findings

* `Conversation`, `Message`, `UploadedFile`, `MemoryItem`, knowledge documents,
  and `ProviderKey` have no owner column. Their services query global tables.
  Any signed-in account can access shared data and change shared provider
  configuration. The first-account lock does not isolate accounts. Guest mode
  likewise has no per-guest identity or safe migration, and the current route
  guard sends unauthenticated visitors to login.
* `create_all` is not a versioned migration system. No safe backfill can assign
  existing shared data to an individual user without an operator decision.
  Durable per-user attachment storage, retention, deletion and ownership checks
  must be built alongside transactional, reviewed schema migrations.
* Google OAuth endpoints are not implemented. An open path in middleware is not
  an implementation. No Google credentials or production access were supplied.
* The existing image pipeline normalizes actual images and sends data URLs to
  models after capability checks; live support depends on provider availability
  and credentials. Explicitly selected providers do not automatically fail over.
  No real provider was contacted during this change. Text PDF extraction exists,
  but scanned PDFs have no OCR. Attachments are stored on local disk, which is
  lost on ephemeral deployments, and preview restoration is not implemented.
* The frontend uses a same-origin HTTP rewrite to avoid third-party cookie
  blocking. Direct cross-site cookie mode can still fail. The old ten-year
  default was excessive; the new default is 30 days sliding inactivity.
  Deployments explicitly setting `VEDNIX_SESSION_DAYS=3650` must update that
  variable. Concurrent refresh now uses a database compare-and-swap; clients
  with Web Locks serialize across tabs, but browsers without Web Locks can still
  race, and a lost response after a successful rotation can require login.
* The old backend logged the complete database URL, possibly including a
  password, at startup. It now logs only the database type. PostgreSQL previously
  attempted SQLite FTS SQL in its schema transaction; that can abort PostgreSQL
  initialization. The async driver is now included, but a real PostgreSQL
  server and existing production schema were not available to validate here.
* Machine secrets can be automatically stored alongside encrypted provider
  keys in the database. Set a stable, strong `VEDNIX_SECRET_KEY` **outside** the
  database before initially provisioning production keys; existing installations
  need a carefully planned key re-encryption procedure before changing it.
  Never print the database URL or secret in logs or commit them to Git.

## Minimum work before public release

Design account/guest ownership for every resource (including memory, knowledge,
settings, keys, WebSocket operations and uploads), migrate and backfill without
claiming shared legacy records for the wrong user, and test IDOR boundaries.
Implement server-side OAuth/OIDC with state, PKCE, token verification and safe
verified-email account linking. Add durable private object storage, scoped
attachment access and deletion. Implement bounded OCR or verified native PDF
support, model-specific multimodal routing, and test real providers. Add a
versioned PostgreSQL migration process and exercise it on a production copy.
Perform live browser, mobile, failover, security and deployment tests.

No paid service has been enabled by these changes. Free endpoints, database
hosting and infrastructure have changing quotas/terms and cannot guarantee
unlimited availability or zero cost. Confirm current hosting/provider terms
and set spending controls before deploying; do not add paid credentials unless
explicitly authorized.

## Rollout order for the partial fixes

Deploy the backend before the frontend. The backend accepts the new WebSocket
subprotocol and the legacy URL token for older clients; the updated frontend
requires the updated backend. Confirm your reverse proxy forwards the
`Sec-WebSocket-Protocol` header. Treat this header as sensitive and do not log
it. Existing deployments explicitly configured for ten years remain at that
setting until their environment variable is changed.
