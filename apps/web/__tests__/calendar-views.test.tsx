import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MonthView } from "@/app/calendar/month-view";
import { WeekView } from "@/app/calendar/week-view";
import type { CalendarEvent } from "@/lib/api";

function makeEvent(overrides: Partial<CalendarEvent>): CalendarEvent {
  return {
    id: "event-1",
    brand_id: "brand-1",
    title: "Event",
    description: null,
    target_platforms: ["linkedin"],
    desired_format: "image",
    // No trailing "Z" — parsed as local time so grid placement in these
    // tests doesn't depend on the machine's timezone.
    target_datetime: "2026-08-10T10:00:00",
    status: "scheduled",
    created_at: "2026-08-01T00:00:00",
    updated_at: "2026-08-01T00:00:00",
    ...overrides,
  };
}

describe("MonthView", () => {
  it("renders events in different statuses with visually distinct classes", () => {
    const referenceDate = new Date(2026, 7, 1); // August 2026
    const events = [
      makeEvent({ id: "e1", title: "Scheduled Post", status: "scheduled", target_datetime: "2026-08-10T09:00:00" }),
      makeEvent({ id: "e2", title: "Review Post", status: "ready_for_review", target_datetime: "2026-08-12T09:00:00" }),
      makeEvent({ id: "e3", title: "Failed Post", status: "failed", target_datetime: "2026-08-15T09:00:00" }),
    ];

    render(
      <MonthView
        referenceDate={referenceDate}
        events={events}
        today={referenceDate}
        onSelectEvent={() => {}}
        onAddEvent={() => {}}
      />
    );

    const scheduled = screen.getByRole("button", { name: /Scheduled Post/ });
    const review = screen.getByRole("button", { name: /Review Post/ });
    const failed = screen.getByRole("button", { name: /Failed Post/ });

    expect(scheduled.className).toContain("status-scheduled");
    expect(review.className).toContain("status-ready-for-review");
    expect(failed.className).toContain("status-failed");

    // Every status renders a different class from every other status.
    expect(scheduled.className).not.toBe(review.className);
    expect(review.className).not.toBe(failed.className);
  });

  it("invokes onSelectEvent when an event chip is clicked and onAddEvent when a day's + is clicked", async () => {
    const referenceDate = new Date(2026, 7, 1);
    const event = makeEvent({ id: "e1", title: "Scheduled Post", target_datetime: "2026-08-10T09:00:00" });
    const onSelectEvent = vi.fn();
    const onAddEvent = vi.fn();
    const user = userEvent.setup();

    render(
      <MonthView
        referenceDate={referenceDate}
        events={[event]}
        today={referenceDate}
        onSelectEvent={onSelectEvent}
        onAddEvent={onAddEvent}
      />
    );

    await user.click(screen.getByRole("button", { name: /Scheduled Post/ }));
    expect(onSelectEvent).toHaveBeenCalledWith(event);

    await user.click(screen.getByRole("button", { name: "Add event on 2026-08-10" }));
    expect(onAddEvent).toHaveBeenCalledTimes(1);
    const addedDate = onAddEvent.mock.calls[0][0] as Date;
    expect(addedDate.getFullYear()).toBe(2026);
    expect(addedDate.getMonth()).toBe(7);
    expect(addedDate.getDate()).toBe(10);
  });
});

describe("WeekView", () => {
  it("renders events for the week with status badges that are visually distinct", () => {
    const referenceDate = new Date(2026, 7, 10);
    const events = [
      makeEvent({ id: "e1", title: "Approved Post", status: "approved", target_datetime: "2026-08-10T09:00:00" }),
      makeEvent({ id: "e2", title: "Published Post", status: "published", target_datetime: "2026-08-11T09:00:00" }),
    ];

    render(
      <WeekView
        referenceDate={referenceDate}
        events={events}
        today={referenceDate}
        onSelectEvent={() => {}}
        onAddEvent={() => {}}
      />
    );

    expect(screen.getByText("Approved")).toBeInTheDocument();
    expect(screen.getByText("Published")).toBeInTheDocument();
    expect(screen.getByText("Approved Post")).toBeInTheDocument();
    expect(screen.getByText("Published Post")).toBeInTheDocument();
  });

  it("shows an empty state for days with no events", () => {
    const referenceDate = new Date(2026, 7, 10);

    render(
      <WeekView referenceDate={referenceDate} events={[]} today={referenceDate} onSelectEvent={() => {}} onAddEvent={() => {}} />
    );

    expect(screen.getAllByText("No events")).toHaveLength(7);
  });
});
