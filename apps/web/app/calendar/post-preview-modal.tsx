"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { CalendarEvent, CalendarEventPost } from "@/lib/api";
import { fetchCalendarEventPost } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { cn } from "@/components/ui/cn";
import { Modal } from "@/components/ui/Modal";
import { Skeleton } from "@/components/ui/Skeleton";
import { agentPersonaColorClass, agentPersonaInitial, agentPersonaName, describeAgentRun } from "./agent-trail";
import { PlatformMock } from "./platform-mock";
import { buildScoreTiles } from "./review-scores";
import { StatusBadge } from "./status-badge";

interface PostPreviewModalProps {
  event: CalendarEvent;
  token: string;
  brandId: string;
  brandName: string;
  onClose: () => void;
  onEdit: (event: CalendarEvent) => void;
}

const AGENT_TRAIL_AGENT_TYPES = new Set(["research", "creative", "generation", "reviewer"]);

export function PostPreviewModal({ event, token, brandId, brandName, onClose, onEdit }: PostPreviewModalProps) {
  const [post, setPost] = useState<CalendarEventPost | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [platform, setPlatform] = useState(event.target_platforms[0] ?? "linkedin");

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    setPost(null);
    setPlatform(event.target_platforms[0] ?? "linkedin");

    fetchCalendarEventPost(token, brandId, event.id)
      .then((result) => {
        if (!cancelled) setPost(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load post details");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [event.id, token, brandId]);

  const scoreTiles = buildScoreTiles(post, platform);
  const trail = (post?.agent_runs ?? []).filter((run) => AGENT_TRAIL_AGENT_TYPES.has(run.agent_type));
  const scheduledLabel = new Date(event.target_datetime).toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });

  return (
    <Modal open onClose={onClose} title={event.title} size="xl">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="rounded-xl bg-canvas p-5">
          {event.target_platforms.length > 1 && (
            <div className="mb-4 flex flex-wrap justify-center gap-1.5" role="tablist" aria-label="Platform preview">
              {event.target_platforms.map((p) => (
                <button
                  key={p}
                  type="button"
                  role="tab"
                  aria-selected={platform === p}
                  onClick={() => setPlatform(p)}
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs font-semibold capitalize transition-colors",
                    platform === p
                      ? "border-brand-600 bg-brand-600 text-white"
                      : "border-line bg-white text-ink-500 hover:bg-canvas",
                  )}
                >
                  {p}
                </button>
              ))}
            </div>
          )}
          <PlatformMock
            platform={platform}
            brandName={brandName}
            title={event.title}
            body={post?.body_text?.[platform] ?? null}
          />
        </div>

        <div className="flex flex-col gap-5">
          <div>
            <div className="mb-1.5 flex flex-wrap items-center gap-2">
              <StatusBadge status={event.status} />
              {event.target_platforms.map((p) => (
                <Badge key={p} tone="slate">
                  {p}
                </Badge>
              ))}
            </div>
            <p className="text-sm text-ink-400">Scheduled {scheduledLabel}</p>
          </div>

          <div>
            <div className="mb-2 text-xs font-bold uppercase tracking-wide text-ink-300">Scores</div>
            {isLoading ? (
              <div className="grid grid-cols-2 gap-2">
                {[0, 1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-14 w-full" />
                ))}
              </div>
            ) : error ? (
              <p role="alert" className="text-sm text-danger">
                {error}
              </p>
            ) : scoreTiles ? (
              <div className="grid grid-cols-2 gap-2">
                {scoreTiles.map((tile) => (
                  <div key={tile.label} className="rounded-[11px] border border-line-faint p-2.5">
                    <div className="mb-1 text-[11px] font-medium text-ink-300">{tile.label}</div>
                    <Badge tone={tile.tone}>{tile.value}</Badge>
                  </div>
                ))}
              </div>
            ) : (
              <p className="rounded-[11px] border border-dashed border-line p-3 text-sm text-ink-400">
                Not reviewed yet — this post hasn&apos;t reached the Reviewer Engine.
              </p>
            )}
          </div>

          <div>
            <div className="mb-2.5 text-xs font-bold uppercase tracking-wide text-ink-300">Agent trail</div>
            {isLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-full" />
              </div>
            ) : trail.length === 0 ? (
              <p className="rounded-[11px] border border-dashed border-line p-3 text-sm text-ink-400">
                No agent activity yet — this post hasn&apos;t entered the pipeline.
              </p>
            ) : (
              <ul className="flex flex-col">
                {trail.map((run, i) => (
                  <li key={run.id} className="flex gap-2.5">
                    <div className="flex w-5 shrink-0 flex-col items-center">
                      <span
                        className={cn(
                          "flex h-5 w-5 items-center justify-center rounded-full text-[9px] font-extrabold text-white",
                          agentPersonaColorClass(run.agent_type),
                        )}
                      >
                        {agentPersonaInitial(run.agent_type)}
                      </span>
                      {i < trail.length - 1 && <span className="mt-0.5 w-px flex-1 bg-line-faint" />}
                    </div>
                    <div className="min-w-0 pb-3.5">
                      <div className="text-xs font-semibold text-ink-950">
                        {agentPersonaName(run.agent_type)}{" "}
                        <span className="font-normal text-ink-200">
                          {new Date(run.created_at).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}
                        </span>
                      </div>
                      <p className="mt-0.5 text-xs leading-relaxed text-ink-500">{describeAgentRun(run)}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {post?.current_pipeline_stage === "human_review" && (
              <Link href="/review-queue" className="mt-1 block">
                <Button type="button" variant="outline" size="sm" className="w-full">
                  ◈ Open in Review Queue
                </Button>
              </Link>
            )}
          </div>

          <div className="mt-auto flex gap-2">
            <Button type="button" variant="primary" className="flex-1" onClick={() => onEdit(event)}>
              Edit
            </Button>
            <Button type="button" variant="outline" onClick={onClose}>
              Close
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
