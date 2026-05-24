# Heimdall

> A security gateway for every LLM call you make.

[![CI](https://img.shields.io/badge/CI-passing-success)]()
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)]()
[![OWASP LLM Top 10](https://img.shields.io/badge/OWASP%20LLM-Top%2010%20(2025)-orange)]()

Heimdall sits between your app and OpenAI / Anthropic / your own vLLM. Every
prompt runs through layered security scanners, every cost is tracked, every
block is explained in plain English. Drop it in front of any
OpenAI-compatible API — change one line of code, get six layers of common sense.

```
client ──► Heimdall ──► OpenAI / Anthropic / OpenRouter / vLLM
              │
              ├── L1 deterministic   sub-ms · jailbreaks · invisible Unicode · 9 secret/PII classes
              ├── L2 semantic        Llama Guard 3 · OWASP LLM Top 10 mapping
              ├── Policy Manager     per-tenant rule overrides + auto-suppress
              ├── Cost engine        per-model pricing · monthly budget caps
              ├── Multi-provider     priority/cost/latency routing + auto-failover
              ├── AI triage          Claude Haiku explains every block
              └── Telemetry          Postgres or SQLite · live SSE feed
```

## Why everyday users care

You don't have to be on an enterprise security team to want this:

- **You leak less.** Sentinel browser extension warns you before you paste
  an API key, a credit card, or "ignore previous instructions" into
  ChatGPT.
- **You spend less.** Per-model pricing means you see "Today: $2.41 — on track for $73 this month" instead of a billing surprise.
- **You fail less.** If OpenAI 5xxs, Heimdall transparently falls over to
  OpenRouter, Groq, or whichever provider you've configured next.
- **You learn more.** Every blocked request comes with a plain-English
  explanation from Claude Haiku — what tried to happen, why it matters, what to do.

## What's in the box

| Surface | What it is |
| --- | --- |
| `app/` | FastAPI backend — proxy, scanners, telemetry, policy, cost, providers, triage |
| `dashboard/` | Next.js 16 console — overview, alerts, OWASP, sandbox, billing, providers, keys |
| `extension/` | Manifest V3 browser extension — local scanner on chat sites |
| `alembic/` | DB migrations (SQLite + Postgres) |
| `tests/` | pytest suite (57 tests, network-free) |
| `docs/` | DEPLOY.md, ARCHITECTURE.md, SECURITY.md, CONTRIBUTING.md, CHANGELOG.md |

## Two ways to run it

### A. Cloud (multi-user SaaS)

```bash
git clone https://github.com/your-org/heimdall && cd heimdall
# follow docs/DEPLOY.md — Vercel + Fly.io + Neon Postgres + Clerk auth
```

Every user signs in with their Clerk account, gets `sk_hd_…` API keys, sees
only their own alerts and costs. Multi-tenant from the ground up.

### B. Self-host (single user, single machine)

```bash
git clone https://github.com/your-org/heimdall && cd heimdall
cp .env.example .env       # at minimum, set UPSTREAM_API_KEY=<your OpenAI key>
docker compose up --build
```

Open <http://localhost:3000>. No auth, no signup, single "default" tenant.
Perfect for personal use.

### C. Just the backend, no Docker

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1                # Windows; source .venv/bin/activate on *nix
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head                      # creates the SQLite schema
uvicorn app.main:app --reload             # http://127.0.0.1:8000

cd dashboard
cp .env.local.example .env.local
npm install
npm run dev                               # http://localhost:3000
```

Then point any OpenAI SDK at Heimdall:

```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8000/v1", api_key="sk-anything")
client.chat.completions.create(model="gpt-4o-mini", messages=[...])
```

## Trying it without a real LLM

Heimdall blocks **before** the proxy step, so you can exercise the security
layers with no upstream key:

```bash
# Jailbreak — blocked by L1
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  --data @tests/fixtures/jailbreak.json

# Invisible-Unicode smuggle + AWS key — blocked by L1
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  --data @tests/fixtures/smuggle.json
```

Or use the dashboard's **Sandbox** tab for interactive evaluation with
inline highlighting and per-phase timings.

## The OWASP LLM Top 10 mapping

| Category | Triggered by |
| --- | --- |
| LLM01 Prompt Injection | jailbreak phrases · invisible-Unicode smuggling · L2 codes S1–S4, S9–S12 |
| LLM02 Sensitive Info Disclosure | secret/PII regexes · credit cards · L2 S7 (Privacy), S8 (IP) |
| LLM06 Excessive Agency | L2 S14 (Code Interpreter Abuse) |
| LLM09 Misinformation | L2 S5 (Defamation), S6 (Specialized Advice), S13 (Elections) |
| LLM10 Unbounded Consumption | Cost engine + monthly budget caps |

## What's new in v0.2

- **Multi-tenancy**: every row tenant-scoped; Clerk JWT or `sk_hd_…` key resolves to the current tenant.
- **Postgres**: SQLAlchemy 2.0 + Alembic. SQLite still works for dev.
- **Cost engine**: pricing table, per-request cost, monthly budget with hard/soft caps.
- **Multi-provider router**: OpenAI / Anthropic / OpenRouter / Groq / custom, with priority/cost/latency strategies and failover.
- **AI triage**: Claude Haiku explains every alert, suggests next steps, clusters similar incidents.
- **Browser extension**: Sentinel — local L1 scanner on ChatGPT/Claude/Gemini/Copilot/Perplexity.
- **Dashboard**: marketing landing, sign-in/up, billing + providers + keys pages, mobile nav.
- **CI/CD**: GitHub Actions for backend (pytest → Fly), dashboard (typecheck → Vercel), extension (zip artifact).
- **Production hardening**: structured JSON logs, request IDs, per-IP rate limit, CORS, Sentry, alembic-on-start.

See [`docs/CHANGELOG.md`](docs/CHANGELOG.md) for the full list.

## Documentation

- [`docs/DEPLOY.md`](docs/DEPLOY.md) — production deploy (Vercel + Fly + Neon + Clerk)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how the pieces fit together
- [`docs/SECURITY.md`](docs/SECURITY.md) — threat model, reporting policy
- [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) — dev workflow, code style
- [`docs/CHANGELOG.md`](docs/CHANGELOG.md) — what's changed between releases

## Tests

```bash
pytest -q          # 57 tests, network-free
```

Covers scanners, repositories, policy manager, alerts/sandbox/policies/chat
routes, and the new cost / triage / multi-provider paths.

## License

Apache 2.0.
