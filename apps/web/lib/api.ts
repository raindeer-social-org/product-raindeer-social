// Thin client around the FastAPI backend (apps/api). Kept dependency-free
// (plain fetch) so the app shell doesn't need an HTTP library just to log
// in and list brands.

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

// Mirrors apps/api/schemas/brand.py::BrandRead.
export interface Brand {
  id: string;
  organization_id: string;
  name: string;
  industry: string | null;
  logo_url: string | null;
  target_audience: string | null;
  colors: string[] | null;
  tone_descriptors: string[] | null;
  product_catalog: Record<string, unknown> | null;
  brand_report: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

// Mirrors apps/api/models/content_calendar_event.py::CalendarEventStatus.
export type CalendarEventStatus =
  | "scheduled"
  | "pipeline_running"
  | "ready_for_review"
  | "approved"
  | "published"
  | "failed";

// Mirrors apps/api/schemas/calendar.py::CalendarEventRead.
export interface CalendarEvent {
  id: string;
  brand_id: string;
  title: string;
  description: string | null;
  target_platforms: string[];
  desired_format: string;
  target_datetime: string;
  status: CalendarEventStatus;
  created_at: string;
  updated_at: string;
}

// Mirrors apps/api/schemas/calendar.py::CalendarEventCreate.
export interface CalendarEventInput {
  title: string;
  description?: string | null;
  target_platforms: string[];
  desired_format: string;
  target_datetime: string;
}

// Mirrors apps/api/schemas/calendar.py::CalendarEventUpdate — every field
// optional, PATCH-style (only fields present are changed server-side).
export interface CalendarEventUpdateInput {
  title?: string;
  description?: string | null;
  target_platforms?: string[];
  desired_format?: string;
  target_datetime?: string;
  status?: CalendarEventStatus;
}

function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

async function parseErrorDetail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch {
    // response wasn't JSON — fall through to the generic message below.
  }
  return `Request failed with status ${res.status}`;
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  const res = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

export async function fetchBrands(token: string): Promise<Brand[]> {
  const res = await fetch(`${API_URL}/brands`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

// apps/api/routers/calendar.py mounts these under
// /brands/{brand_id}/calendar-events, so every call is scoped to a brand.
function calendarEventsUrl(brandId: string, suffix = ""): string {
  return `${API_URL}/brands/${brandId}/calendar-events${suffix}`;
}

export async function fetchCalendarEvents(token: string, brandId: string): Promise<CalendarEvent[]> {
  const res = await fetch(calendarEventsUrl(brandId), {
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

export async function createCalendarEvent(
  token: string,
  brandId: string,
  payload: CalendarEventInput
): Promise<CalendarEvent> {
  const res = await fetch(calendarEventsUrl(brandId), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

export async function updateCalendarEvent(
  token: string,
  brandId: string,
  eventId: string,
  payload: CalendarEventUpdateInput
): Promise<CalendarEvent> {
  const res = await fetch(calendarEventsUrl(brandId, `/${eventId}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

export async function deleteCalendarEvent(token: string, brandId: string, eventId: string): Promise<void> {
  const res = await fetch(calendarEventsUrl(brandId, `/${eventId}`), {
    method: "DELETE",
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }
}
