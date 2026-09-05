// Builds the bottom dock's four tabs (Trace / Outputs / Cost / Sources)
// straight from the real AgentRun/Post rows in an ArenaRun — no invented
// telemetry. Kept separate from build-nodes.ts (which is about the
// canvas) since the dock reads the same run but summarizes it
// differently (a flat timeline instead of per-node cards).
import type { AgentType, ArenaAgentRun, ArenaRun } from "@/lib/api";
import { formatClock, formatCost, formatTokens, truncate } from "./format";

export const AGENT_DISPLAY_NAME: Record<AgentType, string> = {
  research: "Ved",
  creative: "Keshav",
  generation: "Kavi",
  reviewer: "Neer",
  human_review: "system",
  scheduler: "Scheduler",
  publisher: "Publisher",
  analytics_collector: "Analytics",
};

export interface TraceEntry {
  id: string;
  time: string;
  who: string;
  text: string;
}

function summarize(agentRun: ArenaAgentRun): string {
  const output = agentRun.output ?? {};
  switch (agentRun.agent_type) {
    case "research": {
      const brief = output.research_brief as { industry_trends?: { title: string }[] } | undefined;
      const count = brief?.industry_trends?.length ?? 0;
      return `research complete · ${count} industry trend${count === 1 ? "" : "s"} found`;
    }
    case "creative": {
      const brief = output.creative_brief as { platforms?: Record<string, unknown> } | undefined;
      const count = Object.keys(brief?.platforms ?? {}).length;
      return `creative brief ready · ${count} platform${count === 1 ? "" : "s"}`;
    }
    case "generation": {
      const gen = output.generation_output as { platforms?: Record<string, unknown> } | undefined;
      const count = Object.keys(gen?.platforms ?? {}).length;
      return `generated ${count} draft${count === 1 ? "" : "s"}` + (agentRun.model ? ` with ${agentRun.model}` : "");
    }
    case "reviewer":
      return "reviewer pass complete — see Governance for score/verdict";
    case "human_review":
      return "resumed from the human_review checkpoint";
    case "scheduler":
      return "scheduler stage recorded (not yet implemented)";
    case "publisher":
      return "handed off to the publish queue";
    case "analytics_collector":
      return "analytics collector stage recorded (not yet implemented)";
    default:
      return "stage complete";
  }
}

export function buildTrace(run: ArenaRun): TraceEntry[] {
  return run.agent_runs.map((agentRun) => ({
    id: agentRun.id,
    time: agentRun.created_at,
    who: AGENT_DISPLAY_NAME[agentRun.agent_type],
    text: summarize(agentRun),
  }));
}

export interface SourceEntry {
  title: string;
  url: string;
  domain: string;
}

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** Real search results the Research Engine actually retrieved
 * (packages/agents/pipeline/nodes/research_engine.py's
 * industry_trends/platform_trends), not invented sources. Empty when
 * research hasn't run yet. */
export function buildSources(run: ArenaRun): SourceEntry[] {
  const researchRun = run.agent_runs.find((r) => r.agent_type === "research");
  const brief = researchRun?.output?.research_brief as
    | {
        industry_trends?: { title: string; url: string }[];
        platform_trends?: Record<string, { title: string; url: string }[]>;
      }
    | undefined;
  if (!brief) return [];

  const results: { title: string; url: string }[] = [...(brief.industry_trends ?? [])];
  for (const list of Object.values(brief.platform_trends ?? {})) {
    if (Array.isArray(list)) results.push(...list);
  }

  const seen = new Set<string>();
  const sources: SourceEntry[] = [];
  for (const result of results) {
    if (!result?.url || seen.has(result.url)) continue;
    seen.add(result.url);
    sources.push({ title: result.title || result.url, url: result.url, domain: domainOf(result.url) });
  }
  return sources;
}

export interface CostRow {
  agentType: AgentType;
  who: string;
  model: string;
  tokens: string;
  cost: string;
}

export function buildCostRows(run: ArenaRun): CostRow[] {
  return run.agent_runs
    .filter((r) => r.cost !== null || r.tokens !== null)
    .map((r) => ({
      agentType: r.agent_type,
      who: AGENT_DISPLAY_NAME[r.agent_type],
      model: r.model ?? "—",
      tokens: formatTokens(r.tokens),
      cost: formatCost(r.cost),
    }));
}

export function totalCost(run: ArenaRun): number {
  return run.agent_runs.reduce((sum, r) => sum + (r.cost ?? 0), 0);
}

export function totalTokens(run: ArenaRun): number {
  return run.agent_runs.reduce((sum, r) => sum + (r.tokens ?? 0), 0);
}

export interface DraftThumb {
  platform: string;
  format: string;
  url: string;
  captionPreview: string;
}

/** Real generated Post media (apps/api/models/post.py::Post.media) — empty
 * (not filled with placeholders) when generation hasn't produced any
 * media yet, e.g. a text-only run or one that hasn't reached generation. */
export function buildDraftThumbs(run: ArenaRun): DraftThumb[] {
  const media = run.post?.media ?? [];
  const bodyText = run.post?.body_text ?? {};
  return media.map((item) => ({
    platform: item.platform,
    format: item.format,
    url: item.url,
    captionPreview: bodyText[item.platform] ? truncate(bodyText[item.platform], 60) : "",
  }));
}

export { formatClock };
