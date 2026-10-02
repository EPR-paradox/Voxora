"""The speech-to-text contract (design §8.6, §7.11).

Transcription is an input method, not a message: the service turns a recording into text and forgets
the audio. Nothing here touches practice sessions, messages or the database — that is why this
module has
no ORM imports.

Two failure modes are part of the contract rather than surprises:

- ``SpeechNotRecognized`` -> HTTP 422 ``speech_not_recognized``: the clip decoded but held no usable
  speech. Returning empty text instead would let the client send an empty message.
- ``SpeechProviderError`` -> HTTP 502, ``TimeoutError`` -> HTTP 504, both retryable by the learner
with
  the same clip.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TranscriptResult:
    """What the provider found: the text plus enough metadata to trace a model change (§8.6)."""

    text: str
    language: str
    duration_ms: int | None
    provider: str
    model: str


class SpeechProviderError(RuntimeError):
    """The transcription backend failed or returned something unusable."""


class SpeechNotRecognized(SpeechProviderError):
    """The clip decoded but contained no usable speech (§7.11 rule 4)."""


class SpeechProvider(Protocol):
    async def transcribe(
        self, audio: bytes, *, content_type: str, language: str
    ) -> TranscriptResult: ...

    async def aclose(self) -> None: ...


class FakeSpeechProvider:
    """Deterministic provider for tests and offline development.

    The canned text is fixed rather than derived from the audio: a fake that "recognizes" whatever
    it is given would make the tests pass for the wrong reason.
    """

    name = "fake"
    model = "fake-v1"
    #: Tests set this to an exception instance to exercise the failure paths.
    fail_with: Exception | None = None

    async def transcribe(
        self, audio: bytes, *, content_type: str, language: str
    ) -> TranscriptResult:
        if self.fail_with is not None:
            raise self.fail_with
        return TranscriptResult(
            text="I was responsible for the calibration service.",
            language=language,
            duration_ms=2400,
            provider=self.name,
            model=self.model,
        )

    async def aclose(self) -> None:
        return None
