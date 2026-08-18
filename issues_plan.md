# Raindeer Social — Project Status & Reference

**Purpose of this file:** a living snapshot of what's actually true about
this repo right now — policy, issue status, why key decisions were made,
and every real incident hit so far with its fix. Read this first if you're
picking work back up after a gap, or if something's broken and you're not
sure whether it's new or a known issue recurring.

This file does **not** duplicate issue bodies (see
[`ALL_ISSUES.md`](./ALL_ISSUES.md) for the full text of every issue) or the
contributor workflow (see [`CONTRIBUTING.md`](./CONTRIBUTING.md)) — it's the
"what's true, what changed, what broke" layer that sits above both.

Last verified against live GitHub state: 2026-08-18.

---

## 1. Current policy snapshot

- **Repo:** `raindeer-social-org/product-raindeer-social`
- **Branch model:** single `main` branch only. No `dev`/integration branch
  — see [Decision log](#3-decision-log) for why.
- **Contribution model:** fork-only. Only repo admins hold push access to
  `product-raindeer-social` itself; everyone else forks. Admins follow the
  fork-first flow by convention, not technical enforcement.
- **Branch protection on `main`:** 1 required approval (from someone other
  than the PR author — GitHub blocks self-approval by default), required
  status checks `test` (backend-ci) + `sync` (issue-pr-sync), branch must
  be up to date, all conversations resolved, no force-push/direct-push,
  applies to admins too. Full detail: `docs/infra/branch-protection.md`.
- **Access:** `CODERNSINGH` is the only account with real write access at
  the repo level. Five other collaborators (`mitul-bhatia`,
  `Pranav-Singh-Devloper`, `Rana-NST-RU`, `Shreyashgol`, `raindeer-sociaI`)
  are **organization owners**, which grants automatic admin on every repo
  regardless of repo-level settings — they're trusted to follow the
  fork-only convention rather than being technically blocked. `Jivit87`
  still has push access via the `tech-raindeer-social` team, which
  overrides their repo-level read-only setting — unresolved, needs
  `admin:org` scope or a manual fix in Org Settings → Teams.
- **Verify any of this is still accurate:**
  ```bash
  gh api repos/raindeer-social-org/product-raindeer-social/branches/main/protection
  gh api repos/raindeer-social-org/product-raindeer-social/collaborators --jq '.[] | "\(.login): admin=\(.permissions.admin)"'
  ```
  If live output disagrees with this file, the API is correct — update
  this file to match, not the other way around.

---

## 2. Issue status

37 roadmap issues (M0–M7) plus ad-hoc issues filed for gaps found along the
way. Full body/dependencies for every issue: `ALL_ISSUES.md`. Live status:

```bash
gh issue list -R raindeer-social-org/product-raindeer-social --state all --json number,title,state,milestone
```

| # | Title | Milestone | Status |
|---|-------|-----------|--------|
| 1 | Local dev environment setup | M0 | Open |
| 2 | CI pipeline + branch protection | M0 | **Closed** (PR #38) |
| 3 | Repo process scaffolding | M0 | Open |
| 4 | Core database schema v1 | M0 | Open |
| 5 | Docker Compose local stack + job runner | M0 | Open |
| 6 | Observability baseline | M0 | Open |
| 7 | Provider abstraction layer (search + LLM, Tavily/OpenRouter/OpenAI, IntegrationCall) | M1 | Open |
| 8 | Auth + org/role model | M1 | Open |
| 9 | Brand CRUD API | M1 | Open |
| 10 | SocialAccount OAuth connection storage | M1 | Open |
| 11 | Media storage integration (Supabase Storage) | M1 | Open |
| 12 | Shared API conventions (errors, validation, rate limiting) | M1 | Open |
| 13 | Onboarding questionnaire flow | M2 | Open |
| 14 | Web research step (SearchProvider) | M2 | Open |
| 15 | Onboarding Agent (LangGraph) | M2 | Open |
| 16 | Brand Report embedding + pgvector storage | M2 | Open |
| 17 | Brand Report PDF export | M2 | Open |
| 18 | LangGraph orchestration + checkpoint persistence | M3 | Open |
| 19 | Research Engine | M3 | Open |
| 20 | Creative Engine | M3 | Open |
| 21 | Generation Engine | M3 | Open |
| 22 | Image-generation integration (ImageProvider) | M3 | Open |
| 23 | Video/carousel-generation integration (VideoProvider) | M3 | Open |
| 24 | Reviewer Engine (AI) | M3 | Open |
| 25 | Human Review interrupt + UI actions | M3 | Open |
| 26 | ContentCalendarEvent model + CRUD API | M4 | Open |
| 27 | Calendar UI | M4 | Open |
| 28 | Auto-scheduling (optimal-time suggestion) | M4 | Open |
| 29 | Pipeline trigger | M4 | Open |
| 30 | Platform publishing adapters (LinkedIn + X) | M5 | Open |
| 31 | Publish queue with retry/failure handling | M5 | Open |
| 32 | Status notifications (email/Slack) | M5 | Open |
| 33 | Engagement-metrics polling jobs | M6 | Open |
| 34 | Analytics storage + dashboard API | M6 | Open |
| 35 | AI-generated weekly report | M6 | Open |
| 36 | Core Next.js dashboard shell | M7 | Open |
| 37 | Final hardening pass | M7 | Open |
| 39 | Fix README clone URL | ad-hoc | **Closed** (PR #40) |
| 41 | Document fork-only contribution policy | ad-hoc | **Closed** (PR #42) |
| 43 | issue-pr-sync doesn't re-run on new commits | ad-hoc bug | **Closed** (PR #44) |
| 45 | Rewrite issues_plan.md as a live reference | ad-hoc | This issue |

(Issue #38, #40, #42, #44 in the "PR" column above are PR numbers, not
issue numbers — GitHub numbers issues and PRs from one shared sequence in
a repo, so PR numbers land in the gaps between issue numbers.)

---

## 3. Decision log

**Single `main` branch, no `dev`.** Originally set up with a `dev`
integration branch (2 approvals on `main`, 1 on `dev`), matching a
larger-team pattern. Reversed almost immediately — with a small team,
an integration branch is process overhead with no payoff yet. Revisit only
if the team grows enough that batching work behind an integration branch
becomes worth the extra step.

**Fork-only contribution, even for admins.** Decided once the repo already
had 6 collaborators with push access (5 of them org owners). Rather than
relying on "please branch responsibly," access itself was locked down:
everyone but the repo owner is read-only at the repo level, so a fork is
the only way in. Admins keep push rights (needed to merge) but follow the
same fork flow by convention.

**1 required approval, not 2.** Repo has one active human collaborator
(`CODERNSINGH`) most of the time. 2 approvals would mean nobody could ever
merge solo-authored work. GitHub already blocks self-approval by default,
so "1 approval from someone other than the author" doesn't need to be
self-policed — it's structurally guaranteed.

**`docs/infra/branch-protection.md` exists separately from this file.**
That file is the operational record of the exact GitHub API settings
applied (so it can be diffed against live `gh api` output). This file is
the narrative — why those settings, and what's happened since.

---

## 4. Incident log

Real problems hit while operating this repo, root cause, and the fix — so
a repeat doesn't get mistaken for something new.

### `issue-pr-sync` required check got permanently stuck (2026-08-18)

**Symptom:** PRs #38, #40, #42 all showed the `sync` required check as
"Expected — Waiting for status to be reported," indefinitely, blocking
merge despite `sync` having passed earlier in each PR's life.

**Root cause:** `.github/workflows/issue-pr-sync.yml`'s `on.pull_request.types`
was `[opened, reopened, edited, closed]` — missing `synchronize`, the event
GitHub fires when a new commit lands on an already-open PR. Any PR that got
a follow-up commit after opening never got a fresh `sync` report against
the new HEAD commit, and a required check with no report for the current
commit blocks merge forever.

**Fix:** added `synchronize` to the trigger types. Merged in PR #44
(closes issue #43). Verified live: pushed a new commit to #44's own branch
mid-review and watched `sync` correctly re-fire.

**Recovery playbook for any future occurrence of this symptom** (same
symptom, not necessarily the same cause) is documented in
`CONTRIBUTING.md` §7, under "If a required check ever shows 'Expected —
waiting for status to be reported.'" Short version: push a new commit
(even an empty one), edit the PR title/description, or use GitHub's
"Update branch" button — any of those fires an event the required checks
listen for. If it keeps recurring rather than being a one-off, check the
`types` list on the relevant workflow before assuming it's a fluke.

### README referenced the wrong repo name (2026-08-18)

**Symptom:** `README.md`'s clone command pointed at
`raindeer-social-org/raindeer-social.git` — the actual repo is
`product-raindeer-social`. A fresh contributor copy-pasting it hit a 404.

**Root cause:** repo was renamed/re-scaffolded after the README was first
written; the clone URL and a "CI & branch protection" section describing
the old `dev`/`main` model were never updated to match.

**Fix:** corrected in PR #40 (closes issue #39).

---

## 5. Where to look for what

| Question | Answer lives in |
|---|---|
| What does issue #N actually say? | `ALL_ISSUES.md` |
| How do I open a PR, from clone to merge? | `CONTRIBUTING.md` §0 |
| What are the exact branch protection settings? | `docs/infra/branch-protection.md` |
| Why does the system look the way it does (agents, data model, providers)? | `raindeer-social-blueprint.md` |
| Has this specific failure happened before? | §4 of this file |
| What's currently open vs. closed? | §2 of this file, or `gh issue list --state all` |
