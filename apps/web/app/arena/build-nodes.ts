// Merges the real data an Arena run has (ArenaRun from the API, plus the
// CalendarEvent/Brand it belongs to) onto the static graph topology
// (topology.ts) to produce what the canvas actually renders. This is
// deliberately the one place that decides "what does this node say" —
// kept as pure functions, no React, so it's unit-testable without
// mounting the page.
import type { ArenaAgentRun, ArenaReviewFeedback, ArenaRun, Brand, CalendarEvent } from "@/lib/api";
import { formatCost, formatLatency, formatTokens, truncate } from "./format";
import { ArenaNodeId, NODE_LAYOUT, NodeLayout } from "./topology";

export type NodeStatus = "DONE" | "WAITING" | "QUEUED" | "SKIPPED" | "READ";

export interface ArenaNodeView extends NodeLayout {
  status: NodeStatus;
  /** 1-3 short summary lines shown on the node card's body. */
  lines: string[];
  /** Up to 3 label/value stat tiles — real numbers only, "—" when absent. */
  stats: { label: string; value: string }[];
  /** One-line footer, e.g. a timestamp or a static description of what a
   * still-stub stage does. */
  footer: string;
  /** The backing AgentRun row, if this stage has run — null for context
   * nodes and for stages that haven't executed yet. */
  agentRun: ArenaAgentRun | null;
  /** ReviewFeedback rows relevant to this node (reviewer: ai_reviewer
   * rows; human_review: human rows) — empty for every other node. */
  reviewFeedback: ArenaReviewFeedback[];
}

const PIPELINE_STAGE_ORDER: ArenaNodeId[] = [
  "research",
  "creative",
  "generation",
  "reviewer",
  "human_review",
  "scheduler",
  "publisher",
  "analytics_collector",
];

// What each stage's real code actually does — static, factual, and true
// regardless of whether it has run yet. Several of these (scheduler,
// analytics_collector) are still stub nodes in
// packages/agents/pipeline/graph.py — said plainly here rather than
// implying they do something they don't.
const STAGE_DESCRIPTIONS: Record<ArenaNodeId, string> = {
  brief: "The calendar event this run was triggered from.",
  brand: "Brand voice, audience and compliance rules retrieved for this run.",
  research: "Gathers platform + industry trend research and brand context.",
  creative: "Turns the research brief into a per-platform angle/hook/CTA.",
  generation: "Writes per-platform copy (and media, where the brief calls for it).",
  reviewer: "Scores the draft against brand voice/compliance and platform fit.",
  human_review: "Durable pause — waits for a human decision, resumable across restarts.",
  scheduler: "Not yet implemented — still a stub node that only records that it ran.",
  publisher: "Hands the post to the async publish queue for each target platform.",
  analytics_collector: "Not yet implemented — still a stub node that only records that it ran.",
};

function isTerminalRejected(post: ArenaRun["post"]): boolean {
  return post?.current_pipeline_stage === "rejected";
}

function findAgentRun(agentRuns: ArenaAgentRun[], id: ArenaNodeId): ArenaAgentRun | null {
  return agentRuns.find((run) => run.agent_type === id) ?? null;
}

function statusFor(
  id: ArenaNodeId,
  run: ArenaRun,
  agentRun: ArenaAgentRun | null
): NodeStatus {
  if (agentRun) return "DONE";
  if (id === "human_review" && run.post?.current_pipeline_stage === "human_review") {
    return "WAITING";
  }
  const stageIndex = PIPELINE_STAGE_ORDER.indexOf(id);
  if (isTerminalRejected(run.post) && stageIndex > PIPELINE_STAGE_ORDER.indexOf("human_review")) {
    return "SKIPPED";
  }
  return "QUEUED";
}

function contextBriefNode(base: NodeLayout, event: CalendarEvent | null): ArenaNodeView {
  if (!event) {
    return {
      ...base,
      status: "READ",
      lines: ["No calendar event — ad hoc post"],
      stats: [],
      footer: STAGE_DESCRIPTIONS.brief,
      agentRun: null,
      reviewFeedback: [],
    };
  }
  return {
    ...base,
    status: "READ",
    lines: [
      truncate(event.title, 42),
      `platforms: ${event.target_platforms.join(", ") || "—"}`,
      `format: ${event.desired_format}`,
    ],
    stats: [
      { label: "PLATFORMS", value: String(event.target_platforms.length) },
      { label: "STATUS", value: event.status },
      { label: "FORMAT", value: event.desired_format },
    ],
    footer: `calendar event · ${new Date(event.target_datetime).toLocaleDateString()}`,
    agentRun: null,
    reviewFeedback: [],
  };
}

function contextBrandNode(base: NodeLayout, brand: Brand | null): ArenaNodeView {
  if (!brand) {
    return {
      ...base,
      status: "READ",
      lines: ["No brand selected"],
      stats: [],
      footer: STAGE_DESCRIPTIONS.brand,
      agentRun: null,
      reviewFeedback: [],
    };
  }
  return {
    ...base,
    status: "READ",
    lines: [
      brand.industry ?? "industry not set",
      `${brand.tone_descriptors?.length ?? 0} tone descriptors`,
    ],
    stats: [
      { label: "INDUSTRY", value: brand.industry ?? "—" },
      { label: "COLORS", value: String(brand.colors?.length ?? 0) },
      { label: "REPORT", value: brand.brand_report ? "ready" : "none" },
    ],
    footer: brand.name,
    agentRun: null,
    reviewFeedback: [],
  };
}

function researchLines(agentRun: ArenaAgentRun): { lines: string[]; stats: { label: string; value: string }[] } {
  const brief = agentRun.output?.research_brief as
    | { platform_trends?: Record<string, unknown[]>; industry_trends?: { title: string }[] }
    | undefined;
  const platformTrendCount = brief?.platform_trends
    ? Object.values(brief.platform_trends).reduce((sum, arr) => sum + (Array.isArray(arr) ? arr.length : 0), 0)
    : 0;
  const industryTrends = brief?.industry_trends ?? [];
  const sourceCount = platformTrendCount + industryTrends.length;
  return {
    lines: [
      `${sourceCount} source${sourceCount === 1 ? "" : "s"} found`,
      industryTrends[0]?.title ? truncate(industryTrends[0].title, 48) : "no industry trend surfaced",
    ],
    stats: [
      { label: "SOURCES", value: String(sourceCount) },
      { label: "COST", value: formatCost(agentRun.cost) },
      { label: "LATENCY", value: formatLatency(agentRun.latency_ms) },
    ],
  };
}

function creativeLines(agentRun: ArenaAgentRun): { lines: string[]; stats: { label: string; value: string }[] } {
  const brief = agentRun.output?.creative_brief as
    | { platforms?: Record<string, { hook?: string; format?: string }> }
    | undefined;
  const platforms = brief?.platforms ?? {};
  const platformIds = Object.keys(platforms);
  const firstHook = platformIds[0] ? platforms[platformIds[0]]?.hook : undefined;
  return {
    lines: [
      `${platformIds.length} platform brief${platformIds.length === 1 ? "" : "s"}`,
      firstHook ? truncate(firstHook, 52) : "no hook generated",
    ],
    stats: [
      { label: "PLATFORMS", value: String(platformIds.length) },
      { label: "MODEL", value: agentRun.model ?? "—" },
      { label: "COST", value: formatCost(agentRun.cost) },
    ],
  };
}

function generationLines(agentRun: ArenaAgentRun): { lines: string[]; stats: { label: string; value: string }[] } {
  const output = agentRun.output?.generation_output as
    | { platforms?: Record<string, unknown> }
    | undefined;
  const platformIds = Object.keys(output?.platforms ?? {});
  return {
    lines: [
      `${platformIds.length} draft${platformIds.length === 1 ? "" : "s"} written`,
      agentRun.model ? `model: ${agentRun.model}` : "model not recorded",
    ],
    stats: [
      { label: "DRAFTS", value: String(platformIds.length) },
      { label: "TOKENS", value: formatTokens(agentRun.tokens) },
      { label: "COST", value: formatCost(agentRun.cost) },
    ],
  };
}

function reviewerLines(
  agentRun: ArenaAgentRun,
  reviewFeedback: ArenaReviewFeedback[]
): { lines: string[]; stats: { label: string; value: string }[] } {
  const latest = reviewFeedback[reviewFeedback.length - 1];
  return {
    lines: latest
      ? [`score ${latest.score.toFixed(0)}/100 · ${latest.verdict}`]
      : ["review pass complete"],
    stats: [
      { label: "SCORE", value: latest ? latest.score.toFixed(0) : "—" },
      { label: "VERDICT", value: latest ? latest.verdict : "—" },
      { label: "COST", value: formatCost(agentRun.cost) },
    ],
  };
}

function humanReviewLines(
  run: ArenaRun,
  agentRun: ArenaAgentRun | null,
  humanFeedback: ArenaReviewFeedback[]
): { lines: string[]; stats: { label: string; value: string }[] } {
  if (!agentRun && run.post?.current_pipeline_stage === "human_review") {
    return {
      lines: ["Paused — waiting on a human decision", "durable interrupt · resumes exactly here"],
      stats: [{ label: "PENDING", value: "1" }, { label: "SINCE", value: formatClockShort(run.post.updated_at) }, { label: "SLA", value: "—" }],
    };
  }
  const latest = humanFeedback[humanFeedback.length - 1];
  if (latest) {
    return {
      lines: [`${latest.verdict} by a human reviewer`],
      stats: [{ label: "VERDICT", value: latest.verdict }, { label: "SCORE", value: latest.score.toFixed(0) }, { label: "AT", value: formatClockShort(latest.created_at) }],
    };
  }
  return { lines: ["not reached yet"], stats: [] };
}

function formatClockShort(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function genericStageLines(agentRun: ArenaAgentRun): { lines: string[]; stats: { label: string; value: string }[] } {
  return {
    lines: [STAGE_DESCRIPTIONS[agentRun.agent_type], "ran successfully"],
    stats: [
      { label: "MODEL", value: agentRun.model ?? "—" },
      { label: "COST", value: formatCost(agentRun.cost) },
      { label: "LATENCY", value: formatLatency(agentRun.latency_ms) },
    ],
  };
}

function stageNode(
  base: NodeLayout,
  id: ArenaNodeId,
  run: ArenaRun
): ArenaNodeView {
  const agentRun = findAgentRun(run.agent_runs, id);
  const status = statusFor(id, run, agentRun);
  const reviewFeedback =
    id === "reviewer"
      ? run.review_feedback.filter((f) => f.source === "ai_reviewer")
      : id === "human_review"
        ? run.review_feedback.filter((f) => f.source === "human")
        : [];

  if (!agentRun) {
    const waiting = status === "WAITING";
    const skipped = status === "SKIPPED";
    let extra: { lines: string[]; stats: { label: string; value: string }[] } = {
      lines: [skipped ? "skipped — run was rejected before reaching here" : "not run yet"],
      stats: [],
    };
    if (id === "human_review" || waiting) {
      extra = humanReviewLines(run, null, reviewFeedback);
    }
    return {
      ...base,
      status,
      lines: extra.lines,
      stats: extra.stats,
      footer: STAGE_DESCRIPTIONS[id],
      agentRun: null,
      reviewFeedback,
    };
  }

  let extra: { lines: string[]; stats: { label: string; value: string }[] };
  switch (id) {
    case "research":
      extra = researchLines(agentRun);
      break;
    case "creative":
      extra = creativeLines(agentRun);
      break;
    case "generation":
      extra = generationLines(agentRun);
      break;
    case "reviewer":
      extra = reviewerLines(agentRun, reviewFeedback);
      break;
    case "human_review":
      extra = humanReviewLines(run, agentRun, reviewFeedback);
      break;
    default:
      extra = genericStageLines(agentRun);
  }

  return {
    ...base,
    status,
    lines: extra.lines,
    stats: extra.stats,
    footer: `${STAGE_DESCRIPTIONS[id]} · ${formatClockShort(agentRun.created_at)}`,
    agentRun,
    reviewFeedback,
  };
}

export function buildArenaNodes(
  run: ArenaRun,
  event: CalendarEvent | null,
  brand: Brand | null
): ArenaNodeView[] {
  return NODE_LAYOUT.map((base) => {
    if (base.id === "brief") return contextBriefNode(base, event);
    if (base.id === "brand") return contextBrandNode(base, brand);
    return stageNode(base, base.id, run);
  });
}
