"""Local Piper synthesis (design §8.6, docs/meeting-mode-v0.1.md §9).

The second synthesiser behind the same protocol as ``edge_tts_synthesis``. It exists because
edge-tts is not usable from this machine's network: measured 2026-10-02, one line took 6.4-10.1 s
(TLS handshake to the Microsoft endpoint alone 3.3-4.1 s, through a proxy 4.1 s) with intermittent
connection timeouts, against a design budget of "a few hundred milliseconds". Piper runs the ONNX
voice in-process: no network, no key, no third party to be reachable.

Deliberate choices:

- **The model loads on first use, not at import.** A 63 MB ONNX file plus an onnxruntime session
  have no business on the API's startup path, and a session never asks for every voice.
- **One session per voice model, cached for the process.** Loading costs about a second; speaking
  after that is the work. ``aclose`` drops nothing — the memory is reclaimed with the process, the
  same way the Whisper provider treats its model.
- **Synthesis runs in a thread.** onnxruntime releases the GIL inside a session, but the espeak
  phonemisation around it does not, and a whole line on the event loop would stall every other
  request the way a blocked transcription would.
- **WAV out, not MP3.** Piper emits 22.05 kHz 16-bit mono PCM. The client already derives its file
  extension from the content type (``apps/mobile/src/features/speech/synthesis.ts``), so nothing has
  to transcode; a 10 s line is ~430 KB against ~40 KB of MP3.
"""

from __future__ import annotations

import asyncio
import io
import logging
import wave
from pathlib import Path
from typing import Any

from app.ai.speech_synthesis import SpeechSynthesisError, SynthesisResult
from app.core.config import Settings

logger = logging.getLogger(__name__)

#: What the voice models are called once they are on disk. The catalog in ``app/ai/voices.py`` is
#: pinned by name because those strings are already stored inside scenarios, so a voice that is
#: missing on this machine must not take the request down.
DEFAULT_VOICE_MODEL = "en_US-lessac-medium"


class PiperSynthesisProvider:
    def __init__(
        self,
        *,
        voices_dir: Path,
        timeout_seconds: float,
        default_voice: str = DEFAULT_VOICE_MODEL,
    ) -> None:
        self.name = "piper"
        self.model = default_voice
        self._voices_dir = voices_dir
        self._default_voice = default_voice
        self._timeout_seconds = timeout_seconds
        self._voices: dict[str, Any] = {}
        self._load_lock = asyncio.Lock()

    async def synthesize(self, text: str, *, voice: str) -> SynthesisResult:
        model_name = self._model_path(voice).stem
        piper_voice = await self._load(model_name)
        try:
            audio = await asyncio.wait_for(
                asyncio.to_thread(self._speak, piper_voice, text),
                timeout=self._timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            # Python 3.10's asyncio.TimeoutError is not the builtin, and the service maps the
            # builtin to HTTP 504: translate rather than leaking a 500.
            raise TimeoutError("Speech synthesis timed out.") from exc
        except SpeechSynthesisError:
            raise
        except Exception as exc:  # noqa: BLE001 - inference can fail in many ways
            raise SpeechSynthesisError(f"Speech synthesis failed: {exc}") from exc

        if not audio:
            raise SpeechSynthesisError("The synthesiser returned no audio.")
        return SynthesisResult(
            audio=audio,
            content_type="audio/wav",
            voice=voice,
            provider=self.name,
            model=model_name,
        )

    async def aclose(self) -> None:
        """Nothing to close: an onnxruntime session holds memory, not a connection."""
        return None

    def loaded_voices(self) -> list[str]:
        """Test seam: which models this process has actually opened."""
        return sorted(self._voices)

    def _model_path(self, voice: str) -> Path:
        """Resolve a stored voice name to a model file on disk.

        An unknown or missing voice falls back to the default rather than failing: the voice is
        cosmetic, and a scenario written before a voice was renamed must still be speakable
        (``app/ai/voices.py`` makes the same promise on the read path).
        """
        candidate = self._voices_dir / f"{voice}.onnx"
        if candidate.is_file():
            return candidate
        logger.info("piper voice %r is not installed; speaking with %s", voice, self._default_voice)
        return self._voices_dir / f"{self._default_voice}.onnx"

    async def _load(self, model_name: str) -> Any:
        if model_name in self._voices:
            return self._voices[model_name]
        async with self._load_lock:
            if model_name not in self._voices:
                self._voices[model_name] = await asyncio.to_thread(self._build, model_name)
        return self._voices[model_name]

    def _build(self, model_name: str) -> Any:
        try:
            from piper import PiperVoice
        except ImportError as exc:  # pragma: no cover - only in a broken install
            raise SpeechSynthesisError(
                "piper-tts is not installed; install it or set SPEECH_SYNTHESIS_PROVIDER=mock."
            ) from exc

        path = self._voices_dir / f"{model_name}.onnx"
        if not path.is_file():
            raise SpeechSynthesisError(
                f"The Piper voice {model_name!r} is not installed at {path}. Download it with "
                f"`python -m piper.download_voices {model_name}`."
            )
        logger.info("loading piper voice model=%s path=%s", model_name, path)
        try:
            return PiperVoice.load(str(path))
        except Exception as exc:  # noqa: BLE001 - a corrupt or mismatched model fails here
            raise SpeechSynthesisError(
                f"Could not load the Piper voice {model_name!r}: {exc}"
            ) from exc

    def _speak(self, piper_voice: Any, text: str) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as handle:
            piper_voice.synthesize_wav(text, handle)
        return buffer.getvalue()


def build_piper_provider(settings: Settings) -> PiperSynthesisProvider:
    if not settings.speech_synthesis_piper_dir:
        raise RuntimeError(
            "SPEECH_SYNTHESIS_PIPER_DIR must point at the directory holding the .onnx voices "
            "when SPEECH_SYNTHESIS_PROVIDER is 'piper'."
        )
    return PiperSynthesisProvider(
        voices_dir=Path(settings.speech_synthesis_piper_dir),
        timeout_seconds=settings.speech_synthesis_timeout_seconds,
    )
