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
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";

// Same "keep the queue live without a manual refresh" convention as
// apps/web/app/calendar/page.tsx — a paused post can be approved/rejected
// by a teammate, or a new one can land at human_review, at any time.
const POLL_INTERVAL_MS = 15000;

export default function ReviewQueuePage() {
  const { token } = useAuth();
  const { selectedBrand, selectedBrandId } = useBrand();
  const { push } = useToast();

  const [posts, setPosts] = useState<ReviewQueuePost[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    try {
      await approveReviewPost(token, selectedBrandId, postId, { comments: comments || null });
      // Approving resumes the post past human_review, so it no longer
      // belongs in this queue (see apps/api/routers/review.py::approve_post).
      removePost(postId);
      push("Post approved", "success");
    } catch (err) {
      push(err instanceof Error ? err.message : "Failed to approve post", "error");
    }
  }

  async function handleReject(postId: string, comments: string) {
    if (!token || !selectedBrandId) return;
    try {
      await rejectReviewPost(token, selectedBrandId, postId, { comments: comments || null });
      // Rejecting halts the post at a terminal REJECTED stage — also no
      // longer awaiting review.
      removePost(postId);
      push("Post rejected", "success");
    } catch (err) {
      push(err instanceof Error ? err.message : "Failed to reject post", "error");
    }
  }

  async function handleEdit(postId: string, bodyText: Record<string, string>) {
    if (!token || !selectedBrandId) return;
    try {
      const updated = await editReviewPost(token, selectedBrandId, postId, { body_text: bodyText });
      // Editing doesn't resume the graph — the post stays in the queue
      // with its new draft.
      replacePost(updated);
      push("Draft updated", "success");
    } catch (err) {
      push(err instanceof Error ? err.message : "Failed to save edit", "error");
    }
  }

  async function handleReschedule(postId: string, targetDatetimeIso: string) {
    if (!token || !selectedBrandId) return;
    try {
      await rescheduleReviewPost(token, selectedBrandId, postId, { target_datetime: targetDatetimeIso });
      push("Post rescheduled", "success");
    } catch (err) {
      push(err instanceof Error ? err.message : "Failed to reschedule post", "error");
    }
  }

  return (
    <div>
      <PageHeader
        title="Review Queue"
        description={
          <>
            Reviewed by <strong className="font-medium text-slate-700">Neer</strong>, your review agent —
            showing data for: <strong className="font-medium text-slate-700">{selectedBrand ? selectedBrand.name : "no brand selected"}</strong>
          </>
        }
      />

      {error && (
        <p role="alert" className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
          {error}
        </p>
      )}

      {!selectedBrand ? (
        <EmptyState
          title="No brand selected"
          description="Select a brand to see its review queue."
        />
      ) : isLoading && posts.length === 0 ? (
        <div role="status" aria-live="polite" className="space-y-4">
          <span className="sr-only">Loading review queue…</span>
          {[0, 1].map((i) => (
            <Card key={i} className="space-y-3 p-5">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-3 w-48" />
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-8 w-64" />
            </Card>
          ))}
        </div>
      ) : posts.length === 0 ? (
        <EmptyState
          title="All caught up"
          description="Nothing is waiting on human review right now."
        />
      ) : (
        <ul className="space-y-4">
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
    </div>
  );
}
