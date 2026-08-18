# Raindeer Social — Full Issue Roadmap

Local reference copy of every issue tracked on [GitHub](https://github.com/raindeer-social-org/product-raindeer-social/issues), grouped by milestone in dependency order. Generated from the same source used to create the issues — if GitHub and this file ever disagree, GitHub is the live source of truth; update this file to match, not the other way around.

Each entry carries its own **Depends on** and is referenced by number (`#N`) from issues that build on it — use this file to trace the full dependency graph before starting work, or to catch up on prior milestones without paging through GitHub issue by issue.

## Contents

- [M0 Foundations](#m0-foundations) — issues #1–6
- [M1 Core Backend + Integration Foundation](#m1-core-backend-integration-foundation) — issues #7–12
- [M2 Onboarding & Brand Intelligence](#m2-onboarding-brand-intelligence) — issues #13–17
- [M3 Agent Pipeline Core](#m3-agent-pipeline-core) — issues #18–25
- [M4 Calendar & Scheduling](#m4-calendar-scheduling) — issues #26–29
- [M5 Publishing](#m5-publishing) — issues #30–32
- [M6 Analytics](#m6-analytics) — issues #33–35
- [M7 Frontend & Hardening](#m7-frontend-hardening) — issues #36–37

## M0 Foundations

Repo scaffolding, CI, core schema, docker/worker, observability baseline.

### #1 — Local dev environment setup

**Labels:** `type:feature`, `area:infra`

#### Why
Every later issue assumes a working local stack. Mismatched Python versions, missing system packages, or wrong DB config are the most common reason a fresh clone fails to run. This is the shared foundation everyone starts from.

#### What needs to be built
Set up local dev environment completely — clone, install dependencies, start the API server with no errors.

#### Files to create/modify
- `.env.example`
- `requirements.txt` (or update it)
- `README.md` — Getting Started section

#### How this affects overall development
Every subsequent issue depends on this. If the venv isn't active or Postgres isn't running, nothing else works.

#### How to test locally
```bash
python --version   # 3.11.x
which python        # venv path
psql raindeer -c "SELECT 1;"
uvicorn apps.api.main:app --reload   # boots with no import errors
```

#### Acceptance Criteria
- [ ] Python 3.11 installed and active in venv
- [ ] All requirements installed without errors
- [ ] PostgreSQL running, `raindeer` database created, pgvector extension enabled
- [ ] `.env` created from `.env.example` with at least one LLM API key filled in
- [ ] `uvicorn apps.api.main:app --reload` starts clean

#### Branch
`feature/issue-1-dev-environment`

#### Depends on
Nothing — starting point

### #2 — CI pipeline + branch protection

**Labels:** `type:feature`, `area:infra`

#### Why
No PR should be mergeable on a hunch. Automated CI catches broken code before it reaches teammates.

#### What needs to be built
GitHub Actions workflows that run tests on every PR to `dev`, plus branch protection rules.

#### Files to create/modify
- `.github/workflows/backend-ci.yml`
- `.github/workflows/frontend-ci.yml`

#### How this affects overall development
Every PR going forward shows a pass/fail check. This is what lets multiple people work on the same codebase without constantly breaking each other.

#### How to test locally
```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/backend-ci.yml'))"
pytest apps/api/tests -v
# open a throwaway PR, confirm Actions tab runs the workflow
```

#### Acceptance Criteria
- [ ] `backend-ci.yml` runs pytest on every PR targeting `dev`/`main`
- [ ] `frontend-ci.yml` runs lint + build on frontend changes
- [ ] CI passes on a clean branch
- [ ] Branch protection enabled on `main` and `dev` (PR required, CI required, approvals required, no direct push)

#### Branch
`feature/issue-2-ci-setup`

#### Depends on
Closes #1

### #3 — Repo process scaffolding

**Labels:** `type:chore`, `area:infra`

#### Why
Consistent issues and PRs are what let a team move in parallel without a standup every hour.

#### What needs to be built
PR template, issue templates, labels, milestones, and a Projects board — most already exist from repo setup; this issue documents and finalizes them.

#### Files to create/modify
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/ISSUE_TEMPLATE/feature.md`, `bug.md`, `chore.md`

#### How this affects overall development
Standardizes how work gets proposed and reviewed for the rest of the project.

#### How to test locally
Create one throwaway issue and one throwaway PR from the templates, confirm they render correctly and auto-link.

#### Acceptance Criteria
- [ ] PR template requires Why/What/Testing/Screenshots/Checklist
- [ ] Issue templates live for feature/bug/chore
- [ ] Labels and 8 milestones exist
- [ ] Projects board has Backlog → Ready → In Progress → In Review → Done

#### Branch
`feature/issue-3-process-scaffolding`

#### Depends on
Closes #1

### #4 — Core database schema v1

**Labels:** `type:feature`, `area:backend`

#### Why
Organization/User/Brand is the foundation every other table, and every agent's read access, sits on.

#### What needs to be built
SQLAlchemy models + first Alembic migration for the core three entities.

#### Files to create/modify
- `apps/api/models/organization.py`
- `apps/api/models/user.py`
- `apps/api/models/brand.py`
- `apps/api/config/database.py`
- `migrations/versions/001_core_schema.py`

#### How this affects overall development
Every later module reads/writes these tables. Include `brand_report JSONB` and `report_embedding vector(1536)` now — cheaper than migrating a populated table later.

#### How to test locally
```bash
alembic upgrade head
psql raindeer -c "\dt"
psql raindeer -c "\d brands"
alembic downgrade -1 && alembic upgrade head
pytest apps/api/tests/test_models.py -v
```

#### Acceptance Criteria
- [ ] `organizations`, `users`, `brands` tables created
- [ ] `brands` includes `brand_report JSONB` and `report_embedding vector(1536)`
- [ ] Migration is reversible
- [ ] Model tests pass

#### Branch
`feature/issue-4-core-schema`

#### Depends on
Closes #1

### #5 — Docker Compose local stack + job runner

**Labels:** `type:feature`, `area:infra`

#### Why
Postgres + Redis + API + worker as one `docker compose up` removes "works on my machine" and locks in the async job runner before agent code depends on it.

#### What needs to be built
Docker Compose stack, worker skeleton wired to Celery.

#### Files to create/modify
- `docker-compose.yml`
- `apps/api/worker.py`

#### How this affects overall development
Background jobs (scraping, agent runs, analytics polling) all depend on this worker layer existing.

#### How to test locally
```bash
docker compose up
# enqueue a trivial test task, confirm it completes
```

#### Acceptance Criteria
- [ ] `docker compose up` brings up postgres (pgvector), redis, api, web
- [ ] Celery worker connects to Redis and completes a test task
- [ ] Job runner choice documented in README

#### Branch
`feature/issue-5-docker-worker`

#### Depends on
Closes #4

### #6 — Observability baseline

**Labels:** `type:feature`, `area:infra`

#### Why
Once agents start calling LLMs, cost/latency/failure visibility is needed from day one, not bolted on after debugging a mystery.

#### What needs to be built
Structured logging, `agent_runs` table, Sentry integration.

#### Files to create/modify
- `apps/api/middleware/logging.py`
- `apps/api/models/agent_run.py`
- `migrations/versions/002_agent_runs.py`

#### How this affects overall development
This table is the debugging and cost-tracking backbone for every agent built in M3.

#### How to test locally
```bash
# trigger a dummy endpoint error, confirm it appears in Sentry
# insert + query a mock AgentRun row
```

#### Acceptance Criteria
- [ ] JSON structured logging on all API requests
- [ ] `agent_runs` table: agent_type, input, output, tokens, cost, latency, created_at
- [ ] Sentry capturing errors from the API

#### Branch
`feature/issue-6-observability`

#### Depends on
Closes #4

---

## M1 Core Backend + Integration Foundation

Provider abstraction layer, auth/RBAC, Brand CRUD, OAuth storage, media storage, API conventions.

### #7 — Provider abstraction layer: search + LLM interfaces, Tavily + OpenRouter/OpenAI adapters, IntegrationCall table

**Labels:** `type:feature`, `area:integrations`

#### Why
Every 3rd-party capability (search, LLM, image gen, video gen, social) must be swappable behind a config-driven interface from day one — building agents against a vendor SDK directly means rewriting every caller when the vendor changes. This is the single highest-leverage issue in M1: everything from Onboarding's research step through the Generation Engine builds on top of it.

#### What needs to be built
`packages/integrations/` scaffolding — `search/base.py` (SearchProvider interface), `search/tavily.py` (first real adapter), `llm/base.py` (LLMProvider interface), `llm/openrouter_provider.py` (primary), `llm/openai_provider.py` (secondary, for OpenAI-only features), stub `base.py` interfaces for `image_gen/` and `video_gen/` (no adapters yet — implemented in #22/#23), and `registry.py` — a factory that reads `SEARCH_PROVIDER`/`LLM_PROVIDER` env vars and returns the configured adapter. Agent and business logic code must only ever import the interface, never a vendor SDK — the adapter file is the only place allowed to `import tavily` or call OpenRouter/OpenAI directly.

#### Files to create/modify
- `packages/integrations/search/base.py`, `packages/integrations/search/tavily.py`
- `packages/integrations/llm/base.py`, `openrouter_provider.py`, `openai_provider.py`
- `packages/integrations/image_gen/base.py`, `packages/integrations/video_gen/base.py` (interfaces only)
- `packages/integrations/registry.py`
- `apps/api/models/integration_call.py`
- `migrations/versions/003_integration_calls.py`
- `.env.example` — add `SEARCH_PROVIDER`, `LLM_PROVIDER`, `TAVILY_API_KEY`, `OPENROUTER_API_KEY`

#### How this affects overall development
Every later capability (Onboarding research, Research Engine, Generation Engine, image/video gen, social publishing) is built against these interfaces, not raw SDKs. Swapping Tavily for Serper, or adding a fallback provider, becomes a one-line env change instead of a multi-file rewrite.

#### How to test locally
```bash
python -c "from packages.integrations.registry import get_search_provider, get_llm_provider; print(get_search_provider(), get_llm_provider())"
pytest apps/api/tests/test_integrations.py -v
# call get_search_provider().search('test query') against a real Tavily key, confirm results come back and a row lands in integration_calls
```

#### Acceptance Criteria
- [ ] SearchProvider interface + TavilyProvider adapter implemented and passing a live smoke test
- [ ] LLMProvider interface + OpenRouterProvider (primary) + OpenAIProvider (secondary) implemented
- [ ] registry.py resolves the active adapter per capability from env vars, with no vendor SDK imports outside the adapter files
- [ ] `integration_calls` table logs provider, capability, latency, cost, success/failure, org_id on every call
- [ ] `image_gen/base.py` and `video_gen/base.py` interfaces exist (no adapter yet — deferred to #22/#23)

#### Branch
`feature/issue-7-provider-abstraction`

#### Depends on
Closes #4, Closes #6

### #8 — Auth + org/role model

**Labels:** `type:feature`, `area:backend`

#### Why
Every endpoint from here on needs to know who's calling and what they're allowed to do. Building this after endpoints exist means retrofitting auth checks everywhere instead of having them from the first real API.

#### What needs to be built
JWT-based auth (login/refresh), password hashing, and role enforcement for the four roles already in the data model (owner/admin/editor/viewer) scoped to an Organization. A reusable FastAPI dependency (`require_role(...)`) that every future router uses.

#### Files to create/modify
- `apps/api/auth/jwt.py`, `apps/api/auth/dependencies.py`, `apps/api/auth/router.py`
- `apps/api/models/user.py` (extend with password_hash)
- `apps/api/middleware/rbac.py`

#### How this affects overall development
Every router built from #9 onward (Brand CRUD, calendar, publishing, analytics) depends on `require_role` existing and being correct — this is exactly what #37's RBAC audit checks at the end.

#### How to test locally
```bash
pytest apps/api/tests/test_auth.py -v
# log in, hit a protected endpoint with/without a valid token, confirm 401/403 behave correctly
# confirm a viewer gets 403 on a write endpoint, 200 on read
```

#### Acceptance Criteria
- [ ] Login issues a JWT scoped to org_id + role
- [ ] `require_role()` dependency rejects insufficient roles with 403, missing/expired tokens with 401
- [ ] Passwords hashed (bcrypt/argon2), never stored or logged in plaintext
- [ ] Tests cover all four roles against at least one read and one write endpoint

#### Branch
`feature/issue-8-auth-rbac`

#### Depends on
Closes #4

### #9 — Brand CRUD API

**Labels:** `type:feature`, `area:backend`

#### Why
Brand is the entity every downstream domain (calendar, agents, publishing, analytics) reads from. Nothing else in M2+ has anything to point at until this exists as a real API.

#### What needs to be built
Full CRUD for Brand under `/brands`, org-scoped (an org can only see/edit its own brands), role-gated (viewer=read-only, editor+=write).

#### Files to create/modify
- `apps/api/routers/brands.py`
- `apps/api/schemas/brand.py`
- `packages/schemas` (shared Pydantic/Zod source)
- `apps/api/tests/test_brands.py`

#### How this affects overall development
The onboarding flow (#13), calendar (#26), and every agent's brand-context read all point at this API's data shape.

#### How to test locally
```bash
pytest apps/api/tests/test_brands.py -v
# create a brand as org A, confirm org B's token gets 404 (not 403 — don't leak existence) when fetching it
```

#### Acceptance Criteria
- [ ] POST/GET/PATCH/DELETE `/brands` and `/brands/{id}` implemented
- [ ] Org-scoping enforced — cross-org access returns 404
- [ ] viewer role blocked from POST/PATCH/DELETE
- [ ] Schema includes `brand_report` (JSONB) and `report_embedding` (vector) fields, unpopulated until M2

#### Branch
`feature/issue-9-brand-crud`

#### Depends on
Closes #8

### #10 — SocialAccount OAuth connection storage

**Labels:** `type:feature`, `area:integrations`

#### Why
Publishing (M5) and the SocialPublisher adapters both need somewhere to read a brand's connected accounts and valid tokens from — and those tokens are the most sensitive data in the system, so the storage layer has to be right before any OAuth flow is wired to a live platform.

#### What needs to be built
SocialAccount model (brand_id, platform, encrypted oauth tokens, scopes, connection status) + the OAuth connect/callback/disconnect flow for one platform first (LinkedIn), built as a `social/` adapter per the provider-abstraction pattern so X/Meta are additive later, not a rewrite.

#### Files to create/modify
- `apps/api/models/social_account.py`
- `migrations/versions/004_social_accounts.py`
- `packages/integrations/social/base.py`, `linkedin_provider.py`
- `apps/api/routers/social_accounts.py`

#### How this affects overall development
#30 (publishing adapters) reads directly from this table; getting encryption-at-rest and token refresh right here means #30 doesn't have to think about it.

#### How to test locally
```bash
pytest apps/api/tests/test_social_accounts.py -v
# run the LinkedIn OAuth flow against a sandbox/dev app, confirm tokens land encrypted in the DB, not plaintext
```

#### Acceptance Criteria
- [ ] OAuth tokens encrypted at rest (verify with a raw SELECT that ciphertext, not plaintext, is stored)
- [ ] Connect/disconnect flow works end-to-end for LinkedIn
- [ ] `SocialPublisher` interface exists under `packages/integrations/social/base.py` even though only LinkedIn is implemented
- [ ] Connection status (active/expired/revoked) reflected accurately after a token is manually revoked on the platform side

#### Branch
`feature/issue-10-social-oauth`

#### Depends on
Closes #7, Closes #9

### #11 — Media storage integration (Supabase Storage)

**Labels:** `type:feature`, `area:integrations`

#### Why
Brand logos now, generated images/video from M3 onward — the system needs one place to upload/serve media instead of every feature inventing its own storage code.

#### What needs to be built
A storage adapter (interface + adapter, so S3-compatible providers are swappable later) with upload/get-url/delete, wired to Brand logo upload first as the smoke test.

#### Files to create/modify
- `packages/integrations/storage/base.py`, `supabase_provider.py`
- `apps/api/routers/brands.py` (logo upload endpoint)

#### How this affects overall development
#22/#23 (image/video gen) and #17 (PDF export) all write through this same adapter instead of each picking their own storage approach.

#### How to test locally
```bash
pytest apps/api/tests/test_storage.py -v
# upload a test image via the brand logo endpoint, confirm it's retrievable via the returned URL and deletable
```

#### Acceptance Criteria
- [ ] StorageProvider interface + Supabase Storage adapter implemented
- [ ] Brand logo upload/replace/delete works end-to-end through the adapter
- [ ] Uploaded files are org/brand-scoped in storage paths (no way to guess another brand's asset URL from an incrementing ID)

#### Branch
`feature/issue-11-media-storage`

#### Depends on
Closes #7

### #12 — Shared API conventions: error format, validation, rate limiting

**Labels:** `type:chore`, `area:backend`

#### Why
Routers built independently (auth, brands, social accounts, and everything still coming) will each invent their own error shape and validation style unless one convention is enforced centrally now, before the surface area gets too big to retrofit.

#### What needs to be built
A shared error-response schema + FastAPI exception handlers, consistent Pydantic validation error formatting, and per-org rate limiting middleware (token bucket, Redis-backed).

#### Files to create/modify
- `apps/api/middleware/error_handlers.py`, `apps/api/middleware/rate_limit.py`
- `packages/schemas/error.py`

#### How this affects overall development
Every router from #13 onward returns errors in one shape, and the frontend (#36) only has to handle one error format across the whole API instead of one per router.

#### How to test locally
```bash
pytest apps/api/tests/test_error_handling.py apps/api/tests/test_rate_limit.py -v
# hit an endpoint past its rate limit, confirm 429 with a Retry-After header
```

#### Acceptance Criteria
- [ ] All 4xx/5xx responses share one JSON error shape (code, message, details)
- [ ] Pydantic validation errors are reformatted into that shape, not FastAPI's default
- [ ] Rate limiting enforced per-org on at least the auth and brands routers, returns 429 with Retry-After
- [ ] Existing tests from #8/#9 still pass against the new error format

#### Branch
`feature/issue-12-api-conventions`

#### Depends on
Closes #8, Closes #9

---

## M2 Onboarding & Brand Intelligence

Onboarding questionnaire, web research, Onboarding Agent, brand report embedding, PDF export.

### #13 — Onboarding questionnaire flow

**Labels:** `type:feature`, `area:backend`

#### Why
The Onboarding Agent (#15) needs structured answers to synthesize a Brand Report from — this is the human-input half of onboarding, before any agent touches it.

#### What needs to be built
A questionnaire data model + API (brand voice, audience, product catalog, competitors, goals) and the endpoint that stores answers against a Brand, gated on brand creation existing (#9).

#### Files to create/modify
- `apps/api/models/onboarding_response.py`
- `migrations/versions/005_onboarding_responses.py`
- `apps/api/routers/onboarding.py`

#### How this affects overall development
#15 reads this table directly as one of its two inputs (the other being #14's scraped research).

#### How to test locally
```bash
pytest apps/api/tests/test_onboarding.py -v
```

#### Acceptance Criteria
- [ ] Questionnaire schema covers voice/audience/product_catalog/competitors/goals at minimum
- [ ] Answers stored per-brand, editable before onboarding is marked complete
- [ ] Endpoint blocks starting the agent step (#15) until required fields are filled

#### Branch
`feature/issue-13-onboarding-questionnaire`

#### Depends on
Closes #9

### #14 — Web research step (SearchProvider)

**Labels:** `type:feature`, `area:agents`

#### Why
A Brand Report built only from self-reported questionnaire answers is missing the outside view — public web presence, competitor positioning — the same research capability the per-post pipeline needs later.

#### What needs to be built
A research step that calls `SearchProvider` (Tavily, via #7) with brand name/domain/competitors, structures the results (not just raw dumps), and stores them for #15 to consume.

#### Files to create/modify
- `packages/agents/onboarding/research_step.py`
- `apps/api/models/onboarding_research.py`

#### How this affects overall development
This is the first real caller of #7's SearchProvider interface outside a test — it's the proof the abstraction actually works before the higher-stakes Research Engine (#19) builds on it too.

#### How to test locally
```bash
pytest packages/agents/tests/test_onboarding_research.py -v
# run against a real brand domain, confirm structured results land in onboarding_research, and an integration_calls row is logged
```

#### Acceptance Criteria
- [ ] Research step calls SearchProvider exclusively through the interface, no direct Tavily import
- [ ] Structured output (not raw search results) stored and readable by #15
- [ ] Failure (provider timeout/error) degrades gracefully — onboarding continues with questionnaire-only data, doesn't hard-fail

#### Branch
`feature/issue-14-onboarding-research`

#### Depends on
Closes #7, Closes #13

### #15 — Onboarding Agent (LangGraph)

**Labels:** `type:feature`, `area:agents`

#### Why
This is where questionnaire answers + web research actually become the Brand Report every later agent reads — the single most important synthesis step in the whole system.

#### What needs to be built
A LangGraph graph that takes `onboarding_response` + `onboarding_research` as input and produces the structured `brand_report` JSONB, written back onto the Brand row.

#### Files to create/modify
- `packages/agents/onboarding/graph.py`, `packages/agents/onboarding/prompts.py`
- `apps/api/routers/onboarding.py` (trigger endpoint)

#### How this affects overall development
Every agent in M3 (Research/Creative/Generation/Reviewer) reads `brand_report` as shared context — a broken or thin report here means generic output everywhere downstream, exactly the failure mode this whole system exists to prevent.

#### How to test locally
```bash
pytest packages/agents/tests/test_onboarding_agent.py -v
# trigger for a real brand, confirm brand_report is populated with voice/audience/product/competitor sections and an AgentRun row is logged
```

#### Acceptance Criteria
- [ ] Graph runs end-to-end: questionnaire + research in, structured brand_report out
- [ ] Every run logs an AgentRun row (agent_type=onboarding, tokens, cost, latency)
- [ ] Uses LLMProvider (#7), not a direct LLM SDK call
- [ ] Report includes, at minimum: voice/tone, audience, product catalog summary, competitive positioning

#### Branch
`feature/issue-15-onboarding-agent`

#### Depends on
Closes #13, Closes #14

### #16 — Brand Report embedding + pgvector storage

**Labels:** `type:feature`, `area:agents`

#### Why
A JSONB report is readable by a human but not retrievable by relevance — later agents (Research/Creative/Generation) need to pull the relevant slice of a brand report for a given post, not the whole blob stuffed into every prompt.

#### What needs to be built
Chunk + embed the `brand_report` into `report_embedding` (already reserved as a pgvector column since #4), plus a retrieval helper (`get_relevant_brand_context(brand_id, query)`) agents call instead of reading the raw JSONB.

#### Files to create/modify
- `packages/agents/onboarding/embedding.py`
- `apps/api/services/brand_retrieval.py`

#### How this affects overall development
This is the RAG layer every M3 agent depends on for "reads brand context" instead of full-document prompt stuffing — the exact manual pain the product replaces.

#### How to test locally
```bash
pytest apps/api/tests/test_brand_retrieval.py -v
# embed a real brand report, query with a post topic, confirm the top-k results are actually relevant
```

#### Acceptance Criteria
- [ ] `brand_report` is chunked and embedded into `report_embedding` on every onboarding completion/update
- [ ] `get_relevant_brand_context()` returns top-k relevant chunks via pgvector similarity search
- [ ] Re-running onboarding (brand report updated) re-embeds rather than appending stale vectors

#### Branch
`feature/issue-16-brand-embedding`

#### Depends on
Closes #15

### #17 — Brand Report PDF export

**Labels:** `type:feature`, `area:backend`

#### Why
A human-readable brand report (agency deliverable, client sign-off) is a small but real product surface — the JSONB report needs a rendered artifact, not just API access.

#### What needs to be built
A render pipeline from `brand_report` JSONB to a formatted PDF, stored via #11's storage adapter and downloadable from the brand page.

#### Files to create/modify
- `apps/api/services/brand_report_pdf.py`
- `apps/api/routers/brands.py` (export endpoint)

#### How this affects overall development
Self-contained — no later issue depends on this, but it should reuse #11's storage adapter rather than inventing its own file handling.

#### How to test locally
```bash
pytest apps/api/tests/test_brand_pdf.py -v
# export a real brand report, confirm the PDF opens and contains all report sections
```

#### Acceptance Criteria
- [ ] PDF includes all brand_report sections in a readable layout
- [ ] Export stored via the storage adapter (#11), returns a downloadable URL
- [ ] Re-export after a report update produces an updated PDF, not a cached stale one

#### Branch
`feature/issue-17-brand-pdf-export`

#### Depends on
Closes #15, Closes #11

---

## M3 Agent Pipeline Core

LangGraph orchestration, Research/Creative/Generation/Reviewer Engines, image/video gen, human review interrupt.

### #18 — LangGraph orchestration + checkpoint persistence (per-post pipeline skeleton)

**Labels:** `type:feature`, `area:agents`

#### Why
The per-post pipeline's human-review step is a durable interrupt that can pause for hours or days waiting on a human — that has to be built as real LangGraph checkpointing from the start, not bolted on with cron jobs and status flags later.

#### What needs to be built
The seven-step graph skeleton (Research → Creative → Generation → Reviewer → ⏸ Human Review interrupt → Scheduler → Publisher → Analytics Collector) with each step as a stub node and Postgres-backed checkpoint persistence so a paused run survives a server restart.

#### Files to create/modify
- `packages/agents/pipeline/graph.py`
- `packages/agents/pipeline/checkpointer.py`
- `apps/api/models/post.py` (current_pipeline_stage field)
- `migrations/versions/006_pipeline_checkpoints.py`

#### How this affects overall development
#19–#25 fill in the stub nodes one at a time — this issue is what makes the pipeline resumable and testable node-by-node instead of one monolithic script.

#### How to test locally
```bash
pytest packages/agents/tests/test_pipeline_graph.py -v
# start a run, kill the process mid-graph, restart, confirm it resumes from the last completed node rather than restarting
```

#### Acceptance Criteria
- [ ] Graph defines all 7 steps with the human-review step as a real interrupt (not a polling loop)
- [ ] Checkpoint state persists to Postgres and survives a process restart
- [ ] `Post.current_pipeline_stage` reflects the graph's real position at all times

#### Branch
`feature/issue-18-pipeline-orchestration`

#### Depends on
Closes #6, Closes #16

### #19 — Research Engine

**Labels:** `type:feature`, `area:agents`

#### Why
Step 1 of the per-post pipeline — platform + industry trend research grounded in the brand's actual context, not generic prompting.

#### What needs to be built
The Research Engine node, calling SearchProvider (#7) for trend/platform research and #16's retrieval helper for brand context, producing a structured research brief consumed by the Creative Engine.

#### Files to create/modify
- `packages/agents/pipeline/nodes/research_engine.py`

#### How this affects overall development
#20 (Creative Engine) and #28 (auto-scheduling timing signal) both consume this node's output.

#### How to test locally
```bash
pytest packages/agents/tests/test_research_engine.py -v
```

#### Acceptance Criteria
- [ ] Node calls SearchProvider only through the interface
- [ ] Output includes a timing/trend signal usable by #28, not just topic research
- [ ] AgentRun logged with agent_type=research

#### Branch
`feature/issue-19-research-engine`

#### Depends on
Closes #18, Closes #7

### #20 — Creative Engine

**Labels:** `type:feature`, `area:agents`

#### Why
Step 2 — deciding format, angle, hook, and CTA is a distinct creative-strategy decision from actually writing copy (step 3), and keeping them separate nodes makes each independently testable and promptable.

#### What needs to be built
The Creative Engine node, taking the Research Engine's brief + brand context, producing a creative brief (format, angle, hook, CTA, platform-appropriate tone) for the Generation Engine.

#### Files to create/modify
- `packages/agents/pipeline/nodes/creative_engine.py`

#### How this affects overall development
#21 (Generation Engine) is only as good as this brief — if the brief is vague, generation output regresses to generic.

#### How to test locally
```bash
pytest packages/agents/tests/test_creative_engine.py -v
```

#### Acceptance Criteria
- [ ] Output is a structured brief (not free text) with format/angle/hook/CTA fields
- [ ] Tone/format adapts per target platform, verified across at least 2 platforms in tests
- [ ] AgentRun logged with agent_type=creative

#### Branch
`feature/issue-20-creative-engine`

#### Depends on
Closes #19

### #21 — Generation Engine

**Labels:** `type:feature`, `area:agents`

#### Why
Step 3 — turns the creative brief into actual copy, and triggers image/video generation when the brief calls for it. This is the first node built directly on LLMProvider from #7.

#### What needs to be built
The Generation Engine node — copy generation via LLMProvider, with hooks to call image/video generation (stubbed until #22/#23 land) when `desired_format` requires it.

#### Files to create/modify
- `packages/agents/pipeline/nodes/generation_engine.py`

#### How this affects overall development
#22/#23 plug into the hooks this issue defines; #24 (Reviewer) reviews this node's output.

#### How to test locally
```bash
pytest packages/agents/tests/test_generation_engine.py -v
```

#### Acceptance Criteria
- [ ] Copy generation uses LLMProvider exclusively, no direct OpenAI/OpenRouter SDK calls
- [ ] Output written to `Post.body_text` with version history preserved
- [ ] Image/video hook is called (even if stubbed) when desired_format is image/video/carousel
- [ ] AgentRun logged with agent_type=generation, including token/cost

#### Branch
`feature/issue-21-generation-engine`

#### Depends on
Closes #20, Closes #7

### #22 — Image-generation integration (ImageProvider)

**Labels:** `type:feature`, `area:integrations`

#### Why
Fills in the `image_gen/` interface stubbed in #7 with a real adapter, following the same swappable pattern as search/LLM.

#### What needs to be built
ImageProvider adapter (fal.ai first) wired into the Generation Engine's image hook from #21, with output stored via #11's storage adapter.

#### Files to create/modify
- `packages/integrations/image_gen/fal_provider.py`

#### How this affects overall development
Completes the "image" branch of `desired_format` that #21 stubbed.

#### How to test locally
```bash
pytest apps/api/tests/test_image_gen.py -v
# generate a real image for a test post, confirm it's stored via the storage adapter and linked on Post.media
```

#### Acceptance Criteria
- [ ] fal.ai adapter implements ImageProvider, called only through the interface from Generation Engine
- [ ] Generated images stored via #11's adapter, referenced on `Post.media`
- [ ] Failures logged to `integration_calls` and surfaced without crashing the pipeline run

#### Branch
`feature/issue-22-image-generation`

#### Depends on
Closes #21, Closes #11

### #23 — Video/carousel-generation integration (VideoProvider)

**Labels:** `type:feature`, `area:integrations`

#### Why
Fills in the `video_gen/` interface stubbed in #7, completing the last `desired_format` branch (video/carousel) the pipeline needs to support.

#### What needs to be built
VideoProvider adapter (Kling or Runway — pick one for the first implementation) wired into the same generation hook as #22.

#### Files to create/modify
- `packages/integrations/video_gen/kling_provider.py` (or `runway_provider.py`)

#### How this affects overall development
Same role as #22, for video/carousel instead of static image.

#### How to test locally
```bash
pytest apps/api/tests/test_video_gen.py -v
# generate a real short video/carousel for a test post, confirm storage + Post.media linkage
```

#### Acceptance Criteria
- [ ] Adapter implements VideoProvider, called only through the interface
- [ ] Generated video/carousel stored via #11's adapter, referenced on `Post.media`
- [ ] Failures logged to `integration_calls`, degrade gracefully (don't crash the run)

#### Branch
`feature/issue-23-video-generation`

#### Depends on
Closes #21, Closes #11

### #24 — Reviewer Engine (AI)

**Labels:** `type:feature`, `area:agents`

#### Why
Step 4 — an automated brand-alignment, compliance, and platform-fit pass before a human ever sees the draft, so human review time goes toward judgment calls, not catching obvious misses.

#### What needs to be built
The Reviewer Engine node — scores generated Post content against brand voice/compliance/platform norms, writes a ReviewFeedback row (source=ai_reviewer) with score, verdict, and suggested edits.

#### Files to create/modify
- `packages/agents/pipeline/nodes/reviewer_engine.py`
- `apps/api/models/review_feedback.py`
- `migrations/versions/007_review_feedback.py`

#### How this affects overall development
#25's human review UI surfaces this AI review alongside the human's own judgment — the human isn't reviewing blind.

#### How to test locally
```bash
pytest packages/agents/tests/test_reviewer_engine.py -v
# feed a deliberately off-brand draft, confirm the reviewer flags it with a low score and specific suggestions
```

#### Acceptance Criteria
- [ ] ReviewFeedback row written with score, verdict, comments for every generated Post
- [ ] Deliberately off-brand test content scores low with actionable suggestions, not just a number
- [ ] AgentRun logged with agent_type=reviewer

#### Branch
`feature/issue-24-reviewer-engine`

#### Depends on
Closes #21

### #25 — Human Review interrupt + UI actions

**Labels:** `type:feature`, `area:agents`

#### Why
Step 5 — the durable interrupt from the pipeline design needs a real UI surface and resume mechanism, not just a graph-level pause. This is the human-in-the-loop moment the whole pipeline exists to support.

#### What needs to be built
The API + minimal UI for approve/edit/reject/reschedule on a paused Post, which resumes the LangGraph checkpoint (#18) from exactly that point with the human's decision as input.

#### Files to create/modify
- `apps/api/routers/review.py`
- `apps/web/app/review/` (review queue page)

#### How this affects overall development
#29 (pipeline trigger) and #31 (publish queue) both key off the decision recorded here — approved posts flow to Scheduler/Publisher, rejected ones don't.

#### How to test locally
```bash
pytest apps/api/tests/test_review.py -v
# pause a run at the interrupt, approve via the API, confirm the graph resumes and proceeds to Scheduler
# reject a run, confirm it stops and doesn't reach Publisher
```

#### Acceptance Criteria
- [ ] Approve/edit/reject/reschedule all correctly resume or halt the checkpointed graph
- [ ] ReviewFeedback row written with source=human alongside the AI reviewer's from #24
- [ ] Review queue UI shows the AI reviewer's score/suggestions next to the draft

#### Branch
`feature/issue-25-human-review`

#### Depends on
Closes #24, Closes #18

---

## M4 Calendar & Scheduling

ContentCalendarEvent model + UI, auto-scheduling, pipeline trigger.

### #26 — ContentCalendarEvent model + CRUD API

**Labels:** `type:feature`, `area:backend`

#### Why
The calendar is a state machine, not just a list of dates — this issue is the data model and API that #27 renders and #29 triggers off of.

#### What needs to be built
ContentCalendarEvent model (brand_id, title, description, target_platforms[], desired_format, target_datetime, status) + CRUD API.

#### Files to create/modify
- `apps/api/models/content_calendar_event.py`
- `migrations/versions/008_calendar_events.py`
- `apps/api/routers/calendar.py`

#### How this affects overall development
#29's trigger reads event status transitions from this table; #27 is a direct UI on top of this API.

#### How to test locally
```bash
pytest apps/api/tests/test_calendar.py -v
```

#### Acceptance Criteria
- [ ] Full CRUD, org/brand-scoped, role-gated per #8
- [ ] status enum matches the data model exactly (scheduled/pipeline_running/ready_for_review/approved/published/failed)
- [ ] target_platforms and desired_format validated against the platforms #30 will actually support

#### Branch
`feature/issue-26-calendar-model`

#### Depends on
Closes #9

### #27 — Calendar UI

**Labels:** `type:feature`, `area:frontend`

#### Why
The calendar is the primary surface a brand manager interacts with day-to-day — needs to exist early enough to get real usage feedback before M7's full dashboard shell.

#### What needs to be built
A calendar view (month/week) against #26's API, showing event status visually distinct by state.

#### Files to create/modify
- `apps/web/app/calendar/`

#### How this affects overall development
Ships ahead of #36's full shell — frontend screens land alongside their backend milestone, not all at the end.

#### How to test locally
```bash
npm run test --prefix apps/web
# create/move/delete events through the UI, confirm they match the API state
```

#### Acceptance Criteria
- [ ] Month and week views both render event status distinctly
- [ ] Create/edit/delete round-trip correctly against #26's API
- [ ] Status changes (e.g. pipeline_running → ready_for_review) reflect without a manual page refresh

#### Branch
`feature/issue-27-calendar-ui`

#### Depends on
Closes #26

### #28 — Auto-scheduling (optimal-time suggestion)

**Labels:** `type:feature`, `area:agents`

#### Why
The Research Engine (#19) already produces a timing signal — this issue is what turns that signal into an actual suggested publish time instead of leaving it unused in a research brief.

#### What needs to be built
A suggestion service that reads #19's timing signal for a brand/platform and proposes a `target_datetime` when creating a calendar event, which the user can accept or override.

#### Files to create/modify
- `apps/api/services/scheduling_suggestion.py`

#### How this affects overall development
Feeds #26's `target_datetime` at creation time; #29's trigger timing depends on this being reasonably accurate.

#### How to test locally
```bash
pytest apps/api/tests/test_scheduling_suggestion.py -v
```

#### Acceptance Criteria
- [ ] Suggestion pulls from #19's real research signal, not a hardcoded time-of-day table
- [ ] User can override the suggestion; override is respected and not silently reset
- [ ] Suggestion logic covered by tests across at least 2 platforms

#### Branch
`feature/issue-28-auto-scheduling`

#### Depends on
Closes #26, Closes #19

### #29 — Pipeline trigger

**Labels:** `type:feature`, `area:backend`

#### Why
Nothing currently starts the M3 pipeline automatically — this is the scheduled job that watches upcoming calendar events and kicks off the graph early enough that a reviewed draft is sitting ready before the target date.

#### What needs to be built
A background job (via #5's worker) that polls ContentCalendarEvent for events approaching `target_datetime`, starts the #18 pipeline graph, and updates event status to `pipeline_running`.

#### Files to create/modify
- `apps/api/worker.py` (extend)
- `packages/agents/pipeline/trigger.py`

#### How this affects overall development
This is the seam between the calendar (M4) and the agent pipeline (M3) — without it, pipelines only ever start manually.

#### How to test locally
```bash
pytest apps/api/tests/test_pipeline_trigger.py -v
# create an event with a near-future target_datetime, confirm the job picks it up and status flips to pipeline_running
```

#### Acceptance Criteria
- [ ] Job runs on a schedule (Celery beat or equivalent) and picks up events within a configurable lead time
- [ ] Event status transitions correctly through pipeline_running → ready_for_review
- [ ] Duplicate triggering is prevented (an event already pipeline_running isn't re-triggered)

#### Branch
`feature/issue-29-pipeline-trigger`

#### Depends on
Closes #26, Closes #18, Closes #28

---

## M5 Publishing

Platform publishing adapters, publish queue with retry, status notifications.

### #30 — Platform publishing adapters (LinkedIn + X)

**Labels:** `type:feature`, `area:integrations`

#### Why
Publishing is the payoff of everything upstream — and each platform is just a new adapter against `SocialPublisher`, not a bespoke integration.

#### What needs to be built
SocialPublisher adapters for LinkedIn and X (`publish(post) -> PublishResult`), reading tokens from #10's SocialAccount storage.

#### Files to create/modify
- `packages/integrations/social/linkedin_provider.py` (extend from #10), `x_provider.py`

#### How this affects overall development
#31's publish queue calls these adapters; Instagram/YouTube become additive adapters later against the same interface.

#### How to test locally
```bash
pytest apps/api/tests/test_publishing_adapters.py -v
# publish a test post to a real sandbox/dev LinkedIn and X account, confirm it appears on-platform and PublishResult is accurate
```

#### Acceptance Criteria
- [ ] Both adapters implement SocialPublisher and are called only through the interface
- [ ] Token refresh handled transparently (expired token retried once after refresh, not surfaced as a hard failure)
- [ ] Every publish attempt logged to `integration_calls`

#### Branch
`feature/issue-30-publishing-adapters`

#### Depends on
Closes #7, Closes #10

### #31 — Publish queue with retry/failure handling

**Labels:** `type:feature`, `area:backend`

#### Why
A publish call can fail transiently (rate limit, platform outage) — approved posts need a durable queue with retry, not a synchronous call that silently fails once.

#### What needs to be built
A Redis-backed publish queue (via #5's worker) that takes approved Posts (from #25), calls #30's adapters, retries with backoff on transient failure, and marks status=failed only after retries are exhausted.

#### Files to create/modify
- `apps/api/worker.py` (extend)
- `apps/api/services/publish_queue.py`

#### How this affects overall development
#32's failure notifications key off this queue's failed state; #33's analytics polling only starts once a post is confirmed published here.

#### How to test locally
```bash
pytest apps/api/tests/test_publish_queue.py -v
# force a transient failure (mock 429 from the adapter), confirm retry with backoff, then success
# force a permanent failure, confirm status=failed after retries exhaust
```

#### Acceptance Criteria
- [ ] Approved posts are picked up and published without manual triggering
- [ ] Transient failures retry with exponential backoff, capped at a defined max attempts
- [ ] Permanent failures land in status=failed with the failure reason recorded, not silently dropped

#### Branch
`feature/issue-31-publish-queue`

#### Depends on
Closes #25, Closes #30

### #32 — Status notifications (email/Slack)

**Labels:** `type:feature`, `area:backend`

#### Why
A failed publish or a post waiting on human review shouldn't require someone to go check the dashboard — notify the people who can act on it.

#### What needs to be built
Notification service (email via a transactional provider, Slack via webhook) triggered on publish failure (#31) and on a post reaching `ready_for_review` (#25).

#### Files to create/modify
- `apps/api/services/notifications.py`

#### How this affects overall development
Self-contained consumer of state changes from #25 and #31 — no later issue depends on this.

#### How to test locally
```bash
pytest apps/api/tests/test_notifications.py -v
# force a publish failure, confirm a notification fires with the right content and recipient
```

#### Acceptance Criteria
- [ ] Publish failures trigger a notification within the same job run that detects the failure
- [ ] Posts reaching ready_for_review notify the relevant reviewer(s), not the whole org
- [ ] Notification failures (e.g. bad webhook) don't crash the triggering job

#### Branch
`feature/issue-32-notifications`

#### Depends on
Closes #31

---

## M6 Analytics

Engagement polling, analytics dashboard API, AI-generated weekly report.

### #33 — Engagement-metrics polling jobs

**Labels:** `type:feature`, `area:integrations`

#### Why
Without engagement data flowing back in, the Research Engine's "what's working" signal (#19, #28) never actually improves, it just stays static.

#### What needs to be built
Per-platform polling jobs (via #5's worker) that fetch likes/comments/shares/impressions for published posts and write EngagementSnapshot rows on a schedule.

#### Files to create/modify
- `apps/api/models/engagement_snapshot.py`
- `migrations/versions/009_engagement_snapshots.py`
- `apps/api/services/engagement_polling.py`

#### How this affects overall development
#34's dashboard and #35's weekly report both read from EngagementSnapshot; #19/#28 can eventually use historical snapshots as a real (not just first-party) timing signal.

#### How to test locally
```bash
pytest apps/api/tests/test_engagement_polling.py -v
# poll a real published test post, confirm a snapshot row lands with accurate metrics
```

#### Acceptance Criteria
- [ ] Polling job runs on a schedule per published post, per platform
- [ ] EngagementSnapshot is a true time series (one row per poll, not an overwrite)
- [ ] Rate limits on the platform API side are respected (uses #7's provider pattern for backoff)

#### Branch
`feature/issue-33-engagement-polling`

#### Depends on
Closes #31

### #34 — Analytics storage + dashboard API

**Labels:** `type:feature`, `area:backend`

#### Why
Raw EngagementSnapshot rows aren't directly useful — this issue is the aggregation layer the frontend and #35's AI report both read from.

#### What needs to be built
Aggregation queries/materialized views over EngagementSnapshot (per-brand, per-platform, per-post trends) exposed via a `/analytics` router.

#### Files to create/modify
- `apps/api/routers/analytics.py`
- `apps/api/services/analytics_aggregation.py`

#### How this affects overall development
#35 generates its report from this API's output rather than querying raw snapshots directly.

#### How to test locally
```bash
pytest apps/api/tests/test_analytics.py -v
```

#### Acceptance Criteria
- [ ] `/analytics` returns per-brand and per-post aggregates over a configurable date range
- [ ] Aggregation is performant against a realistic snapshot volume (tested with a seeded dataset, not just a handful of rows)
- [ ] Org/brand scoping enforced same as every other router

#### Branch
`feature/issue-34-analytics-api`

#### Depends on
Closes #33

### #35 — AI-generated weekly report

**Labels:** `type:feature`, `area:agents`

#### Why
A brand manager shouldn't have to interpret a metrics dashboard themselves every week — closing the loop with an AI-written summary is what makes the analytics actually actionable rather than just visible.

#### What needs to be built
A scheduled job that reads #34's aggregates for the past week, generates a written summary + recommendations via LLMProvider, and stores it as a Report row per brand.

#### Files to create/modify
- `apps/api/models/report.py`
- `migrations/versions/010_reports.py`
- `packages/agents/reporting/weekly_report.py`

#### How this affects overall development
Terminal node of the M6 milestone — no later issue depends on this.

#### How to test locally
```bash
pytest apps/api/tests/test_weekly_report.py -v
# run against a seeded brand with real snapshot data, confirm the summary references actual numbers, not generic filler
```

#### Acceptance Criteria
- [ ] Report generated weekly per brand with real metrics referenced (not hallucinated placeholders)
- [ ] Uses LLMProvider exclusively, AgentRun logged
- [ ] Report accessible via API and surfaced somewhere in the dashboard (#36)

#### Branch
`feature/issue-35-weekly-report`

#### Depends on
Closes #34

---

## M7 Frontend & Hardening

Core dashboard shell, final hardening pass (secrets, RBAC audit, load test).

### #36 — Core Next.js dashboard shell

**Labels:** `type:feature`, `area:frontend`

#### Why
Auth, brand switching, and navigation across calendar/review/analytics have each been living in feature-specific pages so far — this is the shell that ties them into one coherent app instead of a pile of disconnected routes.

#### What needs to be built
App shell with auth-gated routing, an org/brand switcher, and nav linking #27 (calendar), #25 (review queue), #13 (onboarding), and #34/#35 (analytics) into one experience.

#### Files to create/modify
- `apps/web/app/layout.tsx`
- `apps/web/components/nav.tsx`, `apps/web/components/brand-switcher.tsx`

#### How this affects overall development
Doesn't gate any backend work — it's the integration pass that makes the product usable end-to-end by someone who isn't reading API docs.

#### How to test locally
```bash
npm run test --prefix apps/web
npm run build --prefix apps/web
# manually walk: log in → switch brand → calendar → review queue → analytics, confirm no dead links or auth drops
```

#### Acceptance Criteria
- [ ] Unauthenticated users are redirected to login on every protected route
- [ ] Brand switcher correctly scopes every page's data to the selected brand
- [ ] All M2–M6 feature pages are reachable from the shell nav

#### Branch
`feature/issue-36-dashboard-shell`

#### Depends on
Closes #8, Closes #9

### #37 — Final hardening pass

**Labels:** `type:chore`, `area:infra`, `area:backend`

#### Why
Every issue before this shipped a feature and hit a 70% coverage bar in isolation. This issue is the pass that looks across the whole system: are permissions actually enforced end-to-end, are secrets handled the way real customer data deserves, does anything fall over under real concurrent load. This is the gate before calling M0–M7 genuinely production-ready, not just "all issues closed."

#### What needs to be built
- **Secrets migration:** move off `.env`/GitHub Actions secrets onto a real secrets manager (Doppler, or AWS/GCP Secrets Manager). Every credential currently in `.env.example` gets migrated: LLM keys, Tavily, Supabase, LinkedIn/X OAuth app secrets, encryption keys for token storage.
- **RBAC audit:** walk every endpoint built since #8 and confirm role checks are actually present and correct — not just that they exist somewhere, but that a `viewer` genuinely cannot write anywhere, and that org-scoping is airtight (no endpoint that leaks another org's data through a missing `WHERE org_id = `).
- **Rate limit verification under load:** confirm #12's rate limiting actually holds under concurrent traffic, not just a single test request.
- **Load-test baseline:** establish a real baseline (requests/sec the API handles, pipeline throughput — how many concurrent `Post` pipelines can run before queue latency degrades) so future scaling decisions have a number to compare against instead of a guess.

#### Files to create/modify
- `docs/security/rbac-audit.md` — a table: endpoint, required role, org-scoping confirmed, tested (yes/no)
- `.github/workflows/load-test.yml` (or a documented manual process if full CI automation isn't worth it yet)
- Secrets manager migration touches every service's config loading — `apps/api/config/settings.py` becomes the single place secrets are read from, not scattered `os.environ` calls
- `docs/infra/load-test-baseline.md` — recorded numbers, methodology, date

#### How this affects overall development
This is the last thing before you'd feel comfortable onboarding real paying customers' OAuth tokens and brand data — worth treating as seriously as any feature issue, not as a formality to close out the milestone list.

#### How to test locally
```bash
pytest apps/api/tests/test_rbac_audit.py apps/api/tests/test_org_scoping.py -v --cov-fail-under=70
# load test: run against a local stack with realistic concurrent pipeline volume, record results in docs/infra/load-test-baseline.md
```

#### Acceptance Criteria
- [ ] All secrets migrated off `.env` in any non-local environment
- [ ] RBAC audit table complete, every row tested and passing
- [ ] Org-scoping cross-access test passing on every scoped resource
- [ ] Rate limiting confirmed under concurrent load
- [ ] Load-test baseline recorded and documented
- [ ] Tests written and passing, coverage ≥70%

#### Branch
`feature/issue-37-hardening-pass`

#### Depends on
Closes everything in M1–M6, plus #36 — this is a review pass, not new functionality

---
