import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from apps.api.auth.jwt import create_access_token, hash_password
from apps.api.main import app
from apps.api.models import Brand, EngagementSnapshot, Organization, Post, User, UserRole

client = TestClient(app)
uses_test_session = pytest.mark.usefixtures("override_get_db")


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


BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _iso_range(start: datetime, end: datetime) -> dict[str, str]:
    return {"start_date": start.isoformat(), "end_date": end.isoformat()}


# ---------------------------------------------------------------------------
# Brand summary: correctness
# ---------------------------------------------------------------------------


@uses_test_session
def test_brand_summary_returns_correct_per_platform_aggregates(db_session) -> None:
    brand, user = _setup_brand(db_session)
    post_a = _make_post(db_session, brand)
    post_b = _make_post(db_session, brand)

    db_session.add_all(
        [
            _snapshot(post_a, "linkedin", BASE_TIME, likes=10, comments=1, shares=2, impressions=100),
            _snapshot(
                post_a,
                "linkedin",
                BASE_TIME + timedelta(hours=1),
                likes=20,
                comments=3,
                shares=4,
                impressions=200,
            ),
            _snapshot(post_b, "x", BASE_TIME, likes=5, comments=0, shares=1, impressions=50),
        ]
    )
    db_session.flush()

    response = client.get(
        f"/brands/{brand.id}/analytics/summary",
        params=_iso_range(BASE_TIME - timedelta(hours=1), BASE_TIME + timedelta(hours=2)),
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["post_count"] == 2

    platforms = {row["platform"]: row for row in body["platforms"]}
    assert set(platforms) == {"linkedin", "x"}

    linkedin = platforms["linkedin"]
    assert linkedin["snapshot_count"] == 2
    assert linkedin["total_likes"] == 30
    assert linkedin["total_comments"] == 4
    assert linkedin["total_shares"] == 6
    assert linkedin["total_impressions"] == 300
    assert linkedin["average_likes"] == pytest.approx(15.0)

    x = platforms["x"]
    assert x["snapshot_count"] == 1
    assert x["total_likes"] == 5

    overall = body["overall"]
    assert overall["snapshot_count"] == 3
    assert overall["total_likes"] == 35
    assert overall["total_comments"] == 4
    assert overall["total_shares"] == 7
    assert overall["total_impressions"] == 350


@uses_test_session
def test_brand_summary_excludes_snapshots_outside_date_range(db_session) -> None:
    brand, user = _setup_brand(db_session)
    post = _make_post(db_session, brand)

    db_session.add_all(
        [
            _snapshot(post, "linkedin", BASE_TIME, likes=100),
            _snapshot(post, "linkedin", BASE_TIME - timedelta(days=30), likes=999),
            _snapshot(post, "linkedin", BASE_TIME + timedelta(days=30), likes=999),
        ]
    )
    db_session.flush()

    response = client.get(
        f"/brands/{brand.id}/analytics/summary",
        params=_iso_range(BASE_TIME - timedelta(hours=1), BASE_TIME + timedelta(hours=1)),
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["overall"]["snapshot_count"] == 1
    assert body["overall"]["total_likes"] == 100


@uses_test_session
def test_brand_summary_excludes_other_brands_posts(db_session) -> None:
    brand, user = _setup_brand(db_session)
    other_brand = Brand(organization_id=user.organization_id, name="Other Brand")
    db_session.add(other_brand)
    db_session.flush()

    own_post = _make_post(db_session, brand)
    other_post = _make_post(db_session, other_brand)
    db_session.add_all(
        [
            _snapshot(own_post, "linkedin", BASE_TIME, likes=10),
            _snapshot(other_post, "linkedin", BASE_TIME, likes=999),
        ]
    )
    db_session.flush()

    response = client.get(
        f"/brands/{brand.id}/analytics/summary",
        params=_iso_range(BASE_TIME - timedelta(hours=1), BASE_TIME + timedelta(hours=1)),
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["overall"]["total_likes"] == 10
    assert body["post_count"] == 1


@uses_test_session
def test_brand_summary_defaults_to_last_30_days_when_no_range_given(db_session) -> None:
    brand, user = _setup_brand(db_session)
    post = _make_post(db_session, brand)
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            _snapshot(post, "linkedin", now - timedelta(days=1), likes=7),
            _snapshot(post, "linkedin", now - timedelta(days=90), likes=999),
        ]
    )
    db_session.flush()

    response = client.get(f"/brands/{brand.id}/analytics/summary", headers=_auth_headers(user))

    assert response.status_code == 200
    body = response.json()
    assert body["overall"]["total_likes"] == 7


# ---------------------------------------------------------------------------
# Per-post aggregate + trend: correctness
# ---------------------------------------------------------------------------


@uses_test_session
def test_post_aggregate_returns_correct_numbers(db_session) -> None:
    brand, user = _setup_brand(db_session)
    post = _make_post(db_session, brand)
    other_post = _make_post(db_session, brand)

    db_session.add_all(
        [
            _snapshot(post, "linkedin", BASE_TIME, likes=10, impressions=100),
            _snapshot(post, "x", BASE_TIME, likes=3, impressions=30),
            _snapshot(other_post, "linkedin", BASE_TIME, likes=500, impressions=5000),
        ]
    )
    db_session.flush()

    response = client.get(
        f"/brands/{brand.id}/analytics/posts/{post.id}",
        params=_iso_range(BASE_TIME - timedelta(hours=1), BASE_TIME + timedelta(hours=1)),
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    body = response.json()
    platforms = {row["platform"]: row for row in body["platforms"]}
    assert platforms["linkedin"]["total_likes"] == 10
    assert platforms["x"]["total_likes"] == 3
    assert body["overall"]["total_likes"] == 13
    assert body["overall"]["total_impressions"] == 130


@uses_test_session
def test_post_trend_returns_points_ordered_by_polled_at(db_session) -> None:
    brand, user = _setup_brand(db_session)
    post = _make_post(db_session, brand)

    db_session.add_all(
        [
            _snapshot(post, "linkedin", BASE_TIME + timedelta(hours=2), likes=30),
            _snapshot(post, "linkedin", BASE_TIME, likes=10),
            _snapshot(post, "linkedin", BASE_TIME + timedelta(hours=1), likes=20),
        ]
    )
    db_session.flush()

    response = client.get(
        f"/brands/{brand.id}/analytics/posts/{post.id}/trend",
        params=_iso_range(BASE_TIME - timedelta(hours=1), BASE_TIME + timedelta(hours=3)),
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    points = response.json()["points"]
    assert [p["likes"] for p in points] == [10, 20, 30]


@uses_test_session
def test_post_trend_filters_by_platform(db_session) -> None:
    brand, user = _setup_brand(db_session)
    post = _make_post(db_session, brand)

    db_session.add_all(
        [
            _snapshot(post, "linkedin", BASE_TIME, likes=10),
            _snapshot(post, "x", BASE_TIME, likes=99),
        ]
    )
    db_session.flush()

    response = client.get(
        f"/brands/{brand.id}/analytics/posts/{post.id}/trend",
        params={
            **_iso_range(BASE_TIME - timedelta(hours=1), BASE_TIME + timedelta(hours=1)),
            "platform": "linkedin",
        },
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    points = response.json()["points"]
    assert len(points) == 1
    assert points[0]["platform"] == "linkedin"
    assert points[0]["likes"] == 10


# ---------------------------------------------------------------------------
# Org/brand scoping — 404, not 403, matching this repo's convention
# ---------------------------------------------------------------------------


@uses_test_session
def test_cross_org_brand_summary_returns_404(db_session) -> None:
    brand, _owner = _setup_brand(db_session, UserRole.EDITOR, suffix="-1")
    _other_brand, other_user = _setup_brand(db_session, UserRole.EDITOR, suffix="-2")

    response = client.get(
        f"/brands/{brand.id}/analytics/summary", headers=_auth_headers(other_user)
    )

    assert response.status_code == 404


@uses_test_session
def test_cross_org_post_aggregate_returns_404(db_session) -> None:
    brand, owner = _setup_brand(db_session, UserRole.EDITOR, suffix="-1")
    _other_brand, other_user = _setup_brand(db_session, UserRole.EDITOR, suffix="-2")
    post = _make_post(db_session, brand)
    db_session.add(_snapshot(post, "linkedin", BASE_TIME, likes=10))
    db_session.flush()

    response = client.get(
        f"/brands/{brand.id}/analytics/posts/{post.id}", headers=_auth_headers(other_user)
    )

    assert response.status_code == 404


@uses_test_session
def test_post_from_different_brand_returns_404(db_session) -> None:
    brand, user = _setup_brand(db_session)
    other_brand = Brand(organization_id=user.organization_id, name="Other Brand")
    db_session.add(other_brand)
    db_session.flush()
    other_post = _make_post(db_session, other_brand)

    response = client.get(
        f"/brands/{brand.id}/analytics/posts/{other_post.id}", headers=_auth_headers(user)
    )

    assert response.status_code == 404


@uses_test_session
def test_unknown_brand_returns_404(db_session) -> None:
    _brand, user = _setup_brand(db_session)

    response = client.get(
        f"/brands/{uuid.uuid4()}/analytics/summary", headers=_auth_headers(user)
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Performance: aggregation must be real DB-side SQL, not Python-side
# reduction over every row — proven by seeding a realistic volume and
# asserting both correctness and wall-clock time.
# ---------------------------------------------------------------------------

NUM_POSTS = 5
PLATFORMS = ["linkedin", "x"]
SNAPSHOTS_PER_POST_PLATFORM = 300  # 5 * 2 * 300 = 3,000 rows total
LIKES_PER_SNAPSHOT = 4
COMMENTS_PER_SNAPSHOT = 1
SHARES_PER_SNAPSHOT = 2
IMPRESSIONS_PER_SNAPSHOT = 50


def _seed_volume(db_session, brand: Brand) -> list[Post]:
    posts = [_make_post(db_session, brand) for _ in range(NUM_POSTS)]

    snapshots = []
    for post in posts:
        for platform in PLATFORMS:
            for i in range(SNAPSHOTS_PER_POST_PLATFORM):
                snapshots.append(
                    _snapshot(
                        post,
                        platform,
                        BASE_TIME + timedelta(minutes=i),
                        likes=LIKES_PER_SNAPSHOT,
                        comments=COMMENTS_PER_SNAPSHOT,
                        shares=SHARES_PER_SNAPSHOT,
                        impressions=IMPRESSIONS_PER_SNAPSHOT,
                    )
                )
    db_session.bulk_save_objects(snapshots)
    db_session.flush()
    return posts


@uses_test_session
def test_brand_summary_aggregation_is_correct_and_fast_at_seeded_volume(db_session) -> None:
    brand, user = _setup_brand(db_session)
    _seed_volume(db_session, brand)

    started = time.perf_counter()
    response = client.get(
        f"/brands/{brand.id}/analytics/summary",
        params=_iso_range(BASE_TIME - timedelta(hours=1), BASE_TIME + timedelta(days=1)),
        headers=_auth_headers(user),
    )
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    # This is a generous ceiling meant to catch "fetching every row and
    # summing in Python" (which degrades with row count), not to chase a
    # specific benchmark number — a real GROUP BY SUM/AVG/COUNT in
    # Postgres over a few thousand rows should be nowhere near this.
    assert elapsed < 2.0, f"brand summary aggregate over {NUM_POSTS * len(PLATFORMS) * SNAPSHOTS_PER_POST_PLATFORM} rows took {elapsed:.3f}s"

    body = response.json()
    assert body["post_count"] == NUM_POSTS

    per_platform_count = NUM_POSTS * SNAPSHOTS_PER_POST_PLATFORM
    for row in body["platforms"]:
        assert row["snapshot_count"] == per_platform_count
        assert row["total_likes"] == per_platform_count * LIKES_PER_SNAPSHOT
        assert row["total_comments"] == per_platform_count * COMMENTS_PER_SNAPSHOT
        assert row["total_shares"] == per_platform_count * SHARES_PER_SNAPSHOT
        assert row["total_impressions"] == per_platform_count * IMPRESSIONS_PER_SNAPSHOT
        assert row["average_likes"] == pytest.approx(float(LIKES_PER_SNAPSHOT))

    total_rows = NUM_POSTS * len(PLATFORMS) * SNAPSHOTS_PER_POST_PLATFORM
    overall = body["overall"]
    assert overall["snapshot_count"] == total_rows
    assert overall["total_likes"] == total_rows * LIKES_PER_SNAPSHOT
    assert overall["total_impressions"] == total_rows * IMPRESSIONS_PER_SNAPSHOT


@uses_test_session
def test_post_aggregate_is_correct_at_seeded_volume(db_session) -> None:
    brand, user = _setup_brand(db_session)
    posts = _seed_volume(db_session, brand)
    target_post = posts[0]

    started = time.perf_counter()
    response = client.get(
        f"/brands/{brand.id}/analytics/posts/{target_post.id}",
        params=_iso_range(BASE_TIME - timedelta(hours=1), BASE_TIME + timedelta(days=1)),
        headers=_auth_headers(user),
    )
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert elapsed < 2.0

    body = response.json()
    platforms = {row["platform"]: row for row in body["platforms"]}
    for platform in PLATFORMS:
        assert platforms[platform]["snapshot_count"] == SNAPSHOTS_PER_POST_PLATFORM
        assert platforms[platform]["total_likes"] == SNAPSHOTS_PER_POST_PLATFORM * LIKES_PER_SNAPSHOT
