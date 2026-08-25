"""The seven-stage* per-post pipeline graph (Issue #18).

    Research -> Creative -> Generation -> Reviewer -> [Human Review] ->
    Scheduler -> Publisher -> Analytics Collector

Every node here is a stub — later issues (#19 Research, #20 Creative,
#21 Generation, #24 Reviewer, #25 Human Review, plus the not-yet-filed
Scheduler/Publisher/Analytics Collector issues) replace one node's body at
a time with real logic. This issue's job is the skeleton itself: all
stages wired in order, and the durability guarantee that makes the human
review step safe to build — a paused run's state lives in Postgres (see
checkpointer.py), not in process memory, so it survives a server restart.

The Human Review stage is a genuine LangGraph interrupt (`interrupt()`),
not a status flag polled by a cron job: calling it suspends the graph
mid-node and durably persists everything needed to resume exactly there,
via the checkpointer. Resuming later — even from a freshly started process
with a brand-new checkpointer instance pointed at the same database — replays
up to the interrupt and continues with whatever value the resume provides.

* The issue text calls this a "seven-step" pipeline while listing eight
stage names. Reviewer (#24) and Human Review (#25) are tracked as
separate future issues with distinct real logic, so this graph keeps them
as two distinct nodes rather than forcing a miscount — PIPELINE_STAGES
below is the source of truth for what's actually wired up.
"""

from collections.abc import Iterator
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, Interrupt, interrupt
from sqlalchemy.orm import Session

from apps.api.models.agent_run import AgentRun, AgentType
from apps.api.models.post import PipelineStage, Post

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


def _human_review_node(state: PipelineState) -> dict:
    """The one real (non-stub) piece of behavior in this graph: a durable
    interrupt. Calling interrupt() here pauses graph execution and persists
    everything needed to resume via the checkpointer — the pipeline can sit
    here for hours or days waiting on a human, across process restarts,
    without any polling. Resuming with Command(resume=<decision>) re-enters
    this node, interrupt() returns the decision instead of pausing again,
    and the graph continues on to `scheduler`."""
    decision = interrupt({"stage": "human_review", "post_id": state["post_id"]})
    return _stub_result("human_review", state, human_review_decision=decision)


def build_pipeline_graph(checkpointer) -> CompiledStateGraph:
    """Assembles the pipeline StateGraph and compiles it with the given
    checkpointer. The graph itself is stateless/reusable — it carries no
    reference to any particular Post or DB session, so the same compiled
    graph object could serve every run; callers select a run via the
    per-invocation `thread_id` in the LangGraph config."""
    graph = StateGraph(PipelineState)

    for stage in PIPELINE_STAGES:
        node = _human_review_node if stage == "human_review" else _make_stub_node(stage)
        graph.add_node(stage, node)

    graph.add_edge(START, PIPELINE_STAGES[0])
    for upstream, downstream in zip(PIPELINE_STAGES, PIPELINE_STAGES[1:]):
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
    graph = build_pipeline_graph(checkpointer)
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
            db.add(
                AgentRun(
                    post_id=post.id,
                    agent_type=STAGE_TO_AGENT_TYPE[node_name],
                    input={"post_id": str(post.id)},
                    output=node_output if isinstance(node_output, dict) else None,
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
