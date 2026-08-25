from unittest.mock import MagicMock, patch

import pytest

from packages.integrations.llm.openai_provider import OpenAIProvider
from packages.integrations.llm.openrouter_provider import OpenRouterProvider


def _mock_completion() -> MagicMock:
    completion = MagicMock()
    completion.model = "anthropic/claude-sonnet-5"
    completion.choices = [MagicMock(message=MagicMock(content="Here's your draft."))]
    completion.usage = MagicMock(prompt_tokens=42, completion_tokens=17)
    return completion


@pytest.mark.parametrize("provider_cls", [OpenRouterProvider, OpenAIProvider])
def test_llm_provider_complete_parses_response(db_session, provider_cls) -> None:
    provider = provider_cls(api_key="test-key")
    with patch.object(
        provider.client.chat.completions, "create", return_value=_mock_completion()
    ) as mock_create:
        result = provider.complete("Write a post about X", model="anthropic/claude-sonnet-5")

    assert result.text == "Here's your draft."
    assert result.input_tokens == 42
    assert result.output_tokens == 17
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["model"] == "anthropic/claude-sonnet-5"
    assert call_kwargs["messages"] == [
        {"role": "user", "content": "Write a post about X"}
    ]
