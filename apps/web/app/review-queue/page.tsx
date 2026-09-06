"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  approveReviewPost,
  editReviewPost,
  fetchReviewQueue,
  regenerateReviewPost,
  rejectReviewPost,
  rescheduleReviewPost,
  type ReviewFeedback,
  type ReviewQueuePost,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useBrand } from "@/lib/brand-context";
import { ReviewCard } from "./review-card";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";

// Same "keep the queue live without a manual refresh" convention as
// apps/web/app/calendar/page.tsx — a paused post can be approved/rejected
// by a teammate, or a new one can land at human_review, at any time.
const POLL_INTERVAL_MS = 15000;

// Triage bucket a post falls into, derived from its latest AI review
// (mirrors review-card.tsx's own latestAiReview helper — kept local
// rather than shared since each file needs a slightly different return
// shape and this isn't worth a shared module yet).
type TriageBucket = "needs_changes" | "ready" | "unreviewed";

function latestAiReview(post: ReviewQueuePost): ReviewFeedback | null {
  const aiReviews = post.review_feedback.filter((f) => f.source === "ai_reviewer");
  return aiReviews.length > 0 ? aiReviews[aiReviews.length - 1] : null;
}

function triageBucket(post: ReviewQueuePost): TriageBucket {
  const review = latestAiReview(post);
  if (!review) return "unreviewed";
  return review.verdict === "approve" ? "ready" : "needs_changes";
}

function triageScore(post: ReviewQueuePost): number {
  // Used only to sort "worst first" — a post with no AI review yet sorts
  // after everything that's been scored, since there's nothing urgent to
  // triage about it yet.
  const review = latestAiReview(post);
  return review ? review.score : Infinity;
}

function platformsOf(post: ReviewQueuePost): string[] {
  return Object.keys(post.body_text ?? {});
}

export default function ReviewQueuePage() {
  const { token } = useAuth();
  const { selectedBrand, selectedBrandId } = useBrand();
  const { push } = useToast();

  const [posts, setPosts] = useState<ReviewQueuePost[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bucketFilter, setBucketFilter] = useState<TriageBucket | "all">("all");
  const [platformFilter, setPlatformFilter] = useState<string | "all">("all");

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

  async function handleRegenerate(postId: string) {
    if (!token || !selectedBrandId) return;
    try {
      const updated = await regenerateReviewPost(token, selectedBrandId, postId);
      // Regenerating doesn't resume the graph either — the post stays in
      // the queue with its revised draft.
      replacePost(updated);
      push("Draft regenerated from Neer's feedback", "success");
    } catch (err) {
      push(err instanceof Error ? err.message : "Failed to regenerate draft", "error");
    }
  }

  const platformOptions = useMemo(() => {
    const platforms = new Set<string>();
    for (const post of posts) {
      for (const platform of platformsOf(post)) platforms.add(platform);
    }
    return Array.from(platforms).sort();
  }, [posts]);

  const visiblePosts = useMemo(() => {
    return posts
      .filter((post) => bucketFilter === "all" || triageBucket(post) === bucketFilter)
      .filter((post) => platformFilter === "all" || platformsOf(post).includes(platformFilter))
      // Worst-first triage: lowest AI score (most urgent) surfaces first;
      // posts with no AI review yet sort last (triageScore returns
      // Infinity for those).
      .sort((a, b) => triageScore(a) - triageScore(b));
  }, [posts, bucketFilter, platformFilter]);

  const bucketCounts = useMemo(() => {
    const counts: Record<TriageBucket, number> = { needs_changes: 0, ready: 0, unreviewed: 0 };
    for (const post of posts) counts[triageBucket(post)] += 1;
    return counts;
  }, [posts]);

  return (
    <div>
      <PageHeader
        title="Review Queue"
        description={
          <>
            Showing data for: <strong className="font-medium text-slate-700">{selectedBrand ? selectedBrand.name : "no brand selected"}</strong>
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
        <>
          <div className="mb-4 flex flex-wrap items-center gap-x-6 gap-y-3">
            <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Filter by triage status">
              <Button
                type="button"
                size="sm"
                variant={bucketFilter === "all" ? "primary" : "outline"}
                onClick={() => setBucketFilter("all")}
              >
                All ({posts.length})
              </Button>
              <Button
                type="button"
                size="sm"
                variant={bucketFilter === "needs_changes" ? "primary" : "outline"}
                onClick={() => setBucketFilter("needs_changes")}
              >
                Needs changes ({bucketCounts.needs_changes})
              </Button>
              <Button
                type="button"
                size="sm"
                variant={bucketFilter === "ready" ? "primary" : "outline"}
                onClick={() => setBucketFilter("ready")}
              >
                Ready to approve ({bucketCounts.ready})
              </Button>
              {bucketCounts.unreviewed > 0 && (
                <Button
                  type="button"
                  size="sm"
                  variant={bucketFilter === "unreviewed" ? "primary" : "outline"}
                  onClick={() => setBucketFilter("unreviewed")}
                >
                  Unreviewed ({bucketCounts.unreviewed})
                </Button>
              )}
            </div>

            {platformOptions.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Filter by platform">
                <Button
                  type="button"
                  size="sm"
                  variant={platformFilter === "all" ? "secondary" : "ghost"}
                  onClick={() => setPlatformFilter("all")}
                >
                  All platforms
                </Button>
                {platformOptions.map((platform) => (
                  <Button
                    key={platform}
                    type="button"
                    size="sm"
                    variant={platformFilter === platform ? "secondary" : "ghost"}
                    onClick={() => setPlatformFilter(platform)}
                  >
                    {platform}
                  </Button>
                ))}
              </div>
            )}
          </div>

          {visiblePosts.length === 0 ? (
            <EmptyState
              title="No posts match this filter"
              description="Try a different triage or platform filter."
            />
          ) : (
            <ul className="space-y-4">
              {visiblePosts.map((post) => (
                <li key={post.id}>
                  <ReviewCard
                    post={post}
                    onApprove={handleApprove}
                    onReject={handleReject}
                    onEdit={handleEdit}
                    onReschedule={handleReschedule}
                    onRegenerate={handleRegenerate}
                  />
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
