"use client";

import type { CalendarEvent } from "@/lib/api";
import { cn } from "@/components/ui/cn";
import { dayKey, getMonthGrid, isSameDay } from "./date-utils";
import { STATUS_CHIP_CLASSES, STATUS_CLASS, STATUS_LABELS } from "./status";

const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

interface MonthViewProps {
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

export function MonthView({ referenceDate, events, today, onSelectEvent, onAddEvent }: MonthViewProps) {
  const days = getMonthGrid(referenceDate);
  const eventsByDay = groupByDay(events);

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-card" data-testid="month-view">
      <div className="grid grid-cols-7 border-b border-slate-100 bg-slate-50">
        {WEEKDAY_LABELS.map((label) => (
          <div
            key={label}
            className="px-2 py-2 text-center text-xs font-semibold uppercase tracking-wide text-slate-500"
          >
            {label}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-px bg-slate-100">
        {days.map((day) => {
          const key = dayKey(day);
          const dayEvents = eventsByDay.get(key) ?? [];
          const inMonth = day.getMonth() === referenceDate.getMonth();
          const isToday = isSameDay(day, today);

          return (
            <div
              key={key}
              data-testid={`day-${key}`}
              className={cn(
                "group flex min-h-[6.5rem] flex-col gap-1 bg-white p-1.5 sm:min-h-[8rem] sm:p-2",
                !inMonth && "bg-slate-50",
              )}
            >
              <div className="flex items-center justify-between">
                <span
                  className={cn(
                    "flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium",
                    isToday
                      ? "bg-brand-600 text-white"
                      : inMonth
                        ? "text-slate-700"
                        : "text-slate-400",
                  )}
                >
                  {day.getDate()}
                </span>
                <button
                  type="button"
                  aria-label={`Add event on ${key}`}
                  onClick={() => onAddEvent(day)}
                  className="flex h-5 w-5 items-center justify-center rounded text-slate-400 opacity-0 transition-opacity hover:bg-slate-100 hover:text-slate-600 focus-visible:opacity-100 group-hover:opacity-100"
                >
                  +
                </button>
              </div>
              <ul className="flex flex-1 flex-col gap-1 overflow-y-auto">
                {dayEvents.map((event) => (
                  <li key={event.id}>
                    <button
                      type="button"
                      onClick={() => onSelectEvent(event)}
                      title={`${event.title} — ${STATUS_LABELS[event.status]}`}
                      className={cn(
                        "block w-full truncate rounded-md px-1.5 py-1 text-left text-xs font-medium transition-colors",
                        STATUS_CLASS[event.status],
                        STATUS_CHIP_CLASSES[event.status],
                      )}
                    >
                      {event.title}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </div>
  );
}
