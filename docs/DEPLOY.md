# Deploying Heimdall

This walks through the production setup we recommend: **dashboard on Vercel,
backend on Fly.io, Postgres on Neon, auth via Clerk.** Everything else (single
VPS, your own K8s, etc.) is supported too — the artifacts are the same.

If you just want to play with Heimdall locally, skip to [Self-host (single
machine)](#self-host-single-machine).

---

## Production (multi-tenant SaaS)

### 1. Create the cloud accounts (15 min, one-time)

| Service | What you get | Free tier? |
| --- | --- | --- |
| [Vercel](https://vercel.com) | Dashboard hosting + preview URLs | Hobby tier free |
| [Fly.io](https://fly.io) | FastAPI runtime + persistent volume | $5 trial credit |
| [Neon](https://neon.tech) | Serverless Postgres | 0.5 GB free |
| [Clerk](https://clerk.com) | Auth (sign-in, sign-up, orgs) | 10k MAU free |
| [Anthropic](https://console.anthropic.com) | AI triage (Claude Haiku) | $5 free credit |
| [Sentry](https://sentry.io) (optional) | Errors + tracing | 5k events/mo free |

### 2. Set up Neon Postgres (3 min)

1. Create a project named `heimdall`.
2. Copy the **pooled** connection string (the one that says "pooler" or
   ends in `-pooler.neon.tech`).
3. Replace the scheme prefix: `postgresql://` → `postgresql+asyncpg://`.

You'll set this as `DATABASE_URL` later.

### 3. Set up Clerk (5 min)

1. Create an application. Pick **Next.js** as the framework.
2. From **API Keys** copy:
   - `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` (`pk_test_…` for dev, `pk_live_…` for prod)
   - `CLERK_SECRET_KEY` (`sk_test_…` or `sk_live_…`)
3. From **JWT Templates → Default**, copy the **JWKS URL** and **Issuer**.
   These go on the backend (`CLERK_JWKS_URL`, `CLERK_ISSUER`).
4. In **Paths**, set sign-in/sign-up to `/sign-in` and `/sign-up`.

### 4. Deploy the backend to Fly.io (5 min)

```bash
# install flyctl if you haven't: https://fly.io/docs/flyctl/install/
fly auth login
fly apps create heimdall-api          # (or pick your own name + edit fly.toml)
fly volumes create heimdall_data --size 1 --region ord

fly secrets set \
  DATABASE_URL="postgresql+asyncpg://USER:PASS@HOST/heimdall" \
  CLERK_JWKS_URL="https://YOUR-APP.clerk.accounts.dev/.well-known/jwks.json" \
  CLERK_ISSUER="https://YOUR-APP.clerk.accounts.dev" \
  ANTHROPIC_API_KEY="sk-ant-..." \
  ADMIN_API_TOKEN="$(openssl rand -hex 32)" \
  CORS_ORIGINS="https://heimdall-dashboard.vercel.app,https://your-domain.com" \
  MULTI_TENANT_MODE="true" \
  SENTRY_DSN=""  # optional

fly deploy
```

Verify: `curl https://heimdall-api.fly.dev/health` → `{"status":"ok"...}`.

### 5. Deploy the dashboard to Vercel (3 min)

```bash
# install vercel CLI: npm i -g vercel
cd dashboard
vercel link    # follow the prompts; creates .vercel/project.json
```

Then add env vars in the Vercel dashboard (or via `vercel env add`):

| Variable | Value | Env |
| --- | --- | --- |
| `HEIMDALL_API_URL` | `https://heimdall-api.fly.dev` | Production, Preview, Development |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | `pk_live_…` | Production |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | `pk_test_…` | Preview, Development |
| `CLERK_SECRET_KEY` | `sk_live_…` / `sk_test_…` | match above |

Then:

```bash
vercel --prod
```

### 6. Wire CI/CD (5 min)

Set these GitHub repo secrets (Settings → Secrets and variables → Actions):

- `FLY_API_TOKEN` — `fly tokens create deploy`
- `VERCEL_TOKEN` — Vercel → Account Settings → Tokens
- `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID` — visible in `dashboard/.vercel/project.json` after `vercel link`

Now every push to `main` redeploys both, and PRs get a Vercel preview URL.

### 7. Make your first request

In the dashboard → **Keys** → **Create key** ("laptop"). Copy the
`sk_hd_…` string. Then:

```python
from openai import OpenAI
client = OpenAI(
    base_url="https://heimdall-api.fly.dev/v1",
    api_key="sk_hd_…",        # ← your Heimdall key, NOT your OpenAI key
)
client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}])
```

The provider config in the dashboard's **Providers** tab decides which
upstream key (OPENAI_API_KEY env var on Fly, set via `fly secrets set`) gets
used for the actual upstream call.

---

## Self-host (single machine)

For everyday users who just want a personal LLM bodyguard:

```bash
git clone https://github.com/your-org/heimdall && cd heimdall
cp .env.example .env       # edit UPSTREAM_API_KEY at minimum
docker compose up --build
```

That brings up Heimdall (port 8000), the dashboard (port 3000), and
Ollama with Llama Guard 3. Open <http://localhost:3000>.

In self-host mode every request is attributed to the `default` tenant, no
auth required.

---

## Updating

```bash
fly deploy            # backend
vercel --prod         # dashboard
```

Migrations run automatically on backend startup
(`alembic upgrade head` in the Dockerfile CMD).

---

## Operational tips

- **Backups**: Neon does point-in-time recovery on the free tier. For the
  Fly SQLite fallback volume, run `fly ssh sftp shell` to pull files.
- **Logs**: `fly logs -a heimdall-api` — JSON, ingestible by Logtail / Axiom.
- **Scaling**: `fly scale count 3 --region ord,sjc,fra`. The in-process
  `AlertBus` is per-replica; to share live SSE across replicas, replace
  `app/telemetry/bus.py` with a Redis Pub/Sub shim.
- **Rotating Clerk keys**: bounce the backend after `fly secrets set`. The
  JWKS client caches for 1 hour, so old tokens may still validate during
  the rotation window — that's expected.
