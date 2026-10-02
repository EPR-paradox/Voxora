"""The local whisper provider's failure handling (design §8.6).

No model is loaded here: the point is what the provider does around the decoder, which is where the
expensive mistakes live.

The CUDA case is not hypothetical — measured here (GTX 1660 Ti, driver 580): CTranslate2 advertises
CUDA support, builds a CUDA model, and then fails every encode with `libcublas.so.12 is not
found`. Without the runtime fallback below, `SPEECH_DEVICE=auto` would answer every clip with a 502.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from app.ai.faster_whisper_speech import FasterWhisperSpeechProvider
from app.ai.speech import SpeechNotRecognized

CUDA_MESSAGE = "Library libcublas.so.12 is not found or cannot be loaded"


@dataclass
class FakeSegment:
    text: str
    no_speech_prob: float = 0.0


@dataclass
class FakeInfo:
    language: str = "en"
    duration: float = 3.0


class FakeWhisper:
    """Stands in for `faster_whisper.WhisperModel`, including its habit of failing on CUDA."""

    def __init__(self, model_name: str, *, device: str, compute_type: str) -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type

    def transcribe(self, audio, **kwargs):
        if self.device == "cuda":
            raise RuntimeError(CUDA_MESSAGE)
        return [FakeSegment("Hello from the CPU.")], FakeInfo()


class SilentWhisper(FakeWhisper):
    def transcribe(self, audio, **kwargs):
        return [], FakeInfo()


class SlowWhisper(FakeWhisper):
    def transcribe(self, audio, **kwargs):
        import time

        time.sleep(5)
        return [FakeSegment("too late")], FakeInfo()


def provider(**overrides) -> FasterWhisperSpeechProvider:
    values = {
        "model_name": "small.en",
        "device": "cuda",
        "compute_type": "float16",
        "timeout_seconds": 5.0,
    }
    values.update(overrides)
    return FasterWhisperSpeechProvider(**values)


@pytest.mark.asyncio
async def test_a_cuda_decode_failure_falls_back_to_the_cpu(monkeypatch) -> None:
    monkeypatch.setattr("faster_whisper.WhisperModel", FakeWhisper)
    speech = provider()

    result = await speech.transcribe(b"audio", content_type="audio/m4a", language="en")

    assert result.text == "Hello from the CPU."
    # And it stays on the CPU: the next clip must not pay for another failed CUDA attempt.
    assert speech.using_cuda() is False


@pytest.mark.asyncio
async def test_a_silent_clip_is_a_not_recognized_error(monkeypatch) -> None:
    monkeypatch.setattr("faster_whisper.WhisperModel", SilentWhisper)
    speech = provider(device="cpu", compute_type="int8")

    with pytest.raises(SpeechNotRecognized):
        await speech.transcribe(b"audio", content_type="audio/m4a", language="en")


@pytest.mark.asyncio
async def test_a_slow_decode_becomes_a_timeout(monkeypatch) -> None:
    """The service maps builtin TimeoutError to 504; asyncio's own class would surface as a 500."""
    monkeypatch.setattr("faster_whisper.WhisperModel", SlowWhisper)
    speech = provider(device="cpu", compute_type="int8", timeout_seconds=0.1)

    with pytest.raises(TimeoutError):
        await speech.transcribe(b"audio", content_type="audio/m4a", language="en")


@pytest.mark.asyncio
async def test_the_model_is_loaded_once(monkeypatch) -> None:
    """A 460 MB model reloaded per request would make transcription unusable."""
    builds: list[str] = []

    class CountingWhisper(FakeWhisper):
        def __init__(self, model_name: str, *, device: str, compute_type: str) -> None:
            builds.append(device)
            super().__init__(model_name, device=device, compute_type=compute_type)

    monkeypatch.setattr("faster_whisper.WhisperModel", CountingWhisper)
    speech = provider(device="cpu", compute_type="int8")

    await asyncio.gather(
        speech.transcribe(b"one", content_type="audio/m4a", language="en"),
        speech.transcribe(b"two", content_type="audio/m4a", language="en"),
    )
    await speech.transcribe(b"three", content_type="audio/m4a", language="en")

    assert builds == ["cpu"]
    assert speech.model_is_loaded() is True
