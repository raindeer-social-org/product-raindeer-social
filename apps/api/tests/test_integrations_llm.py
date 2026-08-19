from unittest.mock import MagicMock, patch

import pytest

from packages.integrations.llm.openai_provider import OpenAIProvider
from packages.integrations.llm.openrouter_provider import OpenRouterProvider


def _mock_completion_response() -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "model": "anthropic/claude-sonnet-5",
        "choices": [{"message": {"content": "Here's your draft."}}],
        "usage": {"prompt_tokens": 42, "completion_tokens": 17},
    }
    return response


@pytest.mark.parametrize("provider_cls", [OpenRouterProvider, OpenAIProvider])
def test_llm_provider_complete_parses_response(db_session, provider_cls) -> None:
    with patch("httpx.post", return_value=_mock_completion_response()) as mock_post:
        result = provider_cls(api_key="test-key").complete(
            "Write a post about X", model="anthropic/claude-sonnet-5"
        )

    assert result.text == "Here's your draft."
    assert result.input_tokens == 42
    assert result.output_tokens == 17
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert call_kwargs["json"]["messages"] == [
        {"role": "user", "content": "Write a post about X"}
    ]
