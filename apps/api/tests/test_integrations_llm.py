from unittest.mock import MagicMock, patch

import pytest
from openai import RateLimitError

from packages.integrations.llm.openai_provider import OpenAIProvider
from packages.integrations.llm.openrouter_provider import OpenRouterProvider


def _mock_completion() -> MagicMock:
    completion = MagicMock()
    completion.model = "anthropic/claude-sonnet-5"
    completion.choices = [MagicMock(message=MagicMock(content="Here's your draft."))]
    completion.usage = MagicMock(prompt_tokens=42, completion_tokens=17)
    return completion


def _rate_limit_error() -> RateLimitError:
    response = MagicMock()
    response.status_code = 429
    response.headers = {}
    return RateLimitError("rate limited", response=response, body=None)


def test_openai_provider_complete_parses_response(db_session) -> None:
    provider = OpenAIProvider(api_key="test-key")
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


def test_openrouter_provider_complete_parses_response(db_session) -> None:
    # A pool of one key is the single-key-setup case — same shape as
    # before this provider supported rotating across several.
    provider = OpenRouterProvider(api_keys=["test-key"])
    with patch("packages.integrations.llm.openrouter_provider.OpenAI") as mock_openai_cls:
        mock_openai_cls.return_value.chat.completions.create.return_value = _mock_completion()
        result = provider.complete("Write a post about X", model="anthropic/claude-sonnet-5")

    assert result.text == "Here's your draft."
    assert result.input_tokens == 42
    assert result.output_tokens == 17
    mock_openai_cls.assert_called_once_with(
        api_key="test-key", base_url=OpenRouterProvider.BASE_URL, timeout=provider._timeout
    )
    call_kwargs = mock_openai_cls.return_value.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "anthropic/claude-sonnet-5"
    assert call_kwargs["messages"] == [
        {"role": "user", "content": "Write a post about X"}
    ]


def test_openrouter_provider_falls_back_to_placeholder_key_when_pool_empty(db_session) -> None:
    provider = OpenRouterProvider(api_keys=[])
    assert provider._keys == ["unconfigured"]


def test_openrouter_provider_retries_a_different_key_on_rate_limit(db_session) -> None:
    """The whole point of a key pool: one key hitting OpenRouter's daily
    free-tier cap (a 429) shouldn't fail the call outright — retry against
    another key in the pool before giving up. complete() tries keys in a
    randomized order (see its own docstring), so this pins that order via
    random.sample to make which key fails first deterministic — otherwise
    this test would be flaky: whenever key-b happened to be tried first,
    it would succeed immediately and key-a's retry path would never
    actually run."""
    provider = OpenRouterProvider(api_keys=["key-a", "key-b"])

    calls: list[str] = []

    def fake_openai(api_key: str, **kwargs: object) -> MagicMock:
        calls.append(api_key)
        client = MagicMock()
        if api_key == "key-a":
            client.chat.completions.create.side_effect = _rate_limit_error()
        else:
            client.chat.completions.create.return_value = _mock_completion()
        return client

    with (
        patch("packages.integrations.llm.openrouter_provider.OpenAI", side_effect=fake_openai),
        patch("packages.integrations.llm.openrouter_provider.random.sample", return_value=["key-a", "key-b"]),
    ):
        result = provider.complete("Write a post about X", model="anthropic/claude-sonnet-5")

    assert result.text == "Here's your draft."
    assert calls == ["key-a", "key-b"]


def test_openrouter_provider_raises_when_every_key_is_rate_limited(db_session) -> None:
    provider = OpenRouterProvider(api_keys=["key-a", "key-b"])

    def fake_openai(api_key: str, **kwargs: object) -> MagicMock:
        client = MagicMock()
        client.chat.completions.create.side_effect = _rate_limit_error()
        return client

    with (
        patch("packages.integrations.llm.openrouter_provider.OpenAI", side_effect=fake_openai),
        pytest.raises(RateLimitError),
    ):
        provider.complete("Write a post about X", model="anthropic/claude-sonnet-5")
