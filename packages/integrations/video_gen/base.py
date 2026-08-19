from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class VideoResult:
    url: str


class VideoProvider(ABC):
    """Interface for video/carousel-generation adapters. No adapter
    implements this yet — that lands in Issue #23 (Kling or Runway)."""

    @abstractmethod
    def generate(self, prompt: str, **kwargs: object) -> VideoResult:
        ...
