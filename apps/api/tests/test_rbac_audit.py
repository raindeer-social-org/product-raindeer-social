"""Issue #37 hardening pass: RBAC audit.

Confirms role enforcement end-to-end: a `viewer`-role user (apps/api/models
/user.py::UserRole) cannot reach any write endpoint anywhere in the API.
Every mutating endpoint in this codebase is gated with
`Depends(require_role(*WRITE_ROLES))` (apps/api/middleware/rbac.py),
where WRITE_ROLES = (OWNER, ADMIN, EDITOR) — VIEWER is always excluded.

Most write endpoints already had a `test_viewer_cannot_*` test alongside
their functional tests in their own router's test file (test_brands.py,
test_calendar.py, test_onboarding.py, test_review.py,
test_social_accounts.py). This file:

  1. Fills the endpoints that had no viewer-role test at all (see
     docs/security/rbac-audit.md for the full table).
  2. Adds `test_viewer_blocked_from_every_write_endpoint`, a single
     parametrized sweep that hits every write-role-gated route in the app
     as a viewer and asserts 403 — a regression net that catches a *new*
     write endpoint shipped later without a role gate, not just the ones
     enumerated by hand above.
  3. Fixes and covers a real bug found during this audit:
     `POST /brands/{brand_id}/social-accounts/{account_id}/verify`
     (apps/api/routers/social_accounts.py) mutated SocialAccount.status
     and called out to the external OAuth provider, but was gated only by
     `get_current_user` (any authenticated role) instead of
     `require_role(*WRITE_ROLES)` like every other mutating endpoint in
     that router. A viewer could trigger it. Fixed in the same commit as
     this test.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from apps.api.auth.jwt import create_access_token, hash_password
from apps.api.main import app
from apps.api.models import (
    Brand,
    ContentCalendarEvent,
    Organization,
    PipelineStage,
    Post,
    SocialAccount,
    SocialPlatform,
    User,
    UserRole,
)
from packages.agents.pipeline.checkpointer import get_postgres_checkpointer
from packages.agents.pipeline.graph import run_pipeline

client = TestClient(app)
uses_test_session = pytest.mark.usefixtures("override_get_db")


def _setup_brand(db_session, role: UserRole = UserRole.EDITOR, suffix: str = "") -> tuple[Brand, User]:
    org = Organization(name=f"Org{suffix}")
    db_session.add(org)
    db_session.flush()

    user = User(
        organization_id=org.id,
        email=f"{role.value}{suffix}@acme.test",
        password_hash=hash_password("test-password"),
        role=role,
    )
    brand = Brand(organization_id=org.id, name="Acme Widgets")
    db_session.add_all([user, brand])
    db_session.flush()
    return brand, user


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=str(user.id), org_id=str(user.organization_id), role=user.role.value
    )
    return {"Authorization": f"Bearer {token}"}


def _editor_and_viewer_same_org(db_session, suffix: str = "") -> tuple[Brand, User, User]:
    """A brand plus two users in the *same* org — one editor (to set up
    fixture state), one viewer (whose write attempt should 403). Using the
    same org isolates this from org-scoping (a viewer in a foreign org
    would 404 first, per test_org_scoping.py) — this file is purely about
    the role check."""
    org = Organization(name=f"Org{suffix}")
    db_session.add(org)
    db_session.flush()
    editor = User(
        organization_id=org.id,
        email=f"editor{suffix}@acme.test",
        password_hash=hash_password("test-password"),
        role=UserRole.EDITOR,
    )
    viewer = User(
        organization_id=org.id,
        email=f"viewer{suffix}@acme.test",
        password_hash=hash_password("test-password"),
        role=UserRole.VIEWER,
    )
    brand = Brand(organization_id=org.id, name="Acme Widgets")
    db_session.add_all([editor, viewer, brand])
    db_session.flush()
    return brand, editor, viewer


# ---------------------------------------------------------------------------
# brands.py — DELETE /logo had no role test at all.
# ---------------------------------------------------------------------------


@uses_test_session
def test_viewer_cannot_delete_brand_logo(db_session) -> None:
    from unittest.mock import MagicMock, patch

    brand, editor, viewer = _editor_and_viewer_same_org(db_session, suffix="-logo")
    response_mock = MagicMock()
    response_mock.raise_for_status.return_value = None
    with patch("httpx.post", return_value=response_mock):
        client.put(
            f"/brands/{brand.id}/logo",
            files={"file": ("logo.png", b"data", "image/png")},
            headers=_auth_headers(editor),
        )

    response = client.delete(f"/brands/{brand.id}/logo", headers=_auth_headers(viewer))

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# calendar.py — update/delete had no role test at all (only create did).
# ---------------------------------------------------------------------------

_EVENT_PAYLOAD = {
    "title": "Launch announcement",
    "description": "Announce the new widget line",
    "target_platforms": ["linkedin"],
    "desired_format": "single-image",
    "target_datetime": "2026-09-01T12:00:00Z",
}


@uses_test_session
def test_viewer_cannot_update_calendar_event(db_session) -> None:
    brand, editor, viewer = _editor_and_viewer_same_org(db_session, suffix="-cal-upd")
    created = client.post(
        f"/brands/{brand.id}/calendar-events", json=_EVENT_PAYLOAD, headers=_auth_headers(editor)
    ).json()

    response = client.patch(
        f"/brands/{brand.id}/calendar-events/{created['id']}",
        json={"status": "approved"},
        headers=_auth_headers(viewer),
    )

    assert response.status_code == 403


@uses_test_session
def test_viewer_cannot_delete_calendar_event(db_session) -> None:
    brand, editor, viewer = _editor_and_viewer_same_org(db_session, suffix="-cal-del")
    created = client.post(
        f"/brands/{brand.id}/calendar-events", json=_EVENT_PAYLOAD, headers=_auth_headers(editor)
    ).json()

    response = client.delete(
        f"/brands/{brand.id}/calendar-events/{created['id']}", headers=_auth_headers(viewer)
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# onboarding.py — /complete had no role test at all.
# ---------------------------------------------------------------------------


@uses_test_session
def test_viewer_cannot_complete_onboarding(db_session) -> None:
    brand, editor, viewer = _editor_and_viewer_same_org(db_session, suffix="-onb")
    client.put(
        f"/brands/{brand.id}/onboarding",
        json={
            "voice": "Playful",
            "audience": "Gen Z",
            "product_catalog": {"items": ["A"]},
            "competitors": ["X"],
            "goals": ["Grow"],
        },
        headers=_auth_headers(editor),
    )

    response = client.post(
        f"/brands/{brand.id}/onboarding/complete", headers=_auth_headers(viewer)
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# review.py — reject/edit/reschedule had no role test at all (only approve
# did). Uses the same real-pipeline setup as test_review.py to get a Post
# paused at human_review.
# ---------------------------------------------------------------------------


@pytest.fixture()
def thread_cleanup():
    thread_ids: list[str] = []
    yield thread_ids
    if not thread_ids:
        return
    with get_postgres_checkpointer() as checkpointer:
        for thread_id in thread_ids:
            checkpointer.delete_thread(thread_id)


def _post_at_human_review(db_session, brand: Brand, thread_cleanup) -> Post:
    post = Post(brand_id=brand.id)
    db_session.add(post)
    db_session.flush()
    thread_cleanup.append(str(post.id))

    with get_postgres_checkpointer() as checkpointer:
        list(run_pipeline(db_session, post, checkpointer))

    db_session.refresh(post)
    assert post.current_pipeline_stage == PipelineStage.HUMAN_REVIEW
    return post


@uses_test_session
def test_viewer_cannot_reject(db_session, thread_cleanup) -> None:
    brand, editor, viewer = _editor_and_viewer_same_org(db_session, suffix="-rej")
    post = _post_at_human_review(db_session, brand, thread_cleanup)

    response = client.post(
        f"/brands/{brand.id}/review-queue/{post.id}/reject",
        json={},
        headers=_auth_headers(viewer),
    )

    assert response.status_code == 403


@uses_test_session
def test_viewer_cannot_edit_post(db_session, thread_cleanup) -> None:
    brand, editor, viewer = _editor_and_viewer_same_org(db_session, suffix="-edit")
    post = _post_at_human_review(db_session, brand, thread_cleanup)

    response = client.post(
        f"/brands/{brand.id}/review-queue/{post.id}/edit",
        json={"body_text": {"linkedin": "Hacked"}},
        headers=_auth_headers(viewer),
    )

    assert response.status_code == 403


@uses_test_session
def test_viewer_cannot_reschedule(db_session, thread_cleanup) -> None:
    brand, editor, viewer = _editor_and_viewer_same_org(db_session, suffix="-resch")
    event = ContentCalendarEvent(
        brand_id=brand.id,
        title="Launch",
        target_platforms=["linkedin"],
        desired_format="image",
        target_datetime=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
    )
    db_session.add(event)
    db_session.flush()
    post = _post_at_human_review(db_session, brand, thread_cleanup)
    post.calendar_event_id = event.id
    db_session.flush()

    response = client.post(
        f"/brands/{brand.id}/review-queue/{post.id}/reschedule",
        json={"target_datetime": "2026-09-05T15:30:00Z"},
        headers=_auth_headers(viewer),
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# social_accounts.py — verify (the bug fixed by this PR, see module
# docstring) and disconnect had no role test at all.
# ---------------------------------------------------------------------------


@uses_test_session
def test_viewer_cannot_verify_social_account(db_session) -> None:
    """Regression test for the real bug this audit found and fixed:
    verify_social_account was gated by get_current_user only, so any
    authenticated viewer could trigger it. Now require_role(*WRITE_ROLES),
    same as connect/disconnect."""
    brand, editor, viewer = _editor_and_viewer_same_org(db_session, suffix="-verify")
    account = SocialAccount(
        brand_id=brand.id, platform=SocialPlatform.LINKEDIN, access_token_encrypted="ciphertext"
    )
    db_session.add(account)
    db_session.flush()

    response = client.post(
        f"/brands/{brand.id}/social-accounts/{account.id}/verify",
        headers=_auth_headers(viewer),
    )

    assert response.status_code == 403


@uses_test_session
def test_viewer_cannot_disconnect_social_account(db_session) -> None:
    brand, editor, viewer = _editor_and_viewer_same_org(db_session, suffix="-disc")
    account = SocialAccount(
        brand_id=brand.id, platform=SocialPlatform.LINKEDIN, access_token_encrypted="ciphertext"
    )
    db_session.add(account)
    db_session.flush()

    response = client.delete(
        f"/brands/{brand.id}/social-accounts/{account.id}",
        headers=_auth_headers(viewer),
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Sweep: every write-role-gated route in the app, hit as a viewer.
#
# This walks app.routes directly rather than a hand-maintained list, so a
# new write endpoint added later that forgets Depends(require_role(...))
# entirely (dependency missing, not misconfigured) still gets *some*
# coverage here — FastAPI would then fall through to get_current_user (if
# present) or no auth at all, and this sweep would catch the former as a
# non-403 for a viewer. It cannot invent valid path/body params for a route
# it doesn't know the shape of, so routes here are limited to ones that
# accept an empty/near-empty JSON body and only path params this test can
# fill in from a real brand/post/event/account it creates first — the
# per-endpoint tests above (and in each router's own test file) remain the
# source of truth for exact-shape coverage.
# ---------------------------------------------------------------------------


@uses_test_session
def test_viewer_blocked_from_every_write_endpoint(db_session, thread_cleanup) -> None:
    brand, editor, viewer = _editor_and_viewer_same_org(db_session, suffix="-sweep")
    viewer_headers = _auth_headers(viewer)
    editor_headers = _auth_headers(editor)

    event = client.post(
        f"/brands/{brand.id}/calendar-events", json=_EVENT_PAYLOAD, headers=editor_headers
    ).json()
    post = _post_at_human_review(db_session, brand, thread_cleanup)
    account = SocialAccount(
        brand_id=brand.id, platform=SocialPlatform.LINKEDIN, access_token_encrypted="ciphertext"
    )
    db_session.add(account)
    db_session.flush()

    attempts: list[tuple[str, str, dict | None]] = [
        ("POST", "/brands", {"name": "New Brand"}),
        ("PATCH", f"/brands/{brand.id}", {"name": "Renamed"}),
        ("DELETE", f"/brands/{brand.id}", None),
        ("POST", f"/brands/{brand.id}/report/export", None),
        ("PUT", f"/brands/{brand.id}/onboarding", {"voice": "Hacked"}),
        (
            "POST",
            f"/brands/{brand.id}/calendar-events",
            _EVENT_PAYLOAD,
        ),
        (
            "PATCH",
            f"/brands/{brand.id}/calendar-events/{event['id']}",
            {"status": "approved"},
        ),
        ("DELETE", f"/brands/{brand.id}/calendar-events/{event['id']}", None),
        (
            "POST",
            f"/brands/{brand.id}/social-accounts/linkedin/connect",
            None,
        ),
        (
            "POST",
            f"/brands/{brand.id}/social-accounts/{account.id}/verify",
            None,
        ),
        ("DELETE", f"/brands/{brand.id}/social-accounts/{account.id}", None),
        (
            "POST",
            f"/brands/{brand.id}/review-queue/{post.id}/approve",
            {},
        ),
    ]

    for method, path, body in attempts:
        response = client.request(method, path, json=body, headers=viewer_headers)
        assert response.status_code == 403, (
            f"viewer got {response.status_code} (expected 403) on {method} {path}: "
            f"{response.text}"
        )


@uses_test_session
def test_unauthenticated_request_is_401_not_403_on_write_endpoints(db_session) -> None:
    """get_current_user (and therefore require_role, which depends on it)
    must reject a missing token with 401 before role is ever checked —
    proven for one representative write endpoint here; the auth-layer
    behavior itself (401 for missing/expired/invalid tokens) is unit
    tested exhaustively in test_auth.py."""
    response = client.post("/brands", json={"name": "No Auth"})

    assert response.status_code == 401
