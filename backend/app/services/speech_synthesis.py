"""Synthesis as an output method (docs/meeting-mode-v0.1.md §9).

The rules that shape this module:

1. It is not a message endpoint. Nothing is created, no session changes: a meeting turn is stored
   when it is generated, and speaking it adds nothing.
2. The audio is never stored (§9.2). It exists as the response body and nowhere else — no file, no
   cache, no row. The price is re-synthesising on replay, which is a few hundred milliseconds.
3. Text and voice are checked before a provider is called: an unspeakable line is 422, not a learner
   watching a spinner while a voice service is asked to say nothing.
4. Provider timeout -> 504, provider failure -> 502; both retryable.
"""

from __future__ import annotations

from app.ai.speech_synthesis import (
    SpeechSynthesisError,
    SpeechSynthesisProvider,
    SynthesisResult,
)
from app.ai.voices import is_known_voice
from app.core.config import settings
from app.services.practice import PracticeError


async def synthesize_line(
    provider: SpeechSynthesisProvider,
    *,
    text: str,
    voice: str,
) -> SynthesisResult:
    """Validate one line, then hand it to the synthesiser.

    Raises ``PracticeError`` carrying the code the client branches on.
    """
    spoken = text.strip()
    if not spoken:
        raise PracticeError(422, "validation_error", "There is nothing to say.")
    if len(spoken) > settings.speech_synthesis_max_chars:
        raise PracticeError(
            422,
            "validation_error",
            f"A line of at most {settings.speech_synthesis_max_chars} characters can be spoken.",
        )
    if not is_known_voice(voice):
        # The catalog lives on the server: an unknown name is a client bug or an edited scenario,
        # and either way it must fail now rather than as a silent no-op on the phone.
        raise PracticeError(422, "validation_error", f"Voice {voice!r} is not available.")

    try:
        return await provider.synthesize(spoken, voice=voice)
    except TimeoutError as exc:
        raise PracticeError(
            504, "ai_provider_timeout", "Speech synthesis timed out; the line can be retried."
        ) from exc
    except SpeechSynthesisError as exc:
        raise PracticeError(502, "ai_provider_error", "Speech synthesis failed.") from exc
