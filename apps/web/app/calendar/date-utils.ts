// Local-time date helpers for the calendar month/week grids. Deliberately
// dependency-free (no date-fns/luxon) since apps/web has no date library
// installed yet and this module's needs are small.

export function startOfWeek(date: Date): Date {
  const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  d.setDate(d.getDate() - d.getDay());
  return d;
}

export function addDays(date: Date, days: number): Date {
  const d = new Date(date);
  d.setDate(d.getDate() + days);
  return d;
}

export function addMonths(date: Date, months: number): Date {
  return new Date(date.getFullYear(), date.getMonth() + months, 1);
}

export function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/** Stable "YYYY-MM-DD" key (local time) used to group events by day and as React keys. */
export function dayKey(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/**
 * A 6-week (42-day) grid starting on the Sunday on/before the 1st of
 * `reference`'s month. Six weeks always fully covers any month regardless
 * of which weekday it starts on, so the grid size never has to vary.
 */
export function getMonthGrid(reference: Date): Date[] {
  const firstOfMonth = new Date(reference.getFullYear(), reference.getMonth(), 1);
  const start = startOfWeek(firstOfMonth);
  return Array.from({ length: 42 }, (_, i) => addDays(start, i));
}

export function getWeekDays(reference: Date): Date[] {
  const start = startOfWeek(reference);
  return Array.from({ length: 7 }, (_, i) => addDays(start, i));
}

export function formatMonthLabel(date: Date): string {
  return date.toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

export function formatWeekRangeLabel(reference: Date): string {
  const days = getWeekDays(reference);
  const start = days[0];
  const end = days[6];
  const startLabel = start.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  const endLabel = end.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  return `${startLabel} – ${endLabel}`;
}

/** Converts an ISO datetime string to the "YYYY-MM-DDTHH:mm" shape a `<input type="datetime-local">` needs. */
export function toDatetimeLocalValue(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Converts a `<input type="datetime-local">` value (local time, no timezone) back to an ISO string for the API. */
export function fromDatetimeLocalValue(value: string): string {
  return new Date(value).toISOString();
}
