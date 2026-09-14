from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TranscriptionResult:
    text: str
    language: str | None = None
    duration_seconds: float | None = None


class SpeechToTextProvider(ABC):
    """Interface every speech-to-text adapter implements. Business/router
    code must only ever depend on this interface — never import a vendor
    SDK or model runtime directly outside the adapter that implements it,
    same contract as every other package under packages/integrations/."""

    @abstractmethod
    def transcribe(self, audio_bytes: bytes, content_type: str) -> TranscriptionResult:
        ...
