"""The text-to-speech contract (design §8.6, docs/meeting-mode-v0.1.md §9).

Synthesis is an output method the way transcription is an input method: text goes in, audio comes
out for one playback, and the bytes are forgotten. Nothing here touches practice sessions, messages
or the database — storing the audio would mean answering "for how long, and who can delete it"
(§9.2).

Failures are part of the contract rather than surprises, matching §7.11:

- ``SpeechSynthesisError`` -> HTTP 502, ``TimeoutError`` -> HTTP 504: both retryable by the learner.
  - Text the synthesiser cannot be asked to say (empty, too long) and a voice it does not know are
  rejected before any provider is called -> HTTP 422.
"""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SynthesisResult:
    """One spoken line: the bytes, plus how to label them in a response (§8.6)."""

    audio: bytes
    content_type: str
    voice: str
    provider: str
    model: str


class SpeechSynthesisError(RuntimeError):
    """The synthesiser failed or returned something unusable."""


class SpeechSynthesisProvider(Protocol):
    async def synthesize(self, text: str, *, voice: str) -> SynthesisResult: ...

    async def aclose(self) -> None: ...


class FakeSpeechSynthesisProvider:
    """Deterministic provider for tests and offline development.

    It returns a real silent WAV rather than placeholder bytes: the phone has to be able to hand the
    response to an audio player, so a fake that returns unusable bytes would hide client bugs behind
    a "mock mode" that is never actually exercised.
    """

    name = "fake"
    model = "fake-v1"
    #: : Tests set this to an exception instance to exercise the failure paths.
    fail_with: Exception | None = None

    async def synthesize(self, text: str, *, voice: str) -> SynthesisResult:
        if self.fail_with is not None:
            raise self.fail_with
        return SynthesisResult(
            audio=_silent_wav(),
            content_type="audio/wav",
            voice=voice,
            provider=self.name,
            model=self.model,
        )

    async def aclose(self) -> None:
        return None


def _silent_wav(seconds: float = 0.6, rate: int = 24000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00" * (2 * int(rate * seconds)))
    return buffer.getvalue()
