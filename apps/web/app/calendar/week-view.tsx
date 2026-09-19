"use client";

import type { CalendarEvent } from "@/lib/api";
import { cn } from "@/components/ui/cn";
import { dayKey, getWeekDays, isSameDay } from "./date-utils";
import { primaryPlatformColor } from "./platform";
import { StatusBadge } from "./status-badge";
import { STATUS_ROW_CLASSES } from "./status";

interface WeekViewProps {
  referenceDate: Date;
  events: CalendarEvent[];
  today: Date;
  onSelectEvent: (event: CalendarEvent) => void;
  onAddEvent: (date: Date) => void;
}

function groupByDay(events: CalendarEvent[]): Map<string, CalendarEvent[]> {
  const map = new Map<string, CalendarEvent[]>();
  for (const event of events) {
    const key = dayKey(new Date(event.target_datetime));
    const list = map.get(key);
    if (list) {
      list.push(event);
    } else {
      map.set(key, [event]);
    }
  }
  return map;
}

export function WeekView({ referenceDate, events, today, onSelectEvent, onAddEvent }: WeekViewProps) {
  const days = getWeekDays(referenceDate);
  const eventsByDay = groupByDay(events);

  return (
    <div
      className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-7"
      data-testid="week-view"
    >
      {days.map((day) => {
        const key = dayKey(day);
        const dayEvents = (eventsByDay.get(key) ?? [])
          .slice()
          .sort((a, b) => new Date(a.target_datetime).getTime() - new Date(b.target_datetime).getTime());
        const isToday = isSameDay(day, today);

        return (
          <div
            key={key}
            data-testid={`day-${key}`}
            className={cn(
              "flex flex-col rounded-xl border border-slate-200 bg-white shadow-card",
              isToday && "ring-2 ring-brand-500",
            )}
          >
            <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
              <span className={cn("text-sm font-semibold", isToday ? "text-brand-700" : "text-slate-700")}>
                {day.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}
              </span>
              <button
                type="button"
                aria-label={`Add event on ${key}`}
                onClick={() => onAddEvent(day)}
                className="flex h-6 w-6 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
              >
                +
              </button>
            </div>
            <ul className="flex flex-1 flex-col gap-2 p-2">
              {dayEvents.map((event) => (
                <li key={event.id}>
                  <button
                    type="button"
                    onClick={() => onSelectEvent(event)}
                    style={{ borderLeftColor: primaryPlatformColor(event.target_platforms), borderLeftWidth: 3 }}
                    className={cn(
                      "flex w-full flex-col gap-1 rounded-lg border px-2.5 py-2 text-left transition-colors",
                      STATUS_ROW_CLASSES[event.status],
                    )}
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium text-slate-500">
                        {new Date(event.target_datetime).toLocaleTimeString(undefined, {
                          hour: "numeric",
                          minute: "2-digit",
                        })}
                      </span>
                      <StatusBadge status={event.status} />
                    </span>
                    <span className="truncate text-sm font-medium text-slate-900">{event.title}</span>
                  </button>
                </li>
              ))}
              {dayEvents.length === 0 && (
                <li className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-slate-200 py-6 text-xs text-slate-400">
                  No events
                </li>
              )}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
