"""The edge-tts synthesiser's failure handling (docs/meeting-mode-v0.1.md §9).

No network here: the websocket client is replaced by a fake that streams chunks the way edge-tts
does. The point is what the provider does around it — refusing empty audio, translating the timeout
into the class the service maps to 504, and treating a client explosion as a provider failure rather
than a 500.
"""

from __future__ import annotations

import asyncio
import sys
import types

import pytest

from app.ai.edge_tts_synthesis import EdgeTtsSynthesisProvider
from app.ai.speech_synthesis import SpeechSynthesisError
from app.ai.synthesis_factory import build_synthesis_provider
from app.core.config import settings

VOICE = "en-GB-SoniaNeural"


class FakeCommunicate:
    """Stands in for ``edge_tts.Communicate``."""

    chunks: list[dict] = [{"type": "audio", "data": b"ID3fake-mp3-bytes"}]
    delay: float = 0.0
    raises: Exception | None = None

    def __init__(self, text: str, voice: str) -> None:
        self.text = text
        self.voice = voice

    async def stream(self):
        if self.raises is not None:
            raise self.raises
        for chunk in self.chunks:
            if self.delay:
                await asyncio.sleep(self.delay)
            yield chunk


@pytest.fixture
def fake_edge_tts(monkeypatch):
    """Install a fake ``edge_tts`` module for the duration of one test."""
    module = types.ModuleType("edge_tts")
    module.Communicate = FakeCommunicate
    monkeypatch.setitem(sys.modules, "edge_tts", module)
    FakeCommunicate.chunks = [{"type": "audio", "data": b"ID3fake-mp3-bytes"}]
    FakeCommunicate.delay = 0.0
    FakeCommunicate.raises = None
    return module


async def test_audio_chunks_are_collected_into_one_file(fake_edge_tts) -> None:
    provider = EdgeTtsSynthesisProvider(timeout_seconds=5)

    result = await provider.synthesize("Can I flag one risk?", voice=VOICE)

    assert result.audio == b"ID3fake-mp3-bytes"
    assert result.content_type == "audio/mpeg"
    assert result.voice == VOICE
    assert result.provider == "edge_tts"


async def test_non_audio_chunks_are_ignored(fake_edge_tts) -> None:
    """edge-tts interleaves word-boundary metadata with the audio; only the audio is the answer."""
    FakeCommunicate.chunks = [
        {"type": "WordBoundary", "offset": 100},
        {"type": "audio", "data": b"ID3one"},
        {"type": "audio", "data": b"-two"},
    ]
    provider = EdgeTtsSynthesisProvider(timeout_seconds=5)

    result = await provider.synthesize("Hello", voice=VOICE)

    assert result.audio == b"ID3one-two"


async def test_no_audio_at_all_is_a_provider_error(fake_edge_tts) -> None:
    """Silence would reach the client as a 200 with an empty file: a button that does nothing."""
    FakeCommunicate.chunks = []
    provider = EdgeTtsSynthesisProvider(timeout_seconds=5)

    with pytest.raises(SpeechSynthesisError):
        await provider.synthesize("Hello", voice=VOICE)


async def test_a_slow_synthesis_becomes_a_timeout(fake_edge_tts) -> None:
    """The builtin TimeoutError is what the service maps to 504."""
    FakeCommunicate.delay = 5.0
    provider = EdgeTtsSynthesisProvider(timeout_seconds=0.1)

    with pytest.raises(TimeoutError):
        await provider.synthesize("Hello", voice=VOICE)


async def test_a_client_explosion_is_wrapped(fake_edge_tts) -> None:
    FakeCommunicate.raises = OSError("connection reset by peer")
    provider = EdgeTtsSynthesisProvider(timeout_seconds=5)

    with pytest.raises(SpeechSynthesisError, match="connection reset"):
        await provider.synthesize("Hello", voice=VOICE)


def test_the_provider_is_built_from_settings() -> None:
    provider = build_synthesis_provider(settings)

    assert provider.name == "fake", "the mock provider must be the default outside production"


def test_an_unknown_synthesis_provider_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(settings, "speech_synthesis_provider", "elevenlabs")

    with pytest.raises(RuntimeError, match="Unsupported SPEECH_SYNTHESIS_PROVIDER"):
        build_synthesis_provider(settings)
