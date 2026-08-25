"""Analytics aggregation queries over EngagementSnapshot — Issue #34.

Raw EngagementSnapshot rows (one per poll, #33) aren't directly useful to
a dashboard or to #35's weekly AI report — both want per-brand and
per-post *aggregates* (totals/averages broken down by platform) and
per-post *trends* (the raw time series) over a caller-chosen date range.

Performance is an explicit acceptance criterion for this issue: a brand
can accumulate many thousands of snapshot rows (frequent polling x many
posts x many platforms x a long-lived brand), so every aggregate here is
computed as a single SQL GROUP BY (SUM/AVG/COUNT) executed in Postgres —
never "fetch all matching rows and reduce them in Python". The only query
that returns row-per-snapshot is get_post_trend, which is inherently a
list (a trend *is* the raw series) rather than an aggregate, and is
already scoped to one post so its result set is bounded by that post's
poll history, not the whole brand's.

engagement_snapshots_post_id_platform_idx (migrations/versions/eee13f771456)
and posts_brand_id_idx (migrations/versions/63bac4f4c66f) let Postgres
satisfy both the per-post and per-brand queries via index scans instead of
sequential scans over engagement_snapshots/posts.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from apps.api.models.engagement_snapshot import EngagementSnapshot
from apps.api.models.post import Post


@dataclass
class PlatformAggregateRow:
    platform: str
    snapshot_count: int
    total_likes: int
    total_comments: int
    total_shares: int
    total_impressions: int
    average_likes: float
    average_comments: float
    average_shares: float
    average_impressions: float


@dataclass
class BrandSummary:
    post_count: int
    platforms: list[PlatformAggregateRow]
    overall: PlatformAggregateRow


@dataclass
class PostAggregate:
    platforms: list[PlatformAggregateRow]
    overall: PlatformAggregateRow


@dataclass
class TrendPoint:
    platform: str
    likes: int
    comments: int
    shares: int
    impressions: int
    polled_at: datetime


# Aggregate columns shared by every "totals + averages, grouped by
# platform" query below. COALESCE(..., 0) matters here: SUM/AVG over zero
# matching rows returns SQL NULL, not 0, and this module's callers (and
# their Pydantic response models) expect real numbers even for a
# platform/date-range with no snapshots.
def _aggregate_columns() -> list:
    return [
        func.count(EngagementSnapshot.id).label("snapshot_count"),
        func.coalesce(func.sum(EngagementSnapshot.likes), 0).label("total_likes"),
        func.coalesce(func.sum(EngagementSnapshot.comments), 0).label("total_comments"),
        func.coalesce(func.sum(EngagementSnapshot.shares), 0).label("total_shares"),
        func.coalesce(func.sum(EngagementSnapshot.impressions), 0).label("total_impressions"),
        func.coalesce(func.avg(EngagementSnapshot.likes), 0).label("average_likes"),
        func.coalesce(func.avg(EngagementSnapshot.comments), 0).label("average_comments"),
        func.coalesce(func.avg(EngagementSnapshot.shares), 0).label("average_shares"),
        func.coalesce(func.avg(EngagementSnapshot.impressions), 0).label("average_impressions"),
    ]


def _row_to_platform_aggregate(platform: str, row) -> PlatformAggregateRow:
    return PlatformAggregateRow(
        platform=platform,
        snapshot_count=int(row.snapshot_count),
        total_likes=int(row.total_likes),
        total_comments=int(row.total_comments),
        total_shares=int(row.total_shares),
        total_impressions=int(row.total_impressions),
        average_likes=float(row.average_likes),
        average_comments=float(row.average_comments),
        average_shares=float(row.average_shares),
        average_impressions=float(row.average_impressions),
    )


def get_brand_summary(
    db: Session, brand_id: uuid.UUID, start_date: datetime, end_date: datetime
) -> BrandSummary:
    """Per-brand aggregate over [start_date, end_date), broken down by
    platform, plus an "overall" row summed across every platform. Two
    GROUP BY queries total (one grouped by platform, one not) plus a
    COUNT(DISTINCT) for post_count — all executed in Postgres."""
    base_filters = [
        Post.brand_id == brand_id,
        EngagementSnapshot.polled_at >= start_date,
        EngagementSnapshot.polled_at < end_date,
    ]

    per_platform = (
        db.query(EngagementSnapshot.platform, *_aggregate_columns())
        .join(Post, Post.id == EngagementSnapshot.post_id)
        .filter(*base_filters)
        .group_by(EngagementSnapshot.platform)
        .order_by(EngagementSnapshot.platform)
        .all()
    )
    platforms = [_row_to_platform_aggregate(row.platform, row) for row in per_platform]

    overall_row = (
        db.query(*_aggregate_columns())
        .join(Post, Post.id == EngagementSnapshot.post_id)
        .filter(*base_filters)
        .one()
    )
    overall = _row_to_platform_aggregate("all", overall_row)

    post_count = (
        db.query(func.count(func.distinct(EngagementSnapshot.post_id)))
        .join(Post, Post.id == EngagementSnapshot.post_id)
        .filter(*base_filters)
        .scalar()
    ) or 0

    return BrandSummary(post_count=int(post_count), platforms=platforms, overall=overall)


def get_post_aggregate(
    db: Session, post_id: uuid.UUID, start_date: datetime, end_date: datetime
) -> PostAggregate:
    """Per-post aggregate over [start_date, end_date), broken down by
    platform — e.g. how one post performed on LinkedIn vs X. Callers are
    responsible for confirming the post belongs to the requesting brand
    before calling this (see apps/api/routers/analytics.py)."""
    base_filters = [
        EngagementSnapshot.post_id == post_id,
        EngagementSnapshot.polled_at >= start_date,
        EngagementSnapshot.polled_at < end_date,
    ]

    per_platform = (
        db.query(EngagementSnapshot.platform, *_aggregate_columns())
        .filter(*base_filters)
        .group_by(EngagementSnapshot.platform)
        .order_by(EngagementSnapshot.platform)
        .all()
    )
    platforms = [_row_to_platform_aggregate(row.platform, row) for row in per_platform]

    overall_row = db.query(*_aggregate_columns()).filter(*base_filters).one()
    overall = _row_to_platform_aggregate("all", overall_row)

    return PostAggregate(platforms=platforms, overall=overall)


def get_post_trend(
    db: Session,
    post_id: uuid.UUID,
    start_date: datetime,
    end_date: datetime,
    platform: str | None = None,
) -> list[TrendPoint]:
    """The raw time series for one post over [start_date, end_date),
    ordered by polled_at ascending — every EngagementSnapshot row polled
    in the window (optionally narrowed to one platform), unaggregated, so
    a caller can chart real engagement growth over time. Bounded by one
    post's poll history via engagement_snapshots_post_id_platform_idx, not
    a brand-wide scan."""
    query = db.query(EngagementSnapshot).filter(
        EngagementSnapshot.post_id == post_id,
        EngagementSnapshot.polled_at >= start_date,
        EngagementSnapshot.polled_at < end_date,
    )
    if platform is not None:
        query = query.filter(EngagementSnapshot.platform == platform)

    rows = query.order_by(EngagementSnapshot.polled_at.asc()).all()
    return [
        TrendPoint(
            platform=row.platform,
            likes=row.likes,
            comments=row.comments,
            shares=row.shares,
            impressions=row.impressions,
            polled_at=row.polled_at,
        )
        for row in rows
    ]
