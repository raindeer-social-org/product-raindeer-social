import random

from openai import OpenAI, RateLimitError

from packages.integrations.llm.base import LLMProvider, LLMResponse
from packages.integrations.observability import track_integration_call


class OpenRouterProvider(LLMProvider):
    """The only file allowed to call OpenRouter directly. Primary LLM
    path — model-agnostic, lets agents switch between Claude/GPT/Gemini/
    open models per-call without a new SDK. OpenRouter's API is OpenAI-
    compatible, so this uses the `openai` SDK pointed at OpenRouter's
    base URL rather than a bespoke HTTP client.

    Accepts a pool of one or more API keys (Settings.openrouter_api_key_pool)
    rather than a single key. Each free-tier OpenRouter key carries its own
    independent daily request cap, so a single busy key exhausts fast under
    this app's call volume (onboarding alone makes several LLM calls per
    brand: research summary, up to 4 rounds of adaptive questions, one
    synthesis call). complete() picks a random key from the pool per call —
    spreading load across keys without needing any shared counter/lock —
    and on a 429 specifically (OpenRouter's daily-limit error), retries
    once per remaining key in the pool before giving up, so a single
    exhausted key degrades to "try another key" rather than "fail the
    whole call"."""

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, api_keys: list[str], timeout: float = 60.0) -> None:
        # See OpenAIProvider's __init__ for why an empty pool falls back to
        # a placeholder key rather than letting the openai SDK raise here.
        self._keys = api_keys or ["unconfigured"]
        self._timeout = timeout

    def _client_for(self, api_key: str) -> OpenAI:
        return OpenAI(api_key=api_key, base_url=self.BASE_URL, timeout=self._timeout)

    def complete(self, prompt: str, model: str, **kwargs: object) -> LLMResponse:
        keys_to_try = random.sample(self._keys, k=len(self._keys))

        last_error: RateLimitError | None = None
        for key in keys_to_try:
            try:
                with track_integration_call("openrouter", "llm"):
                    completion = self._client_for(key).chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        **kwargs,
                    )
            except RateLimitError as exc:
                # This specific key's daily cap is exhausted — try the next
                # one in the pool rather than surfacing the failure
                # immediately. Any other error (auth, network, malformed
                # request) is a real failure and propagates as-is; retrying
                # it against a different key wouldn't help.
                last_error = exc
                continue

            usage = completion.usage
            return LLMResponse(
                text=completion.choices[0].message.content,
                model=completion.model,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            )

        assert last_error is not None  # keys_to_try is never empty
        raise last_error
