"use client";

import type { CalendarEvent } from "@/lib/api";
import { cn } from "@/components/ui/cn";
import { dayKey, isSameDay } from "./date-utils";
import { primaryPlatformColor } from "./platform";
import { StatusBadge } from "./status-badge";
import { STATUS_ROW_CLASSES } from "./status";

interface DayViewProps {
  referenceDate: Date;
  events: CalendarEvent[];
  today: Date;
  onSelectEvent: (event: CalendarEvent) => void;
  onAddEvent: (date: Date) => void;
}

export function DayView({ referenceDate, events, today, onSelectEvent, onAddEvent }: DayViewProps) {
  const key = dayKey(referenceDate);
  const dayEvents = events
    .filter((event) => dayKey(new Date(event.target_datetime)) === key)
    .slice()
    .sort((a, b) => new Date(a.target_datetime).getTime() - new Date(b.target_datetime).getTime());

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-card" data-testid="day-view">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <span className="text-sm font-semibold text-ink-950">
          {referenceDate.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}
        </span>
        <button
          type="button"
          aria-label={`Add event on ${key}`}
          onClick={() => onAddEvent(referenceDate)}
          className="flex h-7 w-7 items-center justify-center rounded-md text-ink-300 transition-colors hover:bg-canvas hover:text-ink-600"
        >
          +
        </button>
      </div>
      <ul className="flex flex-col gap-2 p-3" data-testid={`day-${key}`}>
        {dayEvents.map((event) => (
          <li key={event.id}>
            <button
              type="button"
              onClick={() => onSelectEvent(event)}
              style={{ borderLeftColor: primaryPlatformColor(event.target_platforms), borderLeftWidth: 3 }}
              className={cn(
                "flex w-full items-center justify-between gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors",
                STATUS_ROW_CLASSES[event.status],
              )}
            >
              <span className="min-w-0">
                <span className="block text-xs font-medium text-slate-500">
                  {new Date(event.target_datetime).toLocaleTimeString(undefined, {
                    hour: "numeric",
                    minute: "2-digit",
                  })}
                </span>
                <span className="block truncate text-sm font-medium text-slate-900">{event.title}</span>
              </span>
              <StatusBadge status={event.status} />
            </button>
          </li>
        ))}
        {dayEvents.length === 0 && (
          <li className="flex items-center justify-center rounded-lg border border-dashed border-slate-200 py-10 text-sm text-slate-400">
            {isSameDay(referenceDate, today) ? "No events today" : "No events"}
          </li>
        )}
      </ul>
    </div>
  );
}
