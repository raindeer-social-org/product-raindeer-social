import { describe, expect, it } from "vitest";
import { buildArenaNodes } from "@/app/arena/build-nodes";
import type { ArenaAgentRun, ArenaReviewFeedback, ArenaRun, Brand, CalendarEvent } from "@/lib/api";

function makeRun(overrides: Partial<ArenaRun> = {}): ArenaRun {
  return {
    calendar_event_id: null,
    post: null,
    agent_runs: [],
    review_feedback: [],
    ...overrides,
  };
}

function makeAgentRun(overrides: Partial<ArenaAgentRun>): ArenaAgentRun {
  return {
    id: "run-1",
    agent_type: "research",
    output: null,
    model: null,
    tokens: null,
    cost: null,
    latency_ms: null,
    created_at: "2026-08-20T10:00:00Z",
    ...overrides,
  };
}

function findNode(run: ArenaRun, event: CalendarEvent | null, brand: Brand | null, id: string) {
  const nodes = buildArenaNodes(run, event, brand);
  const node = nodes.find((n) => n.id === id);
  if (!node) throw new Error(`node ${id} not found`);
  return node;
}

describe("buildArenaNodes", () => {
  it("marks a stage DONE and pulls real cost/tokens once an AgentRun exists", () => {
    const run = makeRun({
      post: {
        id: "post-1",
        calendar_event_id: null,
        current_pipeline_stage: "generation",
        body_text: null,
        media: null,
        created_at: "2026-08-20T10:00:00Z",
        updated_at: "2026-08-20T10:00:00Z",
      },
      agent_runs: [
        makeAgentRun({
          agent_type: "generation",
          model: "sonnet",
          tokens: 512,
          cost: 0.12,
          latency_ms: 845,
          output: { generation_output: { platforms: { linkedin: { body_text: "hi" } }, model: "sonnet" } },
        }),
      ],
    });

    const node = findNode(run, null, null, "generation");

    expect(node.status).toBe("DONE");
    expect(node.stats).toEqual(
      expect.arrayContaining([
        { label: "DRAFTS", value: "1" },
        { label: "TOKENS", value: "512" },
        { label: "COST", value: "$0.12" },
      ])
    );
  });

  it("marks a stage QUEUED (not fabricated as running) when it hasn't executed yet", () => {
    const run = makeRun({
      post: {
        id: "post-1",
        calendar_event_id: null,
        current_pipeline_stage: "research",
        body_text: null,
        media: null,
        created_at: "2026-08-20T10:00:00Z",
        updated_at: "2026-08-20T10:00:00Z",
      },
      agent_runs: [],
    });

    const node = findNode(run, null, null, "generation");

    expect(node.status).toBe("QUEUED");
    expect(node.agentRun).toBeNull();
    expect(node.lines).toContain("not run yet");
  });

  it("marks human_review WAITING when the post is durably paused there with no AgentRun yet", () => {
    const run = makeRun({
      post: {
        id: "post-1",
        calendar_event_id: null,
        current_pipeline_stage: "human_review",
        body_text: null,
        media: null,
        created_at: "2026-08-20T10:00:00Z",
        updated_at: "2026-08-20T10:04:00Z",
      },
      agent_runs: [],
    });

    const node = findNode(run, null, null, "human_review");

    expect(node.status).toBe("WAITING");
    expect(node.lines[0]).toMatch(/waiting on a human decision/i);
  });

  it("marks downstream stages SKIPPED when the run was rejected at human_review", () => {
    const run = makeRun({
      post: {
        id: "post-1",
        calendar_event_id: null,
        current_pipeline_stage: "rejected",
        body_text: null,
        media: null,
        created_at: "2026-08-20T10:00:00Z",
        updated_at: "2026-08-20T10:04:00Z",
      },
      agent_runs: [makeAgentRun({ agent_type: "human_review", output: {} })],
      review_feedback: [
        {
          id: "fb-1",
          source: "human",
          score: 0,
          verdict: "reject",
          comments: {},
          created_at: "2026-08-20T10:05:00Z",
        },
      ],
    });

    expect(findNode(run, null, null, "human_review").status).toBe("DONE");
    expect(findNode(run, null, null, "scheduler").status).toBe("SKIPPED");
    expect(findNode(run, null, null, "publisher").status).toBe("SKIPPED");
    expect(findNode(run, null, null, "analytics_collector").status).toBe("SKIPPED");
  });

  it("surfaces the AI reviewer's real score/verdict on the reviewer node", () => {
    const reviewFeedback: ArenaReviewFeedback[] = [
      {
        id: "fb-ai-1",
        source: "ai_reviewer",
        score: 84,
        verdict: "approve",
        comments: { platforms: {}, model: "openrouter/free" },
        created_at: "2026-08-20T10:03:00Z",
      },
    ];
    const run = makeRun({
      post: {
        id: "post-1",
        calendar_event_id: null,
        current_pipeline_stage: "human_review",
        body_text: null,
        media: null,
        created_at: "2026-08-20T10:00:00Z",
        updated_at: "2026-08-20T10:03:00Z",
      },
      agent_runs: [makeAgentRun({ agent_type: "reviewer", cost: 0.05, output: { review_output: {} } })],
      review_feedback: reviewFeedback,
    });

    const node = findNode(run, null, null, "reviewer");

    expect(node.status).toBe("DONE");
    expect(node.lines[0]).toBe("score 84/100 · approve");
  });

  it("renders the campaign-brief context node from the real calendar event", () => {
    const event: CalendarEvent = {
      id: "event-1",
      brand_id: "brand-1",
      title: "DPDP launch carousel",
      description: null,
      target_platforms: ["linkedin", "x"],
      desired_format: "carousel",
      target_datetime: "2026-09-01T12:00:00Z",
      status: "pipeline_running",
      created_at: "2026-08-01T00:00:00Z",
      updated_at: "2026-08-01T00:00:00Z",
    };

    const node = findNode(makeRun(), event, null, "brief");

    expect(node.status).toBe("READ");
    expect(node.lines[0]).toBe("DPDP launch carousel");
    expect(node.stats).toEqual(
      expect.arrayContaining([{ label: "PLATFORMS", value: "2" }, { label: "FORMAT", value: "carousel" }])
    );
  });

  it("shows a clear placeholder for the brief node when there is no calendar event", () => {
    const node = findNode(makeRun(), null, null, "brief");

    expect(node.status).toBe("READ");
    expect(node.lines).toEqual(["No calendar event — ad hoc post"]);
    expect(node.stats).toEqual([]);
  });
});
