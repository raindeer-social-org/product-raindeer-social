"use client";

import { useCallback, useEffect, useState } from "react";
import {
  approveReviewPost,
  editReviewPost,
  fetchReviewQueue,
  rejectReviewPost,
  rescheduleReviewPost,
  type ReviewQueuePost,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useBrand } from "@/lib/brand-context";
import { ReviewCard } from "./review-card";

// Same "keep the queue live without a manual refresh" convention as
// apps/web/app/calendar/page.tsx — a paused post can be approved/rejected
// by a teammate, or a new one can land at human_review, at any time.
const POLL_INTERVAL_MS = 15000;

export default function ReviewQueuePage() {
  const { token } = useAuth();
  const { selectedBrand, selectedBrandId } = useBrand();

  const [posts, setPosts] = useState<ReviewQueuePost[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadQueue = useCallback(
    async (showSpinner: boolean) => {
      if (!token || !selectedBrandId) {
        setPosts([]);
        return;
      }
      if (showSpinner) setIsLoading(true);
      setError(null);
      try {
        const result = await fetchReviewQueue(token, selectedBrandId);
        setPosts(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load review queue");
      } finally {
        if (showSpinner) setIsLoading(false);
      }
    },
    [token, selectedBrandId]
  );

  useEffect(() => {
    setPosts([]);
    loadQueue(true);

    const interval = setInterval(() => loadQueue(false), POLL_INTERVAL_MS);
    const onFocus = () => loadQueue(false);
    window.addEventListener("focus", onFocus);

    return () => {
      clearInterval(interval);
      window.removeEventListener("focus", onFocus);
    };
  }, [loadQueue]);

  function removePost(postId: string) {
    setPosts((current) => current.filter((post) => post.id !== postId));
  }

  function replacePost(updated: ReviewQueuePost) {
    setPosts((current) => current.map((post) => (post.id === updated.id ? updated : post)));
  }

  async function handleApprove(postId: string, comments: string) {
    if (!token || !selectedBrandId) return;
    setActionError(null);
    try {
      await approveReviewPost(token, selectedBrandId, postId, { comments: comments || null });
      // Approving resumes the post past human_review, so it no longer
      // belongs in this queue (see apps/api/routers/review.py::approve_post).
      removePost(postId);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to approve post");
    }
  }

  async function handleReject(postId: string, comments: string) {
    if (!token || !selectedBrandId) return;
    setActionError(null);
    try {
      await rejectReviewPost(token, selectedBrandId, postId, { comments: comments || null });
      // Rejecting halts the post at a terminal REJECTED stage — also no
      // longer awaiting review.
      removePost(postId);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to reject post");
    }
  }

  async function handleEdit(postId: string, bodyText: Record<string, string>) {
    if (!token || !selectedBrandId) return;
    setActionError(null);
    try {
      const updated = await editReviewPost(token, selectedBrandId, postId, { body_text: bodyText });
      // Editing doesn't resume the graph — the post stays in the queue
      // with its new draft.
      replacePost(updated);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to save edit");
    }
  }

  async function handleReschedule(postId: string, targetDatetimeIso: string) {
    if (!token || !selectedBrandId) return;
    setActionError(null);
    try {
      await rescheduleReviewPost(token, selectedBrandId, postId, { target_datetime: targetDatetimeIso });
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to reschedule post");
    }
  }

  return (
    <section className="review-queue-page">
      <div className="review-queue-header">
        <h1>Review Queue</h1>
        <p className="scoped-brand">
          Showing data for: <strong>{selectedBrand ? selectedBrand.name : "no brand selected"}</strong>
        </p>
      </div>

      {error && (
        <p className="review-queue-error" role="alert">
          {error}
        </p>
      )}
      {actionError && (
        <p className="review-queue-error" role="alert">
          {actionError}
        </p>
      )}

      {!selectedBrand ? (
        <p>Select a brand to see its review queue.</p>
      ) : isLoading && posts.length === 0 ? (
        <p role="status">Loading review queue…</p>
      ) : posts.length === 0 ? (
        <p>Nothing is waiting on human review right now.</p>
      ) : (
        <ul className="review-queue-list">
          {posts.map((post) => (
            <li key={post.id}>
              <ReviewCard
                post={post}
                onApprove={handleApprove}
                onReject={handleReject}
                onEdit={handleEdit}
                onReschedule={handleReschedule}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
