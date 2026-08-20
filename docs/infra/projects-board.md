# GitHub Projects board

**URL:** https://github.com/orgs/raindeer-social-org/projects/1 ("Raindeer Social Roadmap")

Org-level Projects (v2) board, linked to this repo. Its `Status` field
has exactly the five columns this repo's process calls for:

```
Backlog → Ready → In Progress → In Review → Done
```

Nothing else about the default GitHub Projects setup was changed —
`Title`, `Assignees`, `Labels`, `Linked pull requests`, `Milestone`, and
the rest of the built-in fields are all still there.

## Why an org-level board, not a repo-level one

Projects (v2) boards are created at the org or user level and then linked
to one or more repos — there's no "repo project" distinct from that.
Linking it to `product-raindeer-social` (done via `gh project link`) makes
it discoverable from the repo's Projects tab; nothing about the board
itself is repo-specific.

## Status

Created empty — no issues have been added to it yet. Populating it (and
deciding whether cards should move automatically on PR open/merge, the
same way `issue-pr-sync` already moves issue *labels*) is a reasonable
next step, but is a separate decision from having the board and its
columns exist, which is what this issue's acceptance criteria asked for.

## Verifying this matches reality

```bash
gh project view 1 --owner raindeer-social-org
gh project field-list 1 --owner raindeer-social-org
```

If live output disagrees with this file, the API is correct — update
this file to match, not the other way around.
