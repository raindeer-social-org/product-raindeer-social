import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AnalyticsPage from "@/app/analytics/page";
import { AuthProvider } from "@/lib/auth-context";
import { BrandProvider } from "@/lib/brand-context";
import type { BrandAnalyticsSummary, PlatformAggregate, PostAnalyticsAggregate, PostAnalyticsTrend, Report } from "@/lib/api";

const fetchBrandsMock = vi.fn();
const fetchAnalyticsSummaryMock = vi.fn();
const fetchPostAnalyticsAggregateMock = vi.fn();
const fetchPostAnalyticsTrendMock = vi.fn();
const fetchReportsMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchBrands: (...args: unknown[]) => fetchBrandsMock(...args),
    fetchAnalyticsSummary: (...args: unknown[]) => fetchAnalyticsSummaryMock(...args),
    fetchPostAnalyticsAggregate: (...args: unknown[]) => fetchPostAnalyticsAggregateMock(...args),
    fetchPostAnalyticsTrend: (...args: unknown[]) => fetchPostAnalyticsTrendMock(...args),
    fetchReports: (...args: unknown[]) => fetchReportsMock(...args),
  };
});

function makeReport(overrides: Partial<Report> = {}): Report {
  return {
    id: "report-1",
    brand_id: "brand-1",
    period_start: "2026-07-20T00:00:00Z",
    period_end: "2026-07-27T00:00:00Z",
    summary: "Carousels on LinkedIn carried the week, 2.4x the engagement of text posts.",
    recommendations: ["Post more carousels."],
    metrics: { post_count: 6 },
    model: "gpt-test",
    created_at: "2026-07-27T00:00:00Z",
    ...overrides,
  };
}

const BRANDS = [
  {
    id: "brand-1",
    organization_id: "org-1",
    name: "Acme Co",
    industry: null,
    logo_url: null,
    target_audience: null,
    colors: null,
    tone_descriptors: null,
    product_catalog: null,
    brand_report: null,
    created_at: "2026-01-01",
    updated_at: "2026-01-01",
  },
];

function makePlatformAggregate(overrides: Partial<PlatformAggregate> = {}): PlatformAggregate {
  return {
    platform: "linkedin",
    snapshot_count: 10,
    total_likes: 1284,
    total_comments: 340,
    total_shares: 88,
    total_impressions: 12987,
    average_likes: 128.4,
    average_comments: 34.0,
    average_shares: 8.8,
    average_impressions: 1298.7,
    ...overrides,
  };
}

function makeSummary(overrides: Partial<BrandAnalyticsSummary> = {}): BrandAnalyticsSummary {
  const linkedin = makePlatformAggregate({ platform: "linkedin" });
  const x = makePlatformAggregate({
    platform: "x",
    total_likes: 420,
    total_comments: 60,
    total_shares: 30,
    total_impressions: 5000,
    average_likes: 42,
    average_comments: 6,
    average_shares: 3,
    average_impressions: 500,
    snapshot_count: 10,
  });
  return {
    brand_id: "brand-1",
    start_date: "2026-07-27T00:00:00Z",
    end_date: "2026-08-26T00:00:00Z",
    post_count: 6,
    platforms: [linkedin, x],
    overall: makePlatformAggregate({
      platform: "overall",
      total_likes: 1704,
      total_comments: 400,
      total_shares: 118,
      total_impressions: 17987,
      average_likes: 85.2,
      average_comments: 20,
      average_shares: 5.9,
      average_impressions: 899.35,
      snapshot_count: 20,
    }),
    ...overrides,
  };
}

function makeEmptySummary(): BrandAnalyticsSummary {
  return {
    brand_id: "brand-1",
    start_date: "2026-07-27T00:00:00Z",
    end_date: "2026-08-26T00:00:00Z",
    post_count: 0,
    platforms: [],
    overall: makePlatformAggregate({
      platform: "overall",
      snapshot_count: 0,
      total_likes: 0,
      total_comments: 0,
      total_shares: 0,
      total_impressions: 0,
      average_likes: 0,
      average_comments: 0,
      average_shares: 0,
      average_impressions: 0,
    }),
  };
}

function makePostAggregate(overrides: Partial<PostAnalyticsAggregate> = {}): PostAnalyticsAggregate {
  const linkedin = makePlatformAggregate({ platform: "linkedin" });
  return {
    post_id: "post-1",
    start_date: "2026-07-27T00:00:00Z",
    end_date: "2026-08-26T00:00:00Z",
    platforms: [linkedin],
    overall: linkedin,
    ...overrides,
  };
}

function makeTrend(overrides: Partial<PostAnalyticsTrend> = {}): PostAnalyticsTrend {
  return {
    post_id: "post-1",
    start_date: "2026-07-27T00:00:00Z",
    end_date: "2026-08-26T00:00:00Z",
    points: [
      { platform: "linkedin", likes: 10, comments: 2, shares: 1, impressions: 100, polled_at: "2026-08-01T10:00:00Z" },
      { platform: "linkedin", likes: 25, comments: 5, shares: 2, impressions: 300, polled_at: "2026-08-10T10:00:00Z" },
    ],
    ...overrides,
  };
}

function renderPage() {
  return render(
    <AuthProvider>
      <BrandProvider>
        <AnalyticsPage />
      </BrandProvider>
    </AuthProvider>
  );
}

describe("AnalyticsPage", () => {
  beforeEach(() => {
    fetchBrandsMock.mockReset();
    fetchAnalyticsSummaryMock.mockReset();
    fetchPostAnalyticsAggregateMock.mockReset();
    fetchPostAnalyticsTrendMock.mockReset();
    fetchReportsMock.mockReset();

    window.localStorage.clear();
    window.localStorage.setItem("raindeer.auth.token", "test-token");

    fetchBrandsMock.mockResolvedValue(BRANDS);
    fetchAnalyticsSummaryMock.mockResolvedValue(makeSummary());
    fetchReportsMock.mockResolvedValue([]);
  });

  it("fetches and renders the brand summary with real numbers", async () => {
    renderPage();

    await waitFor(() => expect(fetchAnalyticsSummaryMock).toHaveBeenCalledWith("test-token", "brand-1", expect.any(Object)));

    expect(await screen.findByText("6")).toBeInTheDocument(); // post_count tile
    expect(screen.getByText("1.7K")).toBeInTheDocument(); // total likes, compacted
    expect(screen.getAllByText("linkedin").length).toBeGreaterThan(0);
    expect(screen.getAllByText("x").length).toBeGreaterThan(0);
  });

  it("re-fetches the summary when the date range preset changes", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(fetchAnalyticsSummaryMock).toHaveBeenCalledTimes(1));

    await user.click(screen.getByRole("button", { name: "Last 7 days" }));

    await waitFor(() => expect(fetchAnalyticsSummaryMock).toHaveBeenCalledTimes(2));
    const secondCallRange = fetchAnalyticsSummaryMock.mock.calls[1][2];
    const firstCallRange = fetchAnalyticsSummaryMock.mock.calls[0][2];
    expect(secondCallRange.startDate).not.toEqual(firstCallRange.startDate);
  });

  it("shows an empty state when there is no engagement data in range", async () => {
    fetchAnalyticsSummaryMock.mockResolvedValue(makeEmptySummary());

    renderPage();

    expect(await screen.findByText("No engagement data in this range")).toBeInTheDocument();
    expect(screen.queryByText("linkedin")).not.toBeInTheDocument();
  });

  it("shows an alert when the summary request fails", async () => {
    fetchAnalyticsSummaryMock.mockRejectedValue(new Error("Failed to load the analytics summary"));

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Failed to load the analytics summary");
  });

  it("looks up a post's trend by id and renders its chart data", async () => {
    fetchPostAnalyticsAggregateMock.mockResolvedValue(makePostAggregate());
    fetchPostAnalyticsTrendMock.mockResolvedValue(makeTrend());
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(fetchAnalyticsSummaryMock).toHaveBeenCalled());

    await user.type(screen.getByLabelText("Enter a Post ID to view its trend"), "post-1");
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "View trend" }));
    });

    await waitFor(() =>
      expect(fetchPostAnalyticsAggregateMock).toHaveBeenCalledWith("test-token", "brand-1", "post-1", expect.any(Object))
    );
    expect(fetchPostAnalyticsTrendMock).toHaveBeenCalledWith(
      "test-token",
      "brand-1",
      "post-1",
      expect.objectContaining({ startDate: expect.any(String), endDate: expect.any(String) })
    );

    expect(await screen.findByText("Likes over time")).toBeInTheDocument();
    expect(screen.getByText("Raw snapshots")).toBeInTheDocument();
  });

  it("shows an empty state when a post has no engagement snapshots yet", async () => {
    fetchPostAnalyticsAggregateMock.mockResolvedValue(makePostAggregate());
    fetchPostAnalyticsTrendMock.mockResolvedValue(makeTrend({ points: [] }));
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(fetchAnalyticsSummaryMock).toHaveBeenCalled());

    await user.type(screen.getByLabelText("Enter a Post ID to view its trend"), "post-2");
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "View trend" }));
    });

    expect(await screen.findByText("No engagement snapshots yet")).toBeInTheDocument();
  });

  it("renders the latest weekly report as the AI weekly report card, linking to /reports", async () => {
    fetchReportsMock.mockResolvedValue([
      makeReport({ summary: "Carousels on LinkedIn carried the week." }),
      makeReport({ id: "report-0", summary: "An older report." }),
    ]);

    renderPage();

    expect(await screen.findByText("WEEKLY REPORT · AI")).toBeInTheDocument();
    expect(screen.getByText(/Carousels on LinkedIn carried the week/)).toBeInTheDocument();
    expect(screen.queryByText(/An older report/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Read the full report/ })).toHaveAttribute("href", "/reports");
  });

  it("shows a no-report-yet state in the weekly report card when there are no reports", async () => {
    fetchReportsMock.mockResolvedValue([]);

    renderPage();

    expect(await screen.findByText("WEEKLY REPORT · AI")).toBeInTheDocument();
    expect(screen.getByText(/No weekly report yet/)).toBeInTheDocument();
  });
});
