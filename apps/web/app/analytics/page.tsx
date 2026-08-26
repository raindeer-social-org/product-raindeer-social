"use client";

import type { FormEvent } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  type BrandAnalyticsSummary,
  type PostAnalyticsAggregate,
  type PostAnalyticsTrend,
  fetchAnalyticsSummary,
  fetchPostAnalyticsAggregate,
  fetchPostAnalyticsTrend,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useBrand } from "@/lib/brand-context";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field, Input, Select } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { PageHeader } from "@/components/ui/PageHeader";
import { BarChart } from "./bar-chart";
import {
  colorForPlatform,
  METRIC_KEYS,
  METRIC_LABELS,
  metricAverage,
  metricFromSnapshot,
  metricTotal,
  type MetricKey,
} from "./colors";
import { DateRangeFilter } from "./date-range-filter";
import { defaultDateRangeValue, resolveDateRange, type DateRangeValue } from "./date-range";
import { formatAverage, formatCompactNumber, formatDateLabel, formatDateTimeLabel } from "./format";
import { LineChart, type LineSeries } from "./line-chart";
import { PlatformTable } from "./platform-table";
import { StatTile } from "./stat-tile";

export default function AnalyticsPage() {
  const { token } = useAuth();
  const { selectedBrand, selectedBrandId } = useBrand();

  const [dateRange, setDateRange] = useState<DateRangeValue>(() => defaultDateRangeValue());

  const [summary, setSummary] = useState<BrandAnalyticsSummary | null>(null);
  const [isLoadingSummary, setIsLoadingSummary] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [barMetric, setBarMetric] = useState<MetricKey>("likes");

  const [postIdInput, setPostIdInput] = useState("");
  const [platformFilterInput, setPlatformFilterInput] = useState("");
  const [activePostId, setActivePostId] = useState<string | null>(null);
  const [activePlatformFilter, setActivePlatformFilter] = useState("");
  const [postAggregate, setPostAggregate] = useState<PostAnalyticsAggregate | null>(null);
  const [postTrend, setPostTrend] = useState<PostAnalyticsTrend | null>(null);
  const [isLoadingPost, setIsLoadingPost] = useState(false);
  const [postError, setPostError] = useState<string | null>(null);

  const loadSummary = useCallback(async () => {
    if (!token || !selectedBrandId) {
      setSummary(null);
      return;
    }
    setIsLoadingSummary(true);
    setSummaryError(null);
    try {
      const { startDate, endDate } = resolveDateRange(dateRange);
      const result = await fetchAnalyticsSummary(token, selectedBrandId, {
        startDate: startDate.toISOString(),
        endDate: endDate.toISOString(),
      });
      setSummary(result);
    } catch (err) {
      setSummaryError(err instanceof ApiError ? err.message : "Failed to load the analytics summary");
      setSummary(null);
    } finally {
      setIsLoadingSummary(false);
    }
  }, [token, selectedBrandId, dateRange]);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  const loadPostData = useCallback(async () => {
    if (!token || !selectedBrandId || !activePostId) return;
    setIsLoadingPost(true);
    setPostError(null);
    try {
      const { startDate, endDate } = resolveDateRange(dateRange);
      const rangeInput = { startDate: startDate.toISOString(), endDate: endDate.toISOString() };
      const [aggregate, trend] = await Promise.all([
        fetchPostAnalyticsAggregate(token, selectedBrandId, activePostId, rangeInput),
        fetchPostAnalyticsTrend(token, selectedBrandId, activePostId, {
          ...rangeInput,
          platform: activePlatformFilter || undefined,
        }),
      ]);
      setPostAggregate(aggregate);
      setPostTrend(trend);
    } catch (err) {
      setPostError(err instanceof ApiError ? err.message : "Failed to load this post's analytics");
      setPostAggregate(null);
      setPostTrend(null);
    } finally {
      setIsLoadingPost(false);
    }
  }, [token, selectedBrandId, activePostId, activePlatformFilter, dateRange]);

  useEffect(() => {
    if (activePostId) {
      loadPostData();
    }
  }, [loadPostData, activePostId]);

  function handlePostSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = postIdInput.trim();
    if (!trimmed) return;
    setActivePlatformFilter(platformFilterInput.trim());
    setActivePostId(trimmed);
  }

  const platformNames = useMemo(() => summary?.platforms.map((p) => p.platform) ?? [], [summary]);

  const barData = useMemo(() => {
    if (!summary) return [];
    return summary.platforms.map((platform) => ({
      label: platform.platform,
      value: metricTotal(platform, barMetric),
      color: colorForPlatform(platform.platform, platformNames),
    }));
  }, [summary, barMetric, platformNames]);

  const trendSeriesByMetric = useMemo(() => {
    if (!postTrend) return null;
    const names = Array.from(new Set(postTrend.points.map((p) => p.platform)));
    const byMetric: Record<MetricKey, LineSeries[]> = {
      likes: [],
      comments: [],
      shares: [],
      impressions: [],
    };
    for (const metric of METRIC_KEYS) {
      byMetric[metric] = names.map((name) => ({
        name,
        color: colorForPlatform(name, names),
        points: postTrend.points
          .filter((p) => p.platform === name)
          .map((p) => ({ t: new Date(p.polled_at).getTime(), value: metricFromSnapshot(p, metric) })),
      }));
    }
    return byMetric;
  }, [postTrend]);

  if (!selectedBrand) {
    return (
      <div>
        <PageHeader title="Analytics" description="Track engagement across every published post." />
        <EmptyState title="Select a brand" description="Choose a brand to see its analytics." />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title="Analytics"
        description={
          <>
            Showing data for: <strong className="text-slate-700">{selectedBrand.name}</strong>
          </>
        }
      />

      <Card>
        <CardBody>
          <DateRangeFilter value={dateRange} onChange={setDateRange} />
        </CardBody>
      </Card>

      <section aria-labelledby="analytics-summary-heading" className="space-y-4">
        <h2 id="analytics-summary-heading" className="text-lg font-semibold text-slate-900">
          Brand summary
        </h2>

        {summaryError ? (
          <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
            {summaryError}
          </p>
        ) : null}

        {isLoadingSummary && !summary ? (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
        ) : summary && summary.overall.snapshot_count === 0 ? (
          <EmptyState
            title="No engagement data in this range"
            description="No engagement snapshots were recorded for this brand's posts in the selected date range. Try widening the range, or check back once posts have published and been polled for engagement."
          />
        ) : summary ? (
          <>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
              <StatTile label="Posts in range" value={summary.post_count.toLocaleString("en-US")} />
              {METRIC_KEYS.map((metric) => (
                <StatTile
                  key={metric}
                  label={`Total ${METRIC_LABELS[metric].toLowerCase()}`}
                  value={formatCompactNumber(metricTotal(summary.overall, metric))}
                  secondary={`avg ${formatAverage(metricAverage(summary.overall, metric))} / snapshot`}
                />
              ))}
            </div>

            <Card>
              <CardHeader
                title="Engagement by platform"
                description="Compare one metric across every platform this brand published to in this range."
                action={
                  <Field label="Metric" htmlFor="analytics-bar-metric">
                    <Select
                      id="analytics-bar-metric"
                      value={barMetric}
                      onChange={(event) => setBarMetric(event.target.value as MetricKey)}
                    >
                      {METRIC_KEYS.map((metric) => (
                        <option key={metric} value={metric}>
                          {METRIC_LABELS[metric]}
                        </option>
                      ))}
                    </Select>
                  </Field>
                }
              />
              <CardBody className="space-y-6">
                <BarChart
                  data={barData}
                  formatValue={formatCompactNumber}
                  ariaLabel={`Total ${METRIC_LABELS[barMetric].toLowerCase()} by platform`}
                />
                <PlatformTable platforms={summary.platforms} />
              </CardBody>
            </Card>
          </>
        ) : null}
      </section>

      <section aria-labelledby="analytics-post-heading" className="space-y-4">
        <h2 id="analytics-post-heading" className="text-lg font-semibold text-slate-900">
          Post trend
        </h2>
        <Card>
          <CardBody>
            <form onSubmit={handlePostSubmit} className="flex flex-wrap items-end gap-3">
              <div className="min-w-[20rem] flex-1">
                <Field label="Enter a Post ID to view its trend" htmlFor="analytics-post-id">
                  <Input
                    id="analytics-post-id"
                    value={postIdInput}
                    onChange={(event) => setPostIdInput(event.target.value)}
                    placeholder="e.g. 3f9a1c2e-6b7d-4e8a-9c1a-2b3c4d5e6f7a"
                  />
                </Field>
              </div>
              <Field label="Platform (optional)" htmlFor="analytics-post-platform">
                <Input
                  id="analytics-post-platform"
                  value={platformFilterInput}
                  onChange={(event) => setPlatformFilterInput(event.target.value)}
                  placeholder="linkedin"
                  className="w-40"
                />
              </Field>
              <Button type="submit" isLoading={isLoadingPost}>
                View trend
              </Button>
            </form>
            <p className="mt-2 text-xs text-slate-400">
              There&apos;s no post picker yet — the calendar and review queue don&apos;t expose a post list either. A
              proper picker reusing one of those is a reasonable follow-up once they do; entering an id directly is
              enough to unblock this view for now.
            </p>
          </CardBody>
        </Card>

        {postError ? (
          <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
            {postError}
          </p>
        ) : null}

        {isLoadingPost && !postAggregate ? (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
        ) : postAggregate && postTrend ? (
          postTrend.points.length === 0 ? (
            <EmptyState
              title="No engagement snapshots yet"
              description="This post hasn't been polled for engagement in the selected date range yet. Try widening the range, or check back after the next poll."
            />
          ) : (
            <>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                {METRIC_KEYS.map((metric) => (
                  <StatTile
                    key={metric}
                    label={`Total ${METRIC_LABELS[metric].toLowerCase()}`}
                    value={formatCompactNumber(metricTotal(postAggregate.overall, metric))}
                    secondary={`avg ${formatAverage(metricAverage(postAggregate.overall, metric))} / snapshot`}
                  />
                ))}
              </div>

              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                {METRIC_KEYS.map((metric) => (
                  <Card key={metric}>
                    <CardHeader title={`${METRIC_LABELS[metric]} over time`} />
                    <CardBody>
                      <LineChart
                        series={trendSeriesByMetric?.[metric] ?? []}
                        formatValue={formatCompactNumber}
                        formatTime={(t) => formatDateTimeLabel(new Date(t).toISOString())}
                        ariaLabel={`${METRIC_LABELS[metric]} over time`}
                      />
                    </CardBody>
                  </Card>
                ))}
              </div>

              <Card>
                <CardHeader title="Raw snapshots" description="Every engagement snapshot polled for this post in this range." />
                <CardBody className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-400">
                        <th scope="col" className="py-2 pr-4 font-medium">
                          Polled at
                        </th>
                        <th scope="col" className="py-2 pr-4 font-medium">
                          Platform
                        </th>
                        <th scope="col" className="py-2 pr-4 font-medium">
                          Likes
                        </th>
                        <th scope="col" className="py-2 pr-4 font-medium">
                          Comments
                        </th>
                        <th scope="col" className="py-2 pr-4 font-medium">
                          Shares
                        </th>
                        <th scope="col" className="py-2 font-medium">
                          Impressions
                        </th>
                      </tr>
                    </thead>
                    <tbody className="[font-variant-numeric:tabular-nums]">
                      {postTrend.points.map((point, i) => (
                        <tr key={`${point.platform}-${point.polled_at}-${i}`} className="border-b border-slate-100 last:border-0">
                          <td className="py-2 pr-4 text-slate-600">{formatDateLabel(point.polled_at)}</td>
                          <td className="py-2 pr-4 capitalize text-slate-900">{point.platform}</td>
                          <td className="py-2 pr-4 text-slate-600">{point.likes.toLocaleString("en-US")}</td>
                          <td className="py-2 pr-4 text-slate-600">{point.comments.toLocaleString("en-US")}</td>
                          <td className="py-2 pr-4 text-slate-600">{point.shares.toLocaleString("en-US")}</td>
                          <td className="py-2 text-slate-600">{point.impressions.toLocaleString("en-US")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </CardBody>
              </Card>
            </>
          )
        ) : null}
      </section>
    </div>
  );
}
