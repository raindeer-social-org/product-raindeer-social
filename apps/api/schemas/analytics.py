from datetime import datetime
from typing import Any

from pydantic import BaseModel


class PlatformAggregate(BaseModel):
    """Totals/averages for one platform within a requested date range —
    the per-platform breakdown row both the brand summary and the
    per-post aggregate endpoints return. total_* are real SQL SUM()s and
    average_* are real SQL AVG()s (apps/api/services/analytics_aggregation.py)
    computed in Postgres, not accumulated in Python."""

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


class BrandAnalyticsSummary(BaseModel):
    """Per-brand aggregate over [start_date, end_date), broken down by
    platform, plus an overall row summed across every platform."""

    brand_id: str
    start_date: datetime
    end_date: datetime
    post_count: int
    platforms: list[PlatformAggregate]
    overall: PlatformAggregate


class PostAnalyticsAggregate(BaseModel):
    """Per-post aggregate over [start_date, end_date), broken down by
    platform — e.g. "how did this one post perform on LinkedIn vs X over
    the last 30 days", as opposed to the raw time series the /trend
    endpoint returns."""

    post_id: str
    start_date: datetime
    end_date: datetime
    platforms: list[PlatformAggregate]
    overall: PlatformAggregate


class EngagementSnapshotPoint(BaseModel):
    """One raw point in a post's engagement time series."""

    platform: str
    likes: int
    comments: int
    shares: int
    impressions: int
    polled_at: datetime


class PostAnalyticsTrend(BaseModel):
    """The time series for one post over [start_date, end_date), ordered
    by polled_at ascending — every EngagementSnapshot row polled for this
    post in the window, not aggregated, so a caller (a chart, #35's
    report) can see actual engagement growth over time."""

    post_id: str
    start_date: datetime
    end_date: datetime
    points: list[EngagementSnapshotPoint]


class ReportOut(BaseModel):
    """One weekly AI-generated report (Issue #35) — an immutable row, so
    unlike the aggregate endpoints above (which recompute live) this is
    just a read of what packages/agents/reporting/weekly_report.py
    already generated and stored. `metrics` is the exact
    analytics_aggregation.BrandSummary the report was generated from, so
    a caller can verify `summary`/`recommendations` against real
    numbers."""

    id: str
    brand_id: str
    period_start: datetime
    period_end: datetime
    summary: str
    recommendations: list[Any]
    metrics: dict[str, Any]
    model: str | None
    created_at: datetime


class ReportListOut(BaseModel):
    brand_id: str
    reports: list[ReportOut]
