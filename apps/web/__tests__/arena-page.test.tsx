import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ArenaPage from "@/app/arena/page";
import { AuthProvider } from "@/lib/auth-context";
import { BrandProvider } from "@/lib/brand-context";
import type { ArenaRun } from "@/lib/api";

const fetchBrandsMock = vi.fn();
const fetchLatestArenaRunMock = vi.fn();
const fetchArenaRunForEventMock = vi.fn();
const fetchCalendarEventsMock = vi.fn();

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/api", () => ({
  fetchBrands: (...args: unknown[]) => fetchBrandsMock(...args),
  fetchLatestArenaRun: (...args: unknown[]) => fetchLatestArenaRunMock(...args),
  fetchArenaRunForEvent: (...args: unknown[]) => fetchArenaRunForEventMock(...args),
  fetchCalendarEvents: (...args: unknown[]) => fetchCalendarEventsMock(...args),
}));

const BRANDS = [
  {
    id: "brand-1",
    organization_id: "org-1",
    name: "Acme Co",
    industry: "Legal tech",
    logo_url: null,
    target_audience: null,
    colors: ["#000"],
    tone_descriptors: ["direct"],
    product_catalog: null,
    brand_report: null,
    created_at: "2026-01-01",
    updated_at: "2026-01-01",
  },
];

const CALENDAR_EVENTS = [
  {
    id: "event-1",
    brand_id: "brand-1",
    title: "DPDP launch carousel",
    description: null,
    target_platforms: ["linkedin", "x"],
    desired_format: "carousel",
    target_datetime: "2026-09-01T12:00:00Z",
    status: "pipeline_running",
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
  },
];

function makeRun(overrides: Partial<ArenaRun> = {}): ArenaRun {
  return {
    calendar_event_id: "event-1",
    post: {
      id: "post-1",
      calendar_event_id: "event-1",
      current_pipeline_stage: "human_review",
      body_text: { linkedin: "70% of contracts fail diligence." },
      media: null,
      created_at: "2026-08-20T10:00:00Z",
      updated_at: "2026-08-20T10:04:00Z",
    },
    agent_runs: [
      {
        id: "run-research",
        agent_type: "research",
        output: { research_brief: { industry_trends: [{ title: "DPDP readiness", url: "https://meity.gov.in/x" }] } },
        model: "sonnet",
        tokens: 400,
        cost: 0.08,
        latency_ms: 1200,
        created_at: "2026-08-20T10:00:30Z",
      },
    ],
    review_feedback: [
      {
        id: "fb-ai-1",
        source: "ai_reviewer",
        score: 84,
        verdict: "approve",
        comments: { platforms: {}, model: "openrouter/free" },
        created_at: "2026-08-20T10:03:00Z",
      },
    ],
    ...overrides,
  };
}

function renderPage() {
  return render(
    <AuthProvider>
      <BrandProvider>
        <ArenaPage />
      </BrandProvider>
    </AuthProvider>
  );
}

describe("ArenaPage", () => {
  beforeEach(() => {
    fetchBrandsMock.mockReset();
    fetchLatestArenaRunMock.mockReset();
    fetchArenaRunForEventMock.mockReset();
    fetchCalendarEventsMock.mockReset();

    window.localStorage.clear();
    window.localStorage.setItem("raindeer.auth.token", "test-token");

    fetchBrandsMock.mockResolvedValue(BRANDS);
    fetchCalendarEventsMock.mockResolvedValue(CALENDAR_EVENTS);
    fetchLatestArenaRunMock.mockResolvedValue(makeRun());
  });

  it("fetches the latest run for the selected brand and renders the real event title", async () => {
    renderPage();

    await waitFor(() => expect(fetchLatestArenaRunMock).toHaveBeenCalledWith("test-token", "brand-1"));
    expect(await screen.findByText("RUNNING")).toBeInTheDocument();
    expect(screen.getAllByText("DPDP launch carousel").length).toBeGreaterThan(0);
  });

  it("renders real AgentRun data in the research node and trace tab", async () => {
    renderPage();

    await screen.findByText("RUNNING");

    // Node card + inspector summary line, derived from the real
    // research_brief output (appears in both places).
    expect(screen.getAllByText("1 source found").length).toBeGreaterThan(0);
    // Trace tab entry for the same AgentRun row.
    expect(screen.getByText(/research complete/)).toBeInTheDocument();
  });

  it("selecting a different node updates the inspector panel", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("RUNNING");

    await user.click(screen.getByRole("button", { name: "Select Kavi · Generation" }));

    // The inspector's header now shows the selected node's name.
    const inspectorHeadings = screen.getAllByText("Kavi · Generation");
    expect(inspectorHeadings.length).toBeGreaterThan(1);
  });

  it("the 'Skip to review' control really links to /review-queue", async () => {
    renderPage();

    await screen.findByText("RUNNING");

    const link = screen.getByRole("link", { name: /Skip to review/ });
    expect(link).toHaveAttribute("href", "/review-queue");
  });

  it("never fabricates a system prompt — shows a clear not-available state", async () => {
    renderPage();

    await screen.findByText("RUNNING");

    expect(screen.getByText(/Not available yet/)).toBeInTheDocument();
  });

  it("shows an empty state instead of fetching when no brand is selected", async () => {
    fetchBrandsMock.mockResolvedValue([]);

    renderPage();

    expect(await screen.findByText("Select a brand to see its Content Arena.")).toBeInTheDocument();
    expect(fetchLatestArenaRunMock).not.toHaveBeenCalled();
  });
});
