"use client";

import type { CalendarEventStatus } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { STATUS_BADGE_TONE, STATUS_LABELS } from "./status";

export function StatusBadge({ status }: { status: CalendarEventStatus }) {
  return <Badge tone={STATUS_BADGE_TONE[status]}>{STATUS_LABELS[status]}</Badge>;
}
