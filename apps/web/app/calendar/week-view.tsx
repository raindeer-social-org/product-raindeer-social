"use client";

import type { CalendarEvent } from "@/lib/api";
import { dayKey, getWeekDays, isSameDay } from "./date-utils";
import { StatusBadge } from "./status-badge";

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
    <div className="calendar-week" data-testid="week-view">
      {days.map((day) => {
        const key = dayKey(day);
        const dayEvents = (eventsByDay.get(key) ?? [])
          .slice()
          .sort((a, b) => new Date(a.target_datetime).getTime() - new Date(b.target_datetime).getTime());
        const isToday = isSameDay(day, today);

        return (
          <div
            key={key}
            className={`calendar-week-day${isToday ? " calendar-day-cell-today" : ""}`}
            data-testid={`day-${key}`}
          >
            <div className="calendar-day-header">
              <span className="calendar-day-number">
                {day.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}
              </span>
              <button
                type="button"
                className="calendar-add-event"
                aria-label={`Add event on ${key}`}
                onClick={() => onAddEvent(day)}
              >
                +
              </button>
            </div>
            <ul className="calendar-week-events">
              {dayEvents.map((event) => (
                <li key={event.id}>
                  <button type="button" className="calendar-week-event" onClick={() => onSelectEvent(event)}>
                    <span className="calendar-event-time">
                      {new Date(event.target_datetime).toLocaleTimeString(undefined, {
                        hour: "numeric",
                        minute: "2-digit",
                      })}
                    </span>
                    <span className="calendar-event-title">{event.title}</span>
                    <StatusBadge status={event.status} />
                  </button>
                </li>
              ))}
              {dayEvents.length === 0 && <li className="calendar-week-empty">No events</li>}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
