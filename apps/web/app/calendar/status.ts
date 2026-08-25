import type { CalendarEventStatus } from "@/lib/api";

// Mirrors apps/api/models/content_calendar_event.py::CalendarEventStatus —
// keep this list and the CSS classes below in sync with that enum.
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

// className applied per-status so each state gets a visually distinct color
// (see .status-* rules in globals.css).
export const STATUS_CLASS: Record<CalendarEventStatus, string> = {
  scheduled: "status-scheduled",
  pipeline_running: "status-pipeline-running",
  ready_for_review: "status-ready-for-review",
  approved: "status-approved",
  published: "status-published",
  failed: "status-failed",
};
