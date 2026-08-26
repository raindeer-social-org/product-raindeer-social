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
// badge tone and the meter fill.
function scoreTone(score: number): BadgeTone {
  if (score >= 80) return "green";
  if (score >= 60) return "amber";
  return "red";
}

const SCORE_BAR_CLASSES: Record<BadgeTone, string> = {
  green: "bg-emerald-500",
  amber: "bg-amber-500",
  red: "bg-red-500",
  slate: "bg-slate-400",
  brand: "bg-brand-500",
  blue: "bg-blue-500",
};

function ScoreMeter({ score }: { score: number }) {
  const clamped = Math.max(0, Math.min(100, score));
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200" aria-hidden="true">
      <div
        className={cn("h-full rounded-full transition-all", SCORE_BAR_CLASSES[scoreTone(score)])}
        style={{ width: `${clamped}%` }}
      />
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
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-100 p-5">
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
          <p className="mt-2 text-xs text-slate-500">
            Paused for review since {new Date(post.created_at).toLocaleString()}
          </p>
        </div>

        {aiReview ? (
          <div className="w-40 shrink-0">
            <div className="flex items-center justify-between gap-2">
              <Badge tone={scoreTone(aiReview.score)}>{aiReview.score.toFixed(0)}/100</Badge>
              <Badge tone={verdictTone(aiReview.verdict)} dot>
                {aiReview.verdict}
              </Badge>
            </div>
            <div className="mt-2">
              <ScoreMeter score={aiReview.score} />
            </div>
          </div>
        ) : null}
      </header>

      <section className="border-b border-slate-100 p-5">
        <h3 className="text-sm font-semibold text-slate-900">Draft</h3>

        {platforms.length === 0 && <p className="mt-2 text-sm text-slate-500">No generated copy yet.</p>}

        {!isEditing && (
          <div className="mt-3 space-y-3">
            {platforms.map((platform) => (
              <div key={platform} className="rounded-lg bg-slate-50 p-3">
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">{platform}</span>
                <p className="mt-1 whitespace-pre-wrap text-sm text-slate-800">{post.body_text?.[platform]}</p>
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
        <section className="border-b border-slate-100 bg-brand-50/40 p-5">
          <h3 className="text-sm font-semibold text-slate-900">
            AI reviewer score: {aiReview.score.toFixed(0)}/100
          </h3>

          <ul className="mt-3 space-y-3">
            {Object.entries(platformReviews(aiReview)).map(([platform, review]) => (
              <li key={platform} className="rounded-lg border border-slate-200 bg-white p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">{platform}</span>
                  {review.score !== undefined && (
                    <Badge tone={scoreTone(review.score)}>{review.score.toFixed(0)}/100</Badge>
                  )}
                  {review.verdict && <Badge tone={verdictTone(review.verdict)}>{review.verdict}</Badge>}
                </div>

                {review.issues && review.issues.length > 0 && (
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
                    {review.issues.map((issue, i) => (
                      <li key={i}>{issue}</li>
                    ))}
                  </ul>
                )}

                {review.suggested_edits && (
                  <p className="mt-2 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">
                    {review.suggested_edits}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {humanHistory.length > 0 && (
        <section className="border-b border-slate-100 p-5">
          <h3 className="text-sm font-semibold text-slate-900">Human review history</h3>
          <ul className="mt-3 space-y-2">
            {humanHistory.map((feedback) => (
              <li key={feedback.id} className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
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
        <section className="border-b border-slate-100 p-5">
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
          <p role="alert" className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
            {error}
          </p>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-end gap-2 border-t border-slate-100 bg-slate-50 px-5 py-4">
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
