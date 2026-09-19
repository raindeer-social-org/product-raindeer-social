import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PostPreviewModal } from "@/app/calendar/post-preview-modal";
import type { CalendarEvent, CalendarEventPost } from "@/lib/api";

const fetchCalendarEventPostMock = vi.fn();

vi.mock("@/lib/api", () => ({
  fetchCalendarEventPost: (...args: unknown[]) => fetchCalendarEventPostMock(...args),
}));

function makeEvent(overrides: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    id: "event-1",
    brand_id: "brand-1",
    title: "Why 70% of contracts fail diligence",
    description: null,
    target_platforms: ["linkedin"],
    desired_format: "carousel",
    target_datetime: "2026-08-10T09:00:00",
    status: "ready_for_review",
    created_at: "2026-08-01T00:00:00",
    updated_at: "2026-08-01T00:00:00",
    ...overrides,
  };
}

function makePost(overrides: Partial<CalendarEventPost> = {}): CalendarEventPost {
  return {
    id: "post-1",
    brand_id: "brand-1",
    calendar_event_id: "event-1",
    current_pipeline_stage: "human_review",
    body_text: { linkedin: "Draft copy for LinkedIn." },
    media: null,
    created_at: "2026-08-01T00:00:00",
    updated_at: "2026-08-01T00:00:00",
    review_feedback: [
      {
        id: "rf-1",
        post_id: "post-1",
        source: "ai_reviewer",
        score: 82,
        verdict: "approve",
        comments: {
          platforms: { linkedin: { score: 82, verdict: "approve", issues: ["Minor tone drift"], suggested_edits: "n/a" } },
          model: "test-model",
        },
        created_at: "2026-08-01T01:00:00",
      },
    ],
    agent_runs: [
      {
        id: "run-1",
        agent_type: "research",
        output: { research_brief: { platform_trends: { linkedin: [] } } },
        model: null,
        tokens: null,
        cost: null,
        latency_ms: null,
        created_at: "2026-08-01T00:10:00",
      },
      {
        id: "run-2",
        agent_type: "reviewer",
        output: { review_output: { score: 82, verdict: "approve" } },
        model: "test-model",
        tokens: 120,
        cost: 0.0002,
        latency_ms: 340,
        created_at: "2026-08-01T00:40:00",
      },
    ],
    ...overrides,
  };
}

describe("PostPreviewModal", () => {
  beforeEach(() => {
    fetchCalendarEventPostMock.mockReset();
  });

  it("shows a 'not reviewed yet' state when the event has no Post yet", async () => {
    fetchCalendarEventPostMock.mockResolvedValue(null);

    render(
      <PostPreviewModal
        event={makeEvent()}
        token="test-token"
        brandId="brand-1"
        brandName="LexStart"
        onClose={() => {}}
        onEdit={() => {}}
      />
    );

    expect(await screen.findByText(/Not reviewed yet/)).toBeInTheDocument();
    expect(screen.getByText(/No agent activity yet/)).toBeInTheDocument();
    expect(fetchCalendarEventPostMock).toHaveBeenCalledWith("test-token", "brand-1", "event-1");
  });

  it("renders real score tiles and the agent trail from the fetched Post", async () => {
    fetchCalendarEventPostMock.mockResolvedValue(makePost());

    render(
      <PostPreviewModal
        event={makeEvent()}
        token="test-token"
        brandId="brand-1"
        brandName="LexStart"
        onClose={() => {}}
        onEdit={() => {}}
      />
    );

    await waitFor(() => expect(screen.getAllByText("82/100").length).toBeGreaterThan(0));
    expect(screen.getByText("Predicted reach")).toBeInTheDocument();
    expect(screen.getByText("Not available yet")).toBeInTheDocument();

    expect(screen.getByText("Ved")).toBeInTheDocument();
    expect(screen.getByText("Neer")).toBeInTheDocument();
    expect(screen.getByText(/Scored this draft 82\/100/)).toBeInTheDocument();

    // The post is paused at human_review, so a link into the review queue
    // should be offered.
    expect(screen.getByRole("link", { name: /Open in Review Queue/ })).toBeInTheDocument();
  });

  it("calls onEdit with the event when Edit is clicked, and onClose when Close is clicked", async () => {
    fetchCalendarEventPostMock.mockResolvedValue(null);
    const onEdit = vi.fn();
    const onClose = vi.fn();
    const user = userEvent.setup();
    const event = makeEvent();

    render(
      <PostPreviewModal
        event={event}
        token="test-token"
        brandId="brand-1"
        brandName="LexStart"
        onClose={onClose}
        onEdit={onEdit}
      />
    );

    await screen.findByText(/Not reviewed yet/);

    await user.click(screen.getByRole("button", { name: "Edit" }));
    expect(onEdit).toHaveBeenCalledWith(event);

    // Two "Close" buttons exist: the Modal's own header X (aria-label
    // "Close") and this footer's text button — click the footer one.
    const closeButtons = screen.getAllByRole("button", { name: "Close" });
    await user.click(closeButtons[closeButtons.length - 1]);
    expect(onClose).toHaveBeenCalled();
  });
});
