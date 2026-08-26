"""Issue #105 — Ved's standing research job.

Adds a standing Celery Beat schedule on top of the existing #29 per-post
pipeline trigger: research now also runs on a fixed interval for every
brand, independent of whether a post happens to be scheduled onto the
calendar, so research stays fresh between calendar slots.

The actual research logic (search-provider calls, brand-context
retrieval, degrade-on-failure behavior) is exercised in
packages/agents/tests/test_research_engine.py against
run_standalone_brand_research directly — same "unit-testable without
Celery machinery" split every other worker.py job already uses (see e.g.
apps/api/tests/test_pipeline_trigger.py for #29, apps/api/tests/
test_weekly_report.py for #35). This file only covers what's specific to
the Celery wiring itself, mirroring test_engagement_polling.py's
"worker.py: Celery task wiring" section:

  1. Settings.research_refresh_interval_hours (an env var, per #105's
     "configurable" acceptance criterion) is what the beat_schedule entry's
     interval is actually built from.
  2. The beat_schedule registers "refresh-brand-research" on that interval.
  3. The sweep task fans out one research_brand_task per brand — every
     Brand row, since this schema has no archived/deleted flag yet (same
     "every brand is active" reasoning generate_weekly_reports_task
     already relies on for #35).
  4. The per-brand task's own db-session/commit/rollback handling works,
     exercised via `.run()` (the task body directly, not `.delay`/`.apply`)
     — same approach test_engagement_polling.py's
     test_poll_post_engagement_task_run_success uses.
"""

import uuid
from unittest.mock import patch

import pytest

from apps.api.config import Settings
from apps.api.models import AgentRun, AgentType, Brand, Organization
from packages.integrations.search.base import SearchResult

SEARCH_PATCH_TARGET = "packages.agents.pipeline.nodes.research_engine.get_search_provider"
EMBED_PATCH_TARGET = "apps.api.services.brand_retrieval.get_embedding_provider"


def _setup_brand(db_session, name: str = "Acme Widgets") -> Brand:
    org = Organization(name=f"{name} Org")
    db_session.add(org)
    db_session.flush()

    brand = Brand(organization_id=org.id, name=name)
    db_session.add(brand)
    db_session.flush()
    return brand


def _fake_embed(text: str) -> list[float]:
    return [0.0] * 1536


# --- Settings: the configurable interval (#105's acceptance criterion) -----


def test_research_refresh_interval_hours_defaults_within_the_4_to_5_hour_band() -> None:
    settings = Settings()
    assert 4.0 <= settings.research_refresh_interval_hours <= 5.0


def test_research_refresh_interval_hours_is_overridable_via_env_var(monkeypatch) -> None:
    monkeypatch.setenv("RESEARCH_REFRESH_INTERVAL_HOURS", "6")
    settings = Settings()
    assert settings.research_refresh_interval_hours == 6.0


# --- worker.py: Celery task wiring -----------------------------------------


def test_beat_schedule_registers_refresh_brand_research() -> None:
    from apps.api import worker

    entry = worker.celery_app.conf.beat_schedule["refresh-brand-research"]
    assert entry["task"] == "worker.refresh_brand_research"
    assert entry["schedule"] == worker.RESEARCH_REFRESH_INTERVAL_SECONDS
    assert entry["schedule"] == pytest.approx(
        worker.settings.research_refresh_interval_hours * 60 * 60
    )


def test_refresh_brand_research_task_fans_out_one_task_per_brand(db_session, monkeypatch) -> None:
    """Same "every brand is active" sweep shape as
    generate_weekly_reports_task — asserted against the actual row count
    at fan-out time (rather than a fixed literal) so this isn't coupled
    to whatever else the test database happens to already contain."""
    from apps.api import worker

    brand_a = _setup_brand(db_session, "Brand A")
    brand_b = _setup_brand(db_session, "Brand B")

    monkeypatch.setattr(worker, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    expected_ids = {str(brand_id) for (brand_id,) in db_session.query(Brand.id).all()}
    assert {str(brand_a.id), str(brand_b.id)} <= expected_ids

    with patch.object(worker, "research_brand_task") as mock_task:
        result = worker.refresh_brand_research_task.run()

    assert result == len(expected_ids)
    called_ids = {call.args[0] for call in mock_task.delay.call_args_list}
    assert called_ids == expected_ids


def test_refresh_brand_research_task_enqueues_nothing_beyond_existing_brands(
    db_session, monkeypatch
) -> None:
    """Without creating any new brand, the sweep still fans out exactly
    one task per brand actually present — never more, never fewer."""
    from apps.api import worker

    monkeypatch.setattr(worker, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    expected_count = db_session.query(Brand.id).count()

    with patch.object(worker, "research_brand_task") as mock_task:
        result = worker.refresh_brand_research_task.run()

    assert result == expected_count
    assert mock_task.delay.call_count == expected_count


def test_research_brand_task_run_success(db_session, monkeypatch) -> None:
    """Runs the task's underlying function body directly (`.run`, not
    `.delay`/`.apply`) so this exercises apps/api/worker.py's own
    db-session/commit handling without needing Celery/Redis machinery —
    same approach test_poll_post_engagement_task_run_success uses."""
    from apps.api import worker

    brand = _setup_brand(db_session)

    monkeypatch.setattr(worker, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    trend_results = [
        SearchResult(title="AI content trends 2026", url="https://x.test/a", content="...")
    ]

    with patch(SEARCH_PATCH_TARGET) as mock_search, patch(EMBED_PATCH_TARGET) as mock_embed:
        mock_search.return_value.search.return_value = trend_results
        mock_embed.return_value.embed.return_value = _fake_embed("query")

        worker.research_brand_task.run(str(brand.id))

    run = (
        db_session.query(AgentRun)
        .filter(AgentRun.agent_type == AgentType.RESEARCH, AgentRun.post_id.is_(None))
        .order_by(AgentRun.created_at.desc())
        .first()
    )
    assert run is not None
    assert run.input == {"brand_id": str(brand.id)}
    assert run.output["research_brief"]["timing_signal"]["trending_topics"] == [
        "AI content trends 2026"
    ]


def test_research_brand_task_rolls_back_when_brand_not_found(db_session, monkeypatch) -> None:
    from apps.api import worker
    from packages.agents.pipeline.nodes.research_engine import ResearchEngineError

    monkeypatch.setattr(worker, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    with pytest.raises(ResearchEngineError):
        worker.research_brand_task.run(str(uuid.uuid4()))
