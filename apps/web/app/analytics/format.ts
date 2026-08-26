// Formatting helpers for the analytics dashboard. Kept tiny and
// dependency-free, matching the rest of this app.

/** 1284 -> "1,284", 12987 -> "13.0K", 4230000 -> "4.2M". Proportional
 * figures everywhere these are used (stat tiles, bar labels) — see the
 * dataviz skill's marks-and-anatomy.md: tabular-nums is reserved for
 * columns that must align vertically (table cells), not standalone
 * numbers. */
export function formatCompactNumber(value: number): string {
  const abs = Math.abs(value);
  if (abs < 1000) {
    return Math.round(value).toLocaleString("en-US");
  }
  if (abs < 1_000_000) {
    return `${(value / 1000).toFixed(1)}K`;
  }
  return `${(value / 1_000_000).toFixed(1)}M`;
}

/** Fixed one-decimal average, e.g. 12.375 -> "12.4". */
export function formatAverage(value: number): string {
  return value.toFixed(1);
}

export function formatDateInput(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function formatDateLabel(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function formatDateTimeLabel(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
