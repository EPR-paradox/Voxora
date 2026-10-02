"""Speech synthesis through edge-tts (docs/meeting-mode-v0.1.md §9).

Chosen for the first version because it is measurable and free: plain HTTPS to a cloud voice
service, no API key, verified reachable from this machine without a proxy, eight usable English
voices in the catalog (``app/ai/voices.py``), and a few hundred milliseconds for a meeting-length
line. The provider is behind the same kind of protocol as transcription (§8.6), so a local model can
replace it without touching the API.

Deliberate choices:

- **edge-tts is imported inside the call.** It drags in a websocket client; importing it at module
  scope would put that on the startup path of an API that may never speak.
- **The whole line is buffered before returning.** Playback needs one complete file, and §9.2 says
  the
  audio is not stored, so there is nowhere to stream it to.
- **A byte ceiling while streaming.** A runaway synthesis must not become unbounded memory; the cap
  is
  generous for a meeting line and the request text is bounded separately.
"""

from __future__ import annotations

import asyncio
import logging

from app.ai.speech_synthesis import SpeechSynthesisError, SynthesisResult
from app.core.config import Settings

logger = logging.getLogger(__name__)

#: A meeting line is a few hundred characters of speech; this only has to catch a runaway.
MAX_AUDIO_BYTES = 8 * 1024 * 1024


class EdgeTtsSynthesisProvider:
    def __init__(self, *, timeout_seconds: float) -> None:
        self.name = "edge_tts"
        self.model = "edge-tts"
        self._timeout_seconds = timeout_seconds

    async def synthesize(self, text: str, *, voice: str) -> SynthesisResult:
        try:
            audio = await asyncio.wait_for(self._stream(text, voice), timeout=self._timeout_seconds)
        except asyncio.TimeoutError as exc:
            # Python 3.10's asyncio.TimeoutError is not the builtin, and the service maps the
            # builtin to HTTP 504: translate rather than leaking a 500.
            raise TimeoutError("Speech synthesis timed out.") from exc
        except SpeechSynthesisError:
            raise
        except Exception as exc:  # noqa: BLE001 - the websocket client fails in many ways
            raise SpeechSynthesisError(f"Speech synthesis failed: {exc}") from exc

        if not audio:
            raise SpeechSynthesisError("The synthesiser returned no audio.")
        return SynthesisResult(
            audio=audio,
            content_type="audio/mpeg",
            voice=voice,
            provider=self.name,
            model=self.model,
        )

    async def aclose(self) -> None:
        """Nothing to close: each line uses its own short-lived connection."""
        return None

    async def _stream(self, text: str, voice: str) -> bytes:
        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover - only in a broken install
            raise SpeechSynthesisError(
                "edge-tts is not installed; install it or set SPEECH_SYNTHESIS_PROVIDER=mock."
            ) from exc

        communicate = edge_tts.Communicate(text, voice)
        audio = bytearray()
        async for chunk in communicate.stream():
            if chunk.get("type") != "audio":
                continue
            audio.extend(chunk.get("data") or b"")
            if len(audio) > MAX_AUDIO_BYTES:
                raise SpeechSynthesisError("The synthesised audio exceeded the size ceiling.")
        return bytes(audio)


def build_edge_tts_provider(settings: Settings) -> EdgeTtsSynthesisProvider:
    """Build the edge-tts synthesiser.

    Reached through ``app.ai.synthesis_factory``. Kept although it is no longer the default: the
    implementation is complete and tested, and the only thing wrong with it is the network it needs
    (measured 2026-10-02: 6.4-10.1 s per line from this machine, see ``piper_synthesis``).
    """
    return EdgeTtsSynthesisProvider(
        timeout_seconds=settings.speech_synthesis_timeout_seconds,
    )
