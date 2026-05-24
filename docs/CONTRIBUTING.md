# Contributing to Heimdall

Thanks for considering it.

## Dev setup

```bash
git clone https://github.com/your-org/heimdall && cd heimdall
python -m venv .venv && source .venv/bin/activate   # or `.\.venv\Scripts\Activate.ps1`
pip install -r requirements.txt
pytest -q                                            # 57 tests should pass

cd dashboard
npm install
npm run typecheck
npm run lint
```

## Code style

- **Python**: ruff for lint, mypy for types. Run `ruff check app tests` before pushing.
- **TypeScript**: ESLint + tsc. `npm run lint && npm run typecheck`.
- **Commits**: imperative present tense. "Add provider failover" not "added".
- **Comments**: explain *why*, not *what*. Code should make the "what" obvious.

## Adding a feature

1. Open an issue first if it's non-trivial — saves you a wasted day if the
   maintainers want a different shape.
2. Branch from `main`, name it `feat/your-thing` or `fix/your-bug`.
3. **Write the test first** when fixing a bug. The PR should include a
   failing-without-your-fix test.
4. For schema changes: `alembic revision -m "your change" --autogenerate`,
   then **read the generated migration** — autogenerate is helpful but
   never perfect.

## What we won't merge

- Breaking changes to the public `/v1/*` proxy contract without a major
  version bump.
- Changes that introduce cross-tenant data exposure (no method may read
  rows for a tenant other than the one in the request context).
- Anything that adds a network call to the L1 hot path. L1 must remain
  sub-millisecond and offline.

## Releasing

```bash
# Bump version
sed -i 's/__version__ = ".*"/__version__ = "0.3.0"/' app/__init__.py
sed -i 's/"version": ".*"/"version": "0.3.0"/' dashboard/package.json

# Update CHANGELOG.md, commit, tag
git commit -am "release: v0.3.0"
git tag v0.3.0
git push --follow-tags
```

CI/CD takes it from there: the backend ships to Fly, the dashboard ships
to Vercel, and the extension gets zipped and uploaded as a GitHub Actions
artifact (manual Chrome Web Store upload until we automate it).
