"use client";

import type { CalendarEvent } from "@/lib/api";
import { dayKey, getMonthGrid, isSameDay } from "./date-utils";
import { STATUS_CLASS, STATUS_LABELS } from "./status";

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
  const weeks: Date[][] = [];
  for (let i = 0; i < days.length; i += 7) {
    weeks.push(days.slice(i, i + 7));
  }

  return (
    <div className="calendar-month" data-testid="month-view">
      <div className="calendar-weekday-row">
        {WEEKDAY_LABELS.map((label) => (
          <div key={label} className="calendar-weekday">
            {label}
          </div>
        ))}
      </div>
      {weeks.map((week) => (
        <div className="calendar-week-row" key={dayKey(week[0])}>
          {week.map((day) => {
            const key = dayKey(day);
            const dayEvents = eventsByDay.get(key) ?? [];
            const inMonth = day.getMonth() === referenceDate.getMonth();
            const isToday = isSameDay(day, today);
            const classes = [
              "calendar-day-cell",
              inMonth ? "" : "calendar-day-cell-outside",
              isToday ? "calendar-day-cell-today" : "",
            ]
              .filter(Boolean)
              .join(" ");

            return (
              <div className={classes} key={key} data-testid={`day-${key}`}>
                <div className="calendar-day-header">
                  <span className="calendar-day-number">{day.getDate()}</span>
                  <button
                    type="button"
                    className="calendar-add-event"
                    aria-label={`Add event on ${key}`}
                    onClick={() => onAddEvent(day)}
                  >
                    +
                  </button>
                </div>
                <ul className="calendar-day-events">
                  {dayEvents.map((event) => (
                    <li key={event.id}>
                      <button
                        type="button"
                        className={`calendar-event-chip ${STATUS_CLASS[event.status]}`}
                        onClick={() => onSelectEvent(event)}
                        title={`${event.title} — ${STATUS_LABELS[event.status]}`}
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
      ))}
    </div>
  );
}
