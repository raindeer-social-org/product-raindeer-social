# Secrets Management

Issue #37 — final hardening pass. Date: 2026-08-25.

## Honesty note

**No real secrets manager was provisioned as part of this PR.** Doing so
requires a Doppler (or AWS/GCP Secrets Manager) account, real cloud
credentials, and access to wherever this app is actually deployed — none
of which exist in this development environment. This document audits the
current state, confirms it's already structured to make a real migration
low-risk, and lays out the concrete steps a follow-up with real
credentials would run. Treat "migrated" as a manual follow-up, not
something this PR closes out.

## 1. Current state audit

Every credential the app reads goes through one place:
`apps/api/config/__init__.py::Settings` (a `pydantic-settings`
`BaseSettings` subclass), accessed everywhere via the cached
`get_settings()` factory — never `os.environ` directly.

Verified during this audit:

```bash
grep -rn "os\.environ\|os\.getenv" apps/api packages --include="*.py" | grep -v "/tests/"
# (no output — no stray os.environ/os.getenv reads outside Settings)
```

Every provider adapter (`packages/integrations/*`), the JWT/token-signing
code (`apps/api/auth/jwt.py`), the OAuth token encryption
(`packages/integrations/social/encryption.py`), the rate limiter's Redis
connection (`apps/api/middleware/rate_limit.py`), and Sentry init
(`apps/api/observability.py`) all read from `get_settings()` — none read
environment variables directly. This is exactly the shape a secrets-manager
migration wants: **swap where the environment variables come from, and no
application code changes.**

Locally: `.env` (gitignored — confirmed in `.gitignore`) loaded via
`SettingsConfigDict(env_file=".env")`, with `.env.example` as the
committed template documenting every variable. In CI
(`.github/workflows/backend-ci.yml`): no secrets are configured at
all today — the test suite runs entirely on `Settings`'s built-in
defaults (a fixed dev-only Fernet key for `TOKEN_ENCRYPTION_KEY`,
`SECRET_KEY = "change-me"`, and `None` for every third-party API key,
which the relevant tests mock around). There is currently no production
deployment target in this repo to audit secrets for — this document
covers what a first production deployment should do before it holds real
customer OAuth tokens or brand data, per the issue's own framing.

Every credential currently in `.env.example` that a real migration needs
to carry over:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | JWT signing (access tokens, OAuth `state` params) |
| `TOKEN_ENCRYPTION_KEY` | Fernet key encrypting `SocialAccount` OAuth tokens at rest |
| `DATABASE_URL` | Postgres connection string |
| `REDIS_URL` | Redis connection string (rate limiter, job queue) |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY` | LLM providers |
| `TAVILY_API_KEY` | Search provider (Research Engine) |
| `FAL_API_KEY` | Image-generation provider |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | Media storage |
| `SENTRY_DSN` | Error tracking |
| `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET` | LinkedIn OAuth app credentials |
| `X_CLIENT_ID`, `X_CLIENT_SECRET`, `X_API_KEY` | X OAuth app credentials |

`SECRET_KEY` and `TOKEN_ENCRYPTION_KEY` are the two most sensitive: a
leaked `SECRET_KEY` lets an attacker forge access tokens (any role, any
org) and forge the OAuth `state` param the LinkedIn callback trusts
(`apps/api/routers/social_accounts.py::_verify_state`); a leaked
`TOKEN_ENCRYPTION_KEY` decrypts every stored customer OAuth token. Both
currently have dev-only fallback defaults in `Settings` specifically so
local/CI runs work with zero setup — **the actual risk is deploying with
those defaults still in place**, which the migration below closes.

## 2. Recommended target: Doppler

Doppler is the reasonable default recommendation here: free tier covers
a project this size, it injects secrets as real environment variables
(no SDK, no code change — `Settings` already reads from the environment),
and it has first-class GitHub Actions and most-PaaS integrations. AWS/GCP
Secrets Manager are reasonable alternatives if the app ends up hosted on
AWS/GCP infrastructure where native IAM-based access to the manager is
free (Doppler's per-seat pricing beyond the free tier stops being the
obvious default once cloud-native secrets are "free" alongside the
compute they're already paying for) — the migration steps below are
Doppler-specific but the shape is identical for either.

## 3. Migration steps (for whoever has real Doppler + deployment access)

1. **Create the Doppler project.** One project (e.g. `raindeer-social`),
   three configs: `dev`, `stg`, `prd` (Doppler's standard environment
   split — `dev` can stay optional if local `.env` remains the local-dev
   path, which is reasonable; `stg`/`prd` are the ones that matter).
2. **Populate every variable from the table above** into `stg` and `prd`
   with real values — real LLM keys, a freshly generated `SECRET_KEY`
   (`python -c "import secrets; print(secrets.token_urlsafe(32))"`) and
   `TOKEN_ENCRYPTION_KEY` (`python -c "from cryptography.fernet import
   Fernet; print(Fernet.generate_key().decode())"` — the same command
   already documented in `.env.example`), and the real LinkedIn/X OAuth
   app secrets. **Generate new `SECRET_KEY`/`TOKEN_ENCRYPTION_KEY` values
   for this migration — do not reuse the dev-only defaults baked into
   `Settings`.**
3. **Wire the deployment platform to Doppler**, not `.env`:
   - If deploying via a platform Doppler integrates with directly
     (Railway, Render, Fly.io, Heroku, Vercel), use Doppler's native
     integration to sync secrets into that platform's own env-var store —
     no `doppler run` wrapper needed at runtime.
   - If deploying via plain Docker/VM/Kubernetes, prefix the start
     command with `doppler run --` (e.g. `doppler run -- uvicorn
     apps.api.main:app`), authenticated via a Doppler **service token**
     scoped to the `prd` config, injected into that environment however
     secrets already reach it (a Kubernetes Secret holding just the one
     Doppler token, a platform's own secret store holding just that
     token — the *only* secret that needs to live outside Doppler itself
     is the token that unlocks Doppler).
4. **GitHub Actions**: `backend-ci.yml` currently needs no real secrets
   (tests run entirely on `Settings` defaults, mocking around anything
   that needs a real provider — see e.g. `test_integrations_llm.py`,
   `test_storage.py`). If a future CI job needs real credentials (an
   integration-test job that actually calls a live provider, a deploy
   job), pull them via Doppler's official `dopplerhq/cli-action` with a
   CI-scoped service token stored as a single `DOPPLER_TOKEN` GitHub
   Actions secret — not by hand-adding each individual provider key as
   its own repo secret.
5. **Rotate.** Once `stg`/`prd` are live on Doppler, rotate every
   credential that ever touched a `.env` file, a shell history, or a
   screen-share — treat everything in `.env.example`'s current column as
   potentially exposed simply by having existed in plaintext during
   development, even though `.env` itself was always gitignored (a repo
   scan for accidentally-committed `.env` files is a reasonable one-time
   check before rotating: `git log --all --full-history -- .env`).
6. **Remove local `.env` from the loop for anything but local dev.**
   `SettingsConfigDict(env_file=".env")` in `apps/api/config/__init__.py`
   can stay exactly as-is — Doppler-injected environment variables take
   precedence the same way any other env var does; `pydantic-settings`
   only falls back to `.env` for anything not already set in the
   environment. No code change needed here, which is the whole point of
   already routing every read through `Settings`.

## 4. What this PR did and didn't do

- Did: confirmed (via the `grep` above) there are no stray
  `os.environ`/`os.getenv` reads outside `Settings` to fix — the
  "every secret through one place" convention this issue asked to
  confirm was already fully satisfied.
- Did: documented the concrete migration plan above.
- Did not: create a Doppler account, populate real secrets anywhere, or
  change how any deployment target sources its environment — there is no
  deployed environment in scope to change, and doing so requires
  credentials this environment doesn't have. That step is a manual
  follow-up for whoever has Doppler + real deployment access, using the
  steps in §3 above.
