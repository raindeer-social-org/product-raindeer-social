"""Issue #37 hardening pass: RBAC/org-scoping audit.

Every scoped router already established the convention of a 404 (not 403)
on cross-org access — see e.g. brands.py's `_get_org_brand` docstring:
"don't leak whether a brand with this id exists in another org." Most
endpoints already had a dedicated cross-org test in their own router's
test file (test_brands.py, test_calendar.py, test_onboarding.py,
test_review.py, test_social_accounts.py, test_analytics.py,
test_weekly_report.py).

This file fills the gaps found during the #37 audit: endpoints that share
the same `_get_org_brand`/`_get_*_or_404` helpers as their already-tested
siblings, but never had their own cross-org attempt actually driven
through the API and asserted on. See docs/security/rbac-audit.md for the
full endpoint-by-endpoint table this file (together with the existing
per-router tests and test_rbac_audit.py) backs.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

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


def _two_orgs(db_session) -> tuple[Brand, User, Brand, User]:
    """Brand A belongs to org A (owner), brand B (with `other_user`) belongs
    to org B — the attacker tries to reach brand A's resources using org
    B's token."""
    brand_a, owner = _setup_brand(db_session, UserRole.EDITOR, suffix="-a")
    brand_b, other_user = _setup_brand(db_session, UserRole.EDITOR, suffix="-b")
    return brand_a, owner, brand_b, other_user


def _ok_storage_response():
    from unittest.mock import MagicMock

    response = MagicMock()
    response.raise_for_status.return_value = None
    return response


# ---------------------------------------------------------------------------
# brands.py — PATCH/DELETE/logo endpoints share _get_org_brand with GET
# (already cross-org tested in test_brands.py) but never had their own
# cross-org attempt driven through the API.
# ---------------------------------------------------------------------------


@uses_test_session
def test_cross_org_brand_update_returns_404(db_session) -> None:
    brand_a, owner, _brand_b, other_user = _two_orgs(db_session)

    response = client.patch(
        f"/brands/{brand_a.id}", json={"name": "Hacked"}, headers=_auth_headers(other_user)
    )

    assert response.status_code == 404


@uses_test_session
def test_cross_org_brand_delete_returns_404(db_session) -> None:
    brand_a, owner, _brand_b, other_user = _two_orgs(db_session)

    response = client.delete(f"/brands/{brand_a.id}", headers=_auth_headers(other_user))

    assert response.status_code == 404


@uses_test_session
def test_cross_org_brand_logo_upload_returns_404(db_session) -> None:
    brand_a, owner, _brand_b, other_user = _two_orgs(db_session)

    with patch("httpx.post", return_value=_ok_storage_response()):
        response = client.put(
            f"/brands/{brand_a.id}/logo",
            files={"file": ("logo.png", b"data", "image/png")},
            headers=_auth_headers(other_user),
        )

    assert response.status_code == 404


@uses_test_session
def test_cross_org_brand_logo_delete_returns_404(db_session) -> None:
    brand_a, owner, _brand_b, other_user = _two_orgs(db_session)

    response = client.delete(f"/brands/{brand_a.id}/logo", headers=_auth_headers(other_user))

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# calendar.py — create/update/delete never had their own cross-org attempt
# (only GET-single was tested in test_calendar.py).
# ---------------------------------------------------------------------------

_EVENT_PAYLOAD = {
    "title": "Launch announcement",
    "description": "Announce the new widget line",
    "target_platforms": ["linkedin"],
    "desired_format": "single-image",
    "target_datetime": "2026-09-01T12:00:00Z",
}


@uses_test_session
def test_cross_org_calendar_create_returns_404(db_session) -> None:
    brand_a, owner, _brand_b, other_user = _two_orgs(db_session)

    response = client.post(
        f"/brands/{brand_a.id}/calendar-events",
        json=_EVENT_PAYLOAD,
        headers=_auth_headers(other_user),
    )

    assert response.status_code == 404


@uses_test_session
def test_cross_org_calendar_update_returns_404(db_session) -> None:
    brand_a, owner, _brand_b, other_user = _two_orgs(db_session)
    created = client.post(
        f"/brands/{brand_a.id}/calendar-events", json=_EVENT_PAYLOAD, headers=_auth_headers(owner)
    ).json()

    response = client.patch(
        f"/brands/{brand_a.id}/calendar-events/{created['id']}",
        json={"status": "approved"},
        headers=_auth_headers(other_user),
    )

    assert response.status_code == 404


@uses_test_session
def test_cross_org_calendar_delete_returns_404(db_session) -> None:
    brand_a, owner, _brand_b, other_user = _two_orgs(db_session)
    created = client.post(
        f"/brands/{brand_a.id}/calendar-events", json=_EVENT_PAYLOAD, headers=_auth_headers(owner)
    ).json()

    response = client.delete(
        f"/brands/{brand_a.id}/calendar-events/{created['id']}",
        headers=_auth_headers(other_user),
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# onboarding.py — upsert/complete/run-agent never had their own cross-org
# attempt (only GET was tested in test_onboarding.py).
# ---------------------------------------------------------------------------


@uses_test_session
def test_cross_org_onboarding_upsert_returns_404(db_session) -> None:
    brand_a, owner, _brand_b, other_user = _two_orgs(db_session)

    response = client.put(
        f"/brands/{brand_a.id}/onboarding",
        json={"voice": "Hacked"},
        headers=_auth_headers(other_user),
    )

    assert response.status_code == 404


@uses_test_session
def test_cross_org_onboarding_complete_returns_404(db_session) -> None:
    brand_a, owner, _brand_b, other_user = _two_orgs(db_session)
    client.put(
        f"/brands/{brand_a.id}/onboarding", json={"voice": "Playful"}, headers=_auth_headers(owner)
    )

    response = client.post(
        f"/brands/{brand_a.id}/onboarding/complete", headers=_auth_headers(other_user)
    )

    assert response.status_code == 404


@uses_test_session
def test_cross_org_onboarding_run_agent_returns_404(db_session) -> None:
    brand_a, owner, _brand_b, other_user = _two_orgs(db_session)

    response = client.post(
        f"/brands/{brand_a.id}/onboarding/run-agent", headers=_auth_headers(other_user)
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# review.py — reject/edit/reschedule never had their own cross-org attempt
# (only approve was tested in test_review.py). Uses the same real-pipeline
# setup as test_review.py to get a Post paused at human_review.
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
def test_cross_org_review_reject_returns_404(db_session, thread_cleanup) -> None:
    brand_a, owner, _brand_b, other_user = _two_orgs(db_session)
    post = _post_at_human_review(db_session, brand_a, thread_cleanup)

    response = client.post(
        f"/brands/{brand_a.id}/review-queue/{post.id}/reject",
        json={},
        headers=_auth_headers(other_user),
    )

    assert response.status_code == 404


@uses_test_session
def test_cross_org_review_edit_returns_404(db_session, thread_cleanup) -> None:
    brand_a, owner, _brand_b, other_user = _two_orgs(db_session)
    post = _post_at_human_review(db_session, brand_a, thread_cleanup)

    response = client.post(
        f"/brands/{brand_a.id}/review-queue/{post.id}/edit",
        json={"body_text": {"linkedin": "Hacked"}},
        headers=_auth_headers(other_user),
    )

    assert response.status_code == 404


@uses_test_session
def test_cross_org_review_reschedule_returns_404(db_session, thread_cleanup) -> None:
    brand_a, owner, _brand_b, other_user = _two_orgs(db_session)
    event = ContentCalendarEvent(
        brand_id=brand_a.id,
        title="Launch",
        target_platforms=["linkedin"],
        desired_format="image",
        target_datetime=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
    )
    db_session.add(event)
    db_session.flush()
    post = _post_at_human_review(db_session, brand_a, thread_cleanup)
    post.calendar_event_id = event.id
    db_session.flush()

    response = client.post(
        f"/brands/{brand_a.id}/review-queue/{post.id}/reschedule",
        json={"target_datetime": "2026-09-05T15:30:00Z"},
        headers=_auth_headers(other_user),
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# social_accounts.py — connect/verify/disconnect never had their own
# cross-org attempt (only GET-single was tested in test_social_accounts.py).
# ---------------------------------------------------------------------------


@uses_test_session
def test_cross_org_social_connect_returns_404(db_session, monkeypatch) -> None:
    from apps.api.config import get_settings

    monkeypatch.setenv("LINKEDIN_REDIRECT_URI", "http://localhost:8000/oauth/linkedin/callback")
    get_settings.cache_clear()
    brand_a, owner, _brand_b, other_user = _two_orgs(db_session)

    response = client.post(
        f"/brands/{brand_a.id}/social-accounts/linkedin/connect", headers=_auth_headers(other_user)
    )
    get_settings.cache_clear()

    assert response.status_code == 404


@uses_test_session
def test_cross_org_social_verify_returns_404(db_session) -> None:
    brand_a, owner, _brand_b, other_user = _two_orgs(db_session)
    account = SocialAccount(
        brand_id=brand_a.id, platform=SocialPlatform.LINKEDIN, access_token_encrypted="ciphertext"
    )
    db_session.add(account)
    db_session.flush()

    response = client.post(
        f"/brands/{brand_a.id}/social-accounts/{account.id}/verify",
        headers=_auth_headers(other_user),
    )

    assert response.status_code == 404


@uses_test_session
def test_cross_org_social_disconnect_returns_404(db_session) -> None:
    brand_a, owner, _brand_b, other_user = _two_orgs(db_session)
    account = SocialAccount(
        brand_id=brand_a.id, platform=SocialPlatform.LINKEDIN, access_token_encrypted="ciphertext"
    )
    db_session.add(account)
    db_session.flush()

    response = client.delete(
        f"/brands/{brand_a.id}/social-accounts/{account.id}",
        headers=_auth_headers(other_user),
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# analytics.py — /posts/{id}/trend never had its own cross-org attempt
# (summary and posts/{id} were both tested in test_analytics.py).
# ---------------------------------------------------------------------------


@uses_test_session
def test_cross_org_post_trend_returns_404(db_session) -> None:
    brand_a, owner, _brand_b, other_user = _two_orgs(db_session)
    post = Post(brand_id=brand_a.id)
    db_session.add(post)
    db_session.flush()

    response = client.get(
        f"/brands/{brand_a.id}/analytics/posts/{post.id}/trend",
        headers=_auth_headers(other_user),
    )

    assert response.status_code == 404


@uses_test_session
def test_unknown_brand_id_returns_404_not_500(db_session) -> None:
    """A syntactically valid but nonexistent brand_id must 404 the same way
    a real-but-foreign one does — proves _get_org_brand doesn't distinguish
    "doesn't exist" from "exists in another org" in its response, which is
    the whole point of the 404-not-403 convention (no enumeration signal)."""
    _brand, user = _setup_brand(db_session)

    response = client.get(f"/brands/{uuid.uuid4()}", headers=_auth_headers(user))

    assert response.status_code == 404
