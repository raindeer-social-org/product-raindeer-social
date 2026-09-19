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

// Mirrors apps/api/models/agent_run.py::AgentType.
export type AgentType =
  | "onboarding"
  | "research"
  | "creative"
  | "generation"
  | "reviewer"
  | "human_review"
  | "scheduler"
  | "publisher"
  | "analytics_collector"
  | "weekly_report";

// Mirrors apps/api/schemas/calendar.py::CalendarEventAgentRunRead.
export interface CalendarEventAgentRun {
  id: string;
  agent_type: AgentType;
  output: Record<string, unknown> | null;
  model: string | null;
  tokens: number | null;
  cost: number | null;
  latency_ms: number | null;
  created_at: string;
}

// Mirrors apps/api/models/review_feedback.py::ReviewSource/ReviewVerdict.
export type ReviewSource = "ai_reviewer" | "human";
export type ReviewVerdict = "approve" | "revise" | "reject";

// Mirrors apps/api/schemas/review.py::ReviewFeedbackRead. `comments` is
// free-form JSONB — for an ai_reviewer row it's shaped like
// { platforms: { [platform]: { score, verdict, issues, suggested_edits,
// predicted_engagement_score, predicted_engagement_reasoning } }, model };
// for a human row it's { comments?: string }.
export interface ReviewFeedback {
  id: string;
  post_id: string;
  source: ReviewSource;
  score: number;
  verdict: ReviewVerdict;
  comments: Record<string, unknown>;
  // Issue #107 — only populated on ai_reviewer rows; a human row
  // (approve/reject) never predicts engagement.
  predicted_engagement_score: number | null;
  predicted_engagement_reasoning: string | null;
  created_at: string;
}

// Mirrors apps/api/schemas/calendar.py::CalendarEventPostRead. Returned by
// fetchCalendarEventPost — null when the pipeline trigger hasn't picked up
// this calendar event yet (still SCHEDULED, no Post row exists).
export interface CalendarEventPost {
  id: string;
  brand_id: string;
  calendar_event_id: string | null;
  current_pipeline_stage: PipelineStage;
  body_text: Record<string, string> | null;
  media: { platform: string; format: string; url: string | null }[] | null;
  created_at: string;
  updated_at: string;
  review_feedback: ReviewFeedback[];
  agent_runs: CalendarEventAgentRun[];
}

// Mirrors apps/api/models/post.py::PipelineStage. "failed" is set
// out-of-band by the publish queue (apps/api/services/publish_queue.py)
// once a publish permanently exhausts its retries — added here alongside
// Issue #126's Create Post "Recent runs" list (apps/api/schemas/post.py::
// PostRead), the first place in the web app that surfaces every stage
// rather than just the ones review-queue/calendar already covered.
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
  | "rejected"
  | "failed";

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

// Mirrors apps/api/auth/router.py::RegisterRequest (Issue #123, signup
// step 1 of 3). first_name/last_name aren't stored on User today — the
// backend only uses them to seed a human-readable Organization name — but
// they're still real request fields, not decoration this client drops.
export interface RegisterInput {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
}

export async function register(payload: RegisterInput): Promise<LoginResponse> {
  const res = await fetch(`${API_URL}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
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

// The Post the pipeline trigger has generated for this calendar event (if
// any) plus its review history and agent run trail, for the calendar's
// post preview modal. Resolves to null when no Post exists yet.
export async function fetchCalendarEventPost(
  token: string,
  brandId: string,
  eventId: string
): Promise<CalendarEventPost | null> {
  const res = await fetch(calendarEventsUrl(brandId, `/${eventId}/post`), {
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
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

export async function regenerateReviewPost(
  token: string,
  brandId: string,
  postId: string
): Promise<ReviewQueuePost> {
  const res = await fetch(reviewQueueUrl(brandId, `/${postId}/regenerate`), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
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

// --- Content Arena (Issue #124) ---

// Mirrors apps/api/models/agent_run.py::AgentType — only the eight
// per-post pipeline stages can appear here (onboarding/weekly_report runs
// never carry a post_id, so the arena endpoints below can never surface
// them). Named distinctly from the broader AgentType above since the two
// are intentionally different-width subsets of the same backend enum.
export type ArenaAgentType =
  | "research"
  | "creative"
  | "generation"
  | "reviewer"
  | "human_review"
  | "scheduler"
  | "publisher"
  | "analytics_collector";

// Mirrors apps/api/schemas/arena.py::ArenaAgentRunRead. `output` is
// whatever structured dict that stage's node returned (e.g.
// research_brief/creative_brief/generation_output/review_output) —
// rendered defensively, never assumed to have every key. `input` is not
// exposed: run_pipeline only ever writes {"post_id": ...} into it, never
// a real prompt.
export interface ArenaAgentRun {
  id: string;
  agent_type: ArenaAgentType;
  output: Record<string, unknown> | null;
  model: string | null;
  tokens: number | null;
  cost: number | null;
  latency_ms: number | null;
  created_at: string;
}

// Mirrors apps/api/schemas/arena.py::ArenaReviewFeedbackRead.
export interface ArenaReviewFeedback {
  id: string;
  source: ReviewSource;
  score: number;
  verdict: ReviewVerdict;
  comments: Record<string, unknown>;
  created_at: string;
}

// Mirrors apps/api/schemas/arena.py::ArenaPostRead — a thin Post
// projection, not the full row.
export interface ArenaPost {
  id: string;
  calendar_event_id: string | null;
  current_pipeline_stage: PipelineStage;
  body_text: Record<string, string> | null;
  media: { platform: string; format: string; url: string }[] | null;
  created_at: string;
  updated_at: string;
}

// Mirrors apps/api/schemas/arena.py::ArenaRunRead. `post` is null when the
// calendar event hasn't been triggered into a Post yet (or the brand has
// no posts at all, for fetchLatestArenaRun) — agent_runs/review_feedback
// are always empty in that case too.
export interface ArenaRun {
  calendar_event_id: string | null;
  post: ArenaPost | null;
  agent_runs: ArenaAgentRun[];
  review_feedback: ArenaReviewFeedback[];
}

// apps/api/routers/arena.py mounts these under /brands/{brand_id}/arena —
// same brand-scoping convention as calendarEventsUrl/reviewQueueUrl above.
function arenaUrl(brandId: string, suffix: string): string {
  return `${API_URL}/brands/${brandId}/arena${suffix}`;
}

export async function fetchArenaRunForEvent(
  token: string,
  brandId: string,
  eventId: string
): Promise<ArenaRun> {
  const res = await fetch(arenaUrl(brandId, `/by-event/${eventId}`), {
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

export async function fetchLatestArenaRun(token: string, brandId: string): Promise<ArenaRun> {
  const res = await fetch(arenaUrl(brandId, "/latest"), {
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

// --- Social accounts (Issue #91) ---

// Mirrors apps/api/models/social_account.py::SocialPlatform.
export type SocialPlatform =
  | "linkedin"
  | "x"
  | "instagram"
  | "threads"
  | "facebook"
  | "youtube"
  | "tiktok"
  | "pinterest";

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
  return connectPlatform(token, brandId, "linkedin");
}

// Same "give me a URL, don't navigate yourself" shape as connectLinkedIn
// above, generalized by platform (Issue #138) since every platform's
// /connect endpoint (apps/api/routers/social_accounts.py) is wired
// identically — one function instead of one per platform.
export async function connectPlatform(
  token: string,
  brandId: string,
  platform: SocialPlatform
): Promise<AuthorizeUrlResponse> {
  const res = await fetch(socialAccountsUrl(brandId, `/${platform}/connect`), {
    method: "POST",
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

export async function connectInstagram(token: string, brandId: string): Promise<AuthorizeUrlResponse> {
  return connectPlatform(token, brandId, "instagram");
}

export async function connectThreads(token: string, brandId: string): Promise<AuthorizeUrlResponse> {
  return connectPlatform(token, brandId, "threads");
}

export async function connectFacebook(token: string, brandId: string): Promise<AuthorizeUrlResponse> {
  return connectPlatform(token, brandId, "facebook");
}

export async function connectYouTube(token: string, brandId: string): Promise<AuthorizeUrlResponse> {
  return connectPlatform(token, brandId, "youtube");
}

export async function connectTikTok(token: string, brandId: string): Promise<AuthorizeUrlResponse> {
  return connectPlatform(token, brandId, "tiktok");
}

export async function connectPinterest(token: string, brandId: string): Promise<AuthorizeUrlResponse> {
  return connectPlatform(token, brandId, "pinterest");
}

// Same shape as connectLinkedIn — starts X's OAuth flow via
// apps/api/routers/social_accounts.py::connect_x.
export async function connectX(token: string, brandId: string): Promise<AuthorizeUrlResponse> {
  return connectPlatform(token, brandId, "x");
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
  mission?: string | null;
  content_dos_donts?: string[] | null;
  posting_cadence?: string | null;
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
  mission: string | null;
  content_dos_donts: string[] | null;
  posting_cadence: string | null;
  is_complete: boolean;
  created_at: string;
  updated_at: string;
}

// Mirrors apps/api/schemas/onboarding.py::OnboardingVoiceAnswerRead.
export interface OnboardingVoiceAnswer {
  id: string;
  brand_id: string;
  question_id: string;
  transcript: string;
  audio_url: string;
  language: string | null;
  duration_seconds: number | null;
  created_at: string;
}

// Mirrors apps/api/schemas/onboarding.py::OnboardingAssetRead. `slot` is
// one of apps/api/models/onboarding_asset.py::ONBOARDING_ASSET_SLOTS.
export interface OnboardingAsset {
  id: string;
  brand_id: string;
  slot: string;
  url: string;
  filename: string;
  content_type: string;
  created_at: string;
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

// Mirrors the events apps/api/routers/onboarding.py::stream_research_preview
// emits ("log"/"signal"/"done"), each carrying a small JSON `data` payload
// ({text} for log, {title,url} for signal, {count} for done).
export interface ResearchStreamEvent {
  event: "log" | "signal" | "done";
  data: Record<string, unknown>;
}

// Reads the onboarding research-preview SSE stream (Issue #123's Aarav
// interview "scrape" question). Deliberately uses fetch + a manual
// "event: x\ndata: {...}\n\n" parser rather than the browser's EventSource
// — EventSource can't attach an Authorization header, and every other
// endpoint in this file is a bearer-token GET. Resolves once the stream
// ends (after the backend's "done" event closes the response body).
export async function streamOnboardingResearch(
  token: string,
  brandId: string,
  onEvent: (event: ResearchStreamEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(onboardingUrl(brandId, "/research-stream"), {
    headers: authHeaders(token),
    signal,
  });

  if (!res.ok || !res.body) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const rawEvent = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");

      let eventName = "message";
      let data = "";
      for (const line of rawEvent.split("\n")) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        else if (line.startsWith("data:")) data = line.slice(5).trim();
      }
      if (!data) continue;
      try {
        onEvent({ event: eventName as ResearchStreamEvent["event"], data: JSON.parse(data) });
      } catch {
        // Malformed chunk (shouldn't happen against our own backend) —
        // skip it rather than take the whole stream down.
      }
    }
  }
}

// --- Real voice recording + free open-source transcription (Issue #144) ---
// apps/api/routers/onboarding.py::create_voice_answer takes a multipart
// "file" field (the recorded audio) plus a "question_id" form field, same
// convention as uploadBrandLogo's single "file" field above.
export async function transcribeOnboardingVoiceAnswer(
  token: string,
  brandId: string,
  questionId: string,
  audioBlob: Blob
): Promise<OnboardingVoiceAnswer> {
  const formData = new FormData();
  formData.append("question_id", questionId);
  formData.append("file", audioBlob, "answer.webm");

  const res = await fetch(onboardingUrl(brandId, "/voice-answers"), {
    method: "POST",
    headers: authHeaders(token),
    body: formData,
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

// --- Real asset uploads (Issue #144) ---
// `slot` is one of apps/api/models/onboarding_asset.py::ONBOARDING_ASSET_SLOTS
// — re-uploading to an already-filled slot replaces it (same "one current
// value per slot" model as the brand logo).
export async function uploadOnboardingAsset(
  token: string,
  brandId: string,
  slot: string,
  file: File
): Promise<OnboardingAsset> {
  const formData = new FormData();
  formData.append("slot", slot);
  formData.append("file", file);

  const res = await fetch(onboardingUrl(brandId, "/assets"), {
    method: "POST",
    headers: authHeaders(token),
    body: formData,
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

export async function fetchOnboardingAssets(token: string, brandId: string): Promise<OnboardingAsset[]> {
  const res = await fetch(onboardingUrl(brandId, "/assets"), {
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

// --- Adaptive, LLM-generated follow-up questions (Issue #153) ---
// Mirrors apps/api/schemas/onboarding.py's DynamicQuestion/
// DynamicAnswerSubmit/NextQuestionsRequest/NextQuestionsResponse. Runs
// after the fixed QUESTIONS array in the interview page — each page's
// questions are generated by Aarav from everything answered so far.

export type DynamicQuestionType = "text" | "chips" | "select" | "voice";

export interface DynamicQuestion {
  id: string;
  type: DynamicQuestionType;
  title: string;
  sub: string;
  options: string[] | null;
}

export interface DynamicAnswerSubmit {
  question: DynamicQuestion;
  answer: string | string[];
}

export interface NextQuestionsResult {
  done: boolean;
  page_index: number;
  questions: DynamicQuestion[];
}

// `page_index` is the page whose answers are being submitted right now (0
// on the very first call, with an empty `answers` array, just to fetch
// page 1). The response's `page_index` is the NEW page that was just
// generated — pass that straight back in on the next call.
export async function fetchNextOnboardingQuestions(
  token: string,
  brandId: string,
  pageIndex: number,
  answers: DynamicAnswerSubmit[]
): Promise<NextQuestionsResult> {
  const res = await fetch(onboardingUrl(brandId, "/next-questions"), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ page_index: pageIndex, answers }),
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

// --- Research · Ved (Issue #126) ---

// Mirrors apps/api/schemas/research.py::ResearchRunRead. `brief` is
// exactly what packages/agents/pipeline/nodes/research_engine.py's
// _research_brief produces: brand_context, platform_trends,
// industry_trends, timing_signal.
export interface ResearchRun {
  id: string;
  post_id: string;
  brand_id: string;
  created_at: string;
  brief: {
    post_id: string;
    brand_context: Array<Record<string, unknown>>;
    platform_trends: Record<string, Array<{ title: string; url: string; content: string }>>;
    industry_trends: Array<{ title: string; url: string; content: string }>;
    timing_signal: {
      researched_at: string;
      platforms: string[];
      trending_topics: string[];
      target_datetime: string | null;
    };
  };
}

// apps/api/routers/research.py mounts these under /brands/{brand_id}/research
// — same brand-scoping convention as calendarEventsUrl/reviewQueueUrl above.
function researchUrl(brandId: string, suffix = ""): string {
  return `${API_URL}/brands/${brandId}/research${suffix}`;
}

export async function runResearch(token: string, brandId: string): Promise<ResearchRun> {
  const res = await fetch(researchUrl(brandId, "/run"), {
    method: "POST",
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

// Returns null (rather than throwing) when no research has been run yet —
// apps/api/routers/research.py::latest_research 404s in that case, which
// the Research page treats as its "nothing yet, run one" state.
export async function fetchLatestResearch(token: string, brandId: string): Promise<ResearchRun | null> {
  const res = await fetch(researchUrl(brandId, "/latest"), {
    headers: authHeaders(token),
  });

  if (res.status === 404) return null;
  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}

// --- Creative · Keshav (Issue #126) ---

// Mirrors apps/api/schemas/creative.py::CreativeAngleRead.
export interface CreativeAngle {
  format: string;
  angle: string;
  hook: string;
  why: string;
  cta: string;
  score: number;
}

export async function generateCreativeAngles(
  token: string,
  brandId: string,
  brief: string
): Promise<CreativeAngle[]> {
  const res = await fetch(`${API_URL}/brands/${brandId}/creative/angles`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ brief }),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  const data: { angles: CreativeAngle[] } = await res.json();
  return data.angles;
}

// --- Content AI (Issue #126) ---

// Mirrors apps/api/schemas/content_ai.py::ContentAIVariantRead.
export interface ContentAIVariant {
  status: "generated" | "failed";
  url: string | null;
}

// Mirrors apps/api/schemas/content_ai.py::ContentAIGenerateRequest.
export interface ContentAIGenerateInput {
  prompt: string;
  aspect_ratio?: string | null;
  style?: string | null;
  lock_brand_colors?: boolean;
  count?: number;
}

export async function generateContentAIImages(
  token: string,
  brandId: string,
  payload: ContentAIGenerateInput
): Promise<ContentAIVariant[]> {
  const res = await fetch(`${API_URL}/brands/${brandId}/content-ai/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  const data: { variants: ContentAIVariant[] } = await res.json();
  return data.variants;
}

// --- Posts / recent runs (Issue #126) ---

// Mirrors apps/api/schemas/post.py::PostRead.
export interface PostSummary {
  id: string;
  brand_id: string;
  calendar_event_id: string | null;
  current_pipeline_stage: PipelineStage;
  body_text: Record<string, string> | null;
  created_at: string;
  updated_at: string;
}

// apps/api/routers/posts.py mounts this under /brands/{brand_id}/posts —
// same brand-scoping convention as calendarEventsUrl above.
export async function fetchRecentPosts(token: string, brandId: string, limit = 20): Promise<PostSummary[]> {
  const res = await fetch(`${API_URL}/brands/${brandId}/posts?limit=${limit}`, {
    headers: authHeaders(token),
  });

  if (!res.ok) {
    throw new ApiError(await parseErrorDetail(res), res.status);
  }

  return res.json();
}
