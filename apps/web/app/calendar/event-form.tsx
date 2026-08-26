"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import type { CalendarEvent, CalendarEventInput, CalendarEventStatus, CalendarEventUpdateInput } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select, Textarea } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
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
    <Modal open onClose={onCancel} title={isEdit ? "Edit event" : "New event"}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Field label="Title" htmlFor="event-title">
          <Input id="event-title" value={title} onChange={(e) => setTitle(e.target.value)} required />
        </Field>

        <Field label="Description" htmlFor="event-description">
          <Textarea
            id="event-description"
            value={description ?? ""}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
          />
        </Field>

        <fieldset className="space-y-1.5">
          <legend className="block text-sm font-medium text-slate-700">Platforms</legend>
          <div className="flex flex-wrap gap-4">
            {PLATFORM_OPTIONS.map((option) => (
              <label key={option.value} className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={platforms.includes(option.value)}
                  onChange={() => togglePlatform(option.value)}
                  className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-2 focus:ring-brand-500/30"
                />
                {option.label}
              </label>
            ))}
          </div>
        </fieldset>

        <Field label="Format" htmlFor="event-format">
          <Input
            id="event-format"
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
        </Field>

        <Field label="Date and time" htmlFor="event-datetime">
          <Input
            id="event-datetime"
            type="datetime-local"
            value={targetDatetime}
            onChange={(e) => setTargetDatetime(e.target.value)}
            required
          />
        </Field>

        {isEdit && (
          <Field label="Status" htmlFor="event-status">
            <Select
              id="event-status"
              value={status}
              onChange={(e) => setStatus(e.target.value as CalendarEventStatus)}
            >
              {CALENDAR_EVENT_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABELS[s]}
                </option>
              ))}
            </Select>
          </Field>
        )}

        {error && (
          <p role="alert" className="text-sm font-medium text-red-600">
            {error}
          </p>
        )}

        <div className="flex items-center justify-between gap-2 pt-2">
          <div>
            {isEdit && (
              <Button type="button" variant="danger" onClick={handleDelete} disabled={isSubmitting}>
                Delete
              </Button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" onClick={onCancel} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button type="submit" isLoading={isSubmitting}>
              {isEdit ? "Save" : "Create"}
            </Button>
          </div>
        </div>
      </form>
    </Modal>
  );
}
