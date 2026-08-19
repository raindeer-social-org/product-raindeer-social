import httpx

from packages.integrations.llm.base import LLMProvider, LLMResponse
from packages.integrations.observability import track_integration_call


class OpenRouterProvider(LLMProvider):
    """The only file allowed to call OpenRouter directly. Primary LLM
    path — model-agnostic, lets agents switch between Claude/GPT/Gemini/
    open models per-call without a new SDK."""

    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key: str, timeout: float = 60.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

    def complete(self, prompt: str, model: str, **kwargs: object) -> LLMResponse:
        with track_integration_call("openrouter", "llm"):
            response = httpx.post(
                self.BASE_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    **kwargs,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

        usage = data.get("usage", {})
        return LLMResponse(
            text=data["choices"][0]["message"]["content"],
            model=data.get("model", model),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )
