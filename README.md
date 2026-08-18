# Raindeer Social

AI-native social media management: brand intelligence, an agent pipeline that
turns a calendar slot into a reviewed draft, and human-in-the-loop scheduling
and publishing — built as a modular monolith, not a pile of microservices.

hello i am here

For the full system design, data model, agent pipeline, and issue roadmap,
see [`raindeer-social-blueprint.md`](./raindeer-social-blueprint.md). This
README covers what's here and how to get running; the blueprint covers why.

## System overview

Four backend domains, one repo:

| Path                | Responsibility |
|----------------------|----------------|
| `apps/api`           | FastAPI monolith — routers per domain (`/brands`, `/calendar`, `/posts`, `/agents`, `/publishing`, `/analytics`) |
| `packages/agents`     | LangGraph agent graphs (research, creative, generation, reviewer, onboarding) |
| `apps/web`            | Next.js frontend |
| `packages/schemas`    | Pydantic + Zod schemas, generated from one OpenAPI source of truth |
| `migrations`          | Alembic migrations for the Postgres schema |

**Stack:** Python 3.11 / FastAPI / SQLAlchemy + Alembic · LangGraph ·
PostgreSQL (Supabase) + pgvector · Redis + Celery · Next.js + TypeScript ·
Docker Compose for local dev.

## Getting started

### Prerequisites

- Python 3.11
- PostgreSQL 14+ with the [pgvector](https://github.com/pgvector/pgvector) extension available
- Redis (needed once the job queue lands in a later issue; safe to have running now)
- Docker Desktop (used from Issue #5 onward for the full Compose stack)
- Node 18+ (for `apps/web`, once the frontend lands)

### 1. Clone and create a virtualenv

```bash
git clone https://github.com/raindeer-social-org/raindeer-social.git
cd raindeer-social
python3.11 -m venv .venv
source .venv/bin/activate
python --version   # should print 3.11.x
```

### 2. Install backend dependencies

```bash
pip install --upgrade pip
pip install -r apps/api/requirements.txt
```

### 3. Set up Postgres + pgvector

```bash
createdb raindeer
psql raindeer -c "CREATE EXTENSION IF NOT EXISTS vector;"
psql raindeer -c "SELECT 1;"   # sanity check
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Fill in `.env` with at least one LLM API key (`OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, or `OPENROUTER_API_KEY`) and, if you're pointing at a
non-default local Postgres, update `DATABASE_URL`. `.env` is gitignored —
never commit it.

### 5. Run the API

```bash
uvicorn apps.api.main:app --reload
```

Then check `http://127.0.0.1:8000/health` — it should return
`{"status": "ok", "environment": "development"}` with no import errors in
the console.

Database schema and migrations land in Issue #4; the `docker compose up`
one-command stack lands in Issue #5. Until then, run Postgres/Redis
locally (e.g. via Homebrew services) as shown above.

## CI & branch protection

Every PR into `dev` or `main` runs through GitHub Actions before it can be
merged:

- **`backend-ci.yml`** — spins up Postgres (pgvector), runs Alembic
  migrations, then `pytest` with `--cov-fail-under=70`. A PR that drops
  backend coverage below 70% fails the build.
- **`frontend-ci.yml`** — scoped to `apps/web/**`; runs `lint`, `test`, then
  `build`, in that order, so a broken or untested frontend change never
  reaches `build`.

Branch protection enforces the rest:

- **`main`** — PRs only, 2 required approvals, CI must be green, branch
  must be up to date, no direct pushes or force-pushes.
- **`dev`** — PRs only, 1 required approval, same CI and up-to-date
  requirements, no direct pushes or force-pushes.

Together these make "tests pass and reviewers approved" a hard gate, not a
convention — the merge button is unavailable until both are true.

## Contributing

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for branch naming, PR process,
commit style, and the review rules before opening a PR. See
[`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md) for how we expect people to
treat each other in issues and reviews.

## License

Proprietary — see [`LICENSE.md`](./LICENSE.md).
