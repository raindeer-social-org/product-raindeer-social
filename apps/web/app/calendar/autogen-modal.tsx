"use client";

import { useState } from "react";
import type { CalendarEventInput } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { cn } from "@/components/ui/cn";
import { Textarea } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";

// Presentational only — mirrors the design mockup's platform chip list,
// which included platforms this app's publishing adapters don't support
// yet (see apps/api/models/content_calendar_event.py::SUPPORTED_PLATFORMS).
// Anything not `supported` is shown (for visual fidelity with the mockup)
// but disabled, since sending it to the create-event API would just 422.
const DISPLAY_PLATFORMS: { value: string; label: string; supported: boolean }[] = [
  { value: "linkedin", label: "LinkedIn", supported: true },
  { value: "x", label: "X", supported: true },
  { value: "instagram", label: "Instagram", supported: false },
  { value: "youtube", label: "YouTube Shorts", supported: false },
  { value: "facebook", label: "Facebook", supported: false },
];

// Presentational goal chips (mirrors the mockup) — used only to seed the
// generated events' title client-side; there's no `goal` field on
// ContentCalendarEvent to send these to.
const GOALS = ["Build authority", "Demo bookings", "Hiring", "Product launch", "Community", "SEO support"];

// Evenly spaced posting hours through the working day when a day gets
// more than one post — a deterministic spread so posts-per-day > 1 never
// collides, not a scheduling-recommendation engine (apps/api's real
// scheduling suggestion service, apps/api/services/scheduling_suggestion.py,
// only proposes a single time from research signal, not a whole batch).
function hoursFor(postsPerDay: number): number[] {
  const start = 9;
  const end = 20;
  if (postsPerDay <= 1) return [start];
  const step = (end - start) / (postsPerDay - 1);
  return Array.from({ length: postsPerDay }, (_, i) => Math.round(start + step * i));
}

/**
 * Builds the ContentCalendarEvent payloads this wizard will create. Pure
 * (no fetch) so it's directly unit-testable and so the caller controls how
 * the creates actually run (page.tsx loops them through the existing
 * createCalendarEvent API one at a time — see its own comment for why:
 * there's no bulk-create endpoint, and the existing pipeline_trigger job
 * (packages/agents/pipeline/trigger.py) already picks up any SCHEDULED
 * event on its own poll, so plain per-event creates are all "auto-generate"
 * needs to do).
 */
export function buildAutogenEvents(options: {
  days: number;
  postsPerDay: number;
  platforms: string[];
  goals: string[];
  notes: string;
  now?: Date;
}): CalendarEventInput[] {
  const { days, postsPerDay, platforms, goals, notes, now = new Date() } = options;
  const title = goals.length > 0 ? `${goals[0]} post` : "Scheduled post";
  const hours = hoursFor(postsPerDay);
  const events: CalendarEventInput[] = [];

  for (let day = 1; day <= days; day++) {
    for (let i = 0; i < postsPerDay; i++) {
      const target = new Date(now);
      target.setDate(target.getDate() + day);
      target.setHours(hours[i] ?? hours[hours.length - 1], 0, 0, 0);
      events.push({
        title,
        description: notes.trim() || null,
        target_platforms: platforms,
        desired_format: "text",
        target_datetime: target.toISOString(),
      });
    }
  }
  return events;
}

interface AutogenModalProps {
  onClose: () => void;
  onGenerate: (events: CalendarEventInput[]) => Promise<void>;
}

export function AutogenModal({ onClose, onGenerate }: AutogenModalProps) {
  const [days, setDays] = useState(14);
  const [postsPerDay, setPostsPerDay] = useState(2);
  const [platforms, setPlatforms] = useState<string[]>(["linkedin", "x"]);
  const [goals, setGoals] = useState<string[]>([]);
  const [notes, setNotes] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const totalPosts = days * postsPerDay;

  function togglePlatform(value: string) {
    setPlatforms((current) => (current.includes(value) ? current.filter((p) => p !== value) : [...current, value]));
  }

  function toggleGoal(value: string) {
    setGoals((current) => (current.includes(value) ? current.filter((g) => g !== value) : [...current, value]));
  }

  async function handleSubmit() {
    if (platforms.length === 0) {
      setError("Select at least one platform.");
      return;
    }
    setIsSubmitting(true);
    setError(null);

    const events = buildAutogenEvents({ days, postsPerDay, platforms, goals, notes });

    try {
      await onGenerate(events);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate calendar");
      setIsSubmitting(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="Auto-generate calendar" size="lg">
      <div className="space-y-5">
        <p className="text-sm text-ink-400">
          Creates {totalPosts} scheduled post{totalPosts === 1 ? "" : "s"} across the next {days} day
          {days === 1 ? "" : "s"}. Each one runs through the real pipeline — research, creative angle, draft
          generation, and AI review — automatically as its scheduled time approaches.
        </p>

        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-[13px] border border-line-faint p-3.5">
            <div className="mb-2 text-xs font-semibold text-ink-600">How many days</div>
            <div className="flex items-baseline gap-1.5">
              <span className="text-2xl font-extrabold tracking-tight text-ink-950">{days}</span>
              <span className="text-xs text-ink-300">days ahead</span>
            </div>
            <input
              type="range"
              min={1}
              max={30}
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="mt-1.5 w-full accent-brand-600"
              aria-label="Days ahead"
            />
          </div>
          <div className="rounded-[13px] border border-line-faint p-3.5">
            <div className="mb-2 text-xs font-semibold text-ink-600">Posts per day</div>
            <div className="flex items-baseline gap-1.5">
              <span className="text-2xl font-extrabold tracking-tight text-ink-950">{postsPerDay}</span>
              <span className="text-xs text-ink-300">= {totalPosts} posts total</span>
            </div>
            <input
              type="range"
              min={1}
              max={6}
              value={postsPerDay}
              onChange={(e) => setPostsPerDay(Number(e.target.value))}
              className="mt-1.5 w-full accent-brand-600"
              aria-label="Posts per day"
            />
          </div>
        </div>

        <fieldset>
          <legend className="mb-2 text-xs font-semibold text-ink-600">Platforms</legend>
          <div className="flex flex-wrap gap-2">
            {DISPLAY_PLATFORMS.map((p) => (
              <button
                key={p.value}
                type="button"
                disabled={!p.supported}
                title={p.supported ? undefined : "Not supported yet"}
                aria-pressed={platforms.includes(p.value)}
                onClick={() => togglePlatform(p.value)}
                className={cn(
                  "rounded-[10px] border px-3 py-2 text-sm font-medium transition-colors",
                  !p.supported && "cursor-not-allowed opacity-40",
                  platforms.includes(p.value)
                    ? "border-brand-200 bg-brand-50 text-brand-700"
                    : "border-line bg-white text-ink-600",
                )}
              >
                {p.label}
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className="mb-2 text-xs font-semibold text-ink-600">What is this batch for?</legend>
          <div className="flex flex-wrap gap-2">
            {GOALS.map((goal) => (
              <button
                key={goal}
                type="button"
                aria-pressed={goals.includes(goal)}
                onClick={() => toggleGoal(goal)}
                className={cn(
                  "rounded-[10px] border px-3 py-2 text-sm font-medium transition-colors",
                  goals.includes(goal)
                    ? "border-brand-200 bg-brand-50 text-brand-700"
                    : "border-line bg-white text-ink-600",
                )}
              >
                {goal}
              </button>
            ))}
          </div>
        </fieldset>

        <div>
          <label htmlFor="autogen-notes" className="mb-2 block text-xs font-semibold text-ink-600">
            Anything to note for your team?
          </label>
          <Textarea
            id="autogen-notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            placeholder="e.g. Cover the DPDP Act deadline in March. Don't touch pending litigation."
          />
          <p className="mt-1 text-xs text-ink-300">Saved on each event&apos;s description for your team&apos;s reference.</p>
        </div>

        {error && (
          <p role="alert" className="text-sm font-medium text-danger">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2 border-t border-line-faint pt-4">
          <Button type="button" variant="outline" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button type="button" variant="primary" isLoading={isSubmitting} onClick={handleSubmit}>
            Generate {totalPosts} post{totalPosts === 1 ? "" : "s"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
