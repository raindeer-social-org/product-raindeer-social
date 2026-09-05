// Static graph topology for the Content Arena canvas (Issue #124) —
// lanes, node positions, and edges. This mirrors the layout of "Raindeer
// Social Startup Onboarding/Raindeer Social.dc.html"'s CONTENT ARENA
// block, trimmed to the nodes that map onto something real: the mockup
// invents several flavor sub-steps per lane (trend radar, social
// listening, A/B hook split, risk & compliance, alerts & handoff, ...)
// that have no backend counterpart at all, and Issue #124 is explicit
// that node data must come from real data wherever it exists rather than
// inventing telemetry for things the pipeline doesn't track. So this
// graph has exactly one node per real thing: the two pieces of context a
// run reads (the calendar event's brief, the brand) plus the eight real
// pipeline stages (apps/api/models/agent_run.py::AgentType /
// packages/agents/pipeline/graph.py::PIPELINE_STAGES).
import type { AgentType } from "@/lib/api";

export type ArenaNodeId =
  | "brief"
  | "brand"
  | AgentType; // research | creative | generation | reviewer | human_review | scheduler | publisher | analytics_collector

export interface LaneDef {
  id: string;
  label: string;
  x: number;
  w: number;
  fg: string;
}

// x/w chosen to comfortably fit each lane's node width(s) plus gutters,
// same left-to-right pipeline reading order as the mockup's LANES array.
export const LANES: LaneDef[] = [
  { id: "context", label: "CONTEXT", x: 14, w: 210, fg: "#5B6A96" },
  { id: "research", label: "RESEARCH · VED", x: 240, w: 230, fg: "#8FB4FF" },
  { id: "strategy", label: "STRATEGY · KESHAV", x: 486, w: 230, fg: "#C9A6FF" },
  { id: "production", label: "PRODUCTION · KAVI", x: 732, w: 230, fg: "#6BE3B0" },
  { id: "governance", label: "GOVERNANCE · NEER", x: 978, w: 250, fg: "#FFC46B" },
  { id: "distribution", label: "DISTRIBUTION", x: 1244, w: 230, fg: "#7FD4FF" },
  { id: "learning", label: "LEARNING", x: 1490, w: 200, fg: "#FF9BC4" },
];

export interface NodeLayout {
  id: ArenaNodeId;
  lane: string;
  x: number;
  y: number;
  w: number;
  h: number;
  color: string;
  initial: string;
  name: string;
  /** Shown in the inspector header under the node name. */
  sub: string;
}

export const NODE_LAYOUT: NodeLayout[] = [
  { id: "brief", lane: "context", x: 28, y: 70, w: 182, h: 108, color: "#5B6784", initial: "▤", name: "Campaign brief", sub: "Calendar event · input" },
  { id: "brand", lane: "context", x: 28, y: 210, w: 182, h: 108, color: "#0B2A6B", initial: "B", name: "Brand memory", sub: "Brand · read-only" },
  { id: "research", lane: "research", x: 254, y: 90, w: 202, h: 170, color: "#1B4DFF", initial: "V", name: "Ved · Research", sub: "Research engine" },
  { id: "creative", lane: "strategy", x: 500, y: 90, w: 202, h: 160, color: "#6B32C9", initial: "K", name: "Keshav · Creative", sub: "Creative engine" },
  { id: "generation", lane: "production", x: 746, y: 90, w: 202, h: 160, color: "#0E7A4E", initial: "K", name: "Kavi · Generation", sub: "Generation engine" },
  { id: "reviewer", lane: "governance", x: 992, y: 70, w: 222, h: 150, color: "#B46A00", initial: "N", name: "Neer · Reviewer", sub: "Reviewer engine" },
  { id: "human_review", lane: "governance", x: 992, y: 250, w: 222, h: 140, color: "#1B4DFF", initial: "☺", name: "Human approval", sub: "Flow · durable interrupt" },
  { id: "scheduler", lane: "distribution", x: 1258, y: 90, w: 202, h: 110, color: "#1E7FB8", initial: "◷", name: "Scheduler", sub: "Distribution" },
  { id: "publisher", lane: "distribution", x: 1258, y: 240, w: 202, h: 130, color: "#1E7FB8", initial: "➤", name: "Publisher", sub: "Distribution" },
  { id: "analytics_collector", lane: "learning", x: 1504, y: 150, w: 172, h: 140, color: "#C2477F", initial: "▲", name: "Analytics collector", sub: "Learning loop · always on" },
];

export const NODE_LAYOUT_BY_ID: Record<string, NodeLayout> = Object.fromEntries(
  NODE_LAYOUT.map((n) => [n.id, n])
);

// [from, to] pairs — same left-to-right pipeline order as
// packages/agents/pipeline/graph.py::PIPELINE_STAGES, plus the two
// context nodes feeding into research.
export const EDGES: [ArenaNodeId, ArenaNodeId][] = [
  ["brief", "research"],
  ["brand", "research"],
  ["research", "creative"],
  ["creative", "generation"],
  ["generation", "reviewer"],
  ["reviewer", "human_review"],
  ["human_review", "scheduler"],
  ["scheduler", "publisher"],
  ["publisher", "analytics_collector"],
];

// The one feedback edge the mockup calls out explicitly (dashed, its own
// color) — analytics_collector really does feed the *next* run's research
// stage (Post.brand_id's brand memory accumulates engagement_snapshots),
// just not this run's own research node, hence drawn separately from the
// straight-line EDGES above.
export const FEEDBACK_EDGE: [ArenaNodeId, ArenaNodeId] = ["analytics_collector", "research"];

export const CANVAS_WIDTH = 1820;
export const CANVAS_HEIGHT = 460;

/** A smooth left-to-right cubic bezier between two node edges, same shape
 * as the mockup's own `path()` helper. */
export function edgePath(a: NodeLayout, b: NodeLayout): string {
  const x1 = a.x + a.w;
  const y1 = a.y + a.h / 2;
  const x2 = b.x;
  const y2 = b.y + b.h / 2;
  const dx = Math.max(36, (x2 - x1) / 2);
  return `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`;
}

/** The feedback edge loops under the canvas rather than straight across —
 * same visual treatment as the mockup's FEEDBACK path. */
export function feedbackPath(from: NodeLayout, to: NodeLayout): string {
  const x1 = from.x + from.w / 2;
  const y1 = from.y + from.h;
  const x2 = to.x + to.w / 2;
  const y2 = to.y + to.h;
  const loopY = CANVAS_HEIGHT - 30;
  return `M${x1},${y1} C${x1},${loopY} ${x2},${loopY} ${x2},${y2}`;
}
