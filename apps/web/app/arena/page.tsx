"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  type ArenaRun,
  type CalendarEvent,
  fetchArenaRunForEvent,
  fetchCalendarEvents,
  fetchLatestArenaRun,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useBrand } from "@/lib/brand-context";
import { buildArenaNodes } from "./build-nodes";
import { totalCost } from "./build-dock";
import { Dock } from "./dock";
import { formatCost, formatElapsedSince } from "./format";
import { Inspector } from "./inspector";
import { LibraryPanel } from "./library-panel";
import { NodeCard } from "./node-card";
import { CANVAS_HEIGHT, CANVAS_WIDTH, EDGES, FEEDBACK_EDGE, LANES, edgePath, feedbackPath, type ArenaNodeId } from "./topology";

// Same "keep it live without a manual refresh" convention as
// apps/web/app/calendar/page.tsx and app/review-queue/page.tsx — a run's
// AgentRun rows, review feedback, or pipeline stage can change from
// outside this tab (e.g. the trigger poller advancing it, or a teammate
// approving it from the Review Queue).
const POLL_INTERVAL_MS = 15000;

const TERMINAL_STAGES = new Set(["completed", "rejected", "failed"]);

export default function ArenaPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-arenadark-bg" />}>
      <ArenaScreen />
    </Suspense>
  );
}

function ArenaScreen() {
  const { token } = useAuth();
  const { selectedBrand, selectedBrandId } = useBrand();
  const searchParams = useSearchParams();
  const eventIdParam = searchParams.get("event");

  const [run, setRun] = useState<ArenaRun | null>(null);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<ArenaNodeId>("research");
  // Purely client-side toggle — the transport controls next to it are
  // render-only, per Issue #124's scope (no real playback/streaming).
  const [isPlaying, setIsPlaying] = useState(true);
  const [now, setNow] = useState(() => new Date());

  const load = useCallback(
    async (showSpinner: boolean) => {
      if (!token || !selectedBrandId) {
        setRun(null);
        return;
      }
      if (showSpinner) setIsLoading(true);
      setError(null);
      try {
        const [runResult, eventList] = await Promise.all([
          eventIdParam
            ? fetchArenaRunForEvent(token, selectedBrandId, eventIdParam)
            : fetchLatestArenaRun(token, selectedBrandId),
          fetchCalendarEvents(token, selectedBrandId),
        ]);
        setRun(runResult);
        setEvents(eventList);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load the Content Arena run");
      } finally {
        if (showSpinner) setIsLoading(false);
      }
    },
    [token, selectedBrandId, eventIdParam]
  );

  useEffect(() => {
    setRun(null);
    load(true);
    const interval = setInterval(() => load(false), POLL_INTERVAL_MS);
    const onFocus = () => load(false);
    window.addEventListener("focus", onFocus);
    return () => {
      clearInterval(interval);
      window.removeEventListener("focus", onFocus);
    };
  }, [load]);

  // Live-ticking clock for the header's elapsed-time stat — the
  // underlying timestamp (post.created_at) is real, this just keeps the
  // displayed duration counting up between polls.
  useEffect(() => {
    const tick = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(tick);
  }, []);

  const event = useMemo(() => {
    if (!run?.calendar_event_id) return null;
    return events.find((e) => e.id === run.calendar_event_id) ?? null;
  }, [run, events]);

  const nodes = useMemo(() => {
    if (!run) return [];
    return buildArenaNodes(run, event, selectedBrand ?? null);
  }, [run, event, selectedBrand]);

  const nodesById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const selectedNode = nodesById.get(selectedNodeId) ?? nodes[0] ?? null;

  const edgeElements = useMemo(() => {
    if (nodes.length === 0) return [];
    const straight = EDGES.map(([a, b]) => {
      const from = nodesById.get(a);
      const to = nodesById.get(b);
      if (!from || !to) return null;
      const isActive = a === selectedNodeId || b === selectedNodeId;
      return { key: `${a}-${b}`, d: edgePath(from, to), stroke: isActive ? "#3D6BFF" : "#22305C", dash: "6 6" };
    }).filter((e): e is NonNullable<typeof e> => e !== null);

    const [fa, fb] = FEEDBACK_EDGE;
    const feedbackFrom = nodesById.get(fa);
    const feedbackTo = nodesById.get(fb);
    if (feedbackFrom && feedbackTo) {
      straight.push({
        key: `${fa}-${fb}-feedback`,
        d: feedbackPath(feedbackFrom, feedbackTo),
        stroke: "#C2477F",
        dash: "2 7",
      });
    }
    return straight;
  }, [nodes, nodesById, selectedNodeId]);

  const isRunning = !!run?.post && !TERMINAL_STAGES.has(run.post.current_pipeline_stage);
  const waitingOnYou = nodes.some((n) => n.status === "WAITING");
  const runCost = run ? totalCost(run) : 0;

  const headerTitle = event ? event.title : run?.post ? "Ad hoc post run" : "Content Arena";

  return (
    <div className="flex h-screen flex-col bg-arenadark-bg text-arenadark-text">
      <header className="flex flex-none items-center justify-between gap-4 border-b border-arenadark-border bg-arenadark-panel px-[18px] py-2.5">
        <div className="flex min-w-0 items-center gap-3">
          <Link
            href="/calendar"
            className="flex h-[31px] items-center rounded-[9px] border border-arenadark-border3 bg-arenadark-panel3 px-2.5 text-[12.5px] font-semibold text-arenadark-text2"
          >
            ←
          </Link>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="truncate text-[14.5px] font-bold text-white">{headerTitle}</span>
              {run?.post ? (
                <span
                  className="flex items-center gap-1.5 rounded-[6px] px-[7px] py-[3px] text-[10px] font-extrabold tracking-wide"
                  style={
                    isRunning
                      ? { color: "#6BE3B0", background: "rgba(107,227,176,.12)", border: "1px solid rgba(107,227,176,.3)" }
                      : { color: "#7C8AB4", background: "rgba(124,138,180,.12)", border: "1px solid rgba(124,138,180,.3)" }
                  }
                >
                  {isRunning && <i className="h-1.5 w-1.5 animate-rd-blink rounded-full bg-[#6BE3B0]" />}
                  {isRunning ? "RUNNING" : run.post.current_pipeline_stage.toUpperCase()}
                </span>
              ) : null}
            </div>
            <div className="mt-0.5 flex items-center gap-3.5">
              {run?.post ? (
                <>
                  <Stat label="elapsed" value={formatElapsedSince(run.post.created_at, now)} />
                  <Stat label="agent runs" value={String(run.agent_runs.length)} />
                  <Stat label="spent" value={formatCost(runCost)} />
                  <Stat label="waiting on you" value={waitingOnYou ? "1" : "0"} />
                </>
              ) : (
                <span className="text-[11px] text-arenadark-muted2">No pipeline run yet for this brand.</span>
              )}
            </div>
          </div>
        </div>
        <div className="flex flex-none items-center gap-1.5">
          <div className="flex items-center gap-0.5 rounded-[9px] border border-arenadark-border3 bg-arenadark-panel3 p-[3px]">
            <button type="button" onClick={() => {}} aria-label="Skip to start" className="h-[26px] w-7 rounded-[7px] text-[11px] text-arenadark-text2">
              ⏮
            </button>
            <button
              type="button"
              onClick={() => setIsPlaying((p) => !p)}
              aria-label={isPlaying ? "Pause" : "Play"}
              className="h-[26px] w-7 rounded-[7px] bg-brand-600 text-[11px] text-white"
            >
              {isPlaying ? "⏸" : "▶"}
            </button>
            <button type="button" onClick={() => {}} aria-label="Skip to end" className="h-[26px] w-7 rounded-[7px] text-[11px] text-arenadark-text2">
              ⏭
            </button>
          </div>
          <Link
            href="/review-queue"
            className="flex h-8 items-center rounded-[9px] bg-brand-600 px-3.5 text-xs font-bold text-white"
          >
            Skip to review →
          </Link>
        </div>
      </header>

      {error && (
        <p role="alert" className="flex-none bg-danger-bg px-4 py-2 text-sm font-medium text-danger">
          {error}
        </p>
      )}

      {!selectedBrand ? (
        <div className="flex flex-1 items-center justify-center text-sm text-arenadark-muted2">
          Select a brand to see its Content Arena.
        </div>
      ) : isLoading && !run ? (
        <div role="status" className="flex flex-1 items-center justify-center text-sm text-arenadark-muted2">
          Loading run…
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-[206px_minmax(0,1fr)_336px]">
          <LibraryPanel />

          <div className="flex min-h-0 min-w-0 flex-col">
            <div className="relative flex-1 overflow-auto bg-arenadark-bg">
              {!run?.post ? (
                <div className="flex h-full items-center justify-center px-6 text-center text-sm text-arenadark-muted2">
                  No pipeline runs yet for this brand — trigger a calendar event to see it here.
                </div>
              ) : (
                <div
                  className="relative"
                  style={{
                    width: CANVAS_WIDTH,
                    height: CANVAS_HEIGHT,
                    backgroundImage: "radial-gradient(#18213F 1.1px, transparent 1.1px)",
                    backgroundSize: "26px 26px",
                  }}
                >
                  {LANES.map((lane) => (
                    <div
                      key={lane.id}
                      className="absolute rounded-2xl border border-[#141C36]"
                      style={{ top: 16, bottom: 16, left: lane.x, width: lane.w, background: "rgba(17,26,54,.35)" }}
                    >
                      <div
                        className="absolute left-3.5 top-2.5 text-[9.5px] font-extrabold tracking-[.16em]"
                        style={{ color: lane.fg }}
                      >
                        {lane.label}
                      </div>
                    </div>
                  ))}

                  <svg className="pointer-events-none absolute inset-0 h-full w-full">
                    {edgeElements.map((edge) => (
                      <path
                        key={edge.key}
                        d={edge.d}
                        fill="none"
                        stroke={edge.stroke}
                        strokeWidth={1.6}
                        strokeDasharray={edge.dash}
                        className="animate-rd-dash"
                      />
                    ))}
                  </svg>

                  {nodes.map((node) => (
                    <NodeCard
                      key={node.id}
                      node={node}
                      isSelected={node.id === selectedNodeId}
                      onSelect={(id) => setSelectedNodeId(id as ArenaNodeId)}
                    />
                  ))}
                </div>
              )}
            </div>

            {run && <Dock run={run} />}
          </div>

          {selectedNode ? (
            <Inspector node={selectedNode} />
          ) : (
            <aside className="border-l border-arenadark-border bg-arenadark-panel" />
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <span className="text-[11px] text-arenadark-muted2">
      <b className="font-bold text-arenadark-text2">{value}</b> {label}
    </span>
  );
}
