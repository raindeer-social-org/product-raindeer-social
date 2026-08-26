"""Tests for the Issue #24 Reviewer Engine node.

Per the issue's acceptance criteria:
  1. A ReviewFeedback row (source=ai_reviewer) is written for every
     generated Post — not just a bare score, but a verdict and specific
     suggested edits alongside it.
  2. Deliberately off-brand content scores low with actionable, specific
     suggestions — not just a low number. This is exercised by comparing
     a mocked "off-brand" LLM review against a mocked "on-brand" one:
     the off-brand response scores lower, its verdict is more severe, and
     its suggested edits name the concrete problem in the draft rather
     than reading as generic filler text.
  3. An AgentRun row is logged with agent_type=reviewer.

Mirrors test_generation_engine.py's structure: most cases exercised
directly against build_reviewer_node() (fast, no checkpointer needed),
with LLMProvider mocked through
packages.agents.pipeline.nodes.reviewer_engine.get_llm_provider — never a
direct vendor SDK call. The AgentRun-logging criterion is exercised
through the real pipeline (run_pipeline + a Postgres-backed
checkpointer), since that's the code that actually writes AgentRun rows.
"""

import json
import uuid
from unittest.mock import patch

import pytest

from apps.api.models import (
    AgentRun,
    AgentType,
    Brand,
    ContentCalendarEvent,
    Organization,
    Post,
    ReviewFeedback,
    ReviewSource,
    ReviewVerdict,
)
from packages.agents.pipeline.checkpointer import get_postgres_checkpointer
from packages.agents.pipeline.graph import run_pipeline
from packages.agents.pipeline.nodes.reviewer_engine import (
    ReviewerEngineError,
    build_reviewer_node,
)
from packages.integrations.llm.base import LLMResponse

LLM_PATCH_TARGET = "packages.agents.pipeline.nodes.reviewer_engine.get_llm_provider"
SEARCH_PATCH_TARGET = "packages.agents.pipeline.nodes.research_engine.get_search_provider"
EMBED_PATCH_TARGET = "apps.api.services.brand_retrieval.get_embedding_provider"
CREATIVE_LLM_PATCH_TARGET = "packages.agents.pipeline.nodes.creative_engine.get_llm_provider"
GENERATION_LLM_PATCH_TARGET = "packages.agents.pipeline.nodes.generation_engine.get_llm_provider"


def _setup_brand(db_session) -> Brand:
    org = Organization(name="Calm & Co")
    db_session.add(org)
    db_session.flush()

    brand = Brand(
        organization_id=org.id,
        name="Calm & Co",
        industry="Wellness",
        target_audience="Stressed professionals seeking quiet, evidence-based self-care.",
        tone_descriptors=["calm", "minimalist", "trustworthy", "never hype-driven"],
    )
    db_session.add(brand)
    db_session.flush()
    return brand


def _setup_post(db_session, brand: Brand | None = None, body_text: dict | None = None) -> Post:
    if brand is None:
        brand = _setup_brand(db_session)
    post = Post(brand_id=brand.id, body_text=body_text)
    db_session.add(post)
    db_session.flush()
    return post


def _llm_response(payload: dict) -> LLMResponse:
    return LLMResponse(
        text=json.dumps(payload),
        model="openrouter/free",
        input_tokens=150,
        output_tokens=90,
    )


def _run_node(db_session, post: Post, completed_stages: list[str] | None = None) -> dict:
    """Runs the reviewer node directly, with the embedding provider always
    mocked — the node always calls #16's brand-context retrieval helper
    (via get_relevant_brand_context), which goes through
    get_embedding_provider() regardless of what the LLMProvider mock in
    any given test does, same convention test_research_engine.py uses for
    every one of its node-level tests."""
    node = build_reviewer_node(db_session)
    with patch(EMBED_PATCH_TARGET) as mock_embed:
        mock_embed.return_value.embed.return_value = [0.0] * 1536
        return node(
            {
                "post_id": str(post.id),
                "completed_stages": completed_stages if completed_stages is not None else [],
            }
        )


OFF_BRAND_BODY_TEXT = {
    "linkedin": "BUY NOW!!! LIMITED TIME OFFER!!! Our supplement CURES ANXIETY INSTANTLY, guaranteed or your money back!!! Act fast before it's gone!!!",
}

ON_BRAND_BODY_TEXT = {
    "linkedin": "A quieter way to start your morning: five minutes, no screens, just breath. Small, evidence-backed habits for a calmer day.",
}


def _off_brand_review_payload() -> dict:
    return {
        "platforms": {
            "linkedin": {
                "score": 8,
                "verdict": "reject",
                "issues": [
                    "Uses aggressive, hype-driven sales language ('BUY NOW!!!', 'LIMITED TIME OFFER!!!', 'Act fast') that directly contradicts the brand's calm, minimalist, never-hype-driven tone descriptors.",
                    "Makes an unsubstantiated medical claim ('CURES ANXIETY INSTANTLY') about a supplement — a compliance/regulatory red flag with no evidence cited.",
                    "Excessive exclamation points and all-caps read as spammy, not trustworthy, undermining the brand's trustworthy positioning.",
                ],
                "suggested_edits": (
                    "Remove 'CURES ANXIETY INSTANTLY' entirely — this is an "
                    "unsubstantiated health claim; if any efficacy claim is "
                    "kept it must cite supporting evidence and avoid the word "
                    "'cures'. Replace 'BUY NOW!!! LIMITED TIME OFFER!!!' with "
                    "a calm, benefit-led line consistent with the brand's "
                    "minimalist voice, e.g. 'A quieter way to support your "
                    "calm, five minutes a day.' Drop the exclamation points "
                    "and all-caps throughout."
                ),
            }
        }
    }


def _on_brand_review_payload() -> dict:
    return {
        "platforms": {
            "linkedin": {
                "score": 94,
                "verdict": "approve",
                "issues": [],
                "suggested_edits": "No changes needed — tone, claims, and length all match brand voice and LinkedIn norms.",
            }
        }
    }


@pytest.fixture()
def thread_cleanup():
    """Same teardown as test_pipeline_graph.py's fixture — pipeline
    checkpoint rows live in Postgres on a connection separate from
    db_session's rolled-back transaction, so they need explicit cleanup."""
    thread_ids: list[str] = []
    yield thread_ids
    if not thread_ids:
        return
    with get_postgres_checkpointer() as checkpointer:
        for thread_id in thread_ids:
            checkpointer.delete_thread(thread_id)


# --- LLMProvider used exclusively, never a direct SDK/httpx call -----------


def test_reviewer_engine_calls_llm_provider_only_through_interface(db_session) -> None:
    post = _setup_post(db_session, body_text=ON_BRAND_BODY_TEXT)

    with patch(LLM_PATCH_TARGET) as mock_llm, patch("httpx.post") as mock_httpx_post:
        mock_llm.return_value.complete.return_value = _llm_response(_on_brand_review_payload())
        _run_node(db_session, post)

    mock_llm.return_value.complete.assert_called_once()
    mock_httpx_post.assert_not_called()


def test_reviewer_engine_reads_model_from_settings_not_hardcoded(db_session) -> None:
    post = _setup_post(db_session, body_text=ON_BRAND_BODY_TEXT)

    with (
        patch(LLM_PATCH_TARGET) as mock_llm,
        patch("packages.agents.pipeline.nodes.reviewer_engine.get_settings") as mock_settings,
    ):
        mock_settings.return_value.llm_default_model = "some/custom-model"
        mock_llm.return_value.complete.return_value = _llm_response(_on_brand_review_payload())
        _run_node(db_session, post)

    _, kwargs = mock_llm.return_value.complete.call_args
    assert kwargs["model"] == "some/custom-model"


# --- ReviewFeedback row written, source=ai_reviewer -------------------------


def test_reviewer_writes_review_feedback_row_with_source_ai_reviewer(db_session) -> None:
    post = _setup_post(db_session, body_text=ON_BRAND_BODY_TEXT)

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = _llm_response(_on_brand_review_payload())
        result = _run_node(db_session, post)

    rows = db_session.query(ReviewFeedback).filter(ReviewFeedback.post_id == post.id).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.source == ReviewSource.AI_REVIEWER
    assert row.score == 94.0
    assert row.verdict == ReviewVerdict.APPROVE
    assert "linkedin" in row.comments["platforms"]
    assert row.comments["platforms"]["linkedin"]["suggested_edits"]

    assert result["review_output"]["review_feedback_id"] == str(row.id)
    assert result["review_output"]["score"] == 94.0
    assert result["review_output"]["verdict"] == "approve"


def test_second_review_pass_appends_a_new_row_instead_of_overwriting(db_session) -> None:
    post = _setup_post(db_session, body_text=ON_BRAND_BODY_TEXT)

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = _llm_response(_on_brand_review_payload())
        _run_node(db_session, post)

        mock_llm.return_value.complete.return_value = _llm_response(_off_brand_review_payload())
        _run_node(db_session, post)

    rows = (
        db_session.query(ReviewFeedback)
        .filter(ReviewFeedback.post_id == post.id)
        .order_by(ReviewFeedback.created_at.asc())
        .all()
    )
    assert len(rows) == 2
    assert rows[0].verdict == ReviewVerdict.APPROVE
    assert rows[1].verdict == ReviewVerdict.REJECT


# --- off-brand content scores low with actionable, specific suggestions ----


def test_off_brand_draft_scores_lower_than_on_brand_draft_with_specific_suggestions(
    db_session,
) -> None:
    """The core acceptance criterion: a deliberately off-brand draft must
    score low, with actionable, specific suggestions — not just a low
    number. Verified by comparing two reviews of the same brand against
    genuinely different drafts (one hype-y/unsubstantiated, one on-brand)
    and asserting the off-brand one is scored/verdicted worse *and* its
    suggestions name the concrete problem, rather than generic filler."""
    brand = _setup_brand(db_session)

    off_brand_post = _setup_post(db_session, brand=brand, body_text=OFF_BRAND_BODY_TEXT)
    on_brand_post = _setup_post(db_session, brand=brand, body_text=ON_BRAND_BODY_TEXT)

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = _llm_response(_off_brand_review_payload())
        off_brand_result = _run_node(db_session, off_brand_post)

        mock_llm.return_value.complete.return_value = _llm_response(_on_brand_review_payload())
        on_brand_result = _run_node(db_session, on_brand_post)

    off_brand_output = off_brand_result["review_output"]
    on_brand_output = on_brand_result["review_output"]

    # Low score, correlated with the genuinely off-brand input.
    assert off_brand_output["score"] < 30
    assert off_brand_output["score"] < on_brand_output["score"]
    assert off_brand_output["verdict"] == "reject"
    assert on_brand_output["verdict"] == "approve"

    # Suggestions are specific and actionable, not just a number and not
    # generic boilerplate — they must name the actual problems with THIS
    # draft (the hype language and the unsubstantiated health claim).
    suggested_edits = off_brand_output["platforms"]["linkedin"]["suggested_edits"]
    assert len(suggested_edits) > 60
    assert "BUY NOW" in suggested_edits or "CURES ANXIETY" in suggested_edits.upper()

    issues = off_brand_output["platforms"]["linkedin"]["issues"]
    assert any("claim" in issue.lower() or "hype" in issue.lower() or "tone" in issue.lower() for issue in issues)
    generic_placeholders = {"needs improvement", "content needs work", "please revise"}
    assert not any(issue.strip().lower() in generic_placeholders for issue in issues)

    # Also persisted onto the ReviewFeedback row itself, not just the
    # in-memory node output.
    db_session.refresh(off_brand_post)
    row = (
        db_session.query(ReviewFeedback)
        .filter(ReviewFeedback.post_id == off_brand_post.id)
        .one()
    )
    assert row.score < 30
    assert row.verdict == ReviewVerdict.REJECT
    assert "BUY NOW" in row.comments["platforms"]["linkedin"]["suggested_edits"]


# --- overall aggregation: worst platform sets the overall score/verdict ----


def test_worst_scoring_platform_sets_the_overall_score_and_verdict(db_session) -> None:
    post = _setup_post(
        db_session,
        body_text={"linkedin": "on-brand copy", "x": "off-brand hype copy"},
    )

    payload = {
        "platforms": {
            "linkedin": {
                "score": 90,
                "verdict": "approve",
                "issues": [],
                "suggested_edits": "No changes needed.",
            },
            "x": {
                "score": 20,
                "verdict": "reject",
                "issues": ["Uses hype language inconsistent with brand voice."],
                "suggested_edits": "Rewrite without exclamation points or superlatives; match the calm brand tone.",
            },
        }
    }

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = _llm_response(payload)
        result = _run_node(db_session, post)

    output = result["review_output"]
    assert output["score"] == 20
    assert output["verdict"] == "reject"


# --- degrade-on-failure ------------------------------------------------


def test_reviewer_falls_back_to_manual_review_verdict_on_llm_failure(db_session) -> None:
    post = _setup_post(db_session, body_text=ON_BRAND_BODY_TEXT)

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.side_effect = Exception("LLM provider unreachable")
        result = _run_node(db_session, post)

    output = result["review_output"]
    # Fallback must not silently approve a draft it couldn't actually
    # evaluate — it must flag for manual review instead.
    assert output["verdict"] == "revise"
    assert output["score"] == 50.0

    db_session.refresh(post)
    rows = db_session.query(ReviewFeedback).filter(ReviewFeedback.post_id == post.id).all()
    assert len(rows) == 1
    assert rows[0].verdict == ReviewVerdict.REVISE


def test_reviewer_degrades_gracefully_on_unparseable_llm_output(db_session) -> None:
    post = _setup_post(db_session, body_text=ON_BRAND_BODY_TEXT)

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = LLMResponse(
            text="not valid json at all",
            model="openrouter/free",
            input_tokens=1,
            output_tokens=1,
        )
        result = _run_node(db_session, post)

    output = result["review_output"]
    assert output["verdict"] == "revise"
    assert "linkedin" in output["platforms"]


def test_reviewer_degrades_gracefully_when_llm_omits_required_fields(db_session) -> None:
    post = _setup_post(db_session, body_text=ON_BRAND_BODY_TEXT)

    with patch(LLM_PATCH_TARGET) as mock_llm:
        # Missing "suggested_edits" — should fall back rather than crash.
        mock_llm.return_value.complete.return_value = _llm_response(
            {"platforms": {"linkedin": {"score": 70, "verdict": "revise", "issues": ["vague"]}}}
        )
        result = _run_node(db_session, post)

    output = result["review_output"]
    assert output["verdict"] == "revise"
    assert output["score"] == 50.0


# --- error handling -----------------------------------------------------


def test_build_reviewer_node_requires_a_db_session_to_actually_run() -> None:
    node = build_reviewer_node(None)
    with pytest.raises(RuntimeError):
        node({"post_id": "irrelevant", "completed_stages": []})


def test_reviewer_node_raises_when_post_not_found(db_session) -> None:
    node = build_reviewer_node(db_session)
    with pytest.raises(ReviewerEngineError):
        node({"post_id": str(uuid.uuid4()), "completed_stages": []})


# --- completed_stages bookkeeping (same shape as the other node stubs) -----


def test_reviewer_node_appends_to_completed_stages(db_session) -> None:
    post = _setup_post(db_session, body_text=ON_BRAND_BODY_TEXT)

    with patch(LLM_PATCH_TARGET) as mock_llm:
        mock_llm.return_value.complete.return_value = _llm_response(_on_brand_review_payload())
        result = _run_node(db_session, post, completed_stages=["research", "creative", "generation"])

    assert result["completed_stages"] == ["research", "creative", "generation", "reviewer"]


# --- AgentRun logged with agent_type=reviewer -------------------------------


def test_pipeline_logs_agent_run_with_agent_type_reviewer_and_writes_review_feedback(
    db_session, thread_cleanup
) -> None:
    from datetime import datetime, timezone

    post = _setup_post(db_session)
    # Issues #108/#109/#110 grew SUPPORTED_PLATFORMS beyond ("linkedin",
    # "x") — pin target_platforms explicitly via a calendar event so
    # Research/Creative Engine's "no calendar event" -> "all
    # SUPPORTED_PLATFORMS" fallback doesn't pull in platforms this test's
    # LLM mocks below don't cover.
    event = ContentCalendarEvent(
        brand_id=post.brand_id,
        title="Test event",
        target_platforms=["linkedin", "x"],
        desired_format="text_post",
        target_datetime=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    db_session.add(event)
    db_session.flush()
    post.calendar_event_id = event.id
    db_session.flush()
    thread_cleanup.append(str(post.id))

    creative_brief_payload = {
        "linkedin": {
            "format": "text_post",
            "angle": "thought_leadership",
            "hook": "A calm approach to a stressful topic.",
            "cta": "Learn more.",
            "tone": "calm, trustworthy",
        },
        "x": {
            "format": "short_thread",
            "angle": "practical_tip",
            "hook": "One small habit.",
            "cta": "Try it today.",
            "tone": "calm, concise",
        },
    }
    generated_copy_payload = {
        "linkedin": "A calm approach to a stressful topic. Learn more.",
        "x": "One small habit. Try it today.",
    }
    review_payload = {
        "platforms": {
            "linkedin": {
                "score": 88,
                "verdict": "approve",
                "issues": [],
                "suggested_edits": "No changes needed.",
            },
            "x": {
                "score": 85,
                "verdict": "approve",
                "issues": [],
                "suggested_edits": "No changes needed.",
            },
        }
    }

    with (
        patch(SEARCH_PATCH_TARGET) as mock_search,
        patch(EMBED_PATCH_TARGET) as mock_embed,
        patch(CREATIVE_LLM_PATCH_TARGET) as mock_creative_llm,
        patch(GENERATION_LLM_PATCH_TARGET) as mock_generation_llm,
        patch(LLM_PATCH_TARGET) as mock_reviewer_llm,
    ):
        mock_search.return_value.search.return_value = []
        mock_embed.return_value.embed.return_value = [0.0] * 1536
        mock_creative_llm.return_value.complete.return_value = _llm_response(creative_brief_payload)
        mock_generation_llm.return_value.complete.return_value = _llm_response(generated_copy_payload)
        mock_reviewer_llm.return_value.complete.return_value = _llm_response(review_payload)

        with get_postgres_checkpointer() as checkpointer:
            list(run_pipeline(db_session, post, checkpointer))

    run = (
        db_session.query(AgentRun)
        .filter(AgentRun.post_id == post.id, AgentRun.agent_type == AgentType.REVIEWER)
        .order_by(AgentRun.created_at.desc())
        .first()
    )
    assert run is not None
    assert run.output is not None
    assert run.output["review_output"]["verdict"] == "approve"

    db_session.refresh(post)
    feedback_rows = (
        db_session.query(ReviewFeedback).filter(ReviewFeedback.post_id == post.id).all()
    )
    assert len(feedback_rows) == 1
    assert feedback_rows[0].source == ReviewSource.AI_REVIEWER
    assert feedback_rows[0].score == 85.0
    assert feedback_rows[0].verdict == ReviewVerdict.APPROVE
