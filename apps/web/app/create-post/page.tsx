"use client";

import { useCallback, useEffect, useState } from "react";
import {
  createCalendarEvent,
  fetchRecentPosts,
  type PipelineStage,
  type PostSummary,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useBrand } from "@/lib/brand-context";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { cn } from "@/components/ui/cn";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field, Select, Textarea } from "@/components/ui/Input";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";

// Kept in sync with apps/api/models/content_calendar_event.py::SUPPORTED_PLATFORMS
// — same list apps/web/app/calendar/event-form.tsx uses.
const PLATFORM_OPTIONS: { value: string; label: string }[] = [
  { value: "linkedin", label: "LinkedIn" },
  { value: "x", label: "X" },
];

const FORMAT_OPTIONS = ["text", "image", "video", "carousel"];

const DEFAULT_BRIEF =
  "Post about our new contract-review turnaround — 11 days to 40 minutes. Founder voice, not corporate.";

// current_pipeline_stage -> what the Create Post page shows. "rejected" is
// the real terminal stage a human reviewer's rejection sets (Issue #25,
// apps/api/routers/review.py::reject_post) — "Blocked" is just this page's
// label for it, not an invented backend status.
const STAGE_DISPLAY: Record<PipelineStage, { label: string; tone: BadgeTone }> = {
  research: { label: "Researching", tone: "blue" },
  creative: { label: "Writing angles", tone: "blue" },
  generation: { label: "Generating", tone: "blue" },
  reviewer: { label: "AI review", tone: "blue" },
  human_review: { label: "Awaiting review", tone: "amber" },
  scheduler: { label: "Scheduling", tone: "blue" },
  publisher: { label: "Publishing", tone: "blue" },
  analytics_collector: { label: "Publishing", tone: "blue" },
  completed: { label: "Completed", tone: "green" },
  rejected: { label: "Blocked", tone: "red" },
  failed: { label: "Failed", tone: "red" },
};

function summaryTitle(post: PostSummary): string {
  const firstPlatform = post.body_text ? Object.values(post.body_text)[0] : null;
  if (firstPlatform) return firstPlatform.slice(0, 80);
  return `Post ${post.id.slice(0, 8)}`;
}

export default function CreatePostPage() {
  const { token } = useAuth();
  const { selectedBrand, selectedBrandId } = useBrand();
  const { push } = useToast();

  const [brief, setBrief] = useState(DEFAULT_BRIEF);
  const [platforms, setPlatforms] = useState<string[]>(["linkedin"]);
  const [format, setFormat] = useState(FORMAT_OPTIONS[0]);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [runs, setRuns] = useState<PostSummary[]>([]);
  const [isLoadingRuns, setIsLoadingRuns] = useState(false);

  const loadRuns = useCallback(async () => {
    if (!token || !selectedBrandId) {
      setRuns([]);
      return;
    }
    setIsLoadingRuns(true);
    try {
      const result = await fetchRecentPosts(token, selectedBrandId);
      setRuns(result);
    } catch {
      // Recent runs is a convenience list — a failed refresh shouldn't
      // block the compose form above it.
    } finally {
      setIsLoadingRuns(false);
    }
  }, [token, selectedBrandId]);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  function togglePlatform(value: string) {
    setPlatforms((current) => (current.includes(value) ? current.filter((p) => p !== value) : [...current, value]));
  }

  async function handleRunAllAgents() {
    if (!token || !selectedBrandId) return;
    if (platforms.length === 0) {
      setError("Select at least one platform.");
      return;
    }
    if (!brief.trim()) {
      setError("Describe the post first.");
      return;
    }

    setIsRunning(true);
    setError(null);
    try {
      // Reuses the real calendar-event creation endpoint (Issue #26) with
      // an immediate target_datetime — apps/api/services/pipeline
      // trigger.py's Celery Beat poller (Issue #29) picks up any event
      // within its lead time and starts the real 5-stage pipeline for it,
      // the same path a normal scheduled post takes.
      await createCalendarEvent(token, selectedBrandId, {
        title: brief.slice(0, 120),
        description: brief,
        target_platforms: platforms,
        desired_format: format,
        target_datetime: new Date().toISOString(),
      });
      push("Queued — all agents will run shortly", "success");
      loadRuns();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to queue post";
      setError(message);
      push(message, "error");
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Create a post"
        description="Describe it, pick platforms, and all agents run together on the real pipeline."
      />

      {!selectedBrand ? (
        <EmptyState title="No brand selected" description="Select a brand to create a post for it." />
      ) : (
        <>
          <Card className="mb-6 p-5">
            <Field label="Brief" htmlFor="create-post-brief">
              <Textarea
                id="create-post-brief"
                value={brief}
                onChange={(event) => setBrief(event.target.value)}
                rows={4}
              />
            </Field>

            <div className="mt-4 flex flex-wrap items-center gap-2.5 border-t border-line-faint pt-4">
              {PLATFORM_OPTIONS.map((option) => {
                const active = platforms.includes(option.value);
                return (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => togglePlatform(option.value)}
                    aria-pressed={active}
                    className={cn(
                      "rounded-[9px] border px-2.5 py-1.5 text-[12.5px] font-semibold transition-colors",
                      active
                        ? "border-brand-600 bg-brand-50 text-brand-700"
                        : "border-line bg-white text-ink-600 hover:bg-canvas",
                    )}
                  >
                    {option.label}
                  </button>
                );
              })}

              <Select
                value={format}
                onChange={(event) => setFormat(event.target.value)}
                aria-label="Desired format"
                className="ml-1 h-9 w-auto"
              >
                {FORMAT_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </Select>

              <Button onClick={handleRunAllAgents} isLoading={isRunning} className="ml-auto">
                ✧ Run all agents
              </Button>
            </div>

            {error && (
              <p role="alert" className="mt-3 text-sm font-medium text-danger">
                {error}
              </p>
            )}
          </Card>

          <div className="mb-3 flex items-center gap-2.5">
            <span className="text-[11.5px] font-extrabold tracking-[0.1em] text-ink-300">RECENT RUNS</span>
            <div className="h-px flex-1 bg-line-faint" />
          </div>

          {isLoadingRuns && runs.length === 0 ? (
            <div role="status" aria-live="polite" className="space-y-2.5">
              <span className="sr-only">Loading recent runs…</span>
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-16 w-full rounded-[13px]" />
              ))}
            </div>
          ) : runs.length === 0 ? (
            <EmptyState title="No runs yet" description="Posts you create will show up here." />
          ) : (
            <ul className="flex flex-col gap-2.5">
              {runs.map((post) => {
                const display = STAGE_DISPLAY[post.current_pipeline_stage];
                return (
                  <li key={post.id}>
                    <Card className="flex items-center gap-3.5 p-3.5">
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[13.5px] font-semibold text-ink-950">
                          {summaryTitle(post)}
                        </div>
                        <div className="mt-0.5 text-[11.5px] text-ink-300">
                          {new Date(post.created_at).toLocaleString()}
                        </div>
                      </div>
                      <Badge tone={display.tone}>{display.label}</Badge>
                    </Card>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
