# Raindeer Social — Engineering Blueprint

This is the working blueprint for building `raindeer-social-org/raindeer-social` from an empty repo to a production system, broken into 37 tracked GitHub issues across 8 milestones. It covers system design first, then process (GitHub setup), then the issue roadmap.

**Revision note:** originally 36 issues. Added #7 — the provider abstraction layer — after deciding early that this is a heavily 3rd-party-dependent system (Tavily for search/research today, likely more vendors for image/video/social over time) and the codebase needs to treat every vendor as swappable from day one rather than hard-wired. Everything from #8 onward shifted by one.

I can't create issues directly on GitHub from here — no GitHub connector is available in this chat, so no repo-write tools exist on my end. Everything below is written so you can paste it straight into GitHub Issues / Projects / `.github/` yourself. If you'd rather automate the creation, the `gh` CLI script at the bottom does all 36 in one pass.

---

## 1. System design

### 1.1 What the system actually has to do

Strip away the pitch language and there are four distinct problems, and they should be four distinct subsystems, not one blob:

1. **Brand intelligence** — build and maintain a structured, queryable model of a brand (voice, audience, visual identity, products, past content) that every downstream agent reads from. Get this wrong and every generated post is generic.
2. **Content generation pipeline** — a multi-step agent pipeline (research → creative brief → generation → review) that turns "post about X on LinkedIn" into a reviewed, brand-aligned draft.
3. **Scheduling & human-in-the-loop** — a calendar that isn't just a list of dates but a state machine: a calendar event triggers the pipeline ahead of time, and a human gets a single approve/reject decision, not a blank page.
4. **Distribution & feedback** — publishing to platform APIs, and pulling engagement data back in so the Research Engine's "what's working" signal actually improves over time.

These map cleanly to four backend domains. Design each with a clear ownership boundary so five people can work in parallel without stepping on each other:

```
apps/api            → FastAPI monolith-first (see 1.4), split into routers per domain
packages/agents      → LangGraph agent graphs (research, creative, generation, reviewer, onboarding)
apps/web             → Next.js frontend
packages/schemas     → Pydantic + Zod schemas shared/generated from one OpenAPI source of truth
```

### 1.2 Data model (core entities)

This is the backbone — get this right before any agent code, exactly like your own example issue argued.

- **Organization** — a workspace/account. Has many Users and many Brands (an agency manages multiple client brands; an SMB has one).
- **User** — belongs to an Organization, has a role (`owner`, `admin`, `editor`, `viewer`).
- **Brand** — name, industry, colors, logo_url, tone/voice descriptors, target_audience, product_catalog (JSONB), `brand_report` (JSONB, output of onboarding), `report_embedding` (pgvector, for RAG retrieval by agents).
- **SocialAccount** — brand_id, platform, oauth tokens (encrypted at rest), scopes, connection status.
- **ContentCalendarEvent** — brand_id, title, description, target_platforms[], desired_format (`text|image|video|carousel|audio`), target_datetime, status (`scheduled|pipeline_running|ready_for_review|approved|published|failed`).
- **Post** — calendar_event_id (nullable — posts can be ad hoc), brand_id, platform, body_text, media[], status, current_pipeline_stage, version history.
- **AgentRun** — post_id, agent_type (`research|creative|generation|reviewer|onboarding`), input, output, model, tokens, cost, latency, created_at. This table is your debugging and cost-tracking backbone — build it in Phase 0, not as an afterthought.
- **ReviewFeedback** — post_id, source (`ai_reviewer|human`), score/verdict, comments, decision (`approve|reject|edit_requested|reschedule`).
- **EngagementSnapshot** — post_id, platform, likes, comments, shares, impressions, fetched_at (time series, one row per poll).
- **Report** — brand_id, period, summary (AI-generated), metrics_json.

Everything an agent needs to personalize output — brand voice, audience, past performance — comes from **read-only access to Brand + past Post + EngagementSnapshot**, never from ad hoc prompt stuffing. That's the difference between "feed the brand details again and again" (today's manual pain) and a system that actually remembers.

### 1.3 Agent pipeline (LangGraph)

One `Post` moves through a LangGraph state machine. Model it as a graph with an explicit **human-in-the-loop interrupt**, not five separate scripts:

```
[Onboarding Agent]  (one-time per brand, not per post)
  web scraper → questionnaire answers → synthesize Brand Report → store + embed

[Per-post pipeline]  (triggered by calendar event or ad hoc request)
  1. Research Engine     — platform + industry trend research, reads Brand context
  2. Creative Engine      — decides format + angle + hook + CTA, platform-appropriate tone
  3. Generation Engine     — writes copy; calls image/video model as needed
  4. Reviewer Engine (AI)  — brand-alignment + compliance + platform-fit score + suggestions
  5. ⏸ INTERRUPT — Human Review — approve / edit / reject / reschedule
  6. Scheduler             — picks publish time (from Research Engine timing signal) if approved
  7. Publisher              — platform API call
  8. Analytics Collector    — scheduled polling job, writes EngagementSnapshot
```

Why LangGraph specifically: steps 1–4 are a normal DAG, but step 5 is a **durable interrupt** — the graph has to pause for hours or days waiting on a human, then resume from exactly that point. That's a first-class LangGraph feature (checkpointing), not something you want to hand-roll with cron jobs and status flags.

Each agent is a separate, independently testable module in `packages/agents/`, with the Brand read-access layer as a shared dependency — this is what "Generation Engine has read access to the brand database" becomes concretely.

### 1.4 Provider abstraction layer — build this before you wire in the first 3rd party

This is the change that matters most given the scale you're describing. You're not going to call Tavily. You're going to call *search*, and Tavily happens to be today's implementation. Same for the LLM, image gen, video gen, and every social platform API. If agent code imports the Tavily SDK directly, swapping it for Exa or Serper later means touching every place that called it — and re-testing all of it. A real startup foundation makes that a one-line env var change instead.

**Pattern — one interface + adapter + registry per capability:**

```
packages/integrations/
  search/
    base.py          → SearchProvider interface (search(query) -> list[Result])
    tavily.py         → TavilyProvider(SearchProvider)
    serper.py         → (added later, same interface, zero changes elsewhere)
  llm/
    base.py           → LLMProvider interface
    openai_provider.py, anthropic_provider.py, google_provider.py
  image_gen/
    base.py           → ImageProvider interface
    fal_provider.py, openai_image_provider.py
  video_gen/
    base.py           → VideoProvider interface
    kling_provider.py, runway_provider.py
  social/
    base.py           → SocialPublisher interface (publish(post) -> PublishResult)
    linkedin_provider.py, x_provider.py, meta_provider.py
  registry.py          → factory: reads an env var, returns the right adapter
```

**Rules that make this actually hold:**
- Agent and business logic code only ever imports the interface (e.g. `SearchProvider`), **never** a vendor SDK directly. The adapter is the only file allowed to `import tavily`.
- Provider selection is config-driven: `SEARCH_PROVIDER=tavily`, `IMAGE_PROVIDER=fal`, `VIDEO_PROVIDER=kling` in `.env`. Changing providers is changing one line, not shipping a PR that touches agents.
- Every adapter call gets logged the same way `AgentRun` already logs agent calls — add an `IntegrationCall` table (provider, capability, latency, cost, success/failure, org_id). This is what tells you "Tavily failed 4% of calls last week" instead of finding out from a support ticket.
- This is also what makes fallback chains possible later (try Tavily, fall back to Serper on timeout) without touching any calling code — the registry handles it, not the agent.
- If agencies ever want to bring their own API keys per brand (common ask at scale), this is also the layer that makes that possible: an `integrations` table at the Brand/Organization level storing which provider is active per capability + a reference to a stored secret, not the interface changing.

**Secrets, pragmatically:** `.env` locally + GitHub Actions encrypted secrets in CI is fine for now. Don't let "we need a real secrets manager" block early progress — but do put "migrate to a proper secrets manager (Doppler / AWS or GCP Secrets Manager)" on the M7 hardening pass explicitly, so it doesn't get forgotten once you're handling real customer OAuth tokens.

### 1.5 A note on monolith vs microservices

Given the scope you've described (36 issues, small team, long-term product), start as a **modular monolith**: one FastAPI service with clean router/domain boundaries (`/brands`, `/calendar`, `/posts`, `/agents`, `/publishing`, `/analytics`), one Postgres database, agents as an internal package. Split into real microservices later, only where you actually hit a scaling wall (the publishing/webhook layer and the analytics polling jobs are the most likely first candidates — they're natural background-worker boundaries).

Splitting into microservices on day one, before you have load data, is the single most common way "very very big" projects stall in infrastructure instead of shipping product. Your instinct to be bulletproof about process (CI, reviews, tests) is the right one — apply that rigor to the monolith's internal boundaries instead of to premature service splits.

### 1.6 Tech stack (confirming what you already have in mind)

- **Backend:** Python 3.11, FastAPI, SQLAlchemy + Alembic, Pydantic v2
- **Agents:** LangGraph, `LLMProvider` adapter with **OpenRouter as the primary/base router** (one API, model-agnostic — lets you switch between Claude/GPT/Gemini/open models per agent without new SDKs) and a **direct OpenAI adapter** as a secondary path for anything OpenRouter doesn't cover well (e.g. specific OpenAI-only features). Both sit behind the same `LLMProvider` interface from §1.4 — agents never know which one is actually serving the call.
- **DB:** PostgreSQL (Supabase) + pgvector for brand-report embeddings
- **Queue/jobs:** Redis + a job runner (Celery, or BullMQ if the worker layer moves to Node/TS — pick one and don't mix, decide in Issue 5)
- **Storage:** Supabase Storage / S3-compatible for logos, generated media
- **Frontend:** Next.js, TypeScript
- **Infra:** Docker Compose for local dev now, Terraform later when you have a real environment to provision

---

## 2. GitHub process setup

This is the "fool-proof system" layer — the part that lets 5+ people touch one repo without chaos.

### 2.1 Branch strategy

```
main   ← protected, production. Only PRs from dev, 1–2 approvals + green CI, no direct pushes, no force-push.
dev    ← protected, integration branch. Only PRs from feature/*, 1 approval + green CI.
feature/issue-N-slug  ← one branch per issue, always branches off dev.
```

### 2.2 Branch protection rules (set in repo Settings → Branches)

**On `main`:**
- Require a pull request before merging
- Require 2 approvals (drop to 1 while the team is small, raise once you're 4+ contributors)
- Require status checks to pass (backend-ci, frontend-ci)
- Require branches to be up to date before merging
- Require conversation resolution before merging
- Block force pushes, block deletions

**On `dev`:** same, but 1 approval.

### 2.3 PR template

`.github/PULL_REQUEST_TEMPLATE.md`:

```markdown
## Linked issue
Closes #

## Why
<!-- What problem does this solve? Link back to the issue's "Why" section. -->

## What changed
<!-- Bullet list of concrete changes -->

## How I tested this
<!-- Commands run, scenarios covered -->

## Screenshots / recording
<!-- Required for any frontend or API-response change -->

## Checklist
- [ ] **Tests written for this change and passing locally** — a PR with no new/updated test coverage for new logic will not be approved, no exceptions
- [ ] Migration included if the schema changed (`alembic revision --autogenerate`)
- [ ] No secrets, API keys, or `.env` values committed
- [ ] Docs/README updated if behavior or setup changed
- [ ] I branched from `dev` and am targeting `dev` (not `main`)
```

**The rule, stated plainly:** every PR must include the tests for what it built. CI enforces this two ways, not just a checkbox someone can tick without meaning it — see §2.7's coverage gate below. A PR that fails CI, or has no tests for new logic, does not get approved, no matter how confident anyone is that "it works." The test passing in CI *is* the proof it works — that's the whole point of automating this instead of trusting memory.

### 2.4 Issue template

`.github/ISSUE_TEMPLATE/feature.md` — this is exactly the shape of your own example, standardized:

```markdown
---
name: Feature
about: A tracked unit of work for Raindeer Social
labels: type:feature
---

## Why
<!-- Why this exists, what breaks or stays manual without it -->

## What needs to be built

## Files to create/modify

## Tests required
<!-- Every issue must name its own test cases before work starts, not after. What behavior does "done" actually mean, and how will CI prove it? -->

## How this affects overall development
<!-- What depends on this, what breaks if it's wrong -->

## How to test locally
```bash
# commands
```

## Acceptance Criteria
- [ ] Tests written covering the behavior above and passing in CI
- [ ]

## Branch
`feature/issue-N-slug`

## Depends on
Closes #
```

Duplicate as `bug.md` and `chore.md` with lighter sections.

### 2.5 Labels

`type:feature | type:bug | type:chore` · `area:backend | area:frontend | area:agents | area:integrations | area:infra | area:docs` · `priority:P0 | P1 | P2 | P3` · `size:S | M | L`

### 2.6 Milestones (= phases below)

`M0 Foundations` · `M1 Core Backend` · `M2 Onboarding & Brand Intelligence` · `M3 Agent Pipeline` · `M4 Calendar & Scheduling` · `M5 Publishing` · `M6 Analytics` · `M7 Frontend & Hardening`

### 2.7 CI workflows — tests are a hard gate, not advisory

Two things make testing non-negotiable instead of a polite request: branch protection requires the CI status check to be green before merge is even *possible* (§2.2 — GitHub disables the merge button, it's not a social norm), and CI itself fails the build if coverage drops, so a PR that adds code with no tests fails automatically even if someone forgets to check the box.

`.github/workflows/backend-ci.yml`:
```yaml
name: backend-ci
on:
  pull_request:
    branches: [dev, main]
    paths: ["apps/api/**", "packages/agents/**", "packages/integrations/**", "migrations/**"]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: raindeer_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready --health-interval 10s --health-timeout 5s --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r apps/api/requirements.txt
      - run: alembic upgrade head
        env: { DATABASE_URL: postgresql://postgres:postgres@localhost:5432/raindeer_test }
      # --cov-fail-under is the actual enforcement: build goes red if coverage on changed code drops below the bar.
      # Start at 70 in M0 while the test culture is forming, raise to 80+ once M1 lands.
      - run: pytest apps/api/tests -v --cov=apps/api --cov=packages --cov-report=term-missing --cov-fail-under=70
        env: { DATABASE_URL: postgresql://postgres:postgres@localhost:5432/raindeer_test }
```

`.github/workflows/frontend-ci.yml`:
```yaml
name: frontend-ci
on:
  pull_request:
    branches: [dev, main]
    paths: ["apps/web/**"]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 18 }
      - run: npm ci --prefix apps/web
      - run: npm run lint --prefix apps/web
      - run: npm run test --prefix apps/web
      - run: npm run build --prefix apps/web
```

---

## 3. The 36-issue roadmap

Grouped into 8 milestones. Phase 0 (issues 1–6) is fully specced below in your template format, since it's the actual starting point — everything else has a scope summary + dependency so you can see the shape of the whole build, and I'll spec each phase in full detail as you finish the one before it (matches the "gradually, calculated" approach you described — no value in hyper-detailing Phase 6 before Phase 0 has even merged).

### M0 — Foundations (issues 1–6)

**#1 — Local dev environment**
*Why:* every later issue assumes a working local stack; this is the thing that fails silently otherwise.
*Build:* Python 3.11 + Node 18 + PostgreSQL 16 (pgvector extension) + Docker Desktop + Redis, repo clone, venv, `.env.example`.
*Test:* `uvicorn apps.api.main:app --reload` boots with no import errors; `psql raindeer -c "SELECT 1;"` succeeds.
*Branch:* `feature/issue-1-dev-environment` · *Depends on:* nothing.

**#2 — CI pipeline + branch protection**
*Why:* no PR should be mergeable on a hunch; automate the safety net before anyone else's code lands.
*Build:* `.github/workflows/backend-ci.yml`, `frontend-ci.yml` (content above), enable branch protection on `main`/`dev` as in §2.2.
*Test:* open a throwaway PR, confirm the checks tab runs and blocks merge on failure.
*Branch:* `feature/issue-2-ci-setup` · *Depends on:* Closes #1.

**#3 — Repo process scaffolding**
*Why:* consistent issues and PRs are what let five people move in parallel without a standup every hour.
*Build:* PR template, issue templates (feature/bug/chore), labels, milestones, GitHub Projects board (Backlog → Ready → In Progress → In Review → Done) with auto-move-on-PR-open/merge automation.
*Test:* create one issue and one PR from the templates, confirm auto-linking and board movement.
*Branch:* `feature/issue-3-process-scaffolding` · *Depends on:* Closes #1.

**#4 — Core database schema v1**
*Why:* Organization/User/Brand is the foundation every other table (and every agent's read access) sits on.
*Build:* `apps/api/models/{organization,user,brand}.py`, `apps/api/config/database.py`, first Alembic migration `migrations/versions/001_core_schema.py`. Include `brand_report JSONB` and a `report_embedding vector(1536)` column now even though nothing populates it yet — cheaper to add the column early than migrate a populated table later.
*Test:* `alembic upgrade head` then `alembic downgrade -1` then `alembic upgrade head` clean; `psql -c "\d brands"` shows the pgvector column.
*Branch:* `feature/issue-4-core-schema` · *Depends on:* Closes #1.

**#5 — Docker Compose local stack + job runner decision**
*Why:* Postgres+Redis+API+worker as one `docker compose up` removes "works on my machine" for the whole team, and locks in the async job runner before agent code depends on it.
*Build:* `docker-compose.yml` (postgres w/ pgvector, redis, api, web), `apps/api/worker.py` skeleton wired to the chosen job runner (Celery recommended given the Python-first backend — keeps one language across API and workers).
*Test:* `docker compose up` brings up all services; a trivial test task enqueues and completes.
*Branch:* `feature/issue-5-docker-worker` · *Depends on:* Closes #4.

**#6 — Observability baseline: logging + AgentRun table + error tracking**
*Why:* once agents start calling LLMs, you need cost/latency/failure visibility from day one, not bolted on after debugging a mystery.
*Build:* structured JSON logging middleware, `agent_runs` table + model (agent_type, input, output, tokens, cost, latency, created_at), Sentry SDK wired for the API.
*Test:* trigger a dummy endpoint error, confirm it shows in Sentry; insert+query a mock `AgentRun` row.
*Branch:* `feature/issue-6-observability` · *Depends on:* Closes #4.

---

### M1 — Core Backend + Integration Foundation (issues 7–12)
**#7 is now the provider abstraction layer** (§1.4): `packages/integrations/` scaffolding, the `SearchProvider` interface + Tavily adapter as the first real implementation, the registry/factory pattern, and the `IntegrationCall` observability table. Everything after this — Onboarding's scraper, Research Engine, image/video gen, social publishing — builds on top of this instead of calling vendor SDKs directly. Then: Auth + org/role model, Brand CRUD API, SocialAccount OAuth connection storage (encrypted tokens, itself an adapter under `social/`), media storage integration (Supabase Storage), and shared API conventions (error format, validation, rate limiting). *Depends on: M0.*

### M2 — Onboarding & Brand Intelligence (issues 13–17)
Onboarding questionnaire flow, the web research step (now: Tavily via the `SearchProvider` interface, not a hand-rolled scraper), the Onboarding Agent (LangGraph) that synthesizes the Brand Report from scraped/researched data + answers, embedding + pgvector storage for RAG retrieval by later agents, and the brand PDF export. *Depends on: M1.*

### M3 — Agent Pipeline Core (issues 18–25)
LangGraph orchestration + checkpoint persistence, Research Engine (built on `SearchProvider`), Creative Engine, Generation Engine (built on `LLMProvider`), image-generation integration (`ImageProvider`), video/carousel-generation integration (`VideoProvider`), Reviewer Engine, and the Human Review interrupt + UI actions (approve/edit/reject/reschedule). *Depends on: M2 (agents need Brand Report), M1 (provider layer).*

### M4 — Calendar & Scheduling (issues 26–29)
ContentCalendarEvent model + CRUD API, calendar UI, auto-scheduling (optimal-time suggestion fed by Research Engine signals), and the trigger that kicks off the M3 pipeline ahead of an event's target date so it's sitting ready for one-button approval. *Depends on: M3.*

### M5 — Publishing (issues 30–32)
Platform publishing adapters under `social/` (start with 1–2 platforms, e.g. LinkedIn + X, add Instagram/YouTube after — each is just a new adapter against the existing `SocialPublisher` interface), a publish queue with retry/failure handling, and status notifications (email/Slack) on failures or pending reviews. *Depends on: M1 (SocialAccount + provider layer), M4.*

### M6 — Analytics (issues 33–35)
Engagement-metrics polling jobs per platform, analytics storage + dashboard API, and AI-generated weekly report per brand. *Depends on: M5 (needs published posts to measure).*

### M7 — Frontend & Hardening (issues 36–37)
Core Next.js dashboard shell (auth, brand switcher, nav across all the above), and a full-system hardening pass: secrets manager migration (§1.4), RBAC checks across every endpoint, rate-limit verification, and a load-test baseline. *Depends on: everything — this is the finishing pass, not a starting point.*

*(Frontend screens for calendar, review queue, onboarding, and analytics get built alongside their respective backend milestones in practice — #35/36 is the shell + final integration pass, not "all frontend work happens last." I split it out here to keep the roadmap readable; when we spec M1–M2 in detail I'll fold the matching frontend issues in where they belong.)*

---

## 4. Suggested order of operations from here

1. Create the repo structure (`apps/`, `packages/`, `migrations/`, `.github/`) and push issues 1–6 as GitHub issues using the template above, assigned to `M0 Foundations`.
2. Set branch protection (§2.2) — do this *before* the first PR lands, or it's easy to skip under time pressure.
3. Work #1 → #6 in order; #2 and #3 can run in parallel with #1 once someone's environment is up.
4. Once M0 merges to `dev`, tell me and I'll spec M1 (issues 7–11) in the same full Why/What/Files/Test/Acceptance detail.

If you want these 36 issues actually created on GitHub rather than pasted by hand, here's a `gh` CLI script — run it locally once you're authenticated (`gh auth login`) against the org:

```bash
#!/usr/bin/env bash
# create-issues.sh — run from repo root, gh CLI must be authenticated
gh issue create --title "Local dev environment setup" --body-file issues/01.md --milestone "M0 Foundations" --label "type:feature,area:infra"
gh issue create --title "CI pipeline + branch protection" --body-file issues/02.md --milestone "M0 Foundations" --label "type:feature,area:infra"
# ...repeat per issue, body files pulled from this doc
```