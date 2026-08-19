from apps.api.models import IntegrationCall, Organization


def test_integration_call_insert_and_query(db_session) -> None:
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()

    call = IntegrationCall(
        org_id=org.id,
        provider="tavily",
        capability="search",
        latency_ms=124.5,
        success=True,
    )
    db_session.add(call)
    db_session.flush()

    fetched = db_session.get(IntegrationCall, call.id)
    assert fetched is not None
    assert fetched.provider == "tavily"
    assert fetched.success is True
    assert fetched.error_message is None


def test_integration_call_org_id_is_optional(db_session) -> None:
    call = IntegrationCall(
        provider="openrouter", capability="llm", success=False, error_message="timeout"
    )
    db_session.add(call)
    db_session.flush()

    assert call.org_id is None
    assert call.error_message == "timeout"
