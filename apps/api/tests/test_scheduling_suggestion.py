import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from apps.api.auth.jwt import create_access_token, hash_password
from apps.api.main import app
from apps.api.models import AgentRun, AgentType, Brand, Organization, Post, User, UserRole
from apps.api.services.scheduling_suggestion import (
    NoResearchSignalError,
    suggest_target_datetime,
)

client = TestClient(app)
uses_test_session = pytest.mark.usefixtures("override_get_db")


# --- fixtures/helpers -------------------------------------------------


def _setup_brand(db_session, role: UserRole = UserRole.EDITOR, suffix: str = "") -> tuple[Brand, User]:
    org = Organization(name="Acme Agency")
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


def _make_post(db_session, brand: Brand) -> Post:
    post = Post(brand_id=brand.id)
    db_session.add(post)
    db_session.flush()
    return post


def _research_brief(
    *,
    platforms: list[str],
    trending_topics: list[str],
    researched_at: datetime,
    platform_trends: dict[str, list[dict]] | None = None,
) -> dict:
    return {
        "post_id": "irrelevant-for-these-tests",
        "brand_context": [],
        "platform_trends": platform_trends or {},
        "industry_trends": [],
        "timing_signal": {
            "researched_at": researched_at.isoformat(),
            "platforms": platforms,
            "trending_topics": trending_topics,
            "target_datetime": None,
        },
    }


def _log_research_run(
    db_session, post: Post, brief: dict, created_at: datetime | None = None
) -> AgentRun:
    run = AgentRun(
        post_id=post.id,
        agent_type=AgentType.RESEARCH,
        input={"post_id": str(post.id)},
        output={"completed_stages": ["research"], "research_brief": brief},
    )
    if created_at is not None:
        # Postgres' now()/server_default is the *transaction* start time,
        # constant across every insert in this test's single open
        # transaction (see db_session fixture) — so ordering-sensitive
        # tests need an explicit, distinct created_at per row rather than
        # relying on the server default to vary.
        run.created_at = created_at
    db_session.add(run)
    db_session.flush()
    return run


def _payload(**overrides: object) -> dict:
    base = {
        "title": "Launch announcement",
        "description": "Announce the new widget line",
        "target_platforms": ["linkedin"],
        "desired_format": "single-image",
    }
    base.update(overrides)
    return base


# --- service-level tests ------------------------------------------------


@uses_test_session
def test_no_research_signal_raises(db_session) -> None:
    brand, _user = _setup_brand(db_session)

    with pytest.raises(NoResearchSignalError):
        suggest_target_datetime(db_session, brand.id, "linkedin")


@uses_test_session
def test_platform_not_covered_by_signal_raises(db_session) -> None:
    brand, _user = _setup_brand(db_session)
    post = _make_post(db_session, brand)
    brief = _research_brief(
        platforms=["linkedin"],
        trending_topics=["widget season kickoff"],
        researched_at=datetime.now(timezone.utc),
    )
    _log_research_run(db_session, post, brief)

    # A brief that only researched "linkedin" can't back a suggestion for
    # "x" — the caller should be told there's no usable signal, not handed
    # a fabricated time.
    with pytest.raises(NoResearchSignalError):
        suggest_target_datetime(db_session, brand.id, "x")


@uses_test_session
def test_suggestion_is_derived_from_signal_content_not_hardcoded(db_session) -> None:
    """Two different research briefs (different trending topics / search
    results, same platform) must yield different suggested datetimes —
    proof the value comes from the signal's actual content rather than a
    fixed platform -> time-of-day table."""
    brand, _user = _setup_brand(db_session)
    researched_at = datetime(2026, 8, 1, tzinfo=timezone.utc)

    post_a = _make_post(db_session, brand)
    brief_a = _research_brief(
        platforms=["linkedin"],
        trending_topics=["AI agents in the workplace", "Q3 product launches"],
        researched_at=researched_at,
    )
    run_a = _log_research_run(
        db_session, post_a, brief_a, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    suggestion_a = suggest_target_datetime(db_session, brand.id, "linkedin")

    # A second, later, differently-worded research run for the same brand
    # and platform — it becomes the newest signal considered from here on.
    post_b = _make_post(db_session, brand)
    brief_b = _research_brief(
        platforms=["linkedin"],
        trending_topics=["holiday gifting trends", "sustainable packaging"],
        researched_at=researched_at,
    )
    _log_research_run(
        db_session, post_b, brief_b, created_at=datetime(2026, 1, 2, tzinfo=timezone.utc)
    )
    suggestion_b = suggest_target_datetime(db_session, brand.id, "linkedin")

    assert suggestion_a.target_datetime != suggestion_b.target_datetime
    assert suggestion_a.source["agent_run_id"] == str(run_a.id)
    assert "linkedin" in suggestion_a.reasoning


@uses_test_session
def test_suggestion_reproducible_for_identical_signal(db_session) -> None:
    """Same signal content -> same derived suggestion (not random), so a
    caller re-reading the same brief gets a stable answer."""
    brand, _user = _setup_brand(db_session)
    researched_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
    post = _make_post(db_session, brand)
    brief = _research_brief(
        platforms=["linkedin"],
        trending_topics=["evergreen topic"],
        researched_at=researched_at,
    )
    _log_research_run(db_session, post, brief)

    first = suggest_target_datetime(db_session, brand.id, "linkedin")
    second = suggest_target_datetime(db_session, brand.id, "linkedin")

    assert first.target_datetime == second.target_datetime


@uses_test_session
def test_suggestion_differs_across_platforms(db_session) -> None:
    """Acceptance criteria: suggestion logic covered across at least 2
    platforms with genuinely different outcomes, from the very same
    research run — driven by each platform's own trend search results,
    not a per-platform constant."""
    brand, _user = _setup_brand(db_session)
    researched_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
    post = _make_post(db_session, brand)
    brief = _research_brief(
        platforms=["linkedin", "x"],
        trending_topics=["remote work culture"],
        researched_at=researched_at,
        platform_trends={
            "linkedin": [
                {"title": "B2B thought leadership on the rise", "url": "u1", "content": "..."}
            ],
            "x": [
                {"title": "Breaking: real-time news cycle trends", "url": "u2", "content": "..."}
            ],
        },
    )
    _log_research_run(db_session, post, brief)

    linkedin_suggestion = suggest_target_datetime(db_session, brand.id, "linkedin")
    x_suggestion = suggest_target_datetime(db_session, brand.id, "x")

    assert linkedin_suggestion.target_datetime != x_suggestion.target_datetime
    assert "linkedin" in linkedin_suggestion.reasoning
    assert "x" in x_suggestion.reasoning
    assert linkedin_suggestion.reasoning != x_suggestion.reasoning


@uses_test_session
def test_suggestion_uses_most_recent_research_run(db_session) -> None:
    brand, _user = _setup_brand(db_session)
    researched_at = datetime(2026, 8, 1, tzinfo=timezone.utc)

    old_post = _make_post(db_session, brand)
    _log_research_run(
        db_session,
        old_post,
        _research_brief(
            platforms=["linkedin"],
            trending_topics=["old topic"],
            researched_at=researched_at,
        ),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    new_post = _make_post(db_session, brand)
    newest_run = _log_research_run(
        db_session,
        new_post,
        _research_brief(
            platforms=["linkedin"],
            trending_topics=["fresh topic"],
            researched_at=researched_at + timedelta(days=1),
        ),
        created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )

    suggestion = suggest_target_datetime(db_session, brand.id, "linkedin")

    assert suggestion.source["agent_run_id"] == str(newest_run.id)


@uses_test_session
def test_suggestion_never_in_the_past(db_session) -> None:
    """A research run from far in the past must still yield a future
    suggestion (not, say, a date years ago)."""
    brand, _user = _setup_brand(db_session)
    post = _make_post(db_session, brand)
    _log_research_run(
        db_session,
        post,
        _research_brief(
            platforms=["linkedin"],
            trending_topics=["ancient history"],
            researched_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        ),
    )

    suggestion = suggest_target_datetime(db_session, brand.id, "linkedin")

    assert suggestion.target_datetime > datetime.now(timezone.utc)


# --- API-level (create-event) tests -------------------------------------


@uses_test_session
def test_create_event_without_target_datetime_uses_suggestion(db_session) -> None:
    brand, user = _setup_brand(db_session)
    post = _make_post(db_session, brand)
    _log_research_run(
        db_session,
        post,
        _research_brief(
            platforms=["linkedin"],
            trending_topics=["auto-scheduling launch"],
            researched_at=datetime.now(timezone.utc),
        ),
    )

    response = client.post(
        f"/brands/{brand.id}/calendar-events",
        json=_payload(target_platforms=["linkedin"]),
        headers=_auth_headers(user),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["target_datetime"] is not None
    suggested = datetime.fromisoformat(body["target_datetime"].replace("Z", "+00:00"))
    assert suggested > datetime.now(timezone.utc)


@uses_test_session
def test_create_event_explicit_target_datetime_not_overridden(db_session) -> None:
    brand, user = _setup_brand(db_session)
    post = _make_post(db_session, brand)
    _log_research_run(
        db_session,
        post,
        _research_brief(
            platforms=["linkedin"],
            trending_topics=["some trend"],
            researched_at=datetime.now(timezone.utc),
        ),
    )

    explicit = "2026-09-15T09:30:00Z"
    response = client.post(
        f"/brands/{brand.id}/calendar-events",
        json=_payload(target_platforms=["linkedin"], target_datetime=explicit),
        headers=_auth_headers(user),
    )

    assert response.status_code == 201
    body = response.json()
    assert datetime.fromisoformat(body["target_datetime"]) == datetime.fromisoformat(explicit.replace("Z", "+00:00"))


@uses_test_session
def test_create_event_without_datetime_and_without_signal_returns_422(db_session) -> None:
    brand, user = _setup_brand(db_session)

    response = client.post(
        f"/brands/{brand.id}/calendar-events",
        json=_payload(target_platforms=["linkedin"]),
        headers=_auth_headers(user),
    )

    assert response.status_code == 422


@uses_test_session
def test_update_does_not_reset_target_datetime_when_omitted(db_session) -> None:
    brand, user = _setup_brand(db_session)
    headers = _auth_headers(user)
    created = client.post(
        f"/brands/{brand.id}/calendar-events",
        json=_payload(target_platforms=["linkedin"], target_datetime="2026-09-01T12:00:00Z"),
        headers=headers,
    ).json()

    response = client.patch(
        f"/brands/{brand.id}/calendar-events/{created['id']}",
        json={"status": "approved"},
        headers=headers,
    )

    assert response.status_code == 200
    assert datetime.fromisoformat(response.json()["target_datetime"]) == datetime.fromisoformat(
        "2026-09-01T12:00:00+00:00"
    )


@uses_test_session
def test_update_respects_explicit_target_datetime_override(db_session) -> None:
    brand, user = _setup_brand(db_session)
    headers = _auth_headers(user)
    created = client.post(
        f"/brands/{brand.id}/calendar-events",
        json=_payload(target_platforms=["linkedin"], target_datetime="2026-09-01T12:00:00Z"),
        headers=headers,
    ).json()

    response = client.patch(
        f"/brands/{brand.id}/calendar-events/{created['id']}",
        json={"target_datetime": "2026-10-05T08:00:00Z"},
        headers=headers,
    )

    assert response.status_code == 200
    assert datetime.fromisoformat(response.json()["target_datetime"]) == datetime.fromisoformat(
        "2026-10-05T08:00:00+00:00"
    )
