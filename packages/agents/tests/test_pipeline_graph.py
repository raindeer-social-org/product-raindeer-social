"""Tests for the Issue #18 pipeline skeleton.

Three things matter here, per the issue's acceptance criteria:
  1. All pipeline stages are present and wired in the documented order.
  2. The human_review stage is a *real* LangGraph interrupt — the graph
     actually pauses (no polling), and resuming continues past it.
  3. Checkpoint state survives a simulated process restart: a brand new
     PostgresSaver/connection/compiled-graph, built fresh from nothing but
     the Postgres database, can resume a run exactly where it left off.

These use a real Postgres-backed checkpointer (not an in-memory stand-in)
against this repo's test database, since the load-bearing behavior here —
durable persistence across a restart — is specifically what an in-memory
checkpointer cannot demonstrate.
"""

from sqlalchemy import text

import pytest

from apps.api.config.database import engine
from apps.api.models import AgentRun, Brand, Organization, PipelineStage, Post
from packages.agents.pipeline.checkpointer import get_postgres_checkpointer
from packages.agents.pipeline.graph import (
    PIPELINE_STAGES,
    build_pipeline_graph,
    get_pending_interrupt,
    run_pipeline,
)


def _setup_post(db_session) -> Post:
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()

    brand = Brand(organization_id=org.id, name="Acme Widgets")
    db_session.add(brand)
    db_session.flush()

    post = Post(brand_id=brand.id)
    db_session.add(post)
    db_session.flush()
    return post


@pytest.fixture()
def thread_cleanup():
    """Pipeline checkpoint rows live in Postgres on a connection totally
    separate from db_session's rolled-back transaction, so they need
    explicit teardown — otherwise every test run leaves rows behind."""
    thread_ids: list[str] = []
    yield thread_ids
    if not thread_ids:
        return
    with get_postgres_checkpointer() as checkpointer:
        for thread_id in thread_ids:
            checkpointer.delete_thread(thread_id)


def test_all_pipeline_stages_present_and_wired_in_order() -> None:
    assert PIPELINE_STAGES == (
        "research",
        "creative",
        "generation",
        "reviewer",
        "human_review",
        "scheduler",
        "publisher",
        "analytics_collector",
    )

    with get_postgres_checkpointer() as checkpointer:
        graph = build_pipeline_graph(checkpointer)
        drawable = graph.get_graph()

    node_names = set(drawable.nodes) - {"__start__", "__end__"}
    assert node_names == set(PIPELINE_STAGES)

    edges = {(edge.source, edge.target) for edge in drawable.edges}
    assert ("__start__", PIPELINE_STAGES[0]) in edges
    for upstream, downstream in zip(PIPELINE_STAGES, PIPELINE_STAGES[1:]):
        assert (upstream, downstream) in edges
    assert (PIPELINE_STAGES[-1], "__end__") in edges


def test_human_review_step_is_a_real_interrupt_not_a_polling_loop(
    db_session, thread_cleanup
) -> None:
    post = _setup_post(db_session)
    thread_cleanup.append(str(post.id))

    with get_postgres_checkpointer() as checkpointer:
        updates = list(run_pipeline(db_session, post, checkpointer))

        # The graph actually suspended execution — get_state shows a
        # pending task for human_review rather than the run having
        # finished or raised.
        pending = get_pending_interrupt(checkpointer, post)

    assert pending is not None
    assert pending.value["stage"] == "human_review"

    completed_nodes = [name for update in updates for name in update if name != "__interrupt__"]
    assert completed_nodes == ["research", "creative", "generation", "reviewer"]
    assert any("__interrupt__" in update for update in updates)

    # Nothing downstream of the interrupt ran.
    assert "scheduler" not in completed_nodes
    assert "publisher" not in completed_nodes
    assert "analytics_collector" not in completed_nodes

    db_session.refresh(post)
    assert post.current_pipeline_stage == PipelineStage.HUMAN_REVIEW


def test_checkpoint_rows_are_actually_written_to_postgres(db_session, thread_cleanup) -> None:
    post = _setup_post(db_session)
    thread_cleanup.append(str(post.id))

    with get_postgres_checkpointer() as checkpointer:
        list(run_pipeline(db_session, post, checkpointer))

    with engine.connect() as conn:
        checkpoint_count = conn.execute(
            text("SELECT count(*) FROM checkpoints WHERE thread_id = :tid"),
            {"tid": str(post.id)},
        ).scalar()

    assert checkpoint_count and checkpoint_count > 0


def test_checkpoint_resumes_after_simulated_process_restart(
    db_session, thread_cleanup
) -> None:
    """The important test: a run interrupted by one checkpointer/connection
    can be resumed by a completely separate one built fresh afterward — the
    only thing carried between them is what's durably in Postgres."""
    post = _setup_post(db_session)
    thread_cleanup.append(str(post.id))

    # "Process 1": run until the human_review interrupt, then throw the
    # checkpointer and its connection away entirely.
    with get_postgres_checkpointer() as checkpointer_process_1:
        list(run_pipeline(db_session, post, checkpointer_process_1))

    assert post.current_pipeline_stage == PipelineStage.HUMAN_REVIEW
    logged_before_restart = (
        db_session.query(AgentRun).filter(AgentRun.post_id == post.id).count()
    )
    assert logged_before_restart == 4  # research, creative, generation, reviewer

    # "Process 2": brand-new PostgresSaver instance over a brand-new psycopg
    # connection and a freshly compiled graph — nothing here is shared with
    # process 1 except the Postgres database itself.
    with get_postgres_checkpointer() as checkpointer_process_2:
        resumed_updates = list(
            run_pipeline(db_session, post, checkpointer_process_2, resume="approved")
        )

    resumed_nodes = [
        name for update in resumed_updates for name in update if name != "__interrupt__"
    ]
    assert resumed_nodes == ["human_review", "scheduler", "publisher", "analytics_collector"]

    db_session.refresh(post)
    assert post.current_pipeline_stage == PipelineStage.COMPLETED

    # Every one of the 8 stages ran exactly once across both processes —
    # proof this *resumed* the interrupted run rather than restarting the
    # whole pipeline from scratch.
    all_runs = db_session.query(AgentRun).filter(AgentRun.post_id == post.id).all()
    assert len(all_runs) == 8
    assert sorted(run.agent_type.value for run in all_runs) == sorted(PIPELINE_STAGES)

    # The human_review node's interrupt() call returned the resume value.
    with get_postgres_checkpointer() as checkpointer:
        graph = build_pipeline_graph(checkpointer)
        final_state = graph.get_state({"configurable": {"thread_id": str(post.id)}})
    assert final_state.values["human_review_decision"] == "approved"
    assert final_state.next == ()  # fully finished, nothing pending


def test_post_current_pipeline_stage_tracks_progress_not_just_final_result(
    db_session, thread_cleanup
) -> None:
    """Regression guard for the "at all times" part of the acceptance
    criteria: current_pipeline_stage must move through each stage as the
    graph advances, not jump straight from RESEARCH to whatever's last."""
    post = _setup_post(db_session)
    thread_cleanup.append(str(post.id))
    assert post.current_pipeline_stage == PipelineStage.RESEARCH

    seen_stages = []
    with get_postgres_checkpointer() as checkpointer:
        for update in run_pipeline(db_session, post, checkpointer):
            if "__interrupt__" in update:
                continue
            seen_stages.append(post.current_pipeline_stage)

    assert seen_stages == [
        PipelineStage.RESEARCH,
        PipelineStage.CREATIVE,
        PipelineStage.GENERATION,
        PipelineStage.REVIEWER,
    ]
