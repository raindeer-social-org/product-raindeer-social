import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AutogenModal, buildAutogenEvents } from "@/app/calendar/autogen-modal";

describe("buildAutogenEvents", () => {
  it("builds one event per day per posts-per-day, all targeting the selected platforms", () => {
    const now = new Date(2026, 7, 1);
    const events = buildAutogenEvents({
      days: 3,
      postsPerDay: 2,
      platforms: ["linkedin", "x"],
      goals: [],
      notes: "",
      now,
    });

    expect(events).toHaveLength(6);
    for (const event of events) {
      expect(event.target_platforms).toEqual(["linkedin", "x"]);
      expect(event.title).toBe("Scheduled post");
      expect(event.description).toBeNull();
      expect(new Date(event.target_datetime).getTime()).toBeGreaterThan(now.getTime());
    }
  });

  it("seeds the title from the first selected goal and keeps notes as the description", () => {
    const events = buildAutogenEvents({
      days: 1,
      postsPerDay: 1,
      platforms: ["linkedin"],
      goals: ["Demo bookings", "Hiring"],
      notes: "  Avoid pending litigation.  ",
    });

    expect(events).toHaveLength(1);
    expect(events[0].title).toBe("Demo bookings post");
    expect(events[0].description).toBe("Avoid pending litigation.");
  });

  it("spreads multiple posts-per-day across different hours so they don't collide", () => {
    const events = buildAutogenEvents({
      days: 1,
      postsPerDay: 3,
      platforms: ["linkedin"],
      goals: [],
      notes: "",
    });

    const hours = events.map((e) => new Date(e.target_datetime).getHours());
    expect(new Set(hours).size).toBe(3);
  });
});

describe("AutogenModal", () => {
  it("disables platforms this app doesn't support publishing to yet", () => {
    render(<AutogenModal onClose={() => {}} onGenerate={async () => {}} />);

    expect(screen.getByRole("button", { name: "Instagram" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "LinkedIn" })).toBeEnabled();
  });

  it("calls onGenerate with the built events and reports the total post count", async () => {
    const onGenerate = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(<AutogenModal onClose={() => {}} onGenerate={onGenerate} />);

    // Default: 14 days * 2 posts/day = 28 posts.
    expect(screen.getByRole("button", { name: "Generate 28 posts" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Generate 28 posts" }));

    await waitFor(() => expect(onGenerate).toHaveBeenCalledTimes(1));
    const payload = onGenerate.mock.calls[0][0] as unknown[];
    expect(payload).toHaveLength(28);
  });

  it("shows an error instead of calling onGenerate when no platform is selected", async () => {
    const onGenerate = vi.fn();
    const user = userEvent.setup();

    render(<AutogenModal onClose={() => {}} onGenerate={onGenerate} />);

    await user.click(screen.getByRole("button", { name: "LinkedIn" }));
    await user.click(screen.getByRole("button", { name: "X" }));
    await user.click(screen.getByRole("button", { name: /Generate 28 posts/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Select at least one platform.");
    expect(onGenerate).not.toHaveBeenCalled();
  });
});
