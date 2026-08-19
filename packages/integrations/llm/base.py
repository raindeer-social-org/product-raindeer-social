from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


class LLMProvider(ABC):
    """Interface every LLM adapter implements. Agent code must only ever
    depend on this interface — never import a vendor SDK directly outside
    the adapter that implements it."""

    @abstractmethod
    def complete(self, prompt: str, model: str, **kwargs: object) -> LLMResponse:
        ...
