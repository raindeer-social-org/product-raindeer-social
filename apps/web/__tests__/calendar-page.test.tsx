import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CalendarPage from "@/app/calendar/page";
import { BrandSwitcher } from "@/components/brand-switcher";
import { AuthProvider } from "@/lib/auth-context";
import { BrandProvider } from "@/lib/brand-context";
import type { CalendarEvent, CalendarEventStatus } from "@/lib/api";

const fetchBrandsMock = vi.fn();
const fetchCalendarEventsMock = vi.fn();
const createCalendarEventMock = vi.fn();
const updateCalendarEventMock = vi.fn();
const deleteCalendarEventMock = vi.fn();

vi.mock("@/lib/api", () => ({
  fetchBrands: (...args: unknown[]) => fetchBrandsMock(...args),
  fetchCalendarEvents: (...args: unknown[]) => fetchCalendarEventsMock(...args),
  createCalendarEvent: (...args: unknown[]) => createCalendarEventMock(...args),
  updateCalendarEvent: (...args: unknown[]) => updateCalendarEventMock(...args),
  deleteCalendarEvent: (...args: unknown[]) => deleteCalendarEventMock(...args),
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
  {
    id: "brand-2",
    organization_id: "org-1",
    name: "Beta Inc",
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

// Always "today" at a fixed local hour, formatted with no timezone suffix
// (so it's parsed as local time and always falls inside the currently
// rendered month grid, regardless of which day the suite runs on or the
// runner's timezone).
function todayAt(hour: number): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(hour)}:00:00`;
}

function makeEvent(overrides: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    id: "event-1",
    brand_id: "brand-1",
    title: "Launch post",
    description: null,
    target_platforms: ["linkedin"],
    desired_format: "image",
    target_datetime: todayAt(10),
    status: "scheduled" as CalendarEventStatus,
    created_at: todayAt(9),
    updated_at: todayAt(9),
    ...overrides,
  };
}

function renderPage() {
  return render(
    <AuthProvider>
      <BrandProvider>
        <BrandSwitcher />
        <CalendarPage />
      </BrandProvider>
    </AuthProvider>
  );
}

describe("CalendarPage", () => {
  beforeEach(() => {
    fetchBrandsMock.mockReset();
    fetchCalendarEventsMock.mockReset();
    createCalendarEventMock.mockReset();
    updateCalendarEventMock.mockReset();
    deleteCalendarEventMock.mockReset();

    window.localStorage.clear();
    window.localStorage.setItem("raindeer.auth.token", "test-token");

    fetchBrandsMock.mockResolvedValue(BRANDS);
    fetchCalendarEventsMock.mockResolvedValue([]);
  });

  it("fetches and renders the selected brand's events on mount", async () => {
    fetchCalendarEventsMock.mockResolvedValue([makeEvent({ id: "e1", title: "Launch post" })]);

    renderPage();

    await screen.findByRole("button", { name: /Launch post/ });
    expect(fetchCalendarEventsMock).toHaveBeenCalledWith("test-token", "brand-1");
  });

  it("re-scopes the calendar when the selected brand changes", async () => {
    fetchCalendarEventsMock.mockImplementation((_token: string, brandId: string) => {
      if (brandId === "brand-1") {
        return Promise.resolve([makeEvent({ id: "e1", title: "Brand One Event" })]);
      }
      if (brandId === "brand-2") {
        return Promise.resolve([makeEvent({ id: "e2", title: "Brand Two Event" })]);
      }
      return Promise.resolve([]);
    });
    const user = userEvent.setup();

    renderPage();

    await screen.findByRole("button", { name: /Brand One Event/ });
    expect(screen.queryByRole("button", { name: /Brand Two Event/ })).not.toBeInTheDocument();

    const select = await screen.findByRole("combobox", { name: "Select brand" });
    await act(async () => {
      await user.selectOptions(select, "brand-2");
    });

    await waitFor(() => expect(fetchCalendarEventsMock).toHaveBeenCalledWith("test-token", "brand-2"));
    await screen.findByRole("button", { name: /Brand Two Event/ });
    expect(screen.queryByRole("button", { name: /Brand One Event/ })).not.toBeInTheDocument();
  });

  it("creates a new event through the form and round-trips it through the API", async () => {
    createCalendarEventMock.mockResolvedValue(makeEvent({ id: "new-1", title: "New Launch" }));
    const user = userEvent.setup();

    renderPage();

    await waitFor(() => expect(fetchCalendarEventsMock).toHaveBeenCalled());

    await user.click(screen.getByRole("button", { name: "+ New event" }));
    const dialog = await screen.findByRole("dialog", { name: "New event" });

    await user.type(within(dialog).getByLabelText("Title"), "New Launch");
    await user.click(within(dialog).getByLabelText("LinkedIn"));
    await user.type(within(dialog).getByLabelText("Format"), "image");
    await act(async () => {
      await user.click(within(dialog).getByRole("button", { name: "Create" }));
    });

    await waitFor(() => {
      expect(createCalendarEventMock).toHaveBeenCalledWith(
        "test-token",
        "brand-1",
        expect.objectContaining({
          title: "New Launch",
          target_platforms: ["linkedin"],
          desired_format: "image",
        })
      );
    });

    await screen.findByRole("button", { name: /New Launch/ });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("edits an existing event's status through the form and round-trips it through the API", async () => {
    fetchCalendarEventsMock.mockResolvedValue([makeEvent({ id: "e1", title: "Existing Event", status: "scheduled" })]);
    updateCalendarEventMock.mockResolvedValue(makeEvent({ id: "e1", title: "Existing Event", status: "approved" }));
    const user = userEvent.setup();

    renderPage();

    const chip = await screen.findByRole("button", { name: /Existing Event/ });
    expect(chip.className).toContain("status-scheduled");

    await user.click(chip);
    const dialog = await screen.findByRole("dialog", { name: "Edit event" });

    await user.selectOptions(within(dialog).getByLabelText("Status"), "approved");
    await act(async () => {
      await user.click(within(dialog).getByRole("button", { name: "Save" }));
    });

    await waitFor(() => {
      expect(updateCalendarEventMock).toHaveBeenCalledWith(
        "test-token",
        "brand-1",
        "e1",
        expect.objectContaining({ status: "approved" })
      );
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Existing Event/ }).className).toContain("status-approved");
    });
  });

  it("deletes an event through the form and removes it from the calendar", async () => {
    fetchCalendarEventsMock.mockResolvedValue([makeEvent({ id: "e1", title: "Doomed Event" })]);
    deleteCalendarEventMock.mockResolvedValue(undefined);
    const user = userEvent.setup();

    renderPage();

    const chip = await screen.findByRole("button", { name: /Doomed Event/ });
    await user.click(chip);

    const dialog = await screen.findByRole("dialog", { name: "Edit event" });
    await act(async () => {
      await user.click(within(dialog).getByRole("button", { name: "Delete" }));
    });

    await waitFor(() => expect(deleteCalendarEventMock).toHaveBeenCalledWith("test-token", "brand-1", "e1"));
    await waitFor(() => expect(screen.queryByRole("button", { name: /Doomed Event/ })).not.toBeInTheDocument());
  });

  it("reflects a status change from a background refresh (e.g. on window focus) without a manual reload", async () => {
    fetchCalendarEventsMock
      .mockResolvedValueOnce([makeEvent({ id: "e1", title: "Pipeline Event", status: "pipeline_running" })])
      .mockResolvedValueOnce([makeEvent({ id: "e1", title: "Pipeline Event", status: "ready_for_review" })]);

    renderPage();

    const chip = await screen.findByRole("button", { name: /Pipeline Event/ });
    expect(chip.className).toContain("status-pipeline-running");

    await act(async () => {
      window.dispatchEvent(new Event("focus"));
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Pipeline Event/ }).className).toContain("status-ready-for-review");
    });
  });
});
