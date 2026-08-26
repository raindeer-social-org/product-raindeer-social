import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import CurrentUser, get_current_user
from apps.api.config.database import get_db
from apps.api.models import Brand, Post
from apps.api.models.report import Report
from apps.api.schemas.analytics import (
    BrandAnalyticsSummary,
    EngagementSnapshotPoint,
    PlatformAggregate,
    PostAnalyticsAggregate,
    PostAnalyticsTrend,
    ReportListOut,
    ReportOut,
)
from apps.api.services import analytics_aggregation

router = APIRouter(prefix="/brands/{brand_id}/analytics", tags=["analytics"])

# Same default window used across the dashboard/report if a caller doesn't
# specify one — recent enough to be useful, wide enough to show a trend.
DEFAULT_WINDOW_DAYS = 30

# Cap on how many past weekly reports a single list call returns — a
# brand accumulates one row per week indefinitely (Issue #35's Report is
# an append-only log, apps/api/models/report.py), so this keeps the
# default response bounded without needing full pagination yet.
DEFAULT_REPORT_LIMIT = 20


def _get_org_brand(db: Session, brand_id: uuid.UUID, org_id: str) -> Brand:
    brand = (
        db.query(Brand)
        .filter(Brand.id == brand_id, Brand.organization_id == uuid.UUID(org_id))
        .first()
    )
    if brand is None:
        # 404, not 403 — don't leak whether a brand with this id exists in
        # another org.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
    return brand


def _to_report_out(report: Report) -> ReportOut:
    return ReportOut(
        id=str(report.id),
        brand_id=str(report.brand_id),
        period_start=report.period_start,
        period_end=report.period_end,
        summary=report.summary,
        recommendations=report.recommendations,
        metrics=report.metrics,
        model=report.model,
        created_at=report.created_at,
    )


def _get_brand_post_or_404(db: Session, brand_id: uuid.UUID, post_id: uuid.UUID) -> Post:
    post = (
        db.query(Post)
        .filter(Post.id == post_id, Post.brand_id == brand_id)
        .first()
    )
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post


def _resolve_date_range(
    start_date: datetime | None, end_date: datetime | None
) -> tuple[datetime, datetime]:
    """Defaults to the last DEFAULT_WINDOW_DAYS days ending now (UTC) when
    either bound is omitted, so callers aren't forced to compute a range
    just to see recent activity. Naive datetimes (no tzinfo in the query
    string) are treated as UTC, matching EngagementSnapshot.polled_at's
    timezone-aware storage."""
    resolved_end = end_date or datetime.now(timezone.utc)
    resolved_start = start_date or (resolved_end - timedelta(days=DEFAULT_WINDOW_DAYS))

    if resolved_end.tzinfo is None:
        resolved_end = resolved_end.replace(tzinfo=timezone.utc)
    if resolved_start.tzinfo is None:
        resolved_start = resolved_start.replace(tzinfo=timezone.utc)

    if resolved_start >= resolved_end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date must be before end_date",
        )
    return resolved_start, resolved_end


def _to_platform_aggregate(row: analytics_aggregation.PlatformAggregateRow) -> PlatformAggregate:
    return PlatformAggregate(
        platform=row.platform,
        snapshot_count=row.snapshot_count,
        total_likes=row.total_likes,
        total_comments=row.total_comments,
        total_shares=row.total_shares,
        total_impressions=row.total_impressions,
        average_likes=row.average_likes,
        average_comments=row.average_comments,
        average_shares=row.average_shares,
        average_impressions=row.average_impressions,
    )


@router.get("/summary", response_model=BrandAnalyticsSummary)
def get_brand_summary(
    brand_id: uuid.UUID,
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> BrandAnalyticsSummary:
    _get_org_brand(db, brand_id, current_user.org_id)
    resolved_start, resolved_end = _resolve_date_range(start_date, end_date)

    summary = analytics_aggregation.get_brand_summary(db, brand_id, resolved_start, resolved_end)
    return BrandAnalyticsSummary(
        brand_id=str(brand_id),
        start_date=resolved_start,
        end_date=resolved_end,
        post_count=summary.post_count,
        platforms=[_to_platform_aggregate(row) for row in summary.platforms],
        overall=_to_platform_aggregate(summary.overall),
    )


@router.get("/posts/{post_id}", response_model=PostAnalyticsAggregate)
def get_post_aggregate(
    brand_id: uuid.UUID,
    post_id: uuid.UUID,
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PostAnalyticsAggregate:
    _get_org_brand(db, brand_id, current_user.org_id)
    _get_brand_post_or_404(db, brand_id, post_id)
    resolved_start, resolved_end = _resolve_date_range(start_date, end_date)

    aggregate = analytics_aggregation.get_post_aggregate(db, post_id, resolved_start, resolved_end)
    return PostAnalyticsAggregate(
        post_id=str(post_id),
        start_date=resolved_start,
        end_date=resolved_end,
        platforms=[_to_platform_aggregate(row) for row in aggregate.platforms],
        overall=_to_platform_aggregate(aggregate.overall),
    )


@router.get("/posts/{post_id}/trend", response_model=PostAnalyticsTrend)
def get_post_trend(
    brand_id: uuid.UUID,
    post_id: uuid.UUID,
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    platform: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PostAnalyticsTrend:
    _get_org_brand(db, brand_id, current_user.org_id)
    _get_brand_post_or_404(db, brand_id, post_id)
    resolved_start, resolved_end = _resolve_date_range(start_date, end_date)

    points = analytics_aggregation.get_post_trend(
        db, post_id, resolved_start, resolved_end, platform=platform
    )
    return PostAnalyticsTrend(
        post_id=str(post_id),
        start_date=resolved_start,
        end_date=resolved_end,
        points=[
            EngagementSnapshotPoint(
                platform=p.platform,
                likes=p.likes,
                comments=p.comments,
                shares=p.shares,
                impressions=p.impressions,
                polled_at=p.polled_at,
            )
            for p in points
        ],
    )


@router.get("/reports", response_model=ReportListOut)
def list_reports(
    brand_id: uuid.UUID,
    limit: int = Query(DEFAULT_REPORT_LIMIT, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ReportListOut:
    """Issue #35: read back this brand's weekly AI-generated reports,
    newest first. Reports are appended by
    packages/agents/reporting/weekly_report.py (run on a schedule via
    apps/api/worker.py's generate-weekly-reports Celery Beat entry) — this
    endpoint is a plain read of that log, same org/brand-scoping (404,
    not 403, on cross-org access) as every other endpoint in this
    router."""
    _get_org_brand(db, brand_id, current_user.org_id)

    reports = (
        db.query(Report)
        .filter(Report.brand_id == brand_id)
        .order_by(Report.created_at.desc())
        .limit(limit)
        .all()
    )
    return ReportListOut(
        brand_id=str(brand_id), reports=[_to_report_out(report) for report in reports]
    )


@router.get("/reports/{report_id}", response_model=ReportOut)
def get_report(
    brand_id: uuid.UUID,
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ReportOut:
    _get_org_brand(db, brand_id, current_user.org_id)

    report = (
        db.query(Report)
        .filter(Report.id == report_id, Report.brand_id == brand_id)
        .first()
    )
    if report is None:
        # 404, not 403 — same convention as _get_org_brand/
        # _get_brand_post_or_404 above: don't leak whether a report with
        # this id exists under a different brand/org.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return _to_report_out(report)
