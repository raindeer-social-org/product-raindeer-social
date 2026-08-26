import { formatDateInput } from "./format";

// Mirrors apps/api/routers/analytics.py::DEFAULT_WINDOW_DAYS — the "30d"
// preset below reproduces the backend's own default range, so a caller
// who never touches the picker still sees exactly what the API would
// have defaulted to if no start_date/end_date were sent at all.
export type DateRangePreset = "7d" | "30d" | "90d" | "custom";

export interface DateRangeValue {
  preset: DateRangePreset;
  customStart: string; // YYYY-MM-DD, only used when preset === "custom"
  customEnd: string;
}

export const PRESET_LABELS: Record<Exclude<DateRangePreset, "custom">, string> = {
  "7d": "Last 7 days",
  "30d": "Last 30 days",
  "90d": "Last 90 days",
};

export function defaultDateRangeValue(): DateRangeValue {
  const now = new Date();
  return {
    preset: "30d",
    customStart: formatDateInput(new Date(now.getTime() - 30 * 86_400_000)),
    customEnd: formatDateInput(now),
  };
}

/** Resolves a DateRangeValue to concrete ISO instants at the moment it's
 * called (rather than storing a computed "now" in state), so presets like
 * "last 7 days" stay anchored to whenever the caller actually fetches. */
export function resolveDateRange(value: DateRangeValue): { startDate: Date; endDate: Date } {
  if (value.preset === "custom") {
    const startDate = new Date(`${value.customStart}T00:00:00`);
    // Inclusive of the whole end day — the backend's upper bound is
    // exclusive (< end_date), so anchor it to the end of that day.
    const endDate = new Date(`${value.customEnd}T23:59:59.999`);
    return { startDate, endDate };
  }
  const days = { "7d": 7, "30d": 30, "90d": 90 }[value.preset];
  const endDate = new Date();
  const startDate = new Date(endDate.getTime() - days * 86_400_000);
  return { startDate, endDate };
}
