from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Interface every embedding adapter implements. Agent code must only
    ever depend on this interface — never import a vendor SDK directly
    outside the adapter that implements it."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        ...
