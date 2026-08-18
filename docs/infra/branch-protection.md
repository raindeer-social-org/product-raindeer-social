# Branch protection — `main`

Recorded here so the actual GitHub setting and this repo's documented
policy ([`CONTRIBUTING.md` §5](../../CONTRIBUTING.md#5-review-and-merge-rules))
can be diffed against each other instead of drifting apart silently.

This repo uses a single protected branch, `main` — see
[`CONTRIBUTING.md` §1](../../CONTRIBUTING.md#1-branch-strategy) for why
there's no separate integration branch.

## Settings applied

| Rule | Value |
|------|-------|
| Require a pull request before merging | Yes |
| Required approving reviews | 1 (from someone other than the PR author — GitHub blocks self-approval by default) |
| Dismiss stale approvals on new commits | Yes |
| Require status checks to pass | Yes — `test` (backend-ci), `sync` (issue-pr-sync) |
| Require branches to be up to date before merging | Yes |
| Require conversation resolution before merging | Yes |
| Require linear history | No |
| Allow force pushes | No |
| Allow deletions | No |
| Applies to administrators | Yes |

`frontend-ci`'s `build` check is intentionally **not** a required check —
it's path-scoped to `apps/web/**` (see `.github/workflows/frontend-ci.yml`),
so a backend-only PR never triggers it. Making a path-scoped check required
would leave those PRs permanently blocked waiting on a check that never
runs. Backend-only and frontend-only PRs are both expected; `test` from
`backend-ci` runs unconditionally on every PR and is the one required
check that always fires.

## Verifying this matches reality

```bash
gh api repos/raindeer-social-org/product-raindeer-social/branches/main/protection
```

If this file and that output disagree, the API output is correct — update
this file to match, not the other way around.
