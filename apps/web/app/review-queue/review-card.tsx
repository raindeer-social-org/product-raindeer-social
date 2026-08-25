"use client";

import { useState } from "react";
import type { ReviewFeedback, ReviewQueuePost } from "@/lib/api";
import { fromDatetimeLocalValue, toDatetimeLocalValue } from "../calendar/date-utils";

interface PlatformReview {
  score?: number;
  verdict?: string;
  issues?: string[];
  suggested_edits?: string;
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
    <article className="review-card" aria-label={`Review post ${post.id}`}>
      <header className="review-card-header">
        <span className="review-card-created">Paused for review since {new Date(post.created_at).toLocaleString()}</span>
      </header>

      <section className="review-card-draft">
        <h3>Draft</h3>
        {platforms.length === 0 && <p className="review-card-empty">No generated copy yet.</p>}
        {!isEditing &&
          platforms.map((platform) => (
            <div key={platform} className="review-card-platform-copy">
              <strong>{platform}</strong>
              <p>{post.body_text?.[platform]}</p>
            </div>
          ))}

        {isEditing && (
          <div className="review-card-edit-form">
            {platforms.map((platform) => (
              <label key={platform} className="review-card-edit-field">
                <span>{platform}</span>
                <textarea
                  value={draftBody[platform] ?? ""}
                  onChange={(e) => setDraftBody((current) => ({ ...current, [platform]: e.target.value }))}
                  rows={4}
                />
              </label>
            ))}
            <div className="review-card-edit-actions">
              <button type="button" onClick={() => setIsEditing(false)} disabled={isSubmitting}>
                Cancel
              </button>
              <button type="button" onClick={handleSaveEdit} disabled={isSubmitting}>
                Save edit
              </button>
            </div>
          </div>
        )}

        {!isEditing && (
          <button type="button" onClick={() => setIsEditing(true)} disabled={isSubmitting || platforms.length === 0}>
            Edit
          </button>
        )}
      </section>

      {aiReview && (
        <section className="review-card-ai-review">
          <h3>
            AI reviewer score: {aiReview.score.toFixed(0)}/100 &mdash; <span className={`verdict-${aiReview.verdict}`}>{aiReview.verdict}</span>
          </h3>
          <ul className="review-card-platform-reviews">
            {Object.entries(platformReviews(aiReview)).map(([platform, review]) => (
              <li key={platform}>
                <strong>{platform}</strong>{" "}
                {review.score !== undefined && <span>({review.score.toFixed(0)}/100, {review.verdict})</span>}
                {review.issues && review.issues.length > 0 && (
                  <ul className="review-card-issues">
                    {review.issues.map((issue, i) => (
                      <li key={i}>{issue}</li>
                    ))}
                  </ul>
                )}
                {review.suggested_edits && <p className="review-card-suggested-edits">{review.suggested_edits}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {humanHistory.length > 0 && (
        <section className="review-card-human-history">
          <h3>Human review history</h3>
          <ul>
            {humanHistory.map((feedback) => (
              <li key={feedback.id}>
                <span className={`verdict-${feedback.verdict}`}>{feedback.verdict}</span>
                {typeof feedback.comments?.comments === "string" && <span> &mdash; {feedback.comments.comments as string}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="review-card-reschedule">
        {isRescheduling ? (
          <div className="review-card-reschedule-form">
            <label>
              <span>New date and time</span>
              <input
                type="datetime-local"
                value={rescheduleValue}
                onChange={(e) => setRescheduleValue(e.target.value)}
              />
            </label>
            <div className="review-card-edit-actions">
              <button type="button" onClick={() => setIsRescheduling(false)} disabled={isSubmitting}>
                Cancel
              </button>
              <button type="button" onClick={handleSaveReschedule} disabled={isSubmitting}>
                Save reschedule
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setIsRescheduling(true)}
            disabled={isSubmitting || !post.calendar_event_id}
            title={post.calendar_event_id ? undefined : "This post has no associated calendar event"}
          >
            Reschedule
          </button>
        )}
      </section>

      <label className="review-card-comments">
        <span>Comments (optional)</span>
        <textarea value={comments} onChange={(e) => setComments(e.target.value)} rows={2} />
      </label>

      {error && (
        <p className="review-card-error" role="alert">
          {error}
        </p>
      )}

      <div className="review-card-decision-actions">
        <button type="button" className="review-card-reject" onClick={handleReject} disabled={isSubmitting}>
          Reject
        </button>
        <button type="button" className="review-card-approve" onClick={handleApprove} disabled={isSubmitting}>
          Approve
        </button>
      </div>
    </article>
  );
}
