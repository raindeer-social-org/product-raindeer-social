# Aarav — production rebuild plan & progress tracker

**Read this file first if you're picking this up cold — in a new session, after
a compaction, or after a token-limit reset.** It is the live source of truth
for this initiative. Update the Progress Log at the bottom every time you land
or change something; don't let it drift out of date.

## The ask (verbatim intent, 2026-09-20)

User wants Aarav ("the onboarding agent") built to production quality by a
"senior AI agent tech lead," free to use any tool/third-party API (user adds
real keys to `.env` themselves) but defaulting to free/open-source (explicitly:
`openrouter/free` for the LLM). Concretely, in the user's own words condensed:

1. **One unified "brand image"** — everything ever learned about a brand
   lives in one place, is editable from a sidebar, and every agent
   (Ved/Keshav/Kavi/Neer) actually reads it.
2. **Onboarding flow, client-side:**
   - Page 1: auth (name, etc).
   - Page 2: basic brand facts — industry/field, size, role — mostly
     selection-based, **max 5 questions per page**.
   - **From there on, Aarav (the LLM) generates the next page's questions
     itself, based on everything answered so far** — not a fixed form.
     Page 5's questions must be informed by page 4's answers, etc. A visibly
     different UI treatment (they said "some 3D effect") should mark the
     moment it switches from static to AI-driven.
   - Real website/social scraping — actual page content, logo, photos — not
     search-engine snippets about the brand.
   - A photo/asset library beyond the fixed upload slots.
   - **Scraped content must be summarized/distilled before storage, never
     stored raw** — "don't care how long it takes, should be the best."
   - Voice input available as an answer method broadly (already real per
     issue #144 — faster-whisper — but currently only wired to one question).
   - Capstone: an **editable** brand-identity document shown to the user
     before finishing — not just generated and hidden.
   - Then: connect social accounts (already real — `SocialConnectionsPanel`,
     issue #143 — just needs to come after the new capstone step).
3. **Backend:** the brand-image data must be secured (org-scoped access,
   already the pattern everywhere else in this repo via `require_role`/
   `CurrentUser.org_id` — verify new endpoints follow it, don't invent a new
   pattern) and genuinely connected to all 4 downstream agents.
4. Current onboarding UI "looks done but isn't" — user was explicit: "nothing
   even a single point missing." Treat every item above as a hard requirement,
   not a nice-to-have.

Full grounding/audit of what already exists vs. what's fake: see
[[../brand/README.md]]. Don't re-derive that from scratch — it's current as
of main @ `ae23fbe` (2026-09-20).

## Phased build plan

Phases A and B are independent of each other and can run in parallel. C
depends on both A and B landing first (the capstone doc needs the scrape
summary and the dynamic Q&A history to synthesize from; Kavi's brand-wiring
part of C is independent and can land anytime). D is polish, do last.

### Phase A — real scraping + summarization engine
**Status: not started.**

- New `packages/integrations/webscrape/` package (interface + one adapter,
  same shape as every other integration) — fetches the brand's own site
  (`httpx`), extracts: `<title>`/meta description, `og:image`/favicon (logo
  candidate), visible text (tags stripped, length-capped), and a small
  palette of dominant colors (from the extracted logo/hero image — Pillow is
  fine to add as a dependency for this).
- An LLM summarization pass over the raw scraped text — condensed, structured
  brand knowledge, not a raw dump. Store this (new column/table, your call on
  shape) rather than discarding after the LLM call.
- Wire it into the existing "Let's confirm your website" step
  (`apps/web/app/onboarding/interview/page.tsx`, currently backed by
  `streamOnboardingResearch` which is Tavily search only) so the live log
  shows real scrape progress and offers the extracted logo/colors as
  one-click-accept suggestions instead of 100% manual entry.

### Phase B — adaptive, LLM-driven multi-page questions
**Status: not started.** This is the core "Aarav is actually an agent, not a
form" piece — the biggest single gap.

- New endpoint, e.g. `POST /brands/{brand_id}/onboarding/next-questions`:
  given everything answered so far (structured fields + scrape summary if
  Phase A has landed, else questionnaire-only is fine — don't hard-block on
  Phase A), an LLM call (OpenRouter free model, same provider pattern as
  everywhere else) returns the next page's questions — **max 5**, each with
  a stable id + a type drawn from a small closed set the frontend already
  knows how to render (text / chips / single-select / voice) + a title/sub —
  or a `done: true` signal once Aarav judges it has enough to synthesize a
  good brand_report. Cap the number of AI-generated pages sanely (e.g. 4)
  even if the model doesn't say done — no infinite interview.
- Persist every generated question + its answer (new table, something like
  `OnboardingDynamicAnswer`: `brand_id`, `page_index`, `question` JSONB,
  `answer` JSONB, timestamps) — this is real, durable data, not ephemeral
  client state.
- Frontend: after the fixed first 2 pages (auth is its own page already;
  "basics" is page 2 of the existing `QUESTIONS` array — confirm exactly
  where that boundary is when you implement this), replace the rest of the
  static `QUESTIONS` walk with a loop that calls `next-questions`, renders
  whatever comes back through a small generic question-type renderer (reuse
  the existing per-type render blocks in `interview/page.tsx` rather than
  duplicating them), submits answers back, repeats until `done`.
- The "3D effect": one clearly-distinct transition animation (Framer Motion
  is already a reasonable, light dependency to add — a perspective/rotate-in
  card transition fits "we're in AI mode now" without needing a WebGL/Three.js
  dependency) that plays exactly once, the first time a dynamically-generated
  question appears.

### Phase C — editable capstone + full agent wiring
**Status: not started. Depends on A + B for the capstone; the Kavi-wiring
half is independent and can land anytime.**

- After the dynamic questions phase reports `done`, run onboarding synthesis
  (existing `packages/agents/onboarding/graph.py`, now with richer input:
  scrape summary + dynamic Q&A history in addition to the original
  `OnboardingResponse` fields — extend `build_synthesis_prompt` in
  `prompts.py` accordingly) and show the result as an **editable** brand
  identity screen (extend `apps/web/app/onboarding/brand-report-view.tsx`,
  which today is read-only and only used on the old disconnected
  `/onboarding` page — either make it edit-capable and wire it into the NEW
  `/onboarding/interview` flow's completion step before `stage === "connect"`,
  or build a purpose-built editable capstone component; your call, but it
  must be reachable from the real interview flow, not just the legacy page).
  Needs a `PATCH`-style endpoint to persist edits back onto `brand_report`.
- Wire **Kavi** (`packages/agents/pipeline/nodes/generation_engine.py`) to
  read `Brand` fields directly (tone_descriptors, target_audience, colors at
  minimum) the same way Neer/Keshav already do — right now it's the one
  agent with zero direct brand grounding, only ever seeing Keshav's brief.

### Phase D — polish
**Status: not started.**

- Voice input as an answer method on more/all question types, not just the
  one `"voice"`-typed question — reuse the issue #144 recording+transcribe
  plumbing, don't rebuild it.
- Asset library page: uploads beyond the 4 fixed slots from issue #144
  (reuse `OnboardingAsset`, just don't cap it at 4 named slots).
- Security pass on every new endpoint from A/B/C: confirm org-scoping via
  `CurrentUser.org_id` and brand ownership checks match the existing pattern
  in `apps/api/routers/onboarding.py`/`review.py` — don't invent a new auth
  pattern for this feature.

## Working conventions for this initiative

- **Repo:** `raindeer-social-org/product-raindeer-social`, single `main`
  branch, 1 required approval, `backend-ci`/`test`, `frontend-ci`/`build`,
  `issue-pr-sync`/`sync` all required green.
- **Branches MUST be same-repo** (`origin`, never the `fork` remote) or
  `issue-pr-sync` 403s permanently — this has bitten every wave of work in
  this project. Branch name MUST be `feature/issue-<N>-<slug>` where `<N>` is
  a real GitHub *issue* number (not a PR number — this has also bitten this
  project once already).
- One GitHub issue + one branch/PR per phase (or sub-piece of a phase, if a
  phase is large enough to want splitting) — same pattern as every prior
  wave, see `Claude/` sibling notes / prior PRs #138-149 for the shape.
- Work in an isolated `git worktree` off `origin/main`, never by switching
  the primary working directory's branch — earlier sessions kept local
  uncommitted work there.
- When delegating implementation to a subagent, brief it with the exact
  relevant section of this plan plus [[../brand/README.md]] — don't make it
  re-derive the audit.

## Progress log

- **2026-09-20** — Plan written. Audited current state (see brand/README.md).
  No implementation started yet. About to open issues + dispatch Phase A and
  Phase B in parallel.
