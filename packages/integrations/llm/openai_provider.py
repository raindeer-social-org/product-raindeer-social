from openai import OpenAI

from packages.integrations.llm.base import LLMProvider, LLMResponse
from packages.integrations.observability import track_integration_call


class OpenAIProvider(LLMProvider):
    """The only file allowed to call OpenAI directly. Secondary path —
    for OpenAI-only features OpenRouter doesn't cover well."""

    def __init__(self, api_key: str, timeout: float = 60.0) -> None:
        self.client = OpenAI(api_key=api_key, timeout=timeout)

    def complete(self, prompt: str, model: str, **kwargs: object) -> LLMResponse:
        with track_integration_call("openai", "llm"):
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
