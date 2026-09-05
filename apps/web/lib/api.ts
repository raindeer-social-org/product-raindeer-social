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
  report_pdf_url?: string | null;
  report_pdf_generated_at?: string | null;
  created_at: string;
  updated_at: string;
}

// Mirrors apps/api/schemas/brand.py::BrandCreate.
export interface BrandInput {
  name: string;
  industry?: string | null;
  logo_url?: string | null;
  target_audience?: string | null;
  colors?: string[] | null;
  tone_descriptors?: string[] | null;
  product_catalog?: Record<string, unknown> | null;
}

// Mirrors apps/api/schemas/brand.py::BrandUpdate — every field optional,
// PATCH-style (only fields present are changed server-side).
export type BrandUpdateInput = Partial<BrandInput>;

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

// --- Social accounts (Issue #91) ---

// Mirrors apps/api/models/social_account.py::SocialPlatform. "linkedin" is
// the only value today, but this is kept as a string union (not a literal)
// so the UI layer can stay written generically as more providers land.
export type SocialPlatform = "linkedin";

// Mirrors apps/api/models/social_account.py::SocialAccountStatus.
export type SocialAccountStatus = "active" | "expired" | "revoked";

// Mirrors apps/api/schemas/social_account.py::SocialAccountRead.
export interface SocialAccount {
  id: string;
  brand_id: string;
  platform: SocialPlatform;
  external_account_id: string | null;
  token_expires_at: string | null;
  scopes: string[] | null;
  status: SocialAccountStatus;
  created_at: string;
  updated_at: string;
}

// Mirrors apps/api/schemas/social_account.py::AuthorizeUrlRead.
export interface AuthorizeUrlResponse {
  authorize_url: string;
}

// apps/api/routers/social_accounts.py mounts these under
// /brands/{brand_id}/social-accounts — same brand-scoping convention as
// calendarEventsUrl/reviewQueueUrl above.
function socialAccountsUrl(brandId: string, suffix = ""): string {
  return `${API_URL}/brands/${brandId}/social-accounts${suffix}`;
}

export async function fetchSocialAccounts(token: string, brandId: string): Promise<SocialAccount[]> {
  const res = await fetch(socialAccountsUrl(brandId), {
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

// Starts the LinkedIn OAuth flow and returns the authorize URL to send the
// browser to. Deliberately does not navigate itself (no `window.location`
// here) — that's UI-layer behavior the caller performs, which keeps this
// function trivially testable and matches how apps/api/routers/social_accounts.py
// separates "give me a URL" (POST .../linkedin/connect) from the redirect
// the browser does with it.
export async function connectLinkedIn(token: string, brandId: string): Promise<AuthorizeUrlResponse> {
  const res = await fetch(socialAccountsUrl(brandId, "/linkedin/connect"), {
    method: "POST",
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

export async function disconnectSocialAccount(
  token: string,
  brandId: string,
  accountId: string
): Promise<SocialAccount> {
  const res = await fetch(socialAccountsUrl(brandId, `/${accountId}`), {
    method: "DELETE",
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

// --- Brand CRUD (Issue #89) ---

function brandUrl(brandId: string, suffix = ""): string {
  return `${API_URL}/brands/${brandId}${suffix}`;
}

export async function createBrand(token: string, payload: BrandInput): Promise<Brand> {
  const res = await fetch(`${API_URL}/brands`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

export async function updateBrand(
  token: string,
  brandId: string,
  payload: BrandUpdateInput
): Promise<Brand> {
  const res = await fetch(brandUrl(brandId), {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

export async function deleteBrand(token: string, brandId: string): Promise<void> {
  const res = await fetch(brandUrl(brandId), {
    method: "DELETE",
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }
}

// apps/api/routers/brands.py::upload_brand_logo takes a single multipart
// field named "file" (fastapi.UploadFile) — the field name matters, the
// backend reads request.form()["file"].
export async function uploadBrandLogo(token: string, brandId: string, file: File): Promise<Brand> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(brandUrl(brandId, "/logo"), {
    method: "PUT",
    headers: authHeaders(token),
    body: formData,
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

export async function removeBrandLogo(token: string, brandId: string): Promise<Brand> {
  const res = await fetch(brandUrl(brandId, "/logo"), {
    method: "DELETE",
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

// --- Onboarding + Brand Report (Issue #90) ---

// Mirrors apps/api/schemas/onboarding.py::OnboardingUpsert.
export interface OnboardingUpsertInput {
  voice?: string | null;
  audience?: string | null;
  product_catalog?: Record<string, unknown> | null;
  competitors?: string[] | null;
  goals?: string[] | null;
}

// Mirrors apps/api/schemas/onboarding.py::OnboardingRead.
export interface OnboardingResponseData {
  id: string;
  brand_id: string;
  voice: string | null;
  audience: string | null;
  product_catalog: Record<string, unknown> | null;
  competitors: string[] | null;
  goals: string[] | null;
  is_complete: boolean;
  created_at: string;
  updated_at: string;
}

// Mirrors apps/api/schemas/brand.py::BrandReportExport.
export interface BrandReportExportResult {
  url: string;
  generated_at: string;
}

// apps/api/routers/onboarding.py mounts these under
// /brands/{brand_id}/onboarding, so every call is scoped to a brand — same
// convention as calendarEventsUrl/reviewQueueUrl above.
function onboardingUrl(brandId: string, suffix = ""): string {
  return `${API_URL}/brands/${brandId}/onboarding${suffix}`;
}

// Returns null (rather than throwing) when onboarding hasn't been started
// yet — apps/api/routers/onboarding.py::get_onboarding 404s in that case,
// which the onboarding page treats as its "not started" state, not an error.
export async function fetchOnboarding(
  token: string,
  brandId: string
): Promise<OnboardingResponseData | null> {
  const res = await fetch(onboardingUrl(brandId), {
    headers: authHeaders(token),
  });

  if (res.status === 404) return null;
  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

export async function upsertOnboarding(
  token: string,
  brandId: string,
  payload: OnboardingUpsertInput
): Promise<OnboardingResponseData> {
  const res = await fetch(onboardingUrl(brandId), {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

export async function completeOnboarding(
  token: string,
  brandId: string
): Promise<OnboardingResponseData> {
  const res = await fetch(onboardingUrl(brandId, "/complete"), {
    method: "POST",
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

// Triggers the onboarding research + synthesis agent chain (a real LLM call
// chain — can take tens of seconds) and returns the Brand with brand_report
// populated. apps/api/routers/onboarding.py::run_agent requires onboarding
// to already be complete.
export async function runOnboardingAgent(token: string, brandId: string): Promise<Brand> {
  const res = await fetch(onboardingUrl(brandId, "/run-agent"), {
    method: "POST",
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

export async function exportBrandReport(
  token: string,
  brandId: string
): Promise<BrandReportExportResult> {
  const res = await fetch(`${API_URL}/brands/${brandId}/report/export`, {
    method: "POST",
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

// --- Weekly reports (Issue #93) / Analytics (Issue #92) ---

// Mirrors apps/api/schemas/analytics.py::PlatformAggregate. total_*/
// average_* are real SQL SUM()/AVG() computed server-side, not
// accumulated client-side. Shared by both the weekly-report metrics
// payload and the analytics dashboard endpoints below.
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

// Mirrors the plain-dict shape packages/agents/reporting/weekly_report.py's
// _metrics_dict() builds and Report.metrics stores — the exact
// analytics_aggregation.BrandSummary a report was generated from, minus
// the brand_id/date-range wrapper BrandAnalyticsSummary adds. The API's
// own ReportOut.metrics is typed `dict[str, Any]`, so this is typed
// loosely too — render defensively rather than assuming every key exists.
export interface ReportMetrics {
  post_count?: number;
  platforms?: PlatformAggregate[];
  overall?: PlatformAggregate;
  [key: string]: unknown;
}

// Mirrors apps/api/schemas/analytics.py::ReportOut. `recommendations` is
// `list[Any]` server-side — weekly_report.py currently always writes
// plain strings, but other shapes (e.g. `{title, detail}`) are
// contractually possible, so callers should render generically.
export interface Report {
  id: string;
  brand_id: string;
  period_start: string;
  period_end: string;
  summary: string;
  recommendations: unknown[];
  metrics: ReportMetrics;
  model: string | null;
  created_at: string;
}

// Mirrors apps/api/schemas/analytics.py::ReportListOut.
export interface ReportListOut {
  brand_id: string;
  reports: Report[];
}

// apps/api/routers/analytics.py mounts these under
// /brands/{brand_id}/analytics/reports — same brand-scoping convention as
// calendarEventsUrl/reviewQueueUrl above.
function analyticsReportsUrl(brandId: string, suffix = ""): string {
  return `${API_URL}/brands/${brandId}/analytics/reports${suffix}`;
}

export async function fetchReports(token: string, brandId: string): Promise<Report[]> {
  const res = await fetch(analyticsReportsUrl(brandId), {
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  const data: ReportListOut = await res.json();
  return data.reports;
}

export async function fetchReport(token: string, brandId: string, reportId: string): Promise<Report> {
  const res = await fetch(analyticsReportsUrl(brandId, `/${reportId}`), {
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
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

// --- Brand settings (Issue #128) ---

// Mirrors apps/api/schemas/brand_settings.py::BrandSettingsRead. One row
// per brand, auto-provisioned with these defaults on first GET — see
// apps/api/routers/brand_settings.py. Persistence-only today: nothing
// downstream reads this table yet (see the model's docstring), so these
// toggles are durable but not yet wired to the agent behavior they
// describe.
export interface BrandSettings {
  id: string;
  brand_id: string;
  auto_approve_enabled: boolean;
  auto_approve_threshold: number;
  show_agent_reasoning: boolean;
  email_review_digest_enabled: boolean;
  auto_shift_posting_times: boolean;
  created_at: string;
  updated_at: string;
}

// Mirrors apps/api/schemas/brand_settings.py::BrandSettingsUpdate — every
// field optional, PATCH-style (only fields present are changed server-side).
export interface BrandSettingsUpdateInput {
  auto_approve_enabled?: boolean;
  auto_approve_threshold?: number;
  show_agent_reasoning?: boolean;
  email_review_digest_enabled?: boolean;
  auto_shift_posting_times?: boolean;
}

// apps/api/routers/brand_settings.py mounts these under
// /brands/{brand_id}/settings — same brand-scoping convention as
// calendarEventsUrl/reviewQueueUrl above.
function brandSettingsUrl(brandId: string): string {
  return `${API_URL}/brands/${brandId}/settings`;
}

export async function fetchBrandSettings(token: string, brandId: string): Promise<BrandSettings> {
  const res = await fetch(brandSettingsUrl(brandId), {
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

export async function updateBrandSettings(
  token: string,
  brandId: string,
  payload: BrandSettingsUpdateInput
): Promise<BrandSettings> {
  const res = await fetch(brandSettingsUrl(brandId), {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}
