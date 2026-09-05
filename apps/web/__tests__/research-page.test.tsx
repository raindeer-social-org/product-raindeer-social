import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ResearchPage from "@/app/research/page";
import { AuthProvider } from "@/lib/auth-context";
import { BrandProvider } from "@/lib/brand-context";
import { ToastProvider } from "@/components/ui/Toast";
import type { ResearchRun } from "@/lib/api";

const fetchBrandsMock = vi.fn();
const fetchLatestResearchMock = vi.fn();
const runResearchMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchBrands: (...args: unknown[]) => fetchBrandsMock(...args),
    fetchLatestResearch: (...args: unknown[]) => fetchLatestResearchMock(...args),
    runResearch: (...args: unknown[]) => runResearchMock(...args),
  };
});

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

function makeRun(overrides: Partial<ResearchRun> = {}): ResearchRun {
  return {
    id: "run-1",
    post_id: "post-1",
    brand_id: "brand-1",
    created_at: "2026-08-20T10:00:00Z",
    brief: {
      post_id: "post-1",
      brand_context: [],
      platform_trends: {
        linkedin: [
          { title: "DPDP deadline is reshaping compliance content", url: "https://example.com/a", content: "Founders are posting about it." },
        ],
      },
      industry_trends: [
        { title: "Legal tech funding up 40%", url: "https://news.example.com/b", content: "Investment trend." },
      ],
      timing_signal: {
        researched_at: "2026-08-20T09:55:00Z",
        platforms: ["linkedin"],
        trending_topics: ["DPDP deadline", "diligence failure rate"],
        target_datetime: null,
      },
    },
    ...overrides,
  };
}

function renderPage() {
  return render(
    <ToastProvider>
      <AuthProvider>
        <BrandProvider>
          <ResearchPage />
        </BrandProvider>
      </AuthProvider>
    </ToastProvider>
  );
}

describe("ResearchPage", () => {
  beforeEach(() => {
    fetchBrandsMock.mockReset();
    fetchLatestResearchMock.mockReset();
    runResearchMock.mockReset();

    window.localStorage.clear();
    window.localStorage.setItem("raindeer.auth.token", "test-token");

    fetchBrandsMock.mockResolvedValue(BRANDS);
    fetchLatestResearchMock.mockResolvedValue(null);
  });

  it("shows an empty state and lets the user run research for the first time", async () => {
    const user = userEvent.setup();
    runResearchMock.mockResolvedValue(makeRun());

    renderPage();

    await waitFor(() => expect(fetchLatestResearchMock).toHaveBeenCalledWith("test-token", "brand-1"));
    expect(await screen.findByText(/No research yet/)).toBeInTheDocument();

    await act(async () => {
      await user.click(screen.getAllByRole("button", { name: /Run new research/ })[0]);
    });

    await waitFor(() => expect(runResearchMock).toHaveBeenCalledWith("test-token", "brand-1"));
    expect(await screen.findByText(/DPDP deadline is reshaping compliance content/)).toBeInTheDocument();
    expect(screen.getByText(/Legal tech funding up 40%/)).toBeInTheDocument();
    expect(screen.getByText("diligence failure rate")).toBeInTheDocument();
  });

  it("renders trend cards from the most recent research on load", async () => {
    fetchLatestResearchMock.mockResolvedValue(makeRun());

    renderPage();

    expect(await screen.findByText(/DPDP deadline is reshaping compliance content/)).toBeInTheDocument();
    expect(screen.getAllByText("linkedin").length).toBeGreaterThan(0);
  });
});
