"""Speech transcription contract (design §7.11, §14.2).

What these tests protect:

- the error codes the client branches on (413 / 415 / 422 / 502 / 504),
- that a clip with no usable speech is a 422 and never an empty message,
- and that nothing about a transcription is written anywhere: no session, no message, no file.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from conftest import ApiHarness, build_harness
from sqlalchemy import func, select

from app.ai.speech import FakeSpeechProvider, SpeechNotRecognized, SpeechProviderError
from app.core.config import settings
from app.db.models import Message, PracticeSession

ENDPOINT = "/api/v1/practice/speech/transcriptions"


def audio_bytes(size: int = 2048) -> bytes:
    return b"\x00\x01\x02\x03" * (size // 4)


@asynccontextmanager
async def failing_harness(tmp_path, error: Exception):
    """A harness whose transcription provider always fails with ``error``."""
    provider = FakeSpeechProvider()
    provider.fail_with = error
    async with build_harness(
        f"sqlite+aiosqlite:///{tmp_path / f'speech-{type(error).__name__}.db'}",
        speech_provider=provider,
    ) as harness:
        yield harness


async def post_clip(
    api: ApiHarness,
    *,
    data: bytes | None = None,
    content_type: str = "audio/m4a",
    language: str = "en",
    duration_ms: int | None = None,
):
    files = {"audio_file": ("clip.m4a", data if data is not None else audio_bytes(), content_type)}
    form: dict[str, str] = {"language": language}
    if duration_ms is not None:
        form["duration_ms"] = str(duration_ms)
    return await api.client.post(ENDPOINT, files=files, data=form)


async def test_a_clip_comes_back_as_text(api: ApiHarness) -> None:
    response = await post_clip(api, duration_ms=2400)

    assert response.status_code == 200
    payload = response.json()
    assert payload["text"] == "I was responsible for the calibration service."
    assert payload["language"] == "en"
    assert payload["duration_ms"] == 2400
    assert payload["provider"] == "fake"
    assert payload["model"] == "fake-v1"


async def test_transcription_writes_nothing(api: ApiHarness) -> None:
    """It is an input method: no session, no message, no state (§7.11 rules 1, 2, 7)."""
    await post_clip(api)

    async with api.session_factory() as session:
        sessions = await session.scalar(select(func.count()).select_from(PracticeSession))
        messages = await session.scalar(select(func.count()).select_from(Message))

    assert (sessions, messages) == (0, 0)


async def test_an_unsupported_type_is_rejected(api: ApiHarness) -> None:
    response = await post_clip(api, content_type="text/plain")

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"


async def test_a_clip_over_the_byte_ceiling_is_rejected(api: ApiHarness, monkeypatch) -> None:
    monkeypatch.setattr(settings, "speech_max_bytes", 1024)

    response = await post_clip(api, data=audio_bytes(4096))

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


async def test_a_clip_over_the_duration_ceiling_is_rejected(api: ApiHarness) -> None:
    response = await post_clip(api, duration_ms=(settings.speech_max_seconds + 1) * 1000)

    assert response.status_code == 413


async def test_an_empty_upload_is_rejected(api: ApiHarness) -> None:
    response = await post_clip(api, data=b"")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_silence_is_a_422_not_an_empty_message(tmp_path) -> None:
    async with failing_harness(tmp_path, SpeechNotRecognized("No speech here.")) as harness:
        response = await post_clip(harness)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "speech_not_recognized"


async def test_a_provider_timeout_maps_to_504(tmp_path) -> None:
    async with failing_harness(tmp_path, TimeoutError("too slow")) as harness:
        response = await post_clip(harness)

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "ai_provider_timeout"


async def test_a_provider_failure_maps_to_502(tmp_path) -> None:
    async with failing_harness(tmp_path, SpeechProviderError("decoder exploded")) as harness:
        response = await post_clip(harness)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "ai_provider_error"


async def test_a_rejected_upload_does_not_leak_internals(api: ApiHarness) -> None:
    """§7.12: no traceback, no path, no provider credentials in the body."""
    response = await post_clip(api, content_type="application/octet-stream")

    body = response.text
    assert response.status_code == 415
    assert "/home/" not in body
    assert "Traceback" not in body
