import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CreatePostPage from "@/app/create-post/page";
import { AuthProvider } from "@/lib/auth-context";
import { BrandProvider } from "@/lib/brand-context";
import { ToastProvider } from "@/components/ui/Toast";
import type { PostSummary } from "@/lib/api";

const fetchBrandsMock = vi.fn();
const fetchRecentPostsMock = vi.fn();
const createCalendarEventMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchBrands: (...args: unknown[]) => fetchBrandsMock(...args),
    fetchRecentPosts: (...args: unknown[]) => fetchRecentPostsMock(...args),
    createCalendarEvent: (...args: unknown[]) => createCalendarEventMock(...args),
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

function makePost(overrides: Partial<PostSummary> = {}): PostSummary {
  return {
    id: "post-1",
    brand_id: "brand-1",
    calendar_event_id: "event-1",
    current_pipeline_stage: "completed",
    body_text: { linkedin: "Check out our new widget line!" },
    created_at: "2026-08-20T10:00:00Z",
    updated_at: "2026-08-20T10:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <ToastProvider>
      <AuthProvider>
        <BrandProvider>
          <CreatePostPage />
        </BrandProvider>
      </AuthProvider>
    </ToastProvider>
  );
}

describe("CreatePostPage", () => {
  beforeEach(() => {
    fetchBrandsMock.mockReset();
    fetchRecentPostsMock.mockReset();
    createCalendarEventMock.mockReset();

    window.localStorage.clear();
    window.localStorage.setItem("raindeer.auth.token", "test-token");

    fetchBrandsMock.mockResolvedValue(BRANDS);
    fetchRecentPostsMock.mockResolvedValue([]);
  });

  it("shows a real Blocked status for a rejected post in recent runs", async () => {
    fetchRecentPostsMock.mockResolvedValue([
      makePost({ id: "post-rejected", current_pipeline_stage: "rejected" }),
      makePost({ id: "post-done", current_pipeline_stage: "completed" }),
    ]);

    renderPage();

    await waitFor(() => expect(fetchRecentPostsMock).toHaveBeenCalledWith("test-token", "brand-1"));
    expect(await screen.findByText("Blocked")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
  });

  it("queues a post via the real calendar-event endpoint and refreshes recent runs", async () => {
    createCalendarEventMock.mockResolvedValue({});
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(fetchRecentPostsMock).toHaveBeenCalledTimes(1));

    await user.click(screen.getByRole("button", { name: "X" }));

    await act(async () => {
      await user.click(screen.getByRole("button", { name: /Run all agents/ }));
    });

    await waitFor(() => expect(createCalendarEventMock).toHaveBeenCalledTimes(1));
    const [token, brandId, payload] = createCalendarEventMock.mock.calls[0];
    expect(token).toBe("test-token");
    expect(brandId).toBe("brand-1");
    expect(payload.target_platforms).toEqual(expect.arrayContaining(["linkedin", "x"]));
    expect(typeof payload.target_datetime).toBe("string");

    await waitFor(() => expect(fetchRecentPostsMock).toHaveBeenCalledTimes(2));
  });

  it("requires at least one platform before queuing", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(fetchRecentPostsMock).toHaveBeenCalled());

    // LinkedIn starts selected by default — deselect it to leave none.
    await user.click(screen.getByRole("button", { name: "LinkedIn" }));

    await act(async () => {
      await user.click(screen.getByRole("button", { name: /Run all agents/ }));
    });

    expect(await screen.findByText(/Select at least one platform/)).toBeInTheDocument();
    expect(createCalendarEventMock).not.toHaveBeenCalled();
  });
});
