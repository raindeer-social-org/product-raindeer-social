"use client";

import type { CalendarEventStatus } from "@/lib/api";
import { STATUS_CLASS, STATUS_LABELS } from "./status";

export function StatusBadge({ status }: { status: CalendarEventStatus }) {
  return <span className={`status-badge ${STATUS_CLASS[status]}`}>{STATUS_LABELS[status]}</span>;
}
