# Architecture

A bird's-eye view of how a request flows through Heimdall.

```
              ┌─────────────────┐
client ─────► │   FastAPI app   │ ──► RequestId mw ──► RateLimit mw ──► CORS mw
              └─────────────────┘                                          │
                                                                          ▼
                          ┌─────────────────────── auth.get_tenant_ctx ───────────────┐
                          │  Bearer sk_hd_…   → api_keys table → tenant_id           │
                          │  Bearer <Clerk>   → JWKS verify    → user/org → tenant_id│
                          │  (no auth, single-user) → "default" tenant_id            │
                          └───────────────────────────┬──────────────────────────────┘
                                                       │
                                            ┌──────────▼──────────┐
                                            │  BudgetRepo check   │ → 402 if over hard cap
                                            └──────────┬──────────┘
                                                       │
                                            ┌──────────▼──────────┐
                                            │   L1 deterministic   │
                                            │   (sub-ms scanner)   │ → 403 + telemetry write
                                            └──────────┬──────────┘
                                                       │
                                            ┌──────────▼──────────┐
                                            │   policy.apply()     │ → shadow log
                                            └──────────┬──────────┘
                                                       │
                                            ┌──────────▼──────────┐
                                            │   L2 Llama Guard 3   │ → 403 + telemetry write
                                            └──────────┬──────────┘
                                                       │
                                            ┌──────────▼──────────┐
                                            │  select_provider()   │
                                            │  by priority/cost/   │
                                            │  latency             │
                                            └──────────┬──────────┘
                                                       │
                                            ┌──────────▼──────────┐
                                            │ forward_chat_…       │  → upstream
                                            │ (failover on 5xx)    │  (OpenAI/Anthropic/…)
                                            └──────────┬──────────┘
                                                       │
                                            ┌──────────▼──────────┐
                                            │  UsageRecord row     │  cost = price × tokens
                                            │  + budget headers    │
                                            └──────────┬──────────┘
                                                       │
                                                       ▼
                                                  client gets 200
```

## Module map

| Module | Job |
| --- | --- |
| `app/main.py` | App factory, lifespan, middleware wiring |
| `app/config.py` | Pydantic-Settings env config |
| `app/db.py` | Async engine + session factory (SQLite or Postgres) |
| `app/models.py` | All ORM models (8 tables) |
| `app/auth.py` | TenantContext resolution from Clerk JWT or API key |
| `app/policy.py` | Per-tenant rule overrides with 5s in-process cache |
| `app/cost.py` | Pricing table + budget evaluation |
| `app/triage.py` | Claude Haiku alert explanation with rate limit |
| `app/proxy/forwarder.py` | httpx async client + header filtering |
| `app/proxy/router.py` | Provider selection + failover bookkeeping |
| `app/scanners/deterministic.py` | L1 scanner (unicode, jailbreak, secrets/PII) |
| `app/scanners/semantic.py` | L2 scanner (Llama Guard 3 OpenAI-compat call) |
| `app/repositories/` | One repo class per table; every method is `tenant_id`-scoped |
| `app/routes/chat.py` | `/v1/chat/completions` — the hot path |
| `app/routes/alerts.py` | `/api/alerts/*` + SSE stream |
| `app/routes/policies.py` | `/api/policies/*` CRUD |
| `app/routes/sandbox.py` | `/api/sandbox/evaluate` — interactive scanner |
| `app/routes/budget.py` | `/api/billing/*` — summary + budget upsert |
| `app/routes/providers.py` | `/api/providers/*` CRUD |
| `app/routes/auth_keys.py` | `/api/keys/*` — mint + revoke API keys |
| `app/routes/triage.py` | `/api/alerts/{id}/triage` |
| `app/telemetry/bus.py` | In-process AlertBus pub/sub for SSE |
| `app/telemetry/geoip.py` | Optional MaxMind country lookup |
| `app/core/middleware.py` | RequestId + per-IP rate limit |
| `app/core/logging.py` | Text or JSON formatter switch |
| `app/core/exceptions.py` | HeimdallError + handler |

## Database schema

8 tables — see `app/models.py` for the source of truth.

```
tenants ──< api_keys
        ──< budgets (1:1)
        ──< providers (1:N)

alerts (tenant_id, …)        ── triage cache columns inline
alert_feedback (tenant_id)
rule_policies (tenant_id, rule)  uniq (tenant_id, rule)
usage_records (tenant_id, model, cost_usd, …)
```

All tenant-bearing tables have an index on `tenant_id`; high-cardinality
extras (e.g. `(tenant_id, timestamp)` on usage) are added in the initial
migration.

## Multi-tenant isolation model

Heimdall does **not** rely on Postgres row-level security — it works on
SQLite too, where RLS isn't available. Instead, every repository method
takes `tenant_id` as a required keyword argument, and every query starts
with `WHERE tenant_id = :tenant_id`. The discipline is enforced by the
type signatures, not the database.

Things to keep that way if you contribute:

- **Never** expose a raw `AsyncSession` to route code. Always wrap it in
  a repo.
- **Never** introduce a method that fetches by ID without also taking
  `tenant_id`. The unit tests assume cross-tenant reads return nothing.

## Live event bus

The SSE feed at `/api/alerts/stream` is backed by an in-process
`AlertBus` with per-subscriber bounded queues (200 frames max). On
backpressure the oldest event is dropped. This means:

- **Single replica**: works perfectly.
- **Multi-replica behind a load balancer**: each replica's stream is its
  own. To unify the live feed across replicas, swap `AlertBus` for
  Redis Pub/Sub — the `subscribe()` / `publish()` interface stays the
  same.

The SSE handler filters events by `tenant_id` so two users connected to
the same replica never see each other's traffic.

## Where the cost is

| Surface | Cost per request |
| --- | --- |
| L1 scanner | <1 ms CPU, $0 |
| L2 (Llama Guard via Ollama, self-hosted) | ~50 ms GPU, $0 |
| L2 (OpenRouter `llama-guard-3-8b`) | ~200 ms, ~$0.0001 |
| AI triage (Haiku, on-demand) | ~600 ms, ~$0.0003 per alert (cached after first call) |
| Upstream (the request itself) | whatever the upstream charges |

The cost engine records all of the above as `UsageRecord` rows. The
dashboard "Top models" table is the source of truth for billing — not the
upstream provider's invoice.
