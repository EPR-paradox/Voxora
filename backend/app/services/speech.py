"""Transcription as an input method (design §7.11).

The rules that shape this module:

1. It is not a message endpoint. Nothing is created, no session changes, no ``turn_count``: the
client
   sends the text through the normal message path afterwards, with the normal idempotency rules.
2. Audio is never persisted. It lives as the request body and inside the provider's decoder, and the
   response is the only thing that leaves this function.
4. A clip with no usable speech is 422 ``speech_not_recognized``, not an empty string: an empty
   message is worse than an honest "say that again".
5. Provider timeout -> 504, provider failure -> 502; the learner can retry the same clip.
"""

from __future__ import annotations

from app.ai.speech import (
    SpeechNotRecognized,
    SpeechProvider,
    SpeechProviderError,
    TranscriptResult,
)
from app.core.config import settings
from app.services.practice import PracticeError

SPEECH_NOT_RECOGNIZED = "speech_not_recognized"


async def transcribe_audio(
    provider: SpeechProvider,
    *,
    audio: bytes,
    content_type: str,
    language: str,
    duration_ms: int | None = None,
) -> TranscriptResult:
    """Validate the clip, then hand it to the provider.

    Raises ``PracticeError`` carrying the §7.12 code the client branches on.
    """
    normalized_type = content_type.split(";", 1)[0].strip().lower()
    if normalized_type not in settings.speech_allowed_content_types:
        raise PracticeError(
            415,
            "unsupported_media_type",
            f"Audio type {normalized_type or 'unknown'!r} is not accepted.",
        )

    if len(audio) > settings.speech_max_bytes:
        raise PracticeError(413, "payload_too_large", "The audio clip is too large.")
    # ``duration_ms`` comes from the client, so treat it as a courtesy check: the byte cap is what
    # actually bounds the work the server does.
    if duration_ms is not None and duration_ms > settings.speech_max_seconds * 1000:
        raise PracticeError(
            413,
            "payload_too_large",
            f"Clips longer than {settings.speech_max_seconds} seconds are not accepted.",
        )

    try:
        result = await provider.transcribe(audio, content_type=normalized_type, language=language)
    except SpeechNotRecognized as exc:
        raise PracticeError(422, SPEECH_NOT_RECOGNIZED, str(exc)) from exc
    except TimeoutError as exc:
        raise PracticeError(
            504, "ai_provider_timeout", "Transcription timed out; the clip can be retried."
        ) from exc
    except SpeechProviderError as exc:
        raise PracticeError(502, "ai_provider_error", "Transcription failed.") from exc

    if not result.text.strip():
        # A provider must not hand back empty text either (§7.11 rule 4).
        raise PracticeError(422, SPEECH_NOT_RECOGNIZED, "No speech was recognised in this clip.")
    return result
