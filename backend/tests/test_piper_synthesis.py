"""Piper synthesis: the fallbacks, the failure mapping and the WAV contract (design §8.6).

No model and no onnxruntime here: ``piper`` is replaced by a fake that writes a real WAV the way
the real ``synthesize_wav`` does. What is under test is the provider's own behaviour — which model a
stored voice name resolves to, that a session is loaded once and reused, and that a slow or
exploding inference becomes the exception class the service maps to 504/502 rather than a 500.

The one thing this cannot check is whether the audio is intelligible; that is why the provider is
also exercised against a real model on this machine (22x realtime for ``en_US-lessac-medium``).
"""

from __future__ import annotations

import io
import sys
import time
import types
import wave

import pytest

from app.ai.piper_synthesis import (
    DEFAULT_VOICE_MODEL,
    PiperSynthesisProvider,
    build_piper_provider,
)
from app.ai.speech_synthesis import SpeechSynthesisError
from app.ai.synthesis_factory import build_synthesis_provider
from app.core.config import settings

SAMPLE_RATE = 22050


class FakePiperVoice:
    """Stands in for ``piper.PiperVoice``, including its ONNX session lifecycle."""

    loaded_paths: list[str] = []
    delay: float = 0.0
    raises: Exception | None = None
    seconds: float = 0.04

    def __init__(self, path: str) -> None:
        self.path = path

    @staticmethod
    def load(path: str) -> FakePiperVoice:
        FakePiperVoice.loaded_paths.append(path)
        return FakePiperVoice(path)

    def synthesize_wav(self, text: str, wav_file: wave.Wave_write, **kwargs: object) -> None:
        # The real piper sets the container up before it starts inferring, which is also what makes
        # a mid-inference failure surface as its own exception rather than as a broken WAV header.
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        if FakePiperVoice.raises is not None:
            raise FakePiperVoice.raises
        if FakePiperVoice.delay:
            time.sleep(FakePiperVoice.delay)
        wav_file.writeframes(b"\x00\x00" * int(SAMPLE_RATE * FakePiperVoice.seconds))


@pytest.fixture
def fake_piper(monkeypatch):
    """Install a fake ``piper`` module for the duration of one test."""
    module = types.ModuleType("piper")
    module.PiperVoice = FakePiperVoice
    monkeypatch.setitem(sys.modules, "piper", module)
    FakePiperVoice.loaded_paths = []
    FakePiperVoice.delay = 0.0
    FakePiperVoice.raises = None
    FakePiperVoice.seconds = 0.04
    return module


def _installed(tmp_path, name: str = DEFAULT_VOICE_MODEL):
    (tmp_path / f"{name}.onnx").write_bytes(b"onnx-weights")
    return tmp_path


def test_a_missing_voices_directory_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(settings, "speech_synthesis_piper_dir", "")

    with pytest.raises(RuntimeError, match="SPEECH_SYNTHESIS_PIPER_DIR"):
        build_piper_provider(settings)


def test_the_factory_builds_piper_when_configured(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "speech_synthesis_provider", "piper")
    monkeypatch.setattr(settings, "speech_synthesis_piper_dir", str(tmp_path))

    provider = build_synthesis_provider(settings)

    assert provider.name == "piper"


def test_the_factory_rejects_an_unknown_provider(monkeypatch) -> None:
    monkeypatch.setattr(settings, "speech_synthesis_provider", "elevenlabs")

    with pytest.raises(RuntimeError, match="Unsupported SPEECH_SYNTHESIS_PROVIDER"):
        build_synthesis_provider(settings)


async def test_synthesis_returns_a_playable_wav(fake_piper, tmp_path) -> None:
    provider = PiperSynthesisProvider(voices_dir=_installed(tmp_path), timeout_seconds=5)

    result = await provider.synthesize("Can I flag one risk?", voice=DEFAULT_VOICE_MODEL)

    assert result.content_type == "audio/wav"
    assert result.provider == "piper"
    assert result.model == DEFAULT_VOICE_MODEL
    assert result.voice == DEFAULT_VOICE_MODEL
    # The bytes have to be a real WAV container: the client hands them to a player.
    with wave.open(io.BytesIO(result.audio)) as reader:
        assert reader.getframerate() == SAMPLE_RATE
        assert reader.getnframes() > 0


async def test_a_voice_that_is_not_installed_falls_back_to_the_default(
    fake_piper, tmp_path
) -> None:
    """A renamed or never-downloaded voice must not make a stored scenario unspeakable."""
    provider = PiperSynthesisProvider(voices_dir=_installed(tmp_path), timeout_seconds=5)

    result = await provider.synthesize("Hello", voice="en_IN-NeerjaExpressiveNeural")

    assert result.model == DEFAULT_VOICE_MODEL
    assert result.voice == "en_IN-NeerjaExpressiveNeural", "the requested name is still reported"
    assert FakePiperVoice.loaded_paths == [str(tmp_path / f"{DEFAULT_VOICE_MODEL}.onnx")]


async def test_the_session_is_loaded_once_and_reused(fake_piper, tmp_path) -> None:
    provider = PiperSynthesisProvider(voices_dir=_installed(tmp_path), timeout_seconds=5)

    await provider.synthesize("one", voice=DEFAULT_VOICE_MODEL)
    await provider.synthesize("two", voice=DEFAULT_VOICE_MODEL)

    assert len(FakePiperVoice.loaded_paths) == 1, "loading a 63 MB model per line is not acceptable"
    assert provider.loaded_voices() == [DEFAULT_VOICE_MODEL]


async def test_a_slow_synthesis_becomes_a_timeout(fake_piper, tmp_path) -> None:
    """The builtin TimeoutError is what the service maps to 504."""
    FakePiperVoice.delay = 5.0
    provider = PiperSynthesisProvider(voices_dir=_installed(tmp_path), timeout_seconds=0.1)

    with pytest.raises(TimeoutError):
        await provider.synthesize("Hello", voice=DEFAULT_VOICE_MODEL)


async def test_an_inference_explosion_is_wrapped(fake_piper, tmp_path) -> None:
    FakePiperVoice.raises = OSError("onnx session exploded")
    provider = PiperSynthesisProvider(voices_dir=_installed(tmp_path), timeout_seconds=5)

    with pytest.raises(SpeechSynthesisError, match="onnx session exploded"):
        await provider.synthesize("Hello", voice=DEFAULT_VOICE_MODEL)


async def test_a_model_that_disappears_after_load_is_a_provider_error(fake_piper, tmp_path) -> None:
    """The default voice itself is missing: this fails loudly rather than returning silence."""
    provider = PiperSynthesisProvider(voices_dir=tmp_path, timeout_seconds=5)

    with pytest.raises(SpeechSynthesisError, match="is not installed at"):
        await provider.synthesize("Hello", voice="en_US-ryan-medium")


async def test_mp3_mode_labels_the_bytes_correctly(fake_piper, tmp_path) -> None:
    provider = PiperSynthesisProvider(
        voices_dir=_installed(tmp_path), timeout_seconds=5, mp3_bit_rate=48
    )

    result = await provider.synthesize("Hello", voice=DEFAULT_VOICE_MODEL)

    assert result.content_type == "audio/mpeg"
    assert isinstance(result.audio, bytes), "the contract says bytes, not a bytearray"
    # A real MPEG stream: 11 bits of frame sync, or an ID3 tag in front of it.
    assert result.audio[:3] == b"ID3" or (
        result.audio[0] == 0xFF and (result.audio[1] & 0xE0) == 0xE0
    ), result.audio[:4]


async def test_mp3_is_much_smaller_than_the_wav_it_came_from(fake_piper, tmp_path) -> None:
    """The point of the encoder: the wire is the bottleneck, not the model."""
    FakePiperVoice.seconds = 0.5
    voice_dir = _installed(tmp_path)
    text = "Hello, let us review the overlay residual on the scanner."

    wav = await PiperSynthesisProvider(voices_dir=voice_dir, timeout_seconds=5).synthesize(
        text, voice=DEFAULT_VOICE_MODEL
    )
    mp3 = await PiperSynthesisProvider(
        voices_dir=voice_dir, timeout_seconds=5, mp3_bit_rate=48
    ).synthesize(text, voice=DEFAULT_VOICE_MODEL)

    assert wav.content_type == "audio/wav"
    assert len(mp3.audio) < len(wav.audio) / 2


async def test_a_missing_lameenc_is_a_provider_error(fake_piper, tmp_path, monkeypatch) -> None:
    """A configured bit rate with no encoder must fail loudly, not silently serve WAV."""
    monkeypatch.setitem(sys.modules, "lameenc", None)
    provider = PiperSynthesisProvider(
        voices_dir=_installed(tmp_path), timeout_seconds=5, mp3_bit_rate=48
    )

    with pytest.raises(SpeechSynthesisError, match="lameenc is not installed"):
        await provider.synthesize("Hello", voice=DEFAULT_VOICE_MODEL)
