"""Speech endpoints: transcription in (design §7.11), synthesis out (docs/meeting-mode-v0.1.md §9).

`POST /api/v1/practice/speech/transcriptions` takes one clip and returns text; `POST .../synthesis`
takes one line of text and returns audio. Neither is scoped to a session: transcription does not
depend on the scenario, and neither does speaking a line, so binding either to a session would be a
contract change rather than a new field (§7.11 rule 6).

The upload is read with a hard byte ceiling. Starlette would happily spool a 200 MB body to disk
before we ever see it, and "the audio was too large" must not cost a disk write of the audio.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from fastapi.responses import JSONResponse

from app.ai.speech import SpeechProvider
from app.ai.speech_synthesis import SpeechSynthesisProvider
from app.api.deps import (
    get_speech_provider,
    get_speech_synthesis_provider,
    require_practice_access,
)
from app.api.errors import error_response
from app.core.config import settings
from app.services.practice import PracticeError
from app.services.speech import transcribe_audio
from app.services.speech_synthesis import synthesize_line
from app.speech_schemas import SynthesisRequest, TranscriptionResponse

router = APIRouter(
    prefix="/api/v1/practice/speech",
    tags=["speech"],
    dependencies=[Depends(require_practice_access)],
)

_READ_CHUNK_BYTES = 1 << 16


@router.post("/transcriptions", response_model=TranscriptionResponse)
async def create_transcription(
    request: Request,
    audio_file: Annotated[UploadFile, File(description="One recorded clip.")],
    provider: Annotated[SpeechProvider, Depends(get_speech_provider)],
    language: Annotated[str, Form()] = "en",
    duration_ms: Annotated[int | None, Form()] = None,
) -> TranscriptionResponse | JSONResponse:
    try:
        audio = await _read_upload(audio_file)
        result = await transcribe_audio(
            provider,
            audio=audio,
            content_type=audio_file.content_type or "",
            language=language,
            duration_ms=duration_ms,
        )
    except PracticeError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )

    return TranscriptionResponse(
        text=result.text,
        language=result.language,
        duration_ms=result.duration_ms or duration_ms,
        provider=result.provider,
        model=result.model,
    )


async def _read_upload(upload: UploadFile) -> bytes:
    """Read the clip, refusing to buffer more than the configured ceiling."""
    limit = settings.speech_max_bytes
    buffer = bytearray()
    while True:
        chunk = await upload.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > limit:
            raise PracticeError(413, "payload_too_large", "The audio clip is too large.")
    if not buffer:
        raise PracticeError(422, "validation_error", "The audio clip is empty.")
    return bytes(buffer)


@router.post("/synthesis", response_class=Response)
async def create_synthesis(
    request: Request,
    payload: SynthesisRequest,
    provider: Annotated[SpeechSynthesisProvider, Depends(get_speech_synthesis_provider)],
) -> Response:
    """Speak one line and return the audio.

    The response carries ``Cache-Control: no-store``: the audio is generated for this playback and
    is not kept anywhere (§9.2), and neither the phone nor an intermediary should keep a copy of a
    voice the learner may never hear again.
    """
    try:
        result = await synthesize_line(provider, text=payload.text, voice=payload.voice)
    except PracticeError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )

    return Response(
        content=result.audio,
        media_type=result.content_type,
        headers={"Cache-Control": "no-store"},
    )
