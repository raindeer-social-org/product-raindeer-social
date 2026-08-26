import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ReportsPage from "@/app/reports/page";
import { AuthProvider } from "@/lib/auth-context";
import { BrandProvider } from "@/lib/brand-context";
import type { Report } from "@/lib/api";

const fetchBrandsMock = vi.fn();
const fetchReportsMock = vi.fn();
const fetchReportMock = vi.fn();

vi.mock("@/lib/api", () => ({
  fetchBrands: (...args: unknown[]) => fetchBrandsMock(...args),
  fetchReports: (...args: unknown[]) => fetchReportsMock(...args),
  fetchReport: (...args: unknown[]) => fetchReportMock(...args),
}));

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

function makeReport(overrides: Partial<Report> = {}): Report {
  return {
    id: "report-1",
    brand_id: "brand-1",
    period_start: "2026-08-10T00:00:00Z",
    period_end: "2026-08-17T00:00:00Z",
    summary: "342 likes across 5 posts this week, up from the prior period.",
    recommendations: ["Post more on LinkedIn, which drove the most engagement this week."],
    metrics: {
      post_count: 5,
      platforms: [
        {
          platform: "linkedin",
          snapshot_count: 5,
          total_likes: 342,
          total_comments: 12,
          total_shares: 4,
          total_impressions: 9000,
          average_likes: 68.4,
          average_comments: 2.4,
          average_shares: 0.8,
          average_impressions: 1800,
        },
      ],
      overall: {
        platform: "overall",
        snapshot_count: 5,
        total_likes: 342,
        total_comments: 12,
        total_shares: 4,
        total_impressions: 9000,
        average_likes: 68.4,
        average_comments: 2.4,
        average_shares: 0.8,
        average_impressions: 1800,
      },
    },
    model: "gpt-4o",
    created_at: "2026-08-17T08:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <AuthProvider>
      <BrandProvider>
        <ReportsPage />
      </BrandProvider>
    </AuthProvider>
  );
}

describe("ReportsPage", () => {
  beforeEach(() => {
    fetchBrandsMock.mockReset();
    fetchReportsMock.mockReset();
    fetchReportMock.mockReset();

    window.localStorage.clear();
    window.localStorage.setItem("raindeer.auth.token", "test-token");

    fetchBrandsMock.mockResolvedValue(BRANDS);
    fetchReportsMock.mockResolvedValue([]);
  });

  it("lists the brand's reports, most recent first, with a period and summary excerpt", async () => {
    const recent = makeReport({
      id: "report-2",
      period_start: "2026-08-17T00:00:00Z",
      period_end: "2026-08-24T00:00:00Z",
      summary: "This is the most recent report summary.",
    });
    const older = makeReport({
      id: "report-1",
      period_start: "2026-08-10T00:00:00Z",
      period_end: "2026-08-17T00:00:00Z",
      summary: "This is an older report summary.",
    });
    fetchReportsMock.mockResolvedValue([recent, older]);
    fetchReportMock.mockResolvedValue(recent);

    renderPage();

    await screen.findByText("This is the most recent report summary.");
    expect(screen.getByText("This is an older report summary.")).toBeInTheDocument();
    expect(fetchReportsMock).toHaveBeenCalledWith("test-token", "brand-1");
  });

  it("selecting a report fetches and shows its detail (summary, recommendations, metrics)", async () => {
    const first = makeReport({ id: "report-1", summary: "First report summary." });
    const second = makeReport({
      id: "report-2",
      period_start: "2026-08-17T00:00:00Z",
      period_end: "2026-08-24T00:00:00Z",
      summary: "Second report summary.",
      recommendations: ["Double down on video content on Instagram."],
      metrics: {
        post_count: 8,
        platforms: [],
        overall: {
          platform: "overall",
          snapshot_count: 8,
          total_likes: 500,
          total_comments: 20,
          total_shares: 10,
          total_impressions: 15000,
          average_likes: 62.5,
          average_comments: 2.5,
          average_shares: 1.25,
          average_impressions: 1875,
        },
      },
    });
    fetchReportsMock.mockResolvedValue([first, second]);
    fetchReportMock.mockImplementation((_token: string, _brandId: string, reportId: string) =>
      Promise.resolve(reportId === "report-1" ? first : second)
    );
    const user = userEvent.setup();

    renderPage();

    // First (most recent) report auto-selected on load.
    await waitFor(() => expect(fetchReportMock).toHaveBeenCalledWith("test-token", "brand-1", "report-1"));
    const detail = screen.getByRole("region", { name: "Report detail" });
    await within(detail).findByText("First report summary.");

    await act(async () => {
      await user.click(screen.getByRole("button", { name: /Second report summary\./ }));
    });

    await waitFor(() => expect(fetchReportMock).toHaveBeenCalledWith("test-token", "brand-1", "report-2"));
    await within(detail).findByText("Double down on video content on Instagram.");
    expect(within(detail).getByText(/500 total likes/)).toBeInTheDocument();
    expect(within(detail).getByText(/8 posts/)).toBeInTheDocument();
  });

  it("shows an empty state when the brand has no reports yet", async () => {
    fetchReportsMock.mockResolvedValue([]);

    renderPage();

    await screen.findByText("No reports yet");
    expect(screen.getByText(/generated automatically by a background job/)).toBeInTheDocument();
    expect(fetchReportMock).not.toHaveBeenCalled();
  });
});
