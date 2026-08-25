"use client";

import { useCallback, useEffect, useState } from "react";
import {
  type CalendarEvent,
  type CalendarEventInput,
  type CalendarEventUpdateInput,
  createCalendarEvent,
  deleteCalendarEvent,
  fetchCalendarEvents,
  updateCalendarEvent,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useBrand } from "@/lib/brand-context";
import { addDays, addMonths, formatMonthLabel, formatWeekRangeLabel } from "./date-utils";
import { EventForm } from "./event-form";
import { MonthView } from "./month-view";
import { WeekView } from "./week-view";

// How often to silently re-poll while the calendar is mounted, so status
// transitions driven by the backend pipeline (e.g. pipeline_running ->
// ready_for_review) show up without the user refreshing the page. Also
// re-polled on window focus for the common "tabbed away and back" case.
const POLL_INTERVAL_MS = 15000;

type ViewMode = "month" | "week";

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
  const [formState, setFormState] = useState<FormState | null>(null);

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

  function openCreateForm(date: Date) {
    setFormState({ event: null, defaultDate: date });
  }

  function openEditForm(event: CalendarEvent) {
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

  function goToday() {
    setReferenceDate(new Date());
  }

  function goPrevious() {
    setReferenceDate((current) => (view === "month" ? addMonths(current, -1) : addDays(current, -7)));
  }

  function goNext() {
    setReferenceDate((current) => (view === "month" ? addMonths(current, 1) : addDays(current, 7)));
  }

  const today = new Date();

  return (
    <section className="calendar-page">
      <div className="calendar-toolbar">
        <div className="calendar-toolbar-left">
          <h1>Calendar</h1>
          <p className="scoped-brand">
            Showing data for: <strong>{selectedBrand ? selectedBrand.name : "no brand selected"}</strong>
          </p>
        </div>

        {selectedBrand && (
          <div className="calendar-toolbar-right">
            <div className="calendar-view-toggle" role="group" aria-label="Calendar view">
              <button type="button" aria-pressed={view === "month"} onClick={() => setView("month")}>
                Month
              </button>
              <button type="button" aria-pressed={view === "week"} onClick={() => setView("week")}>
                Week
              </button>
            </div>
            <div className="calendar-nav">
              <button type="button" onClick={goPrevious} aria-label="Previous period">
                &larr;
              </button>
              <button type="button" onClick={goToday}>
                Today
              </button>
              <button type="button" onClick={goNext} aria-label="Next period">
                &rarr;
              </button>
            </div>
            <span className="calendar-period-label">
              {view === "month" ? formatMonthLabel(referenceDate) : formatWeekRangeLabel(referenceDate)}
            </span>
            <button type="button" className="calendar-new-event" onClick={() => openCreateForm(referenceDate)}>
              + New event
            </button>
          </div>
        )}
      </div>

      {error && (
        <p className="calendar-error" role="alert">
          {error}
        </p>
      )}

      {!selectedBrand ? (
        <p>Select a brand to see its calendar.</p>
      ) : isLoading && events.length === 0 ? (
        <p role="status">Loading events…</p>
      ) : view === "month" ? (
        <MonthView
          referenceDate={referenceDate}
          events={events}
          today={today}
          onSelectEvent={openEditForm}
          onAddEvent={openCreateForm}
        />
      ) : (
        <WeekView
          referenceDate={referenceDate}
          events={events}
          today={today}
          onSelectEvent={openEditForm}
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
import { useBrand } from "@/lib/brand-context";

// Stub for #27 — replace with the real calendar view.
export default function CalendarPage() {
  const { selectedBrand } = useBrand();

  return (
    <section className="stub-page">
      <h1>Calendar</h1>
      <p>Coming soon.</p>
      <p className="scoped-brand">
        Showing data for: <strong>{selectedBrand ? selectedBrand.name : "no brand selected"}</strong>
      </p>
    </section>
  );
}
