# Contributing to Raindeer Social

This document is the single source of truth for how work moves through this
repository. If you're new to the project, read this before opening your
first PR — it answers the questions that otherwise get asked in every
review.

## 0. End-to-end walkthrough: from fork to merge

This section is the full path, start to finish. Sections 1–7 below cover
each topic in more depth — this is the sequence that ties them together.

**0. One-time setup**

- **Org member (write access to this repo):** clone directly.
  ```bash
  git clone https://github.com/raindeer-social-org/product-raindeer-social.git
  cd product-raindeer-social
  ```
- **External contributor (no write access):** fork first, then clone your
  fork and add this repo as `upstream` so you can pull in new work.
  ```bash
  gh repo fork raindeer-social-org/product-raindeer-social --clone
  cd product-raindeer-social
  git remote add upstream https://github.com/raindeer-social-org/product-raindeer-social.git
  ```
  (If you don't use `gh`, fork via the GitHub UI's "Fork" button, then
  `git clone` your fork and add the `upstream` remote by hand.)

  Either way, finish the environment setup in the [README's Getting
  Started section](./README.md#getting-started) — Python 3.11, Postgres +
  pgvector, `.env` from `.env.example` — before continuing.

**1. Pick an issue**

Browse [open issues](https://github.com/raindeer-social-org/product-raindeer-social/issues),
filtered by milestone or `area:*` label if you want to work in a specific
part of the system. Read the issue fully — it names the exact branch you
must use and the acceptance criteria that define "done." If nothing's
assigned and you want it, comment or assign yourself before starting so two
people don't duplicate work.

**2. Sync and branch**

```bash
git checkout dev
git pull origin dev          # or `upstream dev` if you're working from a fork
git checkout -b feature/issue-N-slug   # copy the exact name from the issue's "Branch" field
```

Always branch from `dev`, never from `main` — see [§1](#1-branch-strategy).

**3. Do the work**

Follow the issue's "Files to create/modify" list as a starting point, not a
hard boundary — touch what the change actually requires. Keep the PR scoped
to this one issue (§2, point 5).

**4. Test locally before pushing**

```bash
# backend changes
pip install -r apps/api/requirements.txt
alembic upgrade head
pytest apps/api/tests -v --cov

# frontend changes
npm ci --prefix apps/web
npm run lint --prefix apps/web
npm run test --prefix apps/web
npm run build --prefix apps/web
```

These are the exact commands CI runs (§4) — if they're red locally, they'll
be red in CI. Don't push hoping CI catches what you didn't check.

**5. Commit**

```bash
git add <files>
git commit -m "feat(api): add Brand CRUD endpoints"
```

Use [Conventional Commits](#3-commit-message-style). Keep commits atomic —
don't squash "wip" + "fix review comments" into one blob at the end.

**6. Push**

```bash
git push -u origin feature/issue-N-slug
```

(Pushes to *your* fork if you're an external contributor — `origin` there
points at your fork, not this repo.)

**7. Open the PR**

```bash
gh pr create --base dev --title "feat(api): add Brand CRUD endpoints" --web
```

`--web` opens the PR in your browser pre-filled with the template so you
can fill it in there — or drop `--web` and pass `--body-file` with a
completed copy of the template. Either way works; so does just using the
GitHub UI's "Compare & pull request" button.

Target `dev`, not `main`. Fill out every section of the PR template — don't
leave `Closes #N` blank (the bot will fill it in from your branch name if
you forget, but don't rely on that). See [§2](#2-opening-a-pull-request).

**8. Automated checks run**

Three checks fire automatically on open (§7):
- `backend-ci` / `frontend-ci` — the same test commands from step 4, now
  running in CI.
- `issue-pr-sync` — validates your branch name matches `feature/issue-N-slug`
  against a real issue, links the PR to it, comments on the issue, and
  moves its label to `status:in-progress`.

If `issue-pr-sync` fails, it's almost always a branch-naming mismatch —
rename the branch (`git branch -m feature/issue-N-slug`) and force-push
(`git push -u origin feature/issue-N-slug -f`) rather than opening a new PR.

**9. Review**

A reviewer reads the diff on GitHub and leaves the PR **Approved**,
**Request changes**, or plain **Comment**. Push more commits to the same
branch to address feedback — they attach to the existing PR automatically,
no new PR needed. Resolve each comment thread once it's addressed; merge is
blocked while any conversation is unresolved (§5).

**10. Merge**

The merge button only unlocks once every branch protection rule is
satisfied (§5): required approvals in, CI green, branch up to date with
`dev`, all conversations resolved. Once merged:
- `issue-pr-sync` comments on the issue and relabels it `status:done`.
- The issue **auto-closes** — this repo's default branch is `dev`, and
  GitHub auto-closes a `Closes #N` issue the moment its PR merges into the
  default branch (not into `main` — that distinction matters here since
  `main` only receives batched releases from `dev`, not individual feature
  PRs).

**11. Clean up**

```bash
git checkout dev
git pull origin dev
git branch -d feature/issue-N-slug
git push origin --delete feature/issue-N-slug   # if you didn't check "delete branch" on GitHub
```

**12. Releasing `dev` → `main`**

Not part of a contributor's regular loop — a maintainer periodically opens
a `dev → main` PR to cut a release, once `dev` is in a known-good state.
That PR needs 2 approvals (§5) and doesn't reference `Closes #N` (those
issues already closed in step 10).

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
| `main` | 2 | Green CI, branch up to date, all conversations resolved, no force-push, no direct pushes |
| `dev`  | 1 | Same as above |

`dev` is this repo's default branch — `main` only moves via a periodic
`dev → main` release PR (§0, step 12), not individual feature PRs.

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
