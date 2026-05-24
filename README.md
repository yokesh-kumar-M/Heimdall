# Heimdall

A security reverse proxy for OpenAI-compatible LLM APIs. Heimdall sits between
your application and the upstream provider, runs every prompt through a
layered defense, and writes a full audit trail to SQLite.

```
client ──► Heimdall ──► OpenAI / Anthropic / OpenRouter / your own vLLM
              │
              ├── L1: deterministic scanners (Unicode, jailbreak, secrets, PII)
              ├── L2: Llama Guard 3 semantic classifier
              ├── Policy Manager (rule overrides + auto-suppress)
              ├── Telemetry → SQLite
              └── Live SSE feed for the dashboard
```

Blocked requests never reach upstream. Everything that *does* get forwarded is
NFKC-normalized and stripped of invisible / steganographic Unicode first, so
the model never sees Trojan-Source-style payloads.

## Repo layout

| Path | What it is |
| --- | --- |
| `app/` | FastAPI backend — proxy, scanners, telemetry, policy manager |
| `dashboard/` | Next.js 16 operations console (alerts, OWASP, sandbox, policies) |
| `tests/` | pytest suite + JSON fixtures for manual `curl` testing |
| `telemetry/` | Default location for the audit SQLite DB |

## Layered defense

### L1 — Deterministic (`app/scanners/deterministic.py`)

Sub-millisecond scanner that fires on:

* **Invisible Unicode** — zero-width chars, bidi overrides, Tag-block
  smuggling. Stripped before downstream processing.
* **Jailbreak triggers** — DAN, "ignore previous instructions", developer-mode
  toggles, role-reveal probes. Curated from public corpora.
* **Secrets & PII** — AWS / GitHub / OpenAI / Anthropic / Google / Slack
  tokens, private-key blocks, US SSN, Luhn-valid credit cards.

### L2 — Semantic (`app/scanners/semantic.py`)

OpenAI-compatible call to Meta's **Llama Guard 3**. Works with:

* **Ollama** — `OLLAMA_HOST=http://localhost:11434` + `ollama pull llama-guard3`
* **OpenRouter** — `meta-llama/llama-guard-3-8b`
* **Self-hosted vLLM / TGI** — point `SEMANTIC_BASE_URL` at it

L2 codes (S1–S14) are mapped to the OWASP LLM Top 10 (2025) categories so the
dashboard's compliance view stays meaningful.

### Policy Manager (`app/policy.py`)

* Per-rule override (enable / disable, override note).
* Feedback-driven auto-suppress: N false-positive reports → rule muted, with
  a note stamped on the policy row for audit.
* Shadowed violations are still telemetered (with `shadowed_by_policy=True`)
  so the forensic trail is never lost — only the gate decision changes.

REST API:

```
GET    /api/policies            list all + observed rules
GET    /api/policies/{rule}     fetch one
PUT    /api/policies/{rule}     upsert (enabled / threshold / note)
DELETE /api/policies/{rule}     revert to default
```

## OWASP LLM Top 10 mapping

| Category | Triggered by |
| --- | --- |
| LLM01 Prompt Injection | jailbreak phrases, invisible-Unicode smuggling, L2 codes S1–S4, S9–S12 |
| LLM02 Sensitive Info Disclosure | secret/PII regex, credit cards, L2 S7 (Privacy), S8 (IP) |
| LLM06 Excessive Agency | L2 S14 (Code Interpreter Abuse) |
| LLM09 Misinformation | L2 S5 (Defamation), S6 (Specialized Advice), S13 (Elections) |

## Quickstart

```bash
# 1. Backend
python -m venv .venv
.venv\Scripts\Activate.ps1      # Windows; use `source .venv/bin/activate` on *nix
pip install -r requirements.txt
copy .env.example .env          # then edit values
uvicorn app.main:app --reload   # http://127.0.0.1:8000

# 2. (Optional) Llama Guard 3 via Ollama
ollama pull llama-guard3
# leave SEMANTIC_BASE_URL=http://localhost:11434/v1 in .env

# 3. Dashboard
cd dashboard
npm install
npm run dev                     # http://localhost:3000
```

Then point any OpenAI-SDK-compatible client at Heimdall:

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

# Same payloads but through the sandbox (no telemetry written):
curl -X POST http://127.0.0.1:8000/api/sandbox/evaluate \
  -H "Content-Type: application/json" \
  --data @tests/fixtures/sandbox-jailbreak.json
```

The dashboard's **Sandbox** tab does the same evaluation interactively, with
per-phase timings and inline match highlighting.

## Environment

See [`.env.example`](.env.example) for the full list. Highlights:

| Variable | Default | Notes |
| --- | --- | --- |
| `UPSTREAM_BASE_URL` | `https://api.openai.com/v1` | Any OpenAI-compatible base URL |
| `UPSTREAM_API_KEY` | _(empty)_ | Used only if the client request has no Authorization header |
| `SEMANTIC_ENABLED` | `true` | Set `false` to skip the L2 call entirely |
| `SEMANTIC_BASE_URL` | `http://localhost:11434/v1` | Ollama default |
| `SEMANTIC_FAIL_CLOSED` | `false` | When `true`, an unreachable L2 blocks the request instead of letting it through |
| `TELEMETRY_DB_PATH` | `telemetry/heimdall.sqlite3` | The same DB also stores `rule_policies` |
| `POLICY_DEFAULT_FP_THRESHOLD` | `5` | False-positive reports needed before auto-suppress |
| `GEOIP_DB_PATH` | _(unset)_ | Optional MaxMind GeoLite2-Country `.mmdb` for country lookup |
| `HEIMDALL_API_URL` (dashboard) | `http://127.0.0.1:8000` | Where the dashboard finds the backend |
| `HEIMDALL_API_TOKEN` (dashboard) | _(empty)_ | Forwarded as `Authorization: Bearer …` if set |

## Tests

```bash
pytest -q
```

Covers scanners, telemetry store, policy manager, alerts route, and the
sandbox endpoint. Network-free — no real LLM calls.

## Docker

```bash
docker compose up --build
```

This brings up the backend, the dashboard, and an Ollama container with
Llama Guard 3 pre-pulled. The compose file lives at the repo root; tweak the
`OLLAMA_MODEL` env var if you want a smaller variant.

## License

Internal / unreleased — see project owner.
