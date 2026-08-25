import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ReviewQueuePage from "@/app/review-queue/page";
import { AuthProvider } from "@/lib/auth-context";
import { BrandProvider } from "@/lib/brand-context";
import type { ReviewQueuePost } from "@/lib/api";

const fetchBrandsMock = vi.fn();
const fetchReviewQueueMock = vi.fn();
const approveReviewPostMock = vi.fn();
const rejectReviewPostMock = vi.fn();
const editReviewPostMock = vi.fn();
const rescheduleReviewPostMock = vi.fn();

vi.mock("@/lib/api", () => ({
  fetchBrands: (...args: unknown[]) => fetchBrandsMock(...args),
  fetchReviewQueue: (...args: unknown[]) => fetchReviewQueueMock(...args),
  approveReviewPost: (...args: unknown[]) => approveReviewPostMock(...args),
  rejectReviewPost: (...args: unknown[]) => rejectReviewPostMock(...args),
  editReviewPost: (...args: unknown[]) => editReviewPostMock(...args),
  rescheduleReviewPost: (...args: unknown[]) => rescheduleReviewPostMock(...args),
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

function makePost(overrides: Partial<ReviewQueuePost> = {}): ReviewQueuePost {
  return {
    id: "post-1",
    brand_id: "brand-1",
    calendar_event_id: "event-1",
    current_pipeline_stage: "human_review",
    body_text: { linkedin: "Check out our new widget line!" },
    created_at: "2026-08-20T10:00:00Z",
    updated_at: "2026-08-20T10:00:00Z",
    review_feedback: [
      {
        id: "feedback-ai-1",
        post_id: "post-1",
        source: "ai_reviewer",
        score: 72,
        verdict: "revise",
        comments: {
          platforms: {
            linkedin: {
              score: 72,
              verdict: "revise",
              issues: ["Missing a call to action"],
              suggested_edits: "Add a link to the product page at the end.",
            },
          },
          model: "openrouter/free",
        },
        created_at: "2026-08-20T10:05:00Z",
      },
    ],
    ...overrides,
  };
}

function renderPage() {
  return render(
    <AuthProvider>
      <BrandProvider>
        <ReviewQueuePage />
      </BrandProvider>
    </AuthProvider>
  );
}

describe("ReviewQueuePage", () => {
  beforeEach(() => {
    fetchBrandsMock.mockReset();
    fetchReviewQueueMock.mockReset();
    approveReviewPostMock.mockReset();
    rejectReviewPostMock.mockReset();
    editReviewPostMock.mockReset();
    rescheduleReviewPostMock.mockReset();

    window.localStorage.clear();
    window.localStorage.setItem("raindeer.auth.token", "test-token");

    fetchBrandsMock.mockResolvedValue(BRANDS);
    fetchReviewQueueMock.mockResolvedValue([]);
  });

  it("fetches and renders the AI reviewer's score/suggestions next to the draft", async () => {
    fetchReviewQueueMock.mockResolvedValue([makePost()]);

    renderPage();

    await waitFor(() => expect(fetchReviewQueueMock).toHaveBeenCalledWith("test-token", "brand-1"));

    expect(await screen.findByText(/Check out our new widget line!/)).toBeInTheDocument();
    expect(screen.getByText(/AI reviewer score: 72\/100/)).toBeInTheDocument();
    expect(screen.getByText(/Missing a call to action/)).toBeInTheDocument();
    expect(screen.getByText(/Add a link to the product page at the end\./)).toBeInTheDocument();
  });

  it("approves a post through the API and removes it from the queue", async () => {
    fetchReviewQueueMock.mockResolvedValue([makePost()]);
    approveReviewPostMock.mockResolvedValue(makePost({ current_pipeline_stage: "completed" }));
    const user = userEvent.setup();

    renderPage();

    await screen.findByText(/Check out our new widget line!/);
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Approve" }));
    });

    await waitFor(() => {
      expect(approveReviewPostMock).toHaveBeenCalledWith(
        "test-token",
        "brand-1",
        "post-1",
        expect.objectContaining({ comments: null })
      );
    });
    await waitFor(() => expect(screen.queryByText(/Check out our new widget line!/)).not.toBeInTheDocument());
  });

  it("rejects a post through the API and removes it from the queue", async () => {
    fetchReviewQueueMock.mockResolvedValue([makePost()]);
    rejectReviewPostMock.mockResolvedValue(makePost({ current_pipeline_stage: "rejected" }));
    const user = userEvent.setup();

    renderPage();

    await screen.findByText(/Check out our new widget line!/);
    await user.type(screen.getByLabelText("Comments (optional)"), "Off-brand tone");
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Reject" }));
    });

    await waitFor(() => {
      expect(rejectReviewPostMock).toHaveBeenCalledWith(
        "test-token",
        "brand-1",
        "post-1",
        expect.objectContaining({ comments: "Off-brand tone" })
      );
    });
    await waitFor(() => expect(screen.queryByText(/Check out our new widget line!/)).not.toBeInTheDocument());
  });

  it("edits the draft through the API without removing it from the queue", async () => {
    fetchReviewQueueMock.mockResolvedValue([makePost()]);
    editReviewPostMock.mockResolvedValue(
      makePost({ body_text: { linkedin: "An edited, more compelling draft." } })
    );
    const user = userEvent.setup();

    renderPage();

    const card = await screen.findByLabelText("Review post post-1");
    await user.click(within(card).getByRole("button", { name: "Edit" }));

    const textarea = within(card).getByRole("textbox", { name: "linkedin" });
    await user.clear(textarea);
    await user.type(textarea, "An edited, more compelling draft.");

    await act(async () => {
      await user.click(within(card).getByRole("button", { name: "Save edit" }));
    });

    await waitFor(() => {
      expect(editReviewPostMock).toHaveBeenCalledWith(
        "test-token",
        "brand-1",
        "post-1",
        expect.objectContaining({ body_text: { linkedin: "An edited, more compelling draft." } })
      );
    });
    expect(await screen.findByText(/An edited, more compelling draft\./)).toBeInTheDocument();
  });

  it("reschedules a post through the API", async () => {
    fetchReviewQueueMock.mockResolvedValue([makePost()]);
    rescheduleReviewPostMock.mockResolvedValue({
      id: "event-1",
      brand_id: "brand-1",
      title: "Launch",
      description: null,
      target_platforms: ["linkedin"],
      desired_format: "image",
      target_datetime: "2026-09-05T15:30:00Z",
      status: "scheduled",
      created_at: "2026-08-01T00:00:00Z",
      updated_at: "2026-08-01T00:00:00Z",
    });
    const user = userEvent.setup();

    renderPage();

    const card = await screen.findByLabelText("Review post post-1");
    await user.click(within(card).getByRole("button", { name: "Reschedule" }));

    const dateInput = within(card).getByLabelText("New date and time");
    await user.clear(dateInput);
    await user.type(dateInput, "2026-09-05T15:30");

    await act(async () => {
      await user.click(within(card).getByRole("button", { name: "Save reschedule" }));
    });

    await waitFor(() => {
      expect(rescheduleReviewPostMock).toHaveBeenCalledWith(
        "test-token",
        "brand-1",
        "post-1",
        expect.objectContaining({ target_datetime: expect.stringContaining("2026-09-05") })
      );
    });
  });
});
