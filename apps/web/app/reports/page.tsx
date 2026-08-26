"use client";

import type { ReactNode } from "react";
import { useCallback, useEffect, useState } from "react";
import { fetchReport, fetchReports, type Report, type ReportMetrics } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useBrand } from "@/lib/brand-context";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/components/ui/cn";

function IconReport() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M7 3h7l4 4v13a1 1 0 01-1 1H7a1 1 0 01-1-1V4a1 1 0 011-1Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M9 12h6M9 16h6M9 8h2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatPeriodLabel(report: Pick<Report, "period_start" | "period_end">): string {
  return `${formatDate(report.period_start)} – ${formatDate(report.period_end)}`;
}

function excerpt(text: string, maxLength = 140): string {
  const trimmed = text.trim();
  if (trimmed.length <= maxLength) return trimmed;
  return `${trimmed.slice(0, maxLength).trimEnd()}…`;
}

// `recommendations` is `list[Any]` server-side (see apps/api/schemas/
// analytics.py::ReportOut) — weekly_report.py currently always writes
// plain strings, but render generically since other shapes (e.g. a
// `{title, detail}`-ish object) are contractually possible.
function renderRecommendation(item: unknown): ReactNode {
  if (typeof item === "string") return item;

  if (item && typeof item === "object") {
    const obj = item as Record<string, unknown>;
    const title = typeof obj.title === "string" ? obj.title : undefined;
    const detail =
      typeof obj.detail === "string"
        ? obj.detail
        : typeof obj.description === "string"
          ? obj.description
          : undefined;

    if (title || detail) {
      return (
        <>
          {title ? <span className="font-medium text-slate-900">{title}</span> : null}
          {title && detail ? ": " : null}
          {detail}
        </>
      );
    }
  }

  return JSON.stringify(item);
}

// Small "generated from these real numbers" grounding section — the full
// analytics dashboard (#92) already covers charting this data, so a
// compact sentence + stat row is enough here.
function MetricsGrounding({ metrics }: { metrics: ReportMetrics }) {
  const overall = metrics.overall;

  if (!overall) {
    return <p className="text-sm text-slate-500">No metrics were recorded for this period.</p>;
  }

  const postCount = metrics.post_count ?? 0;
  const platformCount = metrics.platforms?.length ?? 0;

  const stats: { label: string; value: number }[] = [
    { label: "Posts", value: postCount },
    { label: "Likes", value: overall.total_likes },
    { label: "Comments", value: overall.total_comments },
    { label: "Shares", value: overall.total_shares },
    { label: "Impressions", value: overall.total_impressions },
  ];

  return (
    <div>
      <p className="text-sm text-slate-500">
        Generated from {postCount} post{postCount === 1 ? "" : "s"} across{" "}
        {platformCount} platform{platformCount === 1 ? "" : "s"}: {overall.total_likes} total likes,{" "}
        {overall.total_comments} comments, {overall.total_shares} shares, and{" "}
        {overall.total_impressions} impressions.
      </p>
      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-5">
        {stats.map((stat) => (
          <div key={stat.label} className="rounded-lg bg-slate-50 px-3 py-2 text-center">
            <div className="text-base font-semibold text-slate-900">{stat.value}</div>
            <div className="text-xs text-slate-500">{stat.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ReportDetail({
  report,
  isLoading,
  error,
}: {
  report: Report | null;
  isLoading: boolean;
  error: string | null;
}) {
  if (error) {
    return (
      <Card>
        <CardBody>
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        </CardBody>
      </Card>
    );
  }

  if (isLoading || !report) {
    return (
      <Card>
        <CardBody className="space-y-3">
          <Skeleton className="h-5 w-1/3" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-2/3" />
        </CardBody>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        title={formatPeriodLabel(report)}
        description={`Generated ${formatDate(report.created_at)}`}
        action={report.model ? <Badge tone="brand">{report.model}</Badge> : null}
      />
      <CardBody className="space-y-6">
        <div>
          <h4 className="mb-1.5 text-sm font-semibold text-slate-900">Summary</h4>
          <p className="text-sm leading-relaxed text-slate-700">{report.summary}</p>
        </div>

        <div>
          <h4 className="mb-1.5 text-sm font-semibold text-slate-900">Recommendations</h4>
          {report.recommendations.length === 0 ? (
            <p className="text-sm text-slate-500">No recommendations for this period.</p>
          ) : (
            <ul className="list-disc space-y-1.5 pl-5 text-sm text-slate-700">
              {report.recommendations.map((item, index) => (
                // eslint-disable-next-line react/no-array-index-key
                <li key={index}>{renderRecommendation(item)}</li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <h4 className="mb-1.5 text-sm font-semibold text-slate-900">Generated from</h4>
          <MetricsGrounding metrics={report.metrics} />
        </div>
      </CardBody>
    </Card>
  );
}

export default function ReportsPage() {
  const { token } = useAuth();
  const { selectedBrand, selectedBrandId } = useBrand();

  const [reports, setReports] = useState<Report[]>([]);
  const [isListLoading, setIsListLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);

  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const [selectedReport, setSelectedReport] = useState<Report | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const loadReports = useCallback(async () => {
    if (!token || !selectedBrandId) {
      setReports([]);
      setSelectedReportId(null);
      return;
    }
    setIsListLoading(true);
    setListError(null);
    try {
      const result = await fetchReports(token, selectedBrandId);
      setReports(result);
      setSelectedReportId((current) => {
        if (current && result.some((report) => report.id === current)) {
          return current;
        }
        return result[0]?.id ?? null;
      });
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Failed to load reports");
    } finally {
      setIsListLoading(false);
    }
  }, [token, selectedBrandId]);

  // Reload whenever the token or the selected brand changes (brand switch
  // re-scopes the report list), same convention as
  // apps/web/app/calendar/page.tsx.
  useEffect(() => {
    setReports([]);
    setSelectedReportId(null);
    setSelectedReport(null);
    loadReports();
  }, [loadReports]);

  // Fetch the full detail for whichever report is selected — the list
  // response already carries every field, but going through
  // GET .../reports/{id} keeps the list and detail views independently
  // correct if the list response is ever slimmed down later.
  useEffect(() => {
    if (!token || !selectedBrandId || !selectedReportId) {
      setSelectedReport(null);
      return;
    }
    let cancelled = false;
    setIsDetailLoading(true);
    setDetailError(null);
    fetchReport(token, selectedBrandId, selectedReportId)
      .then((report) => {
        if (!cancelled) setSelectedReport(report);
      })
      .catch((err) => {
        if (!cancelled) {
          setDetailError(err instanceof Error ? err.message : "Failed to load report");
        }
      })
      .finally(() => {
        if (!cancelled) setIsDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, selectedBrandId, selectedReportId]);

  return (
    <div>
      <PageHeader
        title="Reports"
        description={
          selectedBrand
            ? `AI-generated weekly performance reports for ${selectedBrand.name}.`
            : "AI-generated weekly performance reports."
        }
      />

      {!selectedBrand ? (
        <p className="text-sm text-slate-500">Select a brand to see its weekly reports.</p>
      ) : listError ? (
        <p role="alert" className="text-sm text-red-600">
          {listError}
        </p>
      ) : isListLoading && reports.length === 0 ? (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
          <div className="space-y-3">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
          <Skeleton className="h-64 w-full" />
        </div>
      ) : reports.length === 0 ? (
        <EmptyState
          icon={<IconReport />}
          title="No reports yet"
          description="Weekly reports are generated automatically by a background job once a week. New brands won't have one until their first full week of activity has been recorded — check back soon."
        />
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
          <ul className="space-y-3">
            {reports.map((report) => {
              const isSelected = report.id === selectedReportId;
              return (
                <li key={report.id}>
                  <button
                    type="button"
                    aria-pressed={isSelected}
                    onClick={() => setSelectedReportId(report.id)}
                    className={cn(
                      "block w-full rounded-xl border p-4 text-left shadow-card transition-colors",
                      isSelected
                        ? "border-brand-300 bg-brand-50"
                        : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50",
                    )}
                  >
                    <div className="text-sm font-semibold text-slate-900">{formatPeriodLabel(report)}</div>
                    <p className="mt-1 line-clamp-2 text-sm text-slate-500">{excerpt(report.summary)}</p>
                  </button>
                </li>
              );
            })}
          </ul>

          <div role="region" aria-label="Report detail">
            <ReportDetail report={selectedReport} isLoading={isDetailLoading} error={detailError} />
          </div>
        </div>
      )}
    </div>
  );
}
