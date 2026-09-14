import logging
import os
import tempfile
from typing import Any

from packages.integrations.observability import track_integration_call
from packages.integrations.speech.base import SpeechToTextProvider, TranscriptionResult

logger = logging.getLogger(__name__)

# Guesses a reasonable file extension for whatever container the browser's
# MediaRecorder produced, purely so the temp file we hand to faster-whisper
# (which shells out to ffmpeg/PyAV for decoding) has a hint to work with —
# ffmpeg mostly sniffs the real container anyway, this is a best-effort.
_EXTENSION_BY_CONTENT_TYPE = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
}

# Module-level cache: faster-whisper's WhisperModel loads model weights
# from disk (downloading them once, on first use, into its own cache dir)
# — expensive enough that every adapter instance must share one loaded
# model rather than reloading per-request/per-instance.
_MODEL_CACHE: dict[str, Any] = {}


def _load_model(model_size: str):
    if model_size not in _MODEL_CACHE:
        # Imported lazily (not at module import time) so importing this
        # module — e.g. from registry.py, which is imported broadly —
        # never requires faster-whisper's fairly heavy dependency chain
        # (torch/ctranslate2) unless a WhisperProvider is actually
        # constructed and used.
        from faster_whisper import WhisperModel

        logger.info("Whisper speech provider: loading model size=%r (first use)", model_size)
        _MODEL_CACHE[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _MODEL_CACHE[model_size]


class WhisperSpeechProvider(SpeechToTextProvider):
    """Free, fully open-source, locally-run speech-to-text via
    faster-whisper (CTranslate2's reimplementation of OpenAI's Whisper) —
    no API key, no per-call cost, no network dependency once the model
    weights are cached locally. The only file allowed to import
    faster_whisper directly; every other module reaches it only through
    SpeechToTextProvider, resolved via
    packages.integrations.registry.get_speech_provider(), same
    interface-only contract as every other adapter in this repo."""

    def __init__(self, model_size: str = "base") -> None:
        self.model_size = model_size

    def transcribe(self, audio_bytes: bytes, content_type: str) -> TranscriptionResult:
        model = _load_model(self.model_size)
        suffix = _EXTENSION_BY_CONTENT_TYPE.get(content_type, ".webm")

        with track_integration_call("whisper", "speech_to_text"):
            fd, temp_path = tempfile.mkstemp(suffix=suffix)
            try:
                with os.fdopen(fd, "wb") as temp_file:
                    temp_file.write(audio_bytes)

                segments, info = model.transcribe(temp_path, beam_size=5)
                text = " ".join(segment.text.strip() for segment in segments).strip()
                return TranscriptionResult(
                    text=text,
                    language=getattr(info, "language", None),
                    duration_seconds=getattr(info, "duration", None),
                )
            finally:
                os.remove(temp_path)
