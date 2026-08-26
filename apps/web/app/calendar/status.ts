import type { CalendarEventStatus } from "@/lib/api";
import type { BadgeTone } from "@/components/ui/Badge";

// Mirrors apps/api/models/content_calendar_event.py::CalendarEventStatus —
// keep this list and the style maps below in sync with that enum.
export const CALENDAR_EVENT_STATUSES: CalendarEventStatus[] = [
  "scheduled",
  "pipeline_running",
  "ready_for_review",
  "approved",
  "published",
  "failed",
];

export const STATUS_LABELS: Record<CalendarEventStatus, string> = {
  scheduled: "Scheduled",
  pipeline_running: "Pipeline running",
  ready_for_review: "Ready for review",
  approved: "Approved",
  published: "Published",
  failed: "Failed",
};

// A stable, semantic class-name token per status. These carry no CSS rules
// of their own (styling now comes from the Tailwind maps below) — they
// exist so tests can assert which status an element represents without
// depending on visual styling. Keep the string values unchanged; see
// calendar-page.test.tsx / calendar-views.test.tsx.
export const STATUS_CLASS: Record<CalendarEventStatus, string> = {
  scheduled: "status-scheduled",
  pipeline_running: "status-pipeline-running",
  ready_for_review: "status-ready-for-review",
  approved: "status-approved",
  published: "status-published",
  failed: "status-failed",
};

// Badge tone per status, used by <StatusBadge>.
export const STATUS_BADGE_TONE: Record<CalendarEventStatus, BadgeTone> = {
  scheduled: "slate",
  pipeline_running: "blue",
  ready_for_review: "amber",
  approved: "brand",
  published: "green",
  failed: "red",
};

// Tailwind classes for the compact event chips in the month grid.
export const STATUS_CHIP_CLASSES: Record<CalendarEventStatus, string> = {
  scheduled: "bg-slate-100 text-slate-700 hover:bg-slate-200",
  pipeline_running: "bg-blue-100 text-blue-700 hover:bg-blue-200",
  ready_for_review: "bg-amber-100 text-amber-800 hover:bg-amber-200",
  approved: "bg-brand-100 text-brand-700 hover:bg-brand-200",
  published: "bg-emerald-100 text-emerald-700 hover:bg-emerald-200",
  failed: "bg-red-100 text-red-700 hover:bg-red-200",
};

// Tailwind classes for the event rows in the week view (lighter tint + border).
export const STATUS_ROW_CLASSES: Record<CalendarEventStatus, string> = {
  scheduled: "border-slate-200 bg-slate-50 hover:bg-slate-100",
  pipeline_running: "border-blue-200 bg-blue-50 hover:bg-blue-100",
  ready_for_review: "border-amber-200 bg-amber-50 hover:bg-amber-100",
  approved: "border-brand-200 bg-brand-50 hover:bg-brand-100",
  published: "border-emerald-200 bg-emerald-50 hover:bg-emerald-100",
  failed: "border-red-200 bg-red-50 hover:bg-red-100",
};
