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

// Mirrors apps/api/models/review_feedback.py::ReviewSource/ReviewVerdict.
export type ReviewSource = "ai_reviewer" | "human";
export type ReviewVerdict = "approve" | "revise" | "reject";

// Mirrors apps/api/schemas/review.py::ReviewFeedbackRead. `comments` is
// free-form JSONB — for an ai_reviewer row it's shaped like
// { platforms: { [platform]: { score, verdict, issues, suggested_edits } }, model };
// for a human row it's { comments?: string }.
export interface ReviewFeedback {
  id: string;
  post_id: string;
  source: ReviewSource;
  score: number;
  verdict: ReviewVerdict;
  comments: Record<string, unknown>;
  created_at: string;
}

// Mirrors apps/api/models/post.py::PipelineStage.
export type PipelineStage =
  | "research"
  | "creative"
  | "generation"
  | "reviewer"
  | "human_review"
  | "scheduler"
  | "publisher"
  | "analytics_collector"
  | "completed"
  | "rejected";

// Mirrors apps/api/schemas/review.py::ReviewQueuePostRead.
export interface ReviewQueuePost {
  id: string;
  brand_id: string;
  calendar_event_id: string | null;
  current_pipeline_stage: PipelineStage;
  body_text: Record<string, string> | null;
  created_at: string;
  updated_at: string;
  review_feedback: ReviewFeedback[];
}

// Mirrors apps/api/schemas/review.py::HumanReviewDecision.
export interface HumanReviewDecisionInput {
  comments?: string | null;
  score?: number | null;
}

// Mirrors apps/api/schemas/review.py::HumanReviewEdit.
export interface HumanReviewEditInput {
  body_text: Record<string, string>;
}

// Mirrors apps/api/schemas/review.py::HumanReviewReschedule.
export interface HumanReviewRescheduleInput {
  target_datetime: string;
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

// apps/api/routers/review.py mounts these under
// /brands/{brand_id}/review-queue, so every call is scoped to a brand —
// same convention as calendarEventsUrl above.
function reviewQueueUrl(brandId: string, suffix = ""): string {
  return `${API_URL}/brands/${brandId}/review-queue${suffix}`;
}

export async function fetchReviewQueue(token: string, brandId: string): Promise<ReviewQueuePost[]> {
  const res = await fetch(reviewQueueUrl(brandId), {
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

export async function approveReviewPost(
  token: string,
  brandId: string,
  postId: string,
  payload: HumanReviewDecisionInput = {}
): Promise<ReviewQueuePost> {
  const res = await fetch(reviewQueueUrl(brandId, `/${postId}/approve`), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

export async function rejectReviewPost(
  token: string,
  brandId: string,
  postId: string,
  payload: HumanReviewDecisionInput = {}
): Promise<ReviewQueuePost> {
  const res = await fetch(reviewQueueUrl(brandId, `/${postId}/reject`), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

export async function editReviewPost(
  token: string,
  brandId: string,
  postId: string,
  payload: HumanReviewEditInput
): Promise<ReviewQueuePost> {
  const res = await fetch(reviewQueueUrl(brandId, `/${postId}/edit`), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

export async function rescheduleReviewPost(
  token: string,
  brandId: string,
  postId: string,
  payload: HumanReviewRescheduleInput
): Promise<CalendarEvent> {
  const res = await fetch(reviewQueueUrl(brandId, `/${postId}/reschedule`), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

// --- Analytics (Issue #92) ---

// Mirrors apps/api/schemas/analytics.py::PlatformAggregate. total_*/
// average_* are real SQL SUM()/AVG() computed server-side, not
// accumulated client-side.
export interface PlatformAggregate {
  platform: string;
  snapshot_count: number;
  total_likes: number;
  total_comments: number;
  total_shares: number;
  total_impressions: number;
  average_likes: number;
  average_comments: number;
  average_shares: number;
  average_impressions: number;
}

// Mirrors apps/api/schemas/analytics.py::BrandAnalyticsSummary.
export interface BrandAnalyticsSummary {
  brand_id: string;
  start_date: string;
  end_date: string;
  post_count: number;
  platforms: PlatformAggregate[];
  overall: PlatformAggregate;
}

// Mirrors apps/api/schemas/analytics.py::PostAnalyticsAggregate.
export interface PostAnalyticsAggregate {
  post_id: string;
  start_date: string;
  end_date: string;
  platforms: PlatformAggregate[];
  overall: PlatformAggregate;
}

// Mirrors apps/api/schemas/analytics.py::EngagementSnapshotPoint.
export interface EngagementSnapshotPoint {
  platform: string;
  likes: number;
  comments: number;
  shares: number;
  impressions: number;
  polled_at: string;
}

// Mirrors apps/api/schemas/analytics.py::PostAnalyticsTrend — the raw,
// unaggregated time series for one post, ordered by polled_at ascending.
export interface PostAnalyticsTrend {
  post_id: string;
  start_date: string;
  end_date: string;
  points: EngagementSnapshotPoint[];
}

// start_date/end_date are optional ISO datetimes on every analytics
// endpoint — apps/api/routers/analytics.py::_resolve_date_range defaults
// to the last DEFAULT_WINDOW_DAYS (30) days when either is omitted.
export interface AnalyticsDateRangeInput {
  startDate?: string;
  endDate?: string;
}

// apps/api/routers/analytics.py mounts these under
// /brands/{brand_id}/analytics, so every call is scoped to a brand — same
// convention as calendarEventsUrl/reviewQueueUrl above.
function analyticsUrl(brandId: string, suffix = ""): string {
  return `${API_URL}/brands/${brandId}/analytics${suffix}`;
}

function dateRangeSearchParams(range: AnalyticsDateRangeInput): URLSearchParams {
  const params = new URLSearchParams();
  if (range.startDate) params.set("start_date", range.startDate);
  if (range.endDate) params.set("end_date", range.endDate);
  return params;
}

export async function fetchAnalyticsSummary(
  token: string,
  brandId: string,
  range: AnalyticsDateRangeInput = {}
): Promise<BrandAnalyticsSummary> {
  const query = dateRangeSearchParams(range).toString();
  const res = await fetch(analyticsUrl(brandId, `/summary${query ? `?${query}` : ""}`), {
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

export async function fetchPostAnalyticsAggregate(
  token: string,
  brandId: string,
  postId: string,
  range: AnalyticsDateRangeInput = {}
): Promise<PostAnalyticsAggregate> {
  const query = dateRangeSearchParams(range).toString();
  const res = await fetch(analyticsUrl(brandId, `/posts/${postId}${query ? `?${query}` : ""}`), {
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

export interface PostAnalyticsTrendInput extends AnalyticsDateRangeInput {
  platform?: string;
}

export async function fetchPostAnalyticsTrend(
  token: string,
  brandId: string,
  postId: string,
  range: PostAnalyticsTrendInput = {}
): Promise<PostAnalyticsTrend> {
  const params = dateRangeSearchParams(range);
  if (range.platform) params.set("platform", range.platform);
  const query = params.toString();

  const res = await fetch(analyticsUrl(brandId, `/posts/${postId}/trend${query ? `?${query}` : ""}`), {
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}
