from unittest.mock import MagicMock, patch

from apps.api.models import IntegrationCall
from packages.integrations.search.tavily import TavilyProvider


def _mock_response(json_data: dict) -> MagicMock:
    response = MagicMock()
    response.json.return_value = json_data
    response.raise_for_status.return_value = None
    return response


def test_tavily_search_parses_results(db_session) -> None:
    payload = {
        "results": [
            {"title": "Post-launch trends", "url": "https://x.test/a", "content": "..."},
        ]
    }
    with patch("httpx.post", return_value=_mock_response(payload)) as mock_post:
        results = TavilyProvider(api_key="test-key").search("brand launch trends")

    assert len(results) == 1
    assert results[0].title == "Post-launch trends"
    assert results[0].url == "https://x.test/a"
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["json"]["api_key"] == "test-key"
    assert call_kwargs["json"]["query"] == "brand launch trends"


def test_tavily_search_logs_integration_call(db_session) -> None:
    with patch("httpx.post", return_value=_mock_response({"results": []})):
        TavilyProvider(api_key="test-key").search("query")

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="tavily", capability="search")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is True
    assert logged.latency_ms is not None


def test_tavily_search_logs_failure_on_http_error(db_session) -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = Exception("503 Service Unavailable")

    with patch("httpx.post", return_value=mock_response):
        try:
            TavilyProvider(api_key="test-key").search("query")
        except Exception:
            pass

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="tavily", capability="search")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is False
    assert "503" in logged.error_message
