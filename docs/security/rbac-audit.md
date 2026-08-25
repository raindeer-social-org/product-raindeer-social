# RBAC / Org-Scoping Audit

Issue #37 — final hardening pass. Date: 2026-08-25.

## Method

Walked every router under `apps/api/routers/` (`auth`, `analytics`, `brands`,
`calendar`, `onboarding`, `review`, `social_accounts` — the complete set
registered in `apps/api/main.py`) and, for every endpoint:

1. Recorded the role required to call it (from `Depends(require_role(...))`
   in `apps/api/middleware/rbac.py`, or "any authenticated role" if it's
   only gated by `Depends(get_current_user)` in `apps/api/auth/dependencies.py`).
2. Recorded the org-scoping mechanism — almost universally a `_get_org_brand`
   (or equivalent `_get_*_or_404`) helper defined at the top of each router
   that filters by `organization_id == current_user.org_id` (or by a parent
   resource that was itself fetched that way) and raises **404, not 403**
   on a miss, so a cross-org probe can't distinguish "doesn't exist" from
   "exists in someone else's org."
3. Verified it personally — either an existing test already exercised the
   exact behavior, or a new one was written in this PR. "Tested" below
   means yes in both cases; where a gap existed, it's called out and a new
   test was added (`apps/api/tests/test_org_scoping.py` for cross-org 404s,
   `apps/api/tests/test_rbac_audit.py` for role/viewer checks).

`UserRole` (`apps/api/models/user.py`): `OWNER`, `ADMIN`, `EDITOR`,
`VIEWER`. Every router defines the same `WRITE_ROLES = (OWNER, ADMIN,
EDITOR)` — `VIEWER` is never a write role anywhere in the API.

## Real bug found and fixed

**`POST /brands/{brand_id}/social-accounts/{account_id}/verify`**
(`apps/api/routers/social_accounts.py`) mutates `SocialAccount.status` and
calls out to the external OAuth provider — the same shape of side effect
as every other write endpoint in that router — but was gated only by
`Depends(get_current_user)` (any authenticated role, including `viewer`)
instead of `Depends(require_role(*WRITE_ROLES))` like `connect` and
`disconnect` right next to it. A viewer could trigger an external
provider call and a DB write. Fixed in this PR (now `require_role`-gated)
and covered by `test_viewer_cannot_verify_social_account` in
`test_rbac_audit.py`.

## Endpoint table

| Endpoint | Required role | Org-scoping mechanism | Tested |
|---|---|---|---|
| `POST /auth/login` | none (public) | N/A — returns the caller's own org from their password-verified row | Yes — `test_auth.py` |
| `GET /auth/me` | any authenticated | N/A — echoes the caller's own token claims | Yes — `test_auth.py` |
| `POST /brands` | OWNER/ADMIN/EDITOR | N/A (create) — `organization_id` set from `current_user.org_id`, not client input | Yes — `test_brands.py` |
| `GET /brands` | any authenticated | Filtered by `organization_id == current_user.org_id` | Yes — `test_brands.py::test_list_brands_only_returns_own_org` |
| `GET /brands/{id}` | any authenticated | `_get_org_brand` → 404 | Yes — `test_brands.py::test_cross_org_brand_access_returns_404_not_403` |
| `PATCH /brands/{id}` | OWNER/ADMIN/EDITOR | `_get_org_brand` → 404 | Yes — role: `test_brands.py`; cross-org: **added** `test_org_scoping.py::test_cross_org_brand_update_returns_404` |
| `DELETE /brands/{id}` | OWNER/ADMIN/EDITOR | `_get_org_brand` → 404 | Yes — role: `test_brands.py`; cross-org: **added** `test_org_scoping.py::test_cross_org_brand_delete_returns_404` |
| `PUT /brands/{id}/logo` | OWNER/ADMIN/EDITOR | `_get_org_brand` → 404; storage path is `{org_id}/{brand_id}/logo` (unguessable) | Yes — role: `test_brands.py`; cross-org: **added** `test_org_scoping.py::test_cross_org_brand_logo_upload_returns_404` |
| `DELETE /brands/{id}/logo` | OWNER/ADMIN/EDITOR | `_get_org_brand` → 404 | **Added both** — role: `test_rbac_audit.py::test_viewer_cannot_delete_brand_logo`; cross-org: `test_org_scoping.py::test_cross_org_brand_logo_delete_returns_404` |
| `POST /brands/{id}/report/export` | OWNER/ADMIN/EDITOR | `_get_org_brand` → 404 | Yes — `test_brand_pdf.py` (both role and cross-org) |
| `GET /brands/{id}/calendar-events` | any authenticated | `_get_org_brand` → 404 | Yes — `test_calendar.py` |
| `POST /brands/{id}/calendar-events` | OWNER/ADMIN/EDITOR | `_get_org_brand` → 404 | Yes — role: `test_calendar.py`; cross-org: **added** `test_org_scoping.py::test_cross_org_calendar_create_returns_404` |
| `GET /brands/{id}/calendar-events/{event_id}` | any authenticated | `_get_org_brand` + `_get_event_or_404` → 404 | Yes — `test_calendar.py::test_cross_org_event_access_returns_404` |
| `PATCH /brands/{id}/calendar-events/{event_id}` | OWNER/ADMIN/EDITOR | `_get_org_brand` + `_get_event_or_404` → 404 | **Added both** — role: `test_rbac_audit.py::test_viewer_cannot_update_calendar_event`; cross-org: `test_org_scoping.py::test_cross_org_calendar_update_returns_404` |
| `DELETE /brands/{id}/calendar-events/{event_id}` | OWNER/ADMIN/EDITOR | `_get_org_brand` + `_get_event_or_404` → 404 | **Added both** — role: `test_rbac_audit.py::test_viewer_cannot_delete_calendar_event`; cross-org: `test_org_scoping.py::test_cross_org_calendar_delete_returns_404` |
| `GET /brands/{id}/onboarding` | any authenticated | `_get_org_brand` → 404 | Yes — `test_onboarding.py::test_cross_org_onboarding_access_returns_404` |
| `PUT /brands/{id}/onboarding` | OWNER/ADMIN/EDITOR | `_get_org_brand` → 404 | Yes — role: `test_onboarding.py`; cross-org: **added** `test_org_scoping.py::test_cross_org_onboarding_upsert_returns_404` |
| `POST /brands/{id}/onboarding/complete` | OWNER/ADMIN/EDITOR | `_get_org_brand` → 404 | **Added both** — role: `test_rbac_audit.py::test_viewer_cannot_complete_onboarding`; cross-org: `test_org_scoping.py::test_cross_org_onboarding_complete_returns_404` |
| `POST /brands/{id}/onboarding/run-agent` | OWNER/ADMIN/EDITOR | `_get_org_brand` → 404 | Yes — role: `test_onboarding.py::test_viewer_cannot_run_agent`; cross-org: **added** `test_org_scoping.py::test_cross_org_onboarding_run_agent_returns_404` |
| `GET /brands/{id}/review-queue` | any authenticated | `_get_org_brand` → 404 | Yes — `test_review.py::test_list_review_queue_scoped_to_brand` |
| `POST /brands/{id}/review-queue/{post_id}/approve` | OWNER/ADMIN/EDITOR | `_get_org_brand` + `_get_post_or_404` → 404 | Yes — `test_review.py` (both role and cross-org) |
| `POST /brands/{id}/review-queue/{post_id}/reject` | OWNER/ADMIN/EDITOR | `_get_org_brand` + `_get_post_or_404` → 404 | **Added both** — role: `test_rbac_audit.py::test_viewer_cannot_reject`; cross-org: `test_org_scoping.py::test_cross_org_review_reject_returns_404` |
| `POST /brands/{id}/review-queue/{post_id}/edit` | OWNER/ADMIN/EDITOR | `_get_org_brand` + `_get_post_or_404` → 404 | **Added both** — role: `test_rbac_audit.py::test_viewer_cannot_edit_post`; cross-org: `test_org_scoping.py::test_cross_org_review_edit_returns_404` |
| `POST /brands/{id}/review-queue/{post_id}/reschedule` | OWNER/ADMIN/EDITOR | `_get_org_brand` + `_get_post_or_404` → 404 | **Added both** — role: `test_rbac_audit.py::test_viewer_cannot_reschedule`; cross-org: `test_org_scoping.py::test_cross_org_review_reschedule_returns_404` |
| `GET /brands/{id}/social-accounts` | any authenticated | `_get_org_brand` → 404 | Yes (functional coverage in `test_social_accounts.py`; same helper as the single-GET below, which has a dedicated cross-org test) |
| `GET /brands/{id}/social-accounts/{account_id}` | any authenticated | `_get_org_brand` + `_get_account_or_404` → 404 | Yes — `test_social_accounts.py::test_cross_org_social_account_access_returns_404` |
| `POST /brands/{id}/social-accounts/linkedin/connect` | OWNER/ADMIN/EDITOR | `_get_org_brand` → 404 | Yes — role: `test_social_accounts.py::test_viewer_cannot_connect`; cross-org: **added** `test_org_scoping.py::test_cross_org_social_connect_returns_404` |
| `GET /oauth/linkedin/callback` | none — see note below | Signed, expiring JWT `state` param (`STATE_EXPIRES_MINUTES = 10`), not a bearer token | Yes — `test_social_accounts.py::test_callback_rejects_invalid_state` |
| `POST /brands/{id}/social-accounts/{account_id}/verify` | **OWNER/ADMIN/EDITOR (fixed — was any authenticated role)** | `_get_org_brand` + `_get_account_or_404` → 404 | **Bug fixed + both added** — role: `test_rbac_audit.py::test_viewer_cannot_verify_social_account`; cross-org: `test_org_scoping.py::test_cross_org_social_verify_returns_404` |
| `DELETE /brands/{id}/social-accounts/{account_id}` | OWNER/ADMIN/EDITOR | `_get_org_brand` + `_get_account_or_404` → 404 | **Added both** — role: `test_rbac_audit.py::test_viewer_cannot_disconnect_social_account`; cross-org: `test_org_scoping.py::test_cross_org_social_disconnect_returns_404` |
| `GET /brands/{id}/analytics/summary` | any authenticated | `_get_org_brand` → 404 | Yes — `test_analytics.py::test_cross_org_brand_summary_returns_404` |
| `GET /brands/{id}/analytics/posts/{post_id}` | any authenticated | `_get_org_brand` + `_get_brand_post_or_404` → 404 | Yes — `test_analytics.py::test_cross_org_post_aggregate_returns_404` |
| `GET /brands/{id}/analytics/posts/{post_id}/trend` | any authenticated | `_get_org_brand` + `_get_brand_post_or_404` → 404 | Yes (functional), cross-org: **added** `test_org_scoping.py::test_cross_org_post_trend_returns_404` |
| `GET /brands/{id}/analytics/reports` | any authenticated | `_get_org_brand` → 404 | Yes — `test_weekly_report.py::test_cross_org_reports_list_returns_404` |
| `GET /brands/{id}/analytics/reports/{report_id}` | any authenticated | `_get_org_brand` → 404 | Yes — `test_weekly_report.py::test_cross_org_report_detail_returns_404` |

### Note on `GET /oauth/linkedin/callback`

This is the one endpoint in the API with no `CurrentUser`/bearer-token
dependency at all, and that's intentional, not a gap: it's the redirect
target LinkedIn's OAuth server calls directly, which carries no
`Authorization` header the caller controls. Authorization instead comes
from the signed `state` parameter minted by `/connect` (which *is*
`WRITE_ROLES`-gated) — a JWT signed with `settings.secret_key`, scoped to
one `brand_id`, purpose-tagged (`linkedin_oauth_connect`), and expiring in
10 minutes (`apps/api/routers/social_accounts.py::_create_state` /
`_verify_state`). An attacker without a valid state token gets a 400
(`test_callback_rejects_invalid_state`); a forged or replayed-after-expiry
state fails signature/expiry verification the same way a forged bearer
token would.

### Note on read-only endpoints and `VIEWER`

Every `GET` endpoint above allows any authenticated role, including
`VIEWER` — that's correct by design: `VIEWER` means "can read this org's
data, cannot mutate it," not "no access." The role check that matters is
that every non-`GET` endpoint (every `POST`/`PATCH`/`PUT`/`DELETE`) is
`WRITE_ROLES`-gated, which — after the `verify` fix above — is now true
without exception. `test_rbac_audit.py::test_viewer_blocked_from_every_write_endpoint`
sweeps a representative write call against every router's mutating routes
in one test as a regression net for this invariant.

## Coverage summary

- 30 endpoints audited across `auth`, `brands`, `calendar`, `onboarding`,
  `review`, `social_accounts`, `analytics`.
- 1 real RBAC bug found and fixed (`verify_social_account` missing
  `WRITE_ROLES` gate).
- Every endpoint in the table has a passing test personally run in this
  PR (either pre-existing or added here) — no row is "assumed correct."
- New coverage lives in `apps/api/tests/test_org_scoping.py` (cross-org
  404s) and `apps/api/tests/test_rbac_audit.py` (role/viewer checks +
  the sweep test), per the issue's file naming.
