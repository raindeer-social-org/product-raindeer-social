import type { AgentType, CalendarEventAgentRun } from "@/lib/api";

// Persona identities for the pipeline's real stages. Mirrors
// apps/web/tailwind.config.ts's `agent` color tokens (ved/keshav/kavi/neer),
// already reserved there — per that file's own comment — for "avatars,
// badges, node headers" once a screen needing them was built. This is that
// screen: the calendar's post preview modal "agent trail" (Issue #125).
// Only pipeline stages that actually run before a post reaches a human
// (research -> creative -> generation -> reviewer) get a persona; the
// remaining AgentType values are pipeline-internal steps a human never
// watches happen and are labeled generically instead of invented personas.
const AGENT_PERSONA_NAME: Partial<Record<AgentType, string>> = {
  onboarding: "Aarav",
  research: "Ved",
  creative: "Keshav",
  generation: "Kavi",
  reviewer: "Neer",
};

const AGENT_COLOR_CLASS: Partial<Record<AgentType, string>> = {
  onboarding: "bg-agent-aarav-solid",
  research: "bg-agent-ved-solid",
  creative: "bg-agent-keshav-solid",
  generation: "bg-agent-kavi-solid",
  reviewer: "bg-agent-neer-solid",
};

const GENERIC_LABEL: Record<AgentType, string> = {
  onboarding: "Aarav",
  research: "Ved",
  creative: "Keshav",
  generation: "Kavi",
  reviewer: "Neer",
  human_review: "Human review",
  scheduler: "Scheduler",
  publisher: "Publisher",
  analytics_collector: "Analytics",
  weekly_report: "Weekly report",
};

export function agentPersonaName(agentType: AgentType): string {
  return AGENT_PERSONA_NAME[agentType] ?? GENERIC_LABEL[agentType] ?? agentType;
}

export function agentPersonaColorClass(agentType: AgentType): string {
  return AGENT_COLOR_CLASS[agentType] ?? "bg-ink-300";
}

export function agentPersonaInitial(agentType: AgentType): string {
  const name = agentPersonaName(agentType);
  return name.slice(0, 1).toUpperCase();
}

function platformCount(value: unknown): number {
  if (value && typeof value === "object") {
    return Object.keys(value as Record<string, unknown>).length;
  }
  return 0;
}

/**
 * A short, honest one-line summary of what a real AgentRun row actually
 * produced — built only from fields the corresponding pipeline node
 * (packages/agents/pipeline/nodes/*.py) is documented to write into its
 * output dict, never a fabricated detail. Falls back to a generic
 * "Completed" line for a stage/output shape this doesn't recognize (e.g.
 * a future pipeline stage) rather than guessing.
 */
export function describeAgentRun(run: CalendarEventAgentRun): string {
  const output = (run.output ?? {}) as Record<string, unknown>;

  switch (run.agent_type) {
    case "research": {
      const brief = output.research_brief as Record<string, unknown> | undefined;
      const count = platformCount(brief?.platform_trends);
      return count > 0
        ? `Researched trends across ${count} platform${count === 1 ? "" : "s"} and brand context.`
        : "Researched trends and brand context for this post.";
    }
    case "creative": {
      const brief = output.creative_brief as Record<string, unknown> | undefined;
      const count = platformCount(brief?.platforms);
      return count > 0
        ? `Drafted a creative angle for ${count} platform${count === 1 ? "" : "s"}.`
        : "Drafted a creative angle for this post.";
    }
    case "generation": {
      const generation = output.generation_output as Record<string, unknown> | undefined;
      const count = platformCount(generation?.platforms);
      return count > 0
        ? `Generated draft copy for ${count} platform${count === 1 ? "" : "s"}.`
        : "Generated draft copy for this post.";
    }
    case "reviewer": {
      const review = output.review_output as Record<string, unknown> | undefined;
      const score = review?.score;
      const verdict = review?.verdict;
      if (typeof score === "number") {
        return `Scored this draft ${Math.round(score)}/100${typeof verdict === "string" ? ` (${verdict})` : ""}.`;
      }
      return "Reviewed this draft for brand fit and compliance.";
    }
    default:
      return "Completed.";
  }
}
