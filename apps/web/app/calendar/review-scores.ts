import type { BadgeTone } from "@/components/ui/Badge";
import type { CalendarEventPost, ReviewFeedback } from "@/lib/api";

interface PlatformReview {
  score?: number;
  verdict?: string;
  issues?: string[];
  suggested_edits?: string;
}

export interface ScoreTile {
  label: string;
  value: string;
  tone: BadgeTone;
}

// Mirrors apps/api/models/review_feedback.py::ReviewVerdict/score thresholds
// (see packages/agents/pipeline/nodes/reviewer_engine.py's prompt: >=80
// approve, 50-79 revise, <50 reject).
function scoreTone(score: number): BadgeTone {
  if (score >= 80) return "green";
  if (score >= 50) return "amber";
  return "red";
}

function latestAiReview(feedback: ReviewFeedback[]): ReviewFeedback | null {
  const aiReviews = feedback.filter((f) => f.source === "ai_reviewer");
  return aiReviews.length > 0 ? aiReviews[aiReviews.length - 1] : null;
}

function platformReview(feedback: ReviewFeedback, platform: string | undefined): PlatformReview | null {
  const platforms = feedback.comments?.platforms;
  if (!platform || !platforms || typeof platforms !== "object") return null;
  const entry = (platforms as Record<string, unknown>)[platform];
  return entry && typeof entry === "object" ? (entry as PlatformReview) : null;
}

/**
 * Score tiles for the post preview modal, sourced only from real
 * ReviewFeedback fields (apps/api/models/review_feedback.py) — never a
 * fabricated number. Returns null when the post has no AI review yet, so
 * the caller can render a "not reviewed yet" state instead of empty/zero
 * tiles.
 *
 * There is no separate "brand fit" / "sentiment risk" sub-score in this
 * codebase's review data (the Reviewer Engine writes one overall score per
 * platform, not decomposed sub-scores — see reviewer_engine.py), and no
 * predicted-engagement field exists yet anywhere in the API. Rather than
 * inventing numbers for those, this surfaces the real fields that exist:
 * the overall score, this platform's own score, and how many specific
 * issues the reviewer flagged for it — plus an honest "not available yet"
 * tile for predicted reach.
 */
export function buildScoreTiles(post: CalendarEventPost | null, platform: string | undefined): ScoreTile[] | null {
  if (!post) return null;
  const aiReview = latestAiReview(post.review_feedback);
  if (!aiReview) return null;

  const forPlatform = platformReview(aiReview, platform);
  const platformScore = forPlatform?.score ?? aiReview.score;
  const issueCount = forPlatform?.issues?.length ?? 0;

  return [
    { label: "Overall score", value: `${Math.round(aiReview.score)}/100`, tone: scoreTone(aiReview.score) },
    { label: "Platform fit", value: `${Math.round(platformScore)}/100`, tone: scoreTone(platformScore) },
    {
      label: "Issues flagged",
      value: String(issueCount),
      tone: issueCount === 0 ? "green" : issueCount <= 2 ? "amber" : "red",
    },
    { label: "Predicted reach", value: "Not available yet", tone: "slate" },
  ];
}
