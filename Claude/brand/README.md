# Brand knowledge — Raindeer Social

This folder is Claude's durable notes on what "brand data" means in this
codebase: where it lives today, what's real vs. still shallow, and what the
long-term shape should be. Read this before touching anything Brand-related.
Update it whenever the model changes — this is meant to survive context
resets and new sessions, not just this one conversation.

## What Raindeer Social is

A 5-agent AI marketing pipeline product. Five agents, each with a name and a
job:

- **Aarav** — onboarding. Interviews a new brand, researches it, and builds
  its brand profile. Everything below is about making Aarav's output real.
- **Ved** — research. Runs ahead of each post to ground it in current,
  specific brand/competitor/audience signal.
- **Keshav** — creative. Turns Ved's research into a per-platform creative
  brief (format/angle/hook/cta/tone).
- **Kavi** — generation. Turns Keshav's brief into publish-ready copy (and
  triggers image/video generation).
- **Neer** — reviewer. Scores a draft against brand voice/compliance/platform
  fit before a human sees it.

## Where brand data actually lives today (as of 2026-09-20, main @ ae23fbe)

`apps/api/models/brand.py` — the `Brand` row is the source of truth:

- Flat fields: `name`, `industry`, `logo_url`, `target_audience`, `colors`
  (JSONB list), `tone_descriptors` (JSONB list), `product_catalog` (JSONB).
- `brand_report` (JSONB) — the synthesized "brand identity" output of
  onboarding. This is the closest thing to the "one brand image" the user
  wants — it already exists, it's just thin and not fed by real research.
- `report_embedding` (pgvector) + `apps/api/models/brand_report_chunk.py` +
  `apps/api/services/brand_retrieval.py` — RAG retrieval over brand_report,
  already wired into Ved (`research_engine.py`) and Neer (`reviewer_engine.py`).

`apps/api/models/onboarding_response.py` — structured questionnaire answers
feeding brand_report synthesis: `voice`, `audience`, `product_catalog`,
`competitors`, `goals`, plus deeper-questionnaire fields added in issue #144
(`mission`, `content_dos_donts`, `posting_cadence`).

`apps/api/models/onboarding_voice_answer.py` / `onboarding_asset.py` — real
voice-recording transcripts and uploaded assets (issue #144), each tied to a
`brand_id` and a `StorageProvider` URL.

`packages/agents/onboarding/graph.py` + `prompts.py` — one LLM call
(`_synthesize_node`) turns `OnboardingResponse` + `OnboardingResearch` into
`brand_report`, written onto `Brand.brand_report`.

`packages/agents/onboarding/research_step.py` — as of 2026-09-20 this was
Tavily web *search* only (snippets about the brand), with no real scrape of
the brand's own site. **That gap is closed as of issue #152/Phase A** (see
[[../aarav-agent/PLAN.md]]'s progress log): `run_website_scrape` now
actually fetches the brand's own site via `packages/integrations/webscrape/`
(free `httpx`+BeautifulSoup+Pillow, no third-party API), distills it through
an LLM summarization pass (never stores the raw scrape), extracts a
logo/color-palette suggestion, and (as of #167) surfaces social profile
links found on the page too — all onto `OnboardingResearch`. `search_brand_overview`
in the same file is still the older Tavily-search path, kept separately for
the live "public signals" log the interview shows before the real scrape
runs.

`apps/api/models/onboarding_dynamic_answer.py` — Aarav's own adaptive
follow-up questions (issue #153/Phase B), generated one page at a time by an
LLM call reading everything answered so far (fixed fields + scrape summary +
prior dynamic pages). As of #167 this is where almost all of onboarding's
real interview content lives — the old fixed questionnaire is down to a
single page (confirm website + colors); `OnboardingResponse`'s structured
fields are optional enrichment only, not a completion gate.

## Which agents actually read brand data (audited 2026-09-20)

- **Ved** (`research_engine.py`): reads `brand.industry`/`brand.name` +
  `brand_retrieval` (RAG over `brand_report`). Connected.
- **Keshav** (`creative_engine.py`): reads `brand.name`/`brand.industry` +
  whatever `research_brief["brand_context"]` Ved handed down. Connected,
  indirectly for anything beyond name/industry.
- **Kavi** (`generation_engine.py`): reads **nothing** off `Brand` directly —
  only ever sees Keshav's per-platform brief. This is the weakest link; see
  the plan for closing it.
- **Neer** (`reviewer_engine.py`): reads `brand.tone_descriptors`,
  `brand.target_audience`, `brand.industry`, `brand.name` + `brand_retrieval`.
  Most fully connected of the four.

## Design constraint to preserve

Every external capability in this repo goes through ONE interface (in
`packages/integrations/<capability>/base.py`) plus ONE adapter file per
provider, resolved via `packages/integrations/registry.py` keyed off an env
var. Any new capability this initiative adds (web scraping, LLM-driven
question generation) should follow that same shape — see
`packages/integrations/storage/supabase_provider.py` or
`packages/integrations/speech/whisper_provider.py` for the reference shape.
Default to free/open-source/self-hosted where one exists (this repo already
runs `openrouter/free` for all LLM calls and `faster-whisper` locally for
speech — match that posture for anything new unless the user says otherwise).
