# Security

## Threat model

Heimdall sits in the path of LLM traffic. Its threat model:

| Threat | Mitigation |
| --- | --- |
| **Prompt injection** via attacker-controlled user input | L1 jailbreak patterns + L2 Llama Guard semantic classifier |
| **Unicode smuggling** (Trojan-Source, ASCII-tags) | L1 strips invisible chars before downstream sees them |
| **Secret/PII exfiltration** into the LLM | L1 regex for 9 common token classes + Luhn-valid credit cards |
| **Cross-tenant data leak** | Every query filters by `tenant_id`; SSE filtered server-side |
| **API key theft** | Plaintext shown once on creation; only SHA-256 hash stored; revocation is immediate |
| **Runaway cost** | Per-tenant monthly hard cap (402 response) + soft warning headers |
| **Replay of an old Clerk token** | JWKS-verified; `exp` claim required; clock skew not allowed |
| **Anonymous traffic in production** | `MULTI_TENANT_MODE=true` rejects requests without a JWT or API key |

## Reporting a vulnerability

Email `security@your-org.example` (replace with your real address; or open
a private GitHub Security Advisory). Please include:

1. A description of the issue, ideally with a reproducer.
2. Versions affected (release tag or commit SHA).
3. The impact you've assessed.

We'll acknowledge within 3 business days and aim to release a patch within
14 days for high/critical findings.

## What we promise

- We will not pursue legal action against good-faith security research that
  respects the privacy of others and gives us reasonable time to respond.
- Heimdall is open source under Apache 2.0 — there is no warranty, but
  there is also no fixed disclosure window if you choose to publish
  independently. Our preference is coordinated disclosure.

## Operational hardening checklist (production)

- [ ] `MULTI_TENANT_MODE=true`
- [ ] `ADMIN_API_TOKEN` set to a long random string (`openssl rand -hex 32`)
- [ ] `CLERK_JWKS_URL` and `CLERK_ISSUER` point at your production Clerk app
- [ ] `CORS_ORIGINS` does NOT include `*`; lists only your dashboard origins
- [ ] `RATE_LIMIT_PER_MINUTE` set to a sane per-IP value for your traffic
- [ ] `SENTRY_DSN` configured, `SENTRY_ENVIRONMENT=production`
- [ ] `DATABASE_URL` uses TLS (Neon `?sslmode=require` is the default)
- [ ] Fly secrets store the upstream API keys; nothing sensitive in `fly.toml`
- [ ] HTTPS-only at the edge (Fly + Vercel both default to this)
- [ ] Backups: Neon PITR enabled (default on free tier); SQLite fallback volume snapshotted weekly if you use it
