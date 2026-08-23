from unittest.mock import MagicMock, patch

from apps.api.models import IntegrationCall
from packages.integrations.embedding.openai_provider import OpenAIEmbeddingProvider


def _mock_response(json_data: dict) -> MagicMock:
    response = MagicMock()
    response.json.return_value = json_data
    response.raise_for_status.return_value = None
    return response


def test_embed_returns_vector() -> None:
    payload = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
    with patch("httpx.post", return_value=_mock_response(payload)) as mock_post:
        vector = OpenAIEmbeddingProvider(api_key="test-key").embed("some text")

    assert vector == [0.1, 0.2, 0.3]
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["json"]["input"] == "some text"
    assert call_kwargs["json"]["model"] == OpenAIEmbeddingProvider.MODEL


def test_embed_logs_integration_call(db_session) -> None:
    payload = {"data": [{"embedding": [0.1]}]}
    with patch("httpx.post", return_value=_mock_response(payload)):
        OpenAIEmbeddingProvider(api_key="test-key").embed("text")

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="openai", capability="embedding")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is True
