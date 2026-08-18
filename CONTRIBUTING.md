# Contributing to Raindeer Social

This document is the single source of truth for how work moves through this
repository. If you're new to the project, read this before opening your
first PR — it answers the questions that otherwise get asked in every
review.

## 1. Branch strategy

```
main   ← protected, production. Only accepts PRs from dev.
dev    ← protected, integration branch. Only accepts PRs from feature/*.
feature/issue-N-slug  ← one branch per issue, always branched off dev.
```

- Never commit directly to `main` or `dev`.
- Always branch off `dev`, not `main`.
- One branch per issue. Name it `feature/issue-N-slug`, where `N` is the
  GitHub issue number and `slug` is a short, lowercase, hyphenated
  description of the work.

  ```
  feature/issue-4-core-schema
  feature/issue-12-onboarding-questionnaire
  feature/issue-29-linkedin-publishing-adapter
  ```

  Use `feature/` for all tracked work, including bugs and chores — the
  issue type is captured in the issue's label, not the branch prefix. This
  keeps the convention to one rule instead of three.

## 2. Opening a pull request

1. Push your `feature/issue-N-slug` branch and open a PR **targeting `dev`**
   (not `main` — `main` only ever receives PRs from `dev`).
2. Fill out the PR template completely. It's created automatically from
   [`.github/PULL_REQUEST_TEMPLATE.md`](./.github/PULL_REQUEST_TEMPLATE.md)
   — don't delete sections, and don't leave `Closes #` blank.
3. Link the issue with `Closes #N` so the issue auto-closes on merge and the
   PR shows up on the issue's timeline.
4. Include screenshots or a recording for any frontend or API-response
   change — reviewers shouldn't have to pull your branch to see what
   changed visually.
5. Keep PRs scoped to one issue. If you find unrelated cleanup along the
   way, file a separate chore issue instead of folding it in — it makes
   review and revert both easier.

Opening the PR triggers `.github/workflows/issue-pr-sync.yml` — see
[Automated issue-PR sync](#7-automated-issue-pr-sync) below for exactly
what it does.

## 3. Commit message style

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short summary>

[optional body — the "why", not a restatement of the diff]
```

- **type:** `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `ci`
- **scope:** the area touched — `api`, `web`, `agents`, `schemas`,
  `migrations`, `ci` — omit if the change is repo-wide
- **summary:** imperative mood, lowercase, no trailing period

```
feat(api): add Brand CRUD endpoints
fix(agents): handle empty scrape result in onboarding agent
chore(ci): pin postgres image to pg16
docs(readme): document local dev setup
```

Keep commits reasonably atomic — a commit should represent one logical
change, not "wip" or "fix review comments" squashed at the end. Feel free to
clean up history with an interactive rebase before opening the PR, but never
force-push over a branch someone else is also pushing to without checking
first.

## 4. Running tests locally

**Backend** (`apps/api`, `packages/agents`, `migrations`):

```bash
pip install -r apps/api/requirements.txt
alembic upgrade head
pytest apps/api/tests -v --cov
```

**Frontend** (`apps/web`):

```bash
npm ci --prefix apps/web
npm run lint --prefix apps/web
npm run test --prefix apps/web
npm run build --prefix apps/web
```

These are the exact commands `backend-ci` and `frontend-ci` run in CI
(see [`.github/workflows`](./.github/workflows)) — if they pass locally,
they should pass in CI. Run whichever suite matches the part of the repo
you touched; CI itself is path-scoped, so a backend-only PR won't trigger
the frontend job and vice versa.

## 5. Review and merge rules

Enforced by branch protection, not just convention:

| Branch | Approvals required | Other requirements |
|--------|--------------------|--------------------|
| `main` | 2 (1 while the team is small, raised at 4+ contributors) | Green CI, branch up to date, all conversations resolved, no force-push, no direct pushes |
| `dev`  | 1 | Same as above |

- A PR cannot merge with red CI, regardless of approvals. This includes the
  `issue-pr-sync` check — a PR from a wrongly-named branch cannot merge
  until the branch is renamed.
- A PR cannot merge with unresolved review conversations.
- If `dev` has moved since you branched, update your branch (merge or
  rebase `dev` into your branch) before merge — "up to date" is enforced,
  not optional.
- Don't approve your own PR, and don't merge on your own approval unless
  you're unblocking something urgent and have said so explicitly in the PR.

## 6. Issues

Use the issue templates (`.github/ISSUE_TEMPLATE/`) — `feature.md`,
`bug.md`, or `chore.md`. Every issue should specify:

- **Why** it exists
- **What** needs to be built or fixed
- **Files** likely to be touched
- **How to test** it locally
- **Acceptance criteria**
- The **branch name** the work will land on (`feature/issue-N-slug`)
- Any **dependency** on other issues (`Depends on: Closes #N`)

Label with `type:*`, `area:*`, `priority:*`, and `size:*` so the backlog
stays filterable as the issue count grows past what anyone can hold in
their head.

## 7. Automated issue-PR sync

`.github/workflows/issue-pr-sync.yml` runs on every PR event and does the
following automatically — no manual bookkeeping required:

- **Branch name enforcement.** The PR check fails immediately if the head
  branch doesn't match `feature/issue-N-slug`, with the issue number
  pointing at a real, open issue. This is what makes the rest of the
  automation possible — the issue number is parsed straight from the
  branch name.
- **On open/reopen:**
  - Injects `Closes #N` into the PR body automatically if you left the
    "Linked issue" section blank.
  - Posts a comment on issue `#N` linking back to the PR.
  - Assigns the PR author to the issue.
  - Swaps the issue's label from `status:needs-triage` to
    `status:in-progress`.
- **On merge:** comments on the issue confirming which PR resolved it and
  relabels it `status:done`. (The issue itself closes natively via GitHub's
  `Closes #N` handling — the workflow only handles the label/comment side.)
- **On close without merge:** comments on the issue and relabels it back to
  `status:needs-triage` so it reappears in the backlog instead of silently
  looking "in progress" forever.

You don't need to touch labels or comment on the issue yourself — just get
the branch name and `Closes #N` right (or let the bot fill in `Closes #N`
for you) and the rest follows.

## Questions

If any of this is unclear or you hit a case it doesn't cover, ask in the
issue or PR rather than guessing — and open a chore issue to fix this doc
once you have the answer, so the next person doesn't hit the same gap.
