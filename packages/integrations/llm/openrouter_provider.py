from openai import OpenAI

from packages.integrations.llm.base import LLMProvider, LLMResponse
from packages.integrations.observability import track_integration_call


class OpenRouterProvider(LLMProvider):
    """The only file allowed to call OpenRouter directly. Primary LLM
    path — model-agnostic, lets agents switch between Claude/GPT/Gemini/
    open models per-call without a new SDK. OpenRouter's API is OpenAI-
    compatible, so this uses the `openai` SDK pointed at OpenRouter's
    base URL rather than a bespoke HTTP client."""

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: str, timeout: float = 60.0) -> None:
        self.client = OpenAI(api_key=api_key, base_url=self.BASE_URL, timeout=timeout)

    def complete(self, prompt: str, model: str, **kwargs: object) -> LLMResponse:
        with track_integration_call("openrouter", "llm"):
            completion = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )

        usage = completion.usage
        return LLMResponse(
            text=completion.choices[0].message.content,
            model=completion.model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )
