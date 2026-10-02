"""Local faster-whisper transcription (design §8.6).

Deliberate choices:

- **The model loads on first use, not at import.** A few hundred megabytes of weights and a CUDA
context
  have no business in the way of `pytest`, and the API must start even when nobody has spoken into
  it yet.
- **Decoding runs in a thread.** ``WhisperModel.transcribe`` returns a generator that does the work
while
  being iterated; on the event loop that would freeze every other request for the length of the
  clip.
- **No VAD, no streaming** (§10.4): one clip in, one whole transcript out.
- **Silence is a failure, not empty text.** Whisper happily invents "Thank you." on a silent
  clip, so segments the model marks as probably-not-speech are dropped, and a clip that leaves
  nothing is reported as ``SpeechNotRecognized`` -> HTTP 422 (§7.11 rule 4), never empty text.
  reported as ``SpeechNotRecognized`` -> HTTP 422 (§7.11 rule 4) instead of producing an empty
  message.
"""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Any

from app.ai.speech import SpeechNotRecognized, SpeechProviderError, TranscriptResult
from app.core.config import Settings

logger = logging.getLogger(__name__)

# : Segments the model is this sure contain no speech are dropped (Whisper's own no-speech
# probability).
NO_SPEECH_PROBABILITY_CUTOFF = 0.6


class FasterWhisperSpeechProvider:
    def __init__(
        self,
        *,
        model_name: str,
        device: str,
        compute_type: str,
        timeout_seconds: float,
    ) -> None:
        self.name = "faster_whisper"
        self.model = model_name
        self._device = device
        self._compute_type = compute_type
        self._timeout_seconds = timeout_seconds
        self._model: Any | None = None
        self._load_lock = asyncio.Lock()

    async def transcribe(
        self, audio: bytes, *, content_type: str, language: str
    ) -> TranscriptResult:
        model = await self._load_model()
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._decode, model, audio, language),
                timeout=self._timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            # Python 3.10's asyncio.TimeoutError is not the builtin: the service maps TimeoutError
            # to
            # HTTP 504, so translate it here rather than leaking a 500.
            raise TimeoutError("Transcription timed out.") from exc
        except SpeechProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 - decoded audio can fail in many ways
            raise SpeechProviderError(f"Transcription failed: {exc}") from exc

    async def aclose(self) -> None:
        """Nothing to close: the model holds memory, not a connection.

        Dropping the loaded model is the caller's job.
        """
        return None

    def model_is_loaded(self) -> bool:
        return self._model is not None

    async def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        async with self._load_lock:
            if self._model is None:
                self._model = await asyncio.to_thread(self._build_model)
        return self._model

    def _build_model(self) -> Any:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - exercised only in a broken install
            raise SpeechProviderError(
                "faster-whisper is not installed; install it or set SPEECH_PROVIDER=mock."
            ) from exc

        device, compute_type = self._resolve_device()
        logger.info(
            "loading whisper model name=%s device=%s compute_type=%s",
            self.model,
            device,
            compute_type,
        )
        try:
            return WhisperModel(self.model, device=device, compute_type=compute_type)
        except Exception as exc:  # noqa: BLE001
            if device == "cuda":
                # A missing cuDNN or an unsupported card must not take transcription down: fall back
                # to
                # the CPU path and say so, instead of failing every clip from then on.
                logger.warning("CUDA load failed (%s); falling back to CPU int8", exc)
                return WhisperModel(self.model, device="cpu", compute_type="int8")
            raise SpeechProviderError(
                f"Could not load the whisper model {self.model!r}: {exc}"
            ) from exc

    def _resolve_device(self) -> tuple[str, str]:
        if self._device == "cpu":
            compute_type = "int8" if self._compute_type == "float16" else self._compute_type
            return "cpu", compute_type
        if self._device == "cuda":
            return "cuda", self._compute_type
        # auto: use the GPU only when CTranslate2 itself says it can, otherwise take the CPU path.
        try:
            import ctranslate2

            if "float16" in ctranslate2.get_supported_compute_types("cuda"):
                return "cuda", "float16"
        except Exception:  # noqa: BLE001 - a missing CUDA stack is a normal state on this machine
            logger.info("CUDA is not usable for CTranslate2; transcribing on the CPU")
        return "cpu", "int8"

    def _decode(self, model: Any, audio: bytes, language: str) -> TranscriptResult:
        segments, info = model.transcribe(
            io.BytesIO(audio),
            language=language,
            beam_size=1,
            condition_on_previous_text=False,
            vad_filter=False,
        )
        pieces = [
            segment.text.strip()
            for segment in segments
            if (getattr(segment, "no_speech_prob", 0.0) or 0.0) < NO_SPEECH_PROBABILITY_CUTOFF
        ]
        text = " ".join(piece for piece in pieces if piece).strip()
        if not text:
            raise SpeechNotRecognized("No speech was recognised in this clip.")

        duration = getattr(info, "duration", None)
        return TranscriptResult(
            text=text,
            language=getattr(info, "language", None) or language,
            duration_ms=int(duration * 1000) if duration else None,
            provider=self.name,
            model=self.model,
        )


def build_speech_provider(settings: Settings):
    """Pick the transcription provider from settings, failing closed on a bad configuration."""
    from app.ai.speech import FakeSpeechProvider, SpeechProvider

    if settings.speech_provider == "mock":
        return FakeSpeechProvider()
    if settings.speech_provider != "faster_whisper":
        raise RuntimeError(
            f"Unsupported SPEECH_PROVIDER {settings.speech_provider!r}: "
            "use 'mock' or 'faster_whisper'."
        )
    if not settings.speech_model:
        raise RuntimeError("SPEECH_MODEL must be set when SPEECH_PROVIDER is not 'mock'.")

    provider: SpeechProvider = FasterWhisperSpeechProvider(
        model_name=settings.speech_model,
        device=settings.speech_device,
        compute_type=settings.speech_compute_type,
        timeout_seconds=settings.speech_timeout_seconds,
    )
    return provider
