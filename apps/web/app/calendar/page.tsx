"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  type CalendarEvent,
  type CalendarEventInput,
  type CalendarEventStatus,
  type CalendarEventUpdateInput,
  createCalendarEvent,
  deleteCalendarEvent,
  fetchCalendarEvents,
  updateCalendarEvent,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useBrand } from "@/lib/brand-context";
import { Button } from "@/components/ui/Button";
import { cn } from "@/components/ui/cn";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { AutogenModal } from "./autogen-modal";
import { addDays, addMonths, formatMonthLabel, formatWeekRangeLabel } from "./date-utils";
import { DayView } from "./day-view";
import { EventForm } from "./event-form";
import { MonthView } from "./month-view";
import { platformLabel, primaryPlatformColor } from "./platform";
import { PostPreviewModal } from "./post-preview-modal";
import { CALENDAR_EVENT_STATUSES, STATUS_LABELS } from "./status";
import { WeekView } from "./week-view";

// How often to silently re-poll while the calendar is mounted, so status
// transitions driven by the backend pipeline (e.g. pipeline_running ->
// ready_for_review) show up without the user refreshing the page. Also
// re-polled on window focus for the common "tabbed away and back" case.
const POLL_INTERVAL_MS = 15000;

type ViewMode = "day" | "week" | "month";

interface FormState {
  event: CalendarEvent | null;
  defaultDate: Date | null;
}

export default function CalendarPage() {
  const { token } = useAuth();
  const { selectedBrand, selectedBrandId } = useBrand();

  const [view, setView] = useState<ViewMode>("month");
  const [referenceDate, setReferenceDate] = useState(() => new Date());
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [formState, setFormState] = useState<FormState | null>(null);
  const [previewEvent, setPreviewEvent] = useState<CalendarEvent | null>(null);
  const [showAutogen, setShowAutogen] = useState(false);
  const [platformFilters, setPlatformFilters] = useState<string[]>([]);
  const [statusFilters, setStatusFilters] = useState<CalendarEventStatus[]>([]);

  const loadEvents = useCallback(
    async (showSpinner: boolean) => {
      if (!token || !selectedBrandId) {
        setEvents([]);
        return;
      }
      if (showSpinner) setIsLoading(true);
      setError(null);
      try {
        const result = await fetchCalendarEvents(token, selectedBrandId);
        setEvents(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load calendar events");
      } finally {
        if (showSpinner) setIsLoading(false);
      }
    },
    [token, selectedBrandId]
  );

  // Re-run whenever the token or the selected brand changes (brand switch
  // re-scopes the calendar), and set up polling + focus refresh for the
  // life of that scope.
  useEffect(() => {
    setEvents([]);
    loadEvents(true);

    const interval = setInterval(() => loadEvents(false), POLL_INTERVAL_MS);
    const onFocus = () => loadEvents(false);
    window.addEventListener("focus", onFocus);

    return () => {
      clearInterval(interval);
      window.removeEventListener("focus", onFocus);
    };
  }, [loadEvents]);

  // Reset filters whenever the brand scope changes — a platform/status
  // filter picked for one brand's events isn't meaningful for another's.
  useEffect(() => {
    setPlatformFilters([]);
    setStatusFilters([]);
  }, [selectedBrandId]);

  useEffect(() => {
    if (!notice) return;
    const timeout = setTimeout(() => setNotice(null), 6000);
    return () => clearTimeout(timeout);
  }, [notice]);

  const platformCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const event of events) {
      for (const platform of event.target_platforms) {
        counts.set(platform, (counts.get(platform) ?? 0) + 1);
      }
    }
    return counts;
  }, [events]);

  const statusCounts = useMemo(() => {
    const counts = new Map<CalendarEventStatus, number>();
    for (const event of events) {
      counts.set(event.status, (counts.get(event.status) ?? 0) + 1);
    }
    return counts;
  }, [events]);

  const filteredEvents = useMemo(() => {
    return events.filter((event) => {
      const platformMatch =
        platformFilters.length === 0 || event.target_platforms.some((p) => platformFilters.includes(p));
      const statusMatch = statusFilters.length === 0 || statusFilters.includes(event.status);
      return platformMatch && statusMatch;
    });
  }, [events, platformFilters, statusFilters]);

  function togglePlatformFilter(platform: string) {
    setPlatformFilters((current) =>
      current.includes(platform) ? current.filter((p) => p !== platform) : [...current, platform]
    );
  }

  function toggleStatusFilter(status: CalendarEventStatus) {
    setStatusFilters((current) =>
      current.includes(status) ? current.filter((s) => s !== status) : [...current, status]
    );
  }

  function openCreateForm(date: Date) {
    setFormState({ event: null, defaultDate: date });
  }

  function openEditForm(event: CalendarEvent) {
    setPreviewEvent(null);
    setFormState({ event, defaultDate: null });
  }

  function closeForm() {
    setFormState(null);
  }

  async function handleCreate(payload: CalendarEventInput) {
    if (!token || !selectedBrandId) return;
    const created = await createCalendarEvent(token, selectedBrandId, payload);
    setEvents((current) => [...current, created]);
    setFormState(null);
  }

  async function handleUpdate(eventId: string, payload: CalendarEventUpdateInput) {
    if (!token || !selectedBrandId) return;
    const updated = await updateCalendarEvent(token, selectedBrandId, eventId, payload);
    setEvents((current) => current.map((e) => (e.id === updated.id ? updated : e)));
    setFormState(null);
  }

  async function handleDelete(eventId: string) {
    if (!token || !selectedBrandId) return;
    await deleteCalendarEvent(token, selectedBrandId, eventId);
    setEvents((current) => current.filter((e) => e.id !== eventId));
    setFormState(null);
  }

  // The wizard hands back plain event payloads (see autogen-modal.tsx);
  // this is the "real bulk pipeline generation" trigger the issue asks
  // for. There's no bulk-create endpoint on the calendar-events router
  // (apps/api/routers/calendar.py) — each SCHEDULED event just needs to
  // exist for the existing pipeline_trigger job
  // (packages/agents/pipeline/trigger.py, polled by apps/api/worker.py's
  // Celery beat) to pick it up on its own once it's within
  // Settings.pipeline_trigger_lead_minutes of its target_datetime — so
  // looping the existing single-event create endpoint client-side is the
  // simplest approach that's actually consistent with how #29 already
  // works, rather than inventing a second, parallel bulk-generation path.
  async function handleAutogenerate(payloads: CalendarEventInput[]) {
    if (!token || !selectedBrandId) return;
    const created: CalendarEvent[] = [];
    for (const payload of payloads) {
      created.push(await createCalendarEvent(token, selectedBrandId, payload));
    }
    setEvents((current) => [...current, ...created]);
    setShowAutogen(false);
    setNotice(`Created ${created.length} scheduled post${created.length === 1 ? "" : "s"}.`);
  }

  function goToday() {
    setReferenceDate(new Date());
  }

  function goPrevious() {
    setReferenceDate((current) =>
      view === "month" ? addMonths(current, -1) : view === "week" ? addDays(current, -7) : addDays(current, -1)
    );
  }

  function goNext() {
    setReferenceDate((current) =>
      view === "month" ? addMonths(current, 1) : view === "week" ? addDays(current, 7) : addDays(current, 1)
    );
  }

  const today = new Date();
  const periodLabel =
    view === "month"
      ? formatMonthLabel(referenceDate)
      : view === "week"
        ? formatWeekRangeLabel(referenceDate)
        : referenceDate.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });

  return (
    <div>
      <PageHeader
        title="Calendar"
        description={
          <>
            Showing data for: <strong className="font-semibold text-slate-700">{selectedBrand ? selectedBrand.name : "no brand selected"}</strong>
          </>
        }
        action={
          selectedBrand ? (
            <div className="flex flex-wrap items-center gap-2">
              <div
                className="inline-flex items-center rounded-lg border border-slate-200 bg-white p-0.5"
                role="group"
                aria-label="Calendar view"
              >
                {(["day", "week", "month"] as ViewMode[]).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    aria-pressed={view === mode}
                    onClick={() => setView(mode)}
                    className={cn(
                      "rounded-md px-3 py-1.5 text-sm font-medium capitalize transition-colors",
                      view === mode ? "bg-brand-600 text-white shadow-sm" : "text-slate-600 hover:bg-slate-100",
                    )}
                  >
                    {mode}
                  </button>
                ))}
              </div>
              <Button variant="outline" onClick={() => openCreateForm(referenceDate)}>
                + New post
              </Button>
              <Button onClick={() => setShowAutogen(true)}>✧ Auto-generate calendar</Button>
            </div>
          ) : null
        }
      />

      {selectedBrand && (
        <>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-1.5">
              <Button variant="outline" size="sm" aria-label="Previous period" onClick={goPrevious}>
                &larr;
              </Button>
              <Button variant="outline" size="sm" onClick={goToday}>
                Today
              </Button>
              <Button variant="outline" size="sm" aria-label="Next period" onClick={goNext}>
                &rarr;
              </Button>
            </div>
            <span className="text-sm font-medium text-slate-600">{periodLabel}</span>
          </div>

          {(platformCounts.size > 0 || statusCounts.size > 0) && (
            <div className="mb-4 flex flex-wrap items-center gap-1.5">
              {[...platformCounts.entries()].map(([platform, count]) => (
                <button
                  key={platform}
                  type="button"
                  aria-pressed={platformFilters.includes(platform)}
                  onClick={() => togglePlatformFilter(platform)}
                  className={cn(
                    "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold transition-colors",
                    platformFilters.includes(platform)
                      ? "border-brand-200 bg-brand-50 text-brand-700"
                      : "border-line bg-white text-ink-600 hover:bg-canvas",
                  )}
                >
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ backgroundColor: primaryPlatformColor([platform]) }}
                    aria-hidden="true"
                  />
                  {platformLabel(platform)}
                  <span className="text-ink-300">{count}</span>
                </button>
              ))}
              {CALENDAR_EVENT_STATUSES.filter((status) => statusCounts.has(status)).map((status) => (
                <button
                  key={status}
                  type="button"
                  aria-pressed={statusFilters.includes(status)}
                  onClick={() => toggleStatusFilter(status)}
                  className={cn(
                    "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold transition-colors",
                    statusFilters.includes(status)
                      ? "border-brand-200 bg-brand-50 text-brand-700"
                      : "border-line bg-white text-ink-600 hover:bg-canvas",
                  )}
                >
                  {STATUS_LABELS[status]}
                  <span className="text-ink-300">{statusCounts.get(status)}</span>
                </button>
              ))}
              {(platformFilters.length > 0 || statusFilters.length > 0) && (
                <button
                  type="button"
                  onClick={() => {
                    setPlatformFilters([]);
                    setStatusFilters([]);
                  }}
                  className="text-xs font-semibold text-ink-400 underline-offset-2 hover:underline"
                >
                  Clear filters
                </button>
              )}
            </div>
          )}
        </>
      )}

      {error && (
        <p role="alert" className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
          {error}
        </p>
      )}

      {notice && (
        <p role="status" className="mb-4 rounded-lg bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-700">
          {notice}
        </p>
      )}

      {!selectedBrand ? (
        <EmptyState title="Select a brand to see its calendar." />
      ) : isLoading && events.length === 0 ? (
        <p role="status" className="py-10 text-center text-sm text-slate-500">
          Loading events…
        </p>
      ) : view === "month" ? (
        <MonthView
          referenceDate={referenceDate}
          events={filteredEvents}
          today={today}
          onSelectEvent={setPreviewEvent}
          onAddEvent={openCreateForm}
        />
      ) : view === "week" ? (
        <WeekView
          referenceDate={referenceDate}
          events={filteredEvents}
          today={today}
          onSelectEvent={setPreviewEvent}
          onAddEvent={openCreateForm}
        />
      ) : (
        <DayView
          referenceDate={referenceDate}
          events={filteredEvents}
          today={today}
          onSelectEvent={setPreviewEvent}
          onAddEvent={openCreateForm}
        />
      )}

      {formState && (
        <EventForm
          event={formState.event}
          defaultDate={formState.defaultDate}
          onCancel={closeForm}
          onCreate={handleCreate}
          onUpdate={handleUpdate}
          onDelete={handleDelete}
        />
      )}

      {previewEvent && token && selectedBrandId && (
        <PostPreviewModal
          event={previewEvent}
          token={token}
          brandId={selectedBrandId}
          brandName={selectedBrand?.name ?? "Brand"}
          onClose={() => setPreviewEvent(null)}
          onEdit={openEditForm}
        />
      )}

      {showAutogen && <AutogenModal onClose={() => setShowAutogen(false)} onGenerate={handleAutogenerate} />}
    </div>
  );
}
