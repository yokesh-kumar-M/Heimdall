# Changelog

All notable changes to Heimdall, newest first.

## [0.2.0] — 2026-05-24

The "useful to everyday users" release. Heimdall went from a single-user
operations console to a multi-tenant SaaS-ready security gateway with
budget controls, multi-provider routing, AI triage, and a browser extension.

### Added

- **Multi-tenancy** — every row scoped by `tenant_id`. Clerk JWT or
  `sk_hd_…` API key resolves to the current tenant on each request.
  Single-user mode (`MULTI_TENANT_MODE=false`) still works with a built-in
  `default` tenant.
- **Postgres support** — SQLAlchemy 2.0 + Alembic. `DATABASE_URL` selects
  the dialect. SQLite remains the dev default.
- **Cost & budget engine** (`app/cost.py`) — per-model pricing table,
  per-request cost calculation, monthly budget with soft/hard thresholds.
  402 response when the hard cap is reached.
- **Multi-provider routing** (`app/proxy/router.py`) — per-tenant
  `providers` table; strategies `primary_failover`, `cheapest`, `fastest`;
  auto-failover on 5xx/timeout with health bookkeeping.
- **AI-powered triage** (`app/triage.py`) — `/api/alerts/{id}/triage` calls
  Claude Haiku 4.5 to explain the block in plain English, assign a severity,
  and emit a `cluster_signature` for grouping similar incidents.
  Heuristic fallback when no `ANTHROPIC_API_KEY` is set.
- **Heimdall API keys** — `sk_hd_…`, hashed with SHA-256, plaintext shown
  once on creation, immediate revocation.
- **Browser extension** (`extension/`) — Manifest V3 Sentinel that runs
  the L1 scanner locally on chat.openai.com, claude.ai, gemini.google.com,
  copilot.microsoft.com, perplexity.ai. Warns before paste, blocks
  high-severity sends until confirmed.
- **Dashboard**:
  - Marketing landing page at `/`.
  - Sign-in / sign-up pages with Clerk.
  - Billing tab with spend chart, top models, budget form.
  - Providers tab with quick-add presets.
  - Keys tab with create / revoke.
  - User menu in header.
  - Mobile-friendly horizontal nav with overflow scroll.
- **Production hardening**:
  - JSON structured logging (`LOG_FORMAT=json`).
  - Request-ID middleware (echoed back as `X-Request-ID`).
  - Per-IP fixed-window rate limit on `/v1/*`.
  - CORS with explicit origins list.
  - Sentry init when `SENTRY_DSN` set.
  - Multi-stage Dockerfile (builder + runtime), non-root user, tini PID 1.
- **CI/CD**:
  - `.github/workflows/backend.yml` — ruff + pytest + Docker build + Fly deploy on main.
  - `.github/workflows/dashboard.yml` — lint + typecheck + Next build + Vercel deploy; preview URLs on PRs.
  - `.github/workflows/extension.yml` — manifest validation + zip artifact upload.
- **Deploy artifacts**:
  - `fly.toml` for the backend (region, volume, healthcheck).
  - `dashboard/vercel.json` with security headers.
  - `docs/DEPLOY.md` — step-by-step production setup.
- **Docs**: ARCHITECTURE.md, SECURITY.md, CONTRIBUTING.md, this CHANGELOG.

### Changed

- `app/policy.py` is now stateless per-tenant with a 5-second in-process
  cache (was a single in-memory store).
- `app/telemetry/store.py` is gone — its functionality moved to
  `app/repositories/telemetry.py` (SQLAlchemy-backed, tenant-scoped).
- `app/proxy/forwarder.py` takes a `ResolvedProvider` (from the routing
  layer) instead of reading `settings.upstream_base_url` directly.
- Dashboard auth: all `/api/*` proxy routes now forward the Clerk session
  JWT (or static `HEIMDALL_API_TOKEN` in self-host mode).
- `Dockerfile` is multi-stage; the runtime image has no compiler and runs
  as an unprivileged user. Starts `alembic upgrade head` before `uvicorn`.

### Removed

- The legacy hand-rolled SQLite schema in `app/telemetry/store.py`.
  `TELEMETRY_DB_PATH` still works as a back-compat alias for `DATABASE_URL`.
- The single-upstream `forward_chat_completion(settings=…)` signature.

### Migration from 0.1.x

If you're upgrading an existing 0.1.x SQLite database:

```bash
# Back up first
cp telemetry/heimdall.sqlite3 telemetry/heimdall.sqlite3.bak

# Apply 0.2 schema (drops old tables and rebuilds — 0.1 was unreleased)
alembic upgrade head
```

Your telemetry history won't migrate automatically — 0.1 was pre-release.
If you need to keep the old data, export the `alerts` table to CSV first.

## [0.1.0] — pre-release

Initial release. Single-tenant, SQLite-backed, layered L1/L2 scanners,
OWASP LLM Top 10 mapping, dashboard with overview/alerts/OWASP/policies/
sandbox tabs.
