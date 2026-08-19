from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ImageResult:
    url: str


class ImageProvider(ABC):
    """Interface for image-generation adapters. No adapter implements
    this yet — that lands in Issue #22 (fal.ai)."""

    @abstractmethod
    def generate(self, prompt: str, **kwargs: object) -> ImageResult:
        ...
