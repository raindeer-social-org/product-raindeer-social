"""Tests for the Issue #35 weekly AI-generated report.

Per the issue's acceptance criteria:
  1. A Report is generated weekly per brand with REAL metrics referenced
     (not hallucinated placeholders) — proven here by seeding real
     EngagementSnapshot data (same seeding approach test_analytics.py
     uses) with distinctive, easy-to-assert-on numbers, and checking both
     that the LLM prompt was given those exact numbers and that the
     mocked response's numbers round-trip into the stored Report.
  2. Uses LLMProvider exclusively (mocked through
     packages.agents.reporting.weekly_report.get_llm_provider), never a
     direct vendor SDK call (asserted via httpx.post never being hit).
  3. An AgentRun row is logged with agent_type=weekly_report.
  4. The report is accessible via the
     GET /brands/{brand_id}/analytics/reports (list) and
     GET /brands/{brand_id}/analytics/reports/{report_id} (detail)
     endpoints, with the same org/brand-scoping (404, not 403) every
     other endpoint in this router uses.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from apps.api.auth.jwt import create_access_token, hash_password
from apps.api.main import app
from apps.api.models import (
    AgentRun,
    AgentType,
    Brand,
    EngagementSnapshot,
    Organization,
    Post,
    Report,
    User,
    UserRole,
)
from packages.agents.reporting.weekly_report import (
    REPORT_PERIOD_DAYS,
    WeeklyReportError,
    generate_weekly_report,
)
from packages.integrations.llm.base import LLMResponse

client = TestClient(app)
uses_test_session = pytest.mark.usefixtures("override_get_db")

LLM_PATCH_TARGET = "packages.agents.reporting.weekly_report.get_llm_provider"

BASE_TIME = datetime(2026, 1, 8, tzinfo=timezone.utc)
# All the seeded snapshots below land inside [PERIOD_END - 7d, PERIOD_END),
# so the report's own period_start/period_end resolution matches exactly
# what the test asserts against.
PERIOD_END = BASE_TIME + timedelta(hours=6)


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
    brand = Brand(organization_id=org.id, name="Acme Widgets", industry="Consumer Goods")
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


def _snapshot(
    post: Post,
    platform: str,
    polled_at: datetime,
    likes: int = 0,
    comments: int = 0,
    shares: int = 0,
    impressions: int = 0,
) -> EngagementSnapshot:
    return EngagementSnapshot(
        post_id=post.id,
        platform=platform,
        likes=likes,
        comments=comments,
        shares=shares,
        impressions=impressions,
        polled_at=polled_at,
    )


# Distinctive, easy-to-grep-for numbers so assertions can't accidentally
# pass against some other coincidental figure.
LINKEDIN_LIKES, LINKEDIN_COMMENTS, LINKEDIN_SHARES, LINKEDIN_IMPRESSIONS = 123, 45, 6, 7890
X_LIKES, X_COMMENTS, X_SHARES, X_IMPRESSIONS = 55, 11, 2, 3210
TOTAL_LIKES = LINKEDIN_LIKES + X_LIKES  # 178
TOTAL_IMPRESSIONS = LINKEDIN_IMPRESSIONS + X_IMPRESSIONS  # 11100


def _seed_real_engagement(db_session, brand: Brand) -> None:
    post_a = _make_post(db_session, brand)
    post_b = _make_post(db_session, brand)
    db_session.add_all(
        [
            _snapshot(
                post_a,
                "linkedin",
                BASE_TIME,
                likes=LINKEDIN_LIKES,
                comments=LINKEDIN_COMMENTS,
                shares=LINKEDIN_SHARES,
                impressions=LINKEDIN_IMPRESSIONS,
            ),
            _snapshot(
                post_b,
                "x",
                BASE_TIME + timedelta(hours=1),
                likes=X_LIKES,
                comments=X_COMMENTS,
                shares=X_SHARES,
                impressions=X_IMPRESSIONS,
            ),
            # Outside the report's 7-day window (too far in the past) —
            # must not be counted, proving the window is actually honored.
            _snapshot(post_a, "linkedin", BASE_TIME - timedelta(days=30), likes=999999),
        ]
    )
    db_session.flush()


def _llm_response(summary: str, recommendations: list[str]) -> LLMResponse:
    return LLMResponse(
        text=json.dumps({"summary": summary, "recommendations": recommendations}),
        model="openrouter/free",
        input_tokens=200,
        output_tokens=120,
    )


_MOCKED_SUMMARY = (
    f"LinkedIn drove {LINKEDIN_LIKES} likes on the launch post while X trailed with "
    f"{X_LIKES} likes, for a combined {TOTAL_LIKES} likes and {TOTAL_IMPRESSIONS} "
    "impressions across both platforms this week."
)
_MOCKED_RECOMMENDATIONS = [
    f"Double down on LinkedIn — it drove {LINKEDIN_LIKES} likes versus X's {X_LIKES}.",
    f"Investigate why X only reached {X_IMPRESSIONS} impressions this period.",
]


# --- generation-level tests ----------------------------------------------


@uses_test_session
def test_report_references_real_seeded_numbers_not_generic_filler(db_session) -> None:
    """Core acceptance criterion: the LLM is handed the real aggregate
    numbers (not just told where to find them), and the mocked response's
    numbers round-trip into the persisted Report — proving the pipeline
    doesn't silently discard or paraphrase away the real figures."""
    brand, _user = _setup_brand(db_session)
    _seed_real_engagement(db_session, brand)

    with patch(LLM_PATCH_TARGET) as mock_llm, patch("httpx.post") as mock_httpx_post:
        mock_llm.return_value.complete.return_value = _llm_response(
            _MOCKED_SUMMARY, _MOCKED_RECOMMENDATIONS
        )
        report = generate_weekly_report(db_session, brand.id, period_end=PERIOD_END)

    # LLMProvider exclusively — never a direct vendor SDK call.
    mock_llm.return_value.complete.assert_called_once()
    mock_httpx_post.assert_not_called()

    # The prompt actually given to the LLM must contain the real numbers,
    # not just point at where to find them.
    _, kwargs = mock_llm.return_value.complete.call_args
    prompt = kwargs["prompt"]
    assert str(LINKEDIN_LIKES) in prompt
    assert str(X_LIKES) in prompt
    assert str(TOTAL_LIKES) in prompt
    assert str(TOTAL_IMPRESSIONS) in prompt
    # The out-of-window snapshot's inflated likes must never appear.
    assert "999999" not in prompt

    # The mocked response's real-number-citing text round-trips into the
    # stored Report, unmodified.
    assert report.summary == _MOCKED_SUMMARY
    assert str(LINKEDIN_LIKES) in report.summary
    assert str(TOTAL_LIKES) in report.summary
    assert report.recommendations == _MOCKED_RECOMMENDATIONS

    # The stored metrics snapshot matches the real aggregate, not the
    # out-of-window inflated post.
    assert report.metrics["overall"]["total_likes"] == TOTAL_LIKES
    assert report.metrics["overall"]["total_impressions"] == TOTAL_IMPRESSIONS
    platforms = {p["platform"]: p for p in report.metrics["platforms"]}
    assert platforms["linkedin"]["total_likes"] == LINKEDIN_LIKES
    assert platforms["x"]["total_likes"] == X_LIKES

    assert report.brand_id == brand.id
    assert report.period_end == PERIOD_END
    assert report.period_start == PERIOD_END - timedelta(days=REPORT_PERIOD_DAYS)
    assert report.model == "openrouter/free"


@uses_test_session
def test_agent_run_logged_with_weekly_report_type(db_session) -> None:
    brand, _user = _setup_brand(db_session)
    _seed_real_engagement(db_session, brand)

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = _llm_response(
            _MOCKED_SUMMARY, _MOCKED_RECOMMENDATIONS
        )
        report = generate_weekly_report(db_session, brand.id, period_end=PERIOD_END)

    runs = db_session.query(AgentRun).filter(AgentRun.agent_type == AgentType.WEEKLY_REPORT).all()
    assert len(runs) == 1
    run = runs[0]
    assert run.post_id is None
    assert run.input["brand_id"] == str(brand.id)
    assert run.output["report_id"] == str(report.id)
    assert run.output["summary"] == _MOCKED_SUMMARY
    assert run.model == "openrouter/free"


@uses_test_session
def test_unknown_brand_raises(db_session) -> None:
    with pytest.raises(WeeklyReportError):
        generate_weekly_report(db_session, uuid.uuid4())


@uses_test_session
def test_llm_failure_falls_back_to_real_numbers_not_raising(db_session) -> None:
    """Degrade-on-failure contract: a broken LLM provider must not crash
    the weekly sweep, and the fallback text must still cite the real
    seeded numbers rather than being empty/generic-only."""
    brand, _user = _setup_brand(db_session)
    _seed_real_engagement(db_session, brand)

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.side_effect = RuntimeError("provider unavailable")
        report = generate_weekly_report(db_session, brand.id, period_end=PERIOD_END)

    assert str(TOTAL_LIKES) in report.summary
    assert str(TOTAL_IMPRESSIONS) in report.summary
    assert len(report.recommendations) >= 1

    run = (
        db_session.query(AgentRun)
        .filter(AgentRun.agent_type == AgentType.WEEKLY_REPORT)
        .one()
    )
    assert run.output["report_id"] == str(report.id)


@uses_test_session
def test_unparseable_llm_response_falls_back_to_real_numbers(db_session) -> None:
    brand, _user = _setup_brand(db_session)
    _seed_real_engagement(db_session, brand)

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = LLMResponse(
            text="not json at all", model="openrouter/free", input_tokens=10, output_tokens=5
        )
        report = generate_weekly_report(db_session, brand.id, period_end=PERIOD_END)

    assert str(TOTAL_LIKES) in report.summary


# --- API-level tests -------------------------------------------------------


@uses_test_session
def test_report_accessible_via_list_and_detail_endpoints(db_session) -> None:
    brand, user = _setup_brand(db_session)
    _seed_real_engagement(db_session, brand)

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = _llm_response(
            _MOCKED_SUMMARY, _MOCKED_RECOMMENDATIONS
        )
        report = generate_weekly_report(db_session, brand.id, period_end=PERIOD_END)

    list_response = client.get(
        f"/brands/{brand.id}/analytics/reports", headers=_auth_headers(user)
    )
    assert list_response.status_code == 200
    body = list_response.json()
    assert body["brand_id"] == str(brand.id)
    assert len(body["reports"]) == 1
    listed = body["reports"][0]
    assert listed["id"] == str(report.id)
    assert listed["summary"] == _MOCKED_SUMMARY
    assert listed["recommendations"] == _MOCKED_RECOMMENDATIONS
    assert listed["metrics"]["overall"]["total_likes"] == TOTAL_LIKES

    detail_response = client.get(
        f"/brands/{brand.id}/analytics/reports/{report.id}", headers=_auth_headers(user)
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["id"] == str(report.id)
    assert detail["summary"] == _MOCKED_SUMMARY
    assert str(LINKEDIN_LIKES) in detail["summary"]


@uses_test_session
def test_reports_list_orders_newest_first(db_session) -> None:
    brand, user = _setup_brand(db_session)
    _seed_real_engagement(db_session, brand)

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = _llm_response(
            "first week summary", ["rec"]
        )
        first = generate_weekly_report(
            db_session, brand.id, period_end=PERIOD_END - timedelta(days=7)
        )
        first.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

        mock_llm.return_value.complete.return_value = _llm_response(
            "second week summary", ["rec"]
        )
        second = generate_weekly_report(db_session, brand.id, period_end=PERIOD_END)
        second.created_at = datetime(2026, 1, 8, tzinfo=timezone.utc)
    db_session.flush()

    response = client.get(f"/brands/{brand.id}/analytics/reports", headers=_auth_headers(user))
    assert response.status_code == 200
    ids = [row["id"] for row in response.json()["reports"]]
    assert ids == [str(second.id), str(first.id)]


@uses_test_session
def test_cross_org_reports_list_returns_404(db_session) -> None:
    brand, _owner = _setup_brand(db_session, UserRole.EDITOR, suffix="-1")
    _other_brand, other_user = _setup_brand(db_session, UserRole.EDITOR, suffix="-2")

    response = client.get(
        f"/brands/{brand.id}/analytics/reports", headers=_auth_headers(other_user)
    )
    assert response.status_code == 404


@uses_test_session
def test_cross_org_report_detail_returns_404(db_session) -> None:
    brand, owner = _setup_brand(db_session, UserRole.EDITOR, suffix="-1")
    _other_brand, other_user = _setup_brand(db_session, UserRole.EDITOR, suffix="-2")
    _seed_real_engagement(db_session, brand)

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = _llm_response(
            _MOCKED_SUMMARY, _MOCKED_RECOMMENDATIONS
        )
        report = generate_weekly_report(db_session, brand.id, period_end=PERIOD_END)

    response = client.get(
        f"/brands/{brand.id}/analytics/reports/{report.id}", headers=_auth_headers(other_user)
    )
    assert response.status_code == 404


@uses_test_session
def test_report_from_different_brand_returns_404(db_session) -> None:
    brand, user = _setup_brand(db_session)
    other_brand = Brand(organization_id=user.organization_id, name="Other Brand")
    db_session.add(other_brand)
    db_session.flush()
    _seed_real_engagement(db_session, other_brand)

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = _llm_response(
            _MOCKED_SUMMARY, _MOCKED_RECOMMENDATIONS
        )
        other_report = generate_weekly_report(db_session, other_brand.id, period_end=PERIOD_END)

    response = client.get(
        f"/brands/{brand.id}/analytics/reports/{other_report.id}", headers=_auth_headers(user)
    )
    assert response.status_code == 404


@uses_test_session
def test_unknown_report_id_returns_404(db_session) -> None:
    brand, user = _setup_brand(db_session)

    response = client.get(
        f"/brands/{brand.id}/analytics/reports/{uuid.uuid4()}", headers=_auth_headers(user)
    )
    assert response.status_code == 404
