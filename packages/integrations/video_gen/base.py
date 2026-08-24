from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class VideoResult:
    # The vendor's own hosted URL for the generated asset. Not guaranteed
    # to stay valid indefinitely (most video-gen vendors expire these), so
    # callers that need a durable link should store `content` via
    # StorageProvider (packages/integrations/storage) rather than persist
    # this URL directly.
    url: str
    content: bytes = field(default=b"")
    content_type: str = "video/mp4"


class VideoProvider(ABC):
    """Interface for video/carousel-generation adapters. Issue #23 adds
    the first real implementation (RunwayProvider,
    packages/integrations/video_gen/runway_provider.py) — business/agent
    code must depend on this interface only, never import a vendor SDK or
    call a vendor URL directly outside the adapter that implements it."""

    @abstractmethod
    def generate(self, prompt: str, **kwargs: object) -> VideoResult:
        ...
