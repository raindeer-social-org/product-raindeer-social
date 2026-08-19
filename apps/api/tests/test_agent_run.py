from apps.api.models import AgentRun, AgentType


def test_agent_run_insert_and_query(db_session) -> None:
    run = AgentRun(
        agent_type=AgentType.ONBOARDING,
        input={"brand_name": "Acme Widgets"},
        output={"voice": "playful"},
        model="claude-sonnet-5",
        tokens=1200,
        cost=0.014,
        latency_ms=842.5,
    )
    db_session.add(run)
    db_session.flush()
    db_session.refresh(run)

    fetched = db_session.get(AgentRun, run.id)
    assert fetched is not None
    assert fetched.agent_type == AgentType.ONBOARDING
    assert fetched.input == {"brand_name": "Acme Widgets"}
    assert fetched.output == {"voice": "playful"}
    assert fetched.tokens == 1200
    assert fetched.created_at is not None


def test_agent_run_post_id_is_optional(db_session) -> None:
    run = AgentRun(agent_type=AgentType.RESEARCH, input={})
    db_session.add(run)
    db_session.flush()

    assert run.post_id is None
