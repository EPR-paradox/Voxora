"""Speech synthesis contract (docs/meeting-mode-v0.1.md §9, design §14.2).

What these tests protect:

- the response is audio the phone can hand to a player, and it is marked ``no-store``,
- a line nobody can speak (empty, too long, unknown voice) is a 422 before any provider is called,
- provider timeout -> 504, provider failure -> 502,
- and nothing about a spoken line is written anywhere.
"""

from __future__ import annotations

import io
import wave
from contextlib import asynccontextmanager

from conftest import ApiHarness, build_harness
from sqlalchemy import func, select

from app.ai.speech_synthesis import FakeSpeechSynthesisProvider, SpeechSynthesisError
from app.ai.voices import VOICE_CATALOG
from app.core.config import settings
from app.db.models import Message, PracticeSession

ENDPOINT = "/api/v1/practice/speech/synthesis"
VOICE = VOICE_CATALOG[0]


@asynccontextmanager
async def failing_harness(tmp_path, error: Exception):
    """A harness whose synthesiser always fails with ``error``."""
    provider = FakeSpeechSynthesisProvider()
    provider.fail_with = error
    async with build_harness(
        f"sqlite+aiosqlite:///{tmp_path / f'synthesis-{type(error).__name__}.db'}",
        speech_synthesis_provider=provider,
    ) as harness:
        yield harness


async def post_line(
    api: ApiHarness, *, text: str = "Can I flag one risk before we move on?", voice: str = VOICE
):
    return await api.client.post(ENDPOINT, json={"text": text, "voice": voice})


async def test_a_line_comes_back_as_playable_audio(api: ApiHarness) -> None:
    response = await post_line(api)

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    # The fake returns a real WAV, so this test would catch a fake that returns unusable bytes.
    with wave.open(io.BytesIO(response.content), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getframerate() == 24000


async def test_the_audio_is_marked_no_store(api: ApiHarness) -> None:
    """§9.2: generated for this playback and kept nowhere — not on the phone, not in a proxy."""
    response = await post_line(api)

    assert response.headers["cache-control"] == "no-store"


async def test_synthesis_writes_nothing(api: ApiHarness) -> None:
    await post_line(api)

    async with api.session_factory() as session:
        sessions = await session.scalar(select(func.count()).select_from(PracticeSession))
        messages = await session.scalar(select(func.count()).select_from(Message))

    assert (sessions, messages) == (0, 0)


async def test_an_empty_line_is_rejected(api: ApiHarness) -> None:
    response = await post_line(api, text="   ")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_an_over_long_line_is_rejected(api: ApiHarness) -> None:
    response = await post_line(api, text="a" * (settings.speech_synthesis_max_chars + 1))

    assert response.status_code == 422


async def test_an_unknown_voice_is_rejected_before_the_provider_runs(api: ApiHarness) -> None:
    """A catalog rename on the server must not become a silent no-op on the phone."""
    response = await post_line(api, voice="en-US-VanishedNeural")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_a_provider_timeout_maps_to_504(tmp_path) -> None:
    async with failing_harness(tmp_path, TimeoutError("too slow")) as harness:
        response = await post_line(harness)

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "ai_provider_timeout"


async def test_a_provider_failure_maps_to_502(tmp_path) -> None:
    async with failing_harness(
        tmp_path, SpeechSynthesisError("voice service fell over")
    ) as harness:
        response = await post_line(harness)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "ai_provider_error"


async def test_a_failure_body_does_not_leak_internals(tmp_path) -> None:
    async with failing_harness(tmp_path, SpeechSynthesisError("/home/j/secret.wav")) as harness:
        response = await post_line(harness)

    assert response.status_code == 502
    assert "/home/" not in response.text
    assert "Traceback" not in response.text
