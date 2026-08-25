import httpx

from packages.integrations.embedding.base import EmbeddingProvider
from packages.integrations.observability import track_integration_call


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """The only file in this codebase allowed to call OpenAI's embeddings
    endpoint directly."""

    BASE_URL = "https://api.openai.com/v1/embeddings"
    # 1536 dimensions — matches the Vector(1536) columns reserved since #4
    # exactly, so no dimensionality mismatch at the pgvector layer.
    MODEL = "text-embedding-3-small"

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

    def embed(self, text: str) -> list[float]:
        with track_integration_call("openai", "embedding"):
            response = httpx.post(
                self.BASE_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.MODEL, "input": text},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        return data["data"][0]["embedding"]
