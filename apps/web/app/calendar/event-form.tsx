"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import type { CalendarEvent, CalendarEventInput, CalendarEventStatus, CalendarEventUpdateInput } from "@/lib/api";
import { fromDatetimeLocalValue, toDatetimeLocalValue } from "./date-utils";
import { CALENDAR_EVENT_STATUSES, STATUS_LABELS } from "./status";

// Kept in sync with apps/api/models/content_calendar_event.py::SUPPORTED_PLATFORMS.
const PLATFORM_OPTIONS: { value: string; label: string }[] = [
  { value: "linkedin", label: "LinkedIn" },
  { value: "x", label: "X" },
];

const FORMAT_SUGGESTIONS = ["image", "video", "carousel", "text", "story"];

interface EventFormProps {
  /** null when creating a new event, the existing event when editing one. */
  event: CalendarEvent | null;
  /** Pre-fills the date/time field when creating (e.g. the day cell that was clicked). */
  defaultDate: Date | null;
  onCancel: () => void;
  onCreate: (payload: CalendarEventInput) => Promise<void>;
  onUpdate: (eventId: string, payload: CalendarEventUpdateInput) => Promise<void>;
  onDelete: (eventId: string) => Promise<void>;
}

export function EventForm({ event, defaultDate, onCancel, onCreate, onUpdate, onDelete }: EventFormProps) {
  const isEdit = event !== null;

  const [title, setTitle] = useState(event?.title ?? "");
  const [description, setDescription] = useState(event?.description ?? "");
  const [platforms, setPlatforms] = useState<string[]>(event?.target_platforms ?? []);
  const [desiredFormat, setDesiredFormat] = useState(event?.desired_format ?? "");
  const [targetDatetime, setTargetDatetime] = useState<string>(() => {
    const initialIso = event?.target_datetime ?? (defaultDate ?? new Date()).toISOString();
    return toDatetimeLocalValue(initialIso);
  });
  const [status, setStatus] = useState<CalendarEventStatus>(event?.status ?? "scheduled");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function togglePlatform(value: string) {
    setPlatforms((current) => (current.includes(value) ? current.filter((p) => p !== value) : [...current, value]));
  }

  async function handleSubmit(formEvent: FormEvent) {
    formEvent.preventDefault();
    if (platforms.length === 0) {
      setError("Select at least one platform.");
      return;
    }

    setIsSubmitting(true);
    setError(null);
    const targetIso = fromDatetimeLocalValue(targetDatetime);

    try {
      if (isEdit && event) {
        await onUpdate(event.id, {
          title,
          description: description || null,
          target_platforms: platforms,
          desired_format: desiredFormat,
          target_datetime: targetIso,
          status,
        });
      } else {
        await onCreate({
          title,
          description: description || null,
          target_platforms: platforms,
          desired_format: desiredFormat,
          target_datetime: targetIso,
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save event");
      setIsSubmitting(false);
    }
  }

  async function handleDelete() {
    if (!event) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await onDelete(event.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete event");
      setIsSubmitting(false);
    }
  }

  return (
    <div className="calendar-modal-backdrop" onClick={onCancel}>
      <div
        className="calendar-modal"
        role="dialog"
        aria-modal="true"
        aria-label={isEdit ? "Edit event" : "New event"}
        onClick={(clickEvent) => clickEvent.stopPropagation()}
      >
        <h2>{isEdit ? "Edit event" : "New event"}</h2>
        <form onSubmit={handleSubmit}>
          <label className="calendar-form-field">
            <span>Title</span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} required />
          </label>

          <label className="calendar-form-field">
            <span>Description</span>
            <textarea value={description ?? ""} onChange={(e) => setDescription(e.target.value)} rows={3} />
          </label>

          <fieldset className="calendar-form-field calendar-form-fieldset">
            <legend>Platforms</legend>
            {PLATFORM_OPTIONS.map((option) => (
              <label key={option.value} className="calendar-checkbox">
                <input
                  type="checkbox"
                  checked={platforms.includes(option.value)}
                  onChange={() => togglePlatform(option.value)}
                />
                {option.label}
              </label>
            ))}
          </fieldset>

          <label className="calendar-form-field">
            <span>Format</span>
            <input
              value={desiredFormat}
              onChange={(e) => setDesiredFormat(e.target.value)}
              required
              list="calendar-format-suggestions"
              placeholder="e.g. image, video, carousel"
            />
            <datalist id="calendar-format-suggestions">
              {FORMAT_SUGGESTIONS.map((suggestion) => (
                <option key={suggestion} value={suggestion} />
              ))}
            </datalist>
          </label>

          <label className="calendar-form-field">
            <span>Date and time</span>
            <input
              type="datetime-local"
              value={targetDatetime}
              onChange={(e) => setTargetDatetime(e.target.value)}
              required
            />
          </label>

          {isEdit && (
            <label className="calendar-form-field">
              <span>Status</span>
              <select value={status} onChange={(e) => setStatus(e.target.value as CalendarEventStatus)}>
                {CALENDAR_EVENT_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {STATUS_LABELS[s]}
                  </option>
                ))}
              </select>
            </label>
          )}

          {error && (
            <p className="calendar-form-error" role="alert">
              {error}
            </p>
          )}

          <div className="calendar-form-actions">
            {isEdit && (
              <button
                type="button"
                className="calendar-delete-button"
                onClick={handleDelete}
                disabled={isSubmitting}
              >
                Delete
              </button>
            )}
            <div className="calendar-form-actions-right">
              <button type="button" onClick={onCancel} disabled={isSubmitting}>
                Cancel
              </button>
              <button type="submit" className="calendar-submit-button" disabled={isSubmitting}>
                {isEdit ? "Save" : "Create"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
