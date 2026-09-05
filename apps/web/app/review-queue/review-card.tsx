"use client";

import { useState } from "react";
import type { ReviewFeedback, ReviewQueuePost } from "@/lib/api";
import { fromDatetimeLocalValue, toDatetimeLocalValue } from "../calendar/date-utils";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, Input, Textarea } from "@/components/ui/Input";
import { cn } from "@/components/ui/cn";

interface PlatformReview {
  score?: number;
  verdict?: string;
  issues?: string[];
  suggested_edits?: string;
}

// Mirrors apps/api/models/review_feedback.py::ReviewVerdict.
const VERDICT_TONES: Record<string, BadgeTone> = {
  approve: "green",
  revise: "amber",
  reject: "red",
};

function verdictTone(verdict: string | undefined): BadgeTone {
  return verdict ? VERDICT_TONES[verdict] ?? "slate" : "slate";
}

// The 0-100 score is the headline signal on this page, so it gets a colour
// band rather than being buried in prose: the same thresholds drive both the
// badge tone and every score-bar fill below. Mirrors the reviewer engine's
// own approve (>=80) / revise (50-79) / reject (<50) thresholds
// (packages/agents/pipeline/nodes/reviewer_engine.py::_build_prompt).
function scoreTone(score: number): BadgeTone {
  if (score >= 80) return "green";
  if (score >= 50) return "amber";
  return "red";
}

const SCORE_BAR_CLASSES: Record<BadgeTone, string> = {
  green: "bg-success",
  amber: "bg-warning",
  red: "bg-danger",
  slate: "bg-ink-200",
  brand: "bg-brand-500",
  blue: "bg-brand-500",
};

// The mockup's "Review · Neer" screen shows each draft with a stack of
// labeled score bars (Brand fit / Platform fit / Sentiment — see
// "Raindeer Social Startup Onboarding/Raindeer Social.dc.html"'s `r.bars`).
// The Reviewer Engine doesn't hand back those three as separate sub-scores
// though — it produces a single 0-100 alignment score per platform that
// already folds brand voice, compliance, and platform fit together (see
// reviewer_engine.py's prompt), plus one overall score for the post. So
// this reuses the mockup's bar visual, but keys each bar by real signal
// (the overall score, then one row per platform) instead of fabricating
// sub-metrics that don't exist in the data.
//
// `score` is deliberately nullable: an older review row, or a platform the
// LLM output didn't parse cleanly, can leave this missing — this renders a
// flat, neutral bar rather than crashing on it.
function ScoreBar({ label, score }: { label: string; score: number | null | undefined }) {
  const hasScore = typeof score === "number" && Number.isFinite(score);
  const clamped = hasScore ? Math.max(0, Math.min(100, score)) : 0;
  const tone = hasScore ? scoreTone(score) : "slate";

  return (
    <div className="flex items-center gap-2">
      <span className="w-20 shrink-0 truncate text-xs text-ink-300" title={label}>
        {label}
      </span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-line-soft" aria-hidden="true">
        <div
          className={cn("h-full rounded-full transition-all", SCORE_BAR_CLASSES[tone])}
          style={{ width: `${clamped}%` }}
        />
      </div>
      <span className="w-9 shrink-0 text-right text-xs font-semibold text-ink-700">
        {hasScore ? score.toFixed(0) : "—"}
      </span>
    </div>
  );
}

function latestAiReview(post: ReviewQueuePost): ReviewFeedback | null {
  const aiReviews = post.review_feedback.filter((f) => f.source === "ai_reviewer");
  return aiReviews.length > 0 ? aiReviews[aiReviews.length - 1] : null;
}

function humanReviews(post: ReviewQueuePost): ReviewFeedback[] {
  return post.review_feedback.filter((f) => f.source === "human");
}

function platformReviews(feedback: ReviewFeedback): Record<string, PlatformReview> {
  const platforms = feedback.comments?.platforms;
  if (platforms && typeof platforms === "object") {
    return platforms as Record<string, PlatformReview>;
  }
  return {};
}

interface ReviewCardProps {
  post: ReviewQueuePost;
  onApprove: (postId: string, comments: string) => Promise<void>;
  onReject: (postId: string, comments: string) => Promise<void>;
  onEdit: (postId: string, bodyText: Record<string, string>) => Promise<void>;
  onReschedule: (postId: string, targetDatetimeIso: string) => Promise<void>;
}

export function ReviewCard({ post, onApprove, onReject, onEdit, onReschedule }: ReviewCardProps) {
  const [comments, setComments] = useState("");
  const [isEditing, setIsEditing] = useState(false);
  const [draftBody, setDraftBody] = useState<Record<string, string>>(post.body_text ?? {});
  const [isRescheduling, setIsRescheduling] = useState(false);
  const [rescheduleValue, setRescheduleValue] = useState(() => toDatetimeLocalValue(new Date().toISOString()));
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const aiReview = latestAiReview(post);
  const humanHistory = humanReviews(post);
  const platforms = Object.keys(post.body_text ?? {});
  const aiPlatformEntries = aiReview ? Object.entries(platformReviews(aiReview)) : [];

  async function run(action: () => Promise<void>) {
    setIsSubmitting(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleApprove() {
    run(() => onApprove(post.id, comments));
  }

  function handleReject() {
    run(() => onReject(post.id, comments));
  }

  function handleSaveEdit() {
    run(async () => {
      await onEdit(post.id, draftBody);
      setIsEditing(false);
    });
  }

  function handleSaveReschedule() {
    run(async () => {
      await onReschedule(post.id, fromDatetimeLocalValue(rescheduleValue));
      setIsRescheduling(false);
    });
  }

  return (
    <Card aria-label={`Review post ${post.id}`} className="overflow-hidden">
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-line-faint p-5">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            {platforms.length > 0 ? (
              platforms.map((platform) => (
                <Badge key={platform} tone="blue">
                  {platform}
                </Badge>
              ))
            ) : (
              <Badge tone="slate">no platforms</Badge>
            )}
          </div>
          <p className="mt-2 text-xs text-ink-300">
            Paused for review since {new Date(post.created_at).toLocaleString()}
          </p>
        </div>

        {aiReview ? (
          <div className="w-40 shrink-0">
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5">
                <span
                  aria-hidden="true"
                  className="flex h-4 w-4 items-center justify-center rounded-[5px] bg-gradient-to-br from-agent-neer-from to-agent-neer-to text-[9px] font-extrabold text-white"
                >
                  N
                </span>
                <Badge tone={scoreTone(aiReview.score)}>{aiReview.score.toFixed(0)}/100</Badge>
              </span>
              <Badge tone={verdictTone(aiReview.verdict)} dot>
                {aiReview.verdict}
              </Badge>
            </div>
            <div className="mt-2">
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-line-soft" aria-hidden="true">
                <div
                  className={cn("h-full rounded-full transition-all", SCORE_BAR_CLASSES[scoreTone(aiReview.score)])}
                  style={{ width: `${Math.max(0, Math.min(100, aiReview.score))}%` }}
                />
              </div>
            </div>
          </div>
        ) : null}
      </header>

      <section className="border-b border-line-faint p-5">
        <h3 className="text-sm font-semibold text-ink-950">Draft</h3>

        {platforms.length === 0 && <p className="mt-2 text-sm text-ink-400">No generated copy yet.</p>}

        {!isEditing && (
          <div className="mt-3 space-y-3">
            {platforms.map((platform) => (
              <div key={platform} className="rounded-lg bg-canvas p-3">
                <span className="text-xs font-semibold uppercase tracking-wide text-ink-400">{platform}</span>
                <p className="mt-1 whitespace-pre-wrap text-sm text-ink-800">{post.body_text?.[platform]}</p>
              </div>
            ))}
          </div>
        )}

        {isEditing && (
          <div className="mt-3 space-y-4">
            {platforms.map((platform) => (
              <Field key={platform} label={platform} htmlFor={`edit-${post.id}-${platform}`}>
                <Textarea
                  id={`edit-${post.id}-${platform}`}
                  value={draftBody[platform] ?? ""}
                  onChange={(e) => setDraftBody((current) => ({ ...current, [platform]: e.target.value }))}
                  rows={4}
                />
              </Field>
            ))}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setIsEditing(false)} disabled={isSubmitting}>
                Cancel
              </Button>
              <Button type="button" variant="primary" onClick={handleSaveEdit} disabled={isSubmitting}>
                Save edit
              </Button>
            </div>
          </div>
        )}
      </section>

      {aiReview && (
        <section className="border-b border-line-faint bg-gradient-to-b from-agent-neer-to/10 to-transparent p-5">
          <div className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-gradient-to-br from-agent-neer-from to-agent-neer-to text-[10px] font-extrabold text-white"
            >
              N
            </span>
            <h3 className="text-sm font-semibold text-ink-950">
              AI reviewer score: {aiReview.score.toFixed(0)}/100
            </h3>
          </div>

          {aiPlatformEntries.length > 0 && (
            <div className="mt-3 space-y-2 rounded-lg border border-line-soft bg-white/70 p-3">
              <ScoreBar label="Overall" score={aiReview.score} />
              {aiPlatformEntries.map(([platform, review]) => (
                <ScoreBar key={platform} label={platform} score={review.score} />
              ))}
            </div>
          )}

          <ul className="mt-3 space-y-3">
            {aiPlatformEntries.map(([platform, review]) => (
              <li key={platform} className="rounded-lg border border-line-soft bg-white p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-semibold uppercase tracking-wide text-ink-400">{platform}</span>
                  {review.verdict && <Badge tone={verdictTone(review.verdict)}>{review.verdict}</Badge>}
                </div>

                {review.issues && review.issues.length > 0 && (
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-700">
                    {review.issues.map((issue, i) => (
                      <li key={i}>{issue}</li>
                    ))}
                  </ul>
                )}

                {review.suggested_edits && (
                  <div className="mt-2 rounded-md border border-warning/20 bg-warning-bg px-3 py-2">
                    <div className="text-[10px] font-bold uppercase tracking-wider text-warning">Neer&apos;s note</div>
                    <p className="mt-0.5 text-sm text-ink-800">{review.suggested_edits}</p>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {humanHistory.length > 0 && (
        <section className="border-b border-line-faint p-5">
          <h3 className="text-sm font-semibold text-ink-950">Human review history</h3>
          <ul className="mt-3 space-y-2">
            {humanHistory.map((feedback) => (
              <li key={feedback.id} className="flex flex-wrap items-center gap-2 text-sm text-ink-600">
                <Badge tone={verdictTone(feedback.verdict)}>{feedback.verdict}</Badge>
                {typeof feedback.comments?.comments === "string" && (
                  <span>{feedback.comments.comments as string}</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {isRescheduling && (
        <section className="border-b border-line-faint p-5">
          <Field label="New date and time" htmlFor={`reschedule-${post.id}`}>
            <Input
              id={`reschedule-${post.id}`}
              type="datetime-local"
              value={rescheduleValue}
              onChange={(e) => setRescheduleValue(e.target.value)}
            />
          </Field>
          <div className="mt-3 flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setIsRescheduling(false)} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button type="button" variant="primary" onClick={handleSaveReschedule} disabled={isSubmitting}>
              Save reschedule
            </Button>
          </div>
        </section>
      )}

      <div className="p-5">
        <Field label="Comments (optional)" htmlFor={`comments-${post.id}`}>
          <Textarea
            id={`comments-${post.id}`}
            value={comments}
            onChange={(e) => setComments(e.target.value)}
            rows={2}
            className="min-h-[3.5rem]"
          />
        </Field>

        {error && (
          <p role="alert" className="mt-3 rounded-lg bg-danger-bg px-3 py-2 text-sm font-medium text-danger">
            {error}
          </p>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-end gap-2 border-t border-line-faint bg-canvas px-5 py-4">
        {!isEditing && (
          <Button
            type="button"
            variant="ghost"
            onClick={() => setIsEditing(true)}
            disabled={isSubmitting || platforms.length === 0}
          >
            Edit
          </Button>
        )}
        {!isRescheduling && (
          <Button
            type="button"
            variant="outline"
            onClick={() => setIsRescheduling(true)}
            disabled={isSubmitting || !post.calendar_event_id}
            title={post.calendar_event_id ? undefined : "This post has no associated calendar event"}
          >
            Reschedule
          </Button>
        )}
        <Button type="button" variant="danger" onClick={handleReject} disabled={isSubmitting}>
          Reject
        </Button>
        <Button type="button" variant="primary" onClick={handleApprove} disabled={isSubmitting}>
          Approve
        </Button>
      </div>
    </Card>
  );
}
