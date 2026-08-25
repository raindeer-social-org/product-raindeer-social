"""The seven-stage* per-post pipeline graph (Issue #18).

    Research -> Creative -> Generation -> Reviewer -> [Human Review] ->
    Scheduler -> Publisher -> Analytics Collector

Every node here started as a stub — later issues (#19 Research, #20
Creative, #21 Generation, #24 Reviewer, #25 Human Review, #31 Publisher,
plus the not-yet-filed Scheduler/Analytics Collector issues) replace one
node's body at a time with real logic. #18's job was the skeleton itself:
all stages wired in order, and the durability guarantee that makes the
human review step safe to build — a paused run's state lives in Postgres
(see checkpointer.py), not in process memory, so it survives a server
restart. #19 is the first of those real-logic swaps: "research" now runs
packages/agents/pipeline/nodes/research_engine.py instead of a stub. #20,
#21, and #24 followed the same pattern for "creative"
(nodes/creative_engine.py), "generation" (nodes/generation_engine.py),
and "reviewer" (nodes/reviewer_engine.py). #31 followed it again for
"publisher" — see _publisher_node below — though that one stays a
one-line handoff to apps/api/services/publish_queue.py rather than
gaining its own nodes/ module, since the actual publish logic needs no
LangGraph-specific state, just a post_id.

The Human Review stage is a genuine LangGraph interrupt (`interrupt()`),
not a status flag polled by a cron job: calling it suspends the graph
mid-node and durably persists everything needed to resume exactly there,
via the checkpointer. Resuming later — even from a freshly started process
with a brand-new checkpointer instance pointed at the same database — replays
up to the interrupt and continues with whatever value the resume provides.

* The issue text calls this a "seven-step" pipeline while listing eight
stage names. Reviewer (#24) and Human Review (#25) were tracked as
separate issues with distinct real logic, so this graph keeps them as two
distinct nodes rather than forcing a miscount — PIPELINE_STAGES below is
the source of truth for what's actually wired up.
"""

import uuid
from collections.abc import Iterator
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, Interrupt, interrupt
from sqlalchemy.orm import Session

from apps.api.models.agent_run import AgentRun, AgentType
from apps.api.models.post import PipelineStage, Post
from apps.api.services.publish_queue import enqueue_publish
from packages.agents.pipeline.nodes.creative_engine import build_creative_node
from packages.agents.pipeline.nodes.generation_engine import build_generation_node
from packages.agents.pipeline.nodes.research_engine import build_research_node
from packages.agents.pipeline.nodes.reviewer_engine import build_reviewer_node

# Pipeline order — the single source of truth for both graph wiring and the
# tests that assert nodes are "present and wired in order".
PIPELINE_STAGES: tuple[str, ...] = (
    "research",
    "creative",
    "generation",
    "reviewer",
    "human_review",
    "scheduler",
    "publisher",
    "analytics_collector",
)

STAGE_TO_PIPELINE_STAGE: dict[str, PipelineStage] = {
    "research": PipelineStage.RESEARCH,
    "creative": PipelineStage.CREATIVE,
    "generation": PipelineStage.GENERATION,
    "reviewer": PipelineStage.REVIEWER,
    "human_review": PipelineStage.HUMAN_REVIEW,
    "scheduler": PipelineStage.SCHEDULER,
    "publisher": PipelineStage.PUBLISHER,
    "analytics_collector": PipelineStage.ANALYTICS_COLLECTOR,
}

STAGE_TO_AGENT_TYPE: dict[str, AgentType] = {
    "research": AgentType.RESEARCH,
    "creative": AgentType.CREATIVE,
    "generation": AgentType.GENERATION,
    "reviewer": AgentType.REVIEWER,
    "human_review": AgentType.HUMAN_REVIEW,
    "scheduler": AgentType.SCHEDULER,
    "publisher": AgentType.PUBLISHER,
    "analytics_collector": AgentType.ANALYTICS_COLLECTOR,
}


class PipelineState(TypedDict):
    post_id: str
    completed_stages: list[str]
    # Populated once the human_review node's interrupt() is resumed.
    human_review_decision: Any
    # Populated by the research node (#19) — the structured research brief
    # #20 (Creative Engine) consumes, including a timing_signal field #28
    # (auto-scheduling) will eventually use. LangGraph drops any state key
    # not declared here, so this must be listed even though it's only
    # ever set by one stage.
    research_brief: dict[str, Any] | None
    # Populated by the creative node (#20) — the structured creative brief
    # (format/angle/hook/CTA per target platform) #21 (Generation Engine)
    # consumes to actually write copy.
    creative_brief: dict[str, Any] | None
    # Populated by the generation node (#21) — the generated copy per
    # platform (written onto Post.body_text), plus model/tokens/cost/
    # latency_ms metadata that run_pipeline below reads onto this stage's
    # AgentRun row. LangGraph drops any state key not declared here (see
    # research_brief's comment above), so this must be listed even though
    # it's only ever set by this one stage.
    generation_output: dict[str, Any] | None
    # Populated by the reviewer node (#24) — the automated brand-voice/
    # compliance/platform-fit review of Post.body_text: an overall score/
    # verdict plus a per-platform breakdown (score/verdict/issues/
    # suggested_edits), the same info persisted onto the ReviewFeedback
    # row that stage writes (apps/api/models/review_feedback.py,
    # source=ai_reviewer). LangGraph drops any state key not declared
    # here (see research_brief's comment above), so this must be listed
    # even though it's only ever set by this one stage.
    review_output: dict[str, Any] | None


def _stub_result(stage: str, state: PipelineState, **extra: Any) -> dict:
    """Common return shape for every stub node: append this stage to the
    run's history so both tests and the pipeline runner can see it ran."""
    return {
        "completed_stages": [*state.get("completed_stages", []), stage],
        **extra,
    }


def _make_stub_node(stage: str):
    """Builds a plain stub node function for a pipeline stage that has no
    real logic yet — it just records that it ran. Later issues replace
    these one at a time with the real Research/Creative/Generation/etc.
    agents; the graph wiring and node name stay the same."""

    def _node(state: PipelineState) -> dict:
        return _stub_result(stage, state)

    _node.__name__ = f"{stage}_node"
    return _node


def _publisher_node(state: PipelineState) -> dict:
    """Issue #31 — the first real (non-stub) version of the `publisher`
    stage. Its only job is to hand the post off to the durable,
    Redis-backed publish queue (apps/api/services/publish_queue.py /
    apps/api/worker.py) — the actual SocialPublisher calls, and their
    retry-with-backoff, happen out-of-band in the Celery worker, not
    synchronously inside this graph node. That keeps this stage cheap
    (so a human's approve request — apps/api/routers/review.py, which
    resumes the graph synchronously through this node and on to
    COMPLETED — doesn't block on a live network call to LinkedIn/X) while
    still guaranteeing every post that reaches `publisher` genuinely gets
    enqueued, not silently dropped the way the old stub left it."""
    enqueue_publish(uuid.UUID(state["post_id"]))
    return _stub_result("publisher", state)


def _human_review_node(state: PipelineState) -> dict:
    """The one real (non-stub) piece of behavior in this graph: a durable
    interrupt. Calling interrupt() here pauses graph execution and persists
    everything needed to resume via the checkpointer — the pipeline can sit
    here for hours or days waiting on a human, across process restarts,
    without any polling. Resuming with Command(resume=<decision>) re-enters
    this node, interrupt() returns the decision instead of pausing again,
    and the graph continues on to `scheduler` (or halts at END — see
    _route_after_human_review below) depending on that decision."""
    decision = interrupt({"stage": "human_review", "post_id": state["post_id"]})
    return _stub_result("human_review", state, human_review_decision=decision)


def _decision_action(decision: Any) -> str | None:
    """Normalizes a resumed human_review_decision down to its action
    string. Accepts either a bare string (e.g. "approved" — the shape
    test_pipeline_graph.py's pre-#25 tests already resume with) or a dict
    with a "decision" key (the shape apps/api/routers/review.py sends,
    e.g. {"decision": "rejected", "comments": "..."}), so #25's API can
    carry richer payloads without breaking the simpler existing callers."""
    if isinstance(decision, dict):
        decision = decision.get("decision")
    if isinstance(decision, str):
        return decision.lower()
    return None


def _route_after_human_review(state: PipelineState) -> str:
    """Issue #25's actual resume-or-halt mechanism: a human's "rejected"
    decision must not let the run reach `scheduler`/`publisher` — every
    other decision (e.g. "approved") proceeds through the rest of the
    pipeline as before. This is the only conditional edge in the graph;
    every other stage is an unconditional straight line."""
    if _decision_action(state.get("human_review_decision")) == "rejected":
        return END
    return "scheduler"


def build_pipeline_graph(checkpointer, db: Session | None = None) -> CompiledStateGraph:
    """Assembles the pipeline StateGraph and compiles it with the given
    checkpointer. The graph itself is otherwise stateless/reusable — it
    carries no reference to any particular Post, so the same compiled
    graph object could serve every run; callers select a run via the
    per-invocation `thread_id` in the LangGraph config.

    `db` is the one exception: the "research" (#19), "creative" (#20),
    "generation" (#21), and "reviewer" (#24) stages are the first nodes
    with real logic that need a database session (to resolve Post ->
    Brand, and, for generation, to write Post.body_text/PostVersion, and
    for reviewer, to write ReviewFeedback), so it's threaded through here
    to those nodes' factories. It's optional and defaults to None so
    callers that only want to inspect the compiled graph's structure —
    never stream/invoke it — can keep calling this with just a
    checkpointer, same as before #19."""
    graph = StateGraph(PipelineState)

    for stage in PIPELINE_STAGES:
        if stage == "human_review":
            node = _human_review_node
        elif stage == "research":
            node = build_research_node(db)
        elif stage == "creative":
            node = build_creative_node(db)
        elif stage == "generation":
            node = build_generation_node(db)
        elif stage == "reviewer":
            node = build_reviewer_node(db)
        elif stage == "publisher":
            node = _publisher_node
        else:
            node = _make_stub_node(stage)
        graph.add_node(stage, node)

    graph.add_edge(START, PIPELINE_STAGES[0])
    for upstream, downstream in zip(PIPELINE_STAGES, PIPELINE_STAGES[1:]):
        if upstream == "human_review":
            # The one conditional edge in the graph — see
            # _route_after_human_review's docstring. Every other stage is
            # an unconditional straight line, same as before #25.
            graph.add_conditional_edges(
                "human_review", _route_after_human_review, {"scheduler": "scheduler", END: END}
            )
        else:
            graph.add_edge(upstream, downstream)
    graph.add_edge(PIPELINE_STAGES[-1], END)

    return graph.compile(checkpointer=checkpointer)


def _thread_config(post: Post) -> dict:
    return {"configurable": {"thread_id": str(post.id)}}


def run_pipeline(
    db: Session,
    post: Post,
    checkpointer,
    *,
    resume: Any = None,
) -> Iterator[dict]:
    """Advances `post` through the pipeline graph until it either finishes
    or hits the human_review interrupt, updating Post.current_pipeline_stage
    (and logging an AgentRun row) after every node that actually completes —
    not just once at the end — so the column always reflects the graph's
    real position, including for a run that's paused mid-pipeline.

    Pass `resume=<value>` to continue a previously interrupted run (e.g. a
    human's approve/reject decision) instead of starting a new one.

    Yields each node's raw update dict as it completes, in case a caller
    wants to observe progress; most callers can just ignore the return
    value and inspect `post.current_pipeline_stage` afterwards.
    """
    graph = build_pipeline_graph(checkpointer, db=db)
    config = _thread_config(post)

    if resume is not None:
        graph_input: Any = Command(resume=resume)
    else:
        graph_input = {"post_id": str(post.id), "completed_stages": []}

    for update in graph.stream(graph_input, config=config, stream_mode="updates"):
        for node_name, node_output in update.items():
            if node_name == "__interrupt__":
                # Nothing to persist for the interrupt marker itself — the
                # node that raised it hasn't completed (that's the whole
                # point of interrupt()), so there's no AgentRun to log yet.
                # current_pipeline_stage for this case is set below, after
                # the loop, from the checkpointer's own notion of what's
                # pending — the authoritative source, not this marker.
                continue

            stage = STAGE_TO_PIPELINE_STAGE[node_name]
            post.current_pipeline_stage = stage

            # Every stage gets exactly one AgentRun row here, from
            # whatever dict the node returned — this is the single
            # AgentRun-logging path for the whole pipeline (see
            # test_pipeline_graph.py's exact per-stage row-count
            # assertions). Most stages' output dicts carry no model/
            # tokens/cost info, so those columns stay None for them, same
            # as before #21. The generation node (#21) is the first to
            # populate them — via a "generation_output" entry with
            # model/tokens/cost/latency_ms keys — because it's the first
            # stage whose LLM usage this repo tracks a cost for.
            run_metadata: dict[str, Any] = {}
            if isinstance(node_output, dict):
                candidate = node_output.get("generation_output")
                if isinstance(candidate, dict):
                    run_metadata = candidate

            db.add(
                AgentRun(
                    post_id=post.id,
                    agent_type=STAGE_TO_AGENT_TYPE[node_name],
                    input={"post_id": str(post.id)},
                    output=node_output if isinstance(node_output, dict) else None,
                    model=run_metadata.get("model"),
                    tokens=run_metadata.get("tokens"),
                    cost=run_metadata.get("cost"),
                    latency_ms=run_metadata.get("latency_ms"),
                )
            )
            db.flush()

        yield update

    # Sync current_pipeline_stage to the checkpointer's authoritative view
    # of where the run actually stands now — not just the last node that
    # finished. A run paused at human_review has *not* completed that node
    # (interrupt() suspended it mid-execution), but the post is very much
    # "at" human_review from a caller's perspective — that's the stage a
    # UI should show as pending, not the "reviewer" stage that already
    # finished and handed off to it.
    state = graph.get_state(config)
    if state.next:
        post.current_pipeline_stage = STAGE_TO_PIPELINE_STAGE[state.next[0]]
    elif _decision_action(state.values.get("human_review_decision")) == "rejected":
        # Reached END via _route_after_human_review's reject branch, not
        # by running the full pipeline to Analytics Collector — COMPLETED
        # would misleadingly imply the post was actually published.
        post.current_pipeline_stage = PipelineStage.REJECTED
    else:
        post.current_pipeline_stage = PipelineStage.COMPLETED
    db.flush()
    db.refresh(post)


def get_pending_interrupt(checkpointer, post: Post) -> Interrupt | None:
    """Returns the pending Interrupt for this post's run, if it's currently
    paused at one (e.g. waiting on human review), else None. Useful for a
    caller that wants to show the human reviewer what's being asked without
    re-running the graph."""
    graph = build_pipeline_graph(checkpointer)
    state = graph.get_state(_thread_config(post))
    return state.interrupts[0] if state.interrupts else None
