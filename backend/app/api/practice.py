"""Finish a session, read its evaluation, retry a failed report (design §7.8, §7.9)."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.evaluation import EvaluationProvider
from app.ai.roleplay import RoleplayProvider
from app.api.deps import (
    get_db_session,
    get_evaluation_provider,
    get_roleplay_provider,
    require_practice_access,
)
from app.api.errors import error_response
from app.db.models import Evaluation, Message, PracticeSession
from app.evaluation_schemas import (
    EvaluationPayload,
    EvaluationStatusResponse,
    FinishPracticeSessionRequest,
)
from app.practice_schemas import (
    AdvanceMeetingRequest,
    AdvanceMeetingResponse,
    CreatePracticeSessionRequest,
    OpeningMessage,
    PracticeMessageDetail,
    PracticeMessageResponse,
    PracticeSessionCreated,
    PracticeSessionDetail,
    PracticeSessionListResponse,
    PracticeSessionSummary,
    ScenarioParticipant,
    ScenarioReference,
    SendPracticeMessageRequest,
    SendPracticeMessageResponse,
)
from app.scenario_cast import participant_payloads
from app.services.evaluation import finish_practice_session, get_evaluation, retry_evaluation
from app.services.practice import (
    PracticeError,
    advance_meeting,
    create_practice_session,
    get_practice_session,
    list_practice_sessions,
    send_practice_message,
)

router = APIRouter(
    prefix="/api/v1/practice/sessions",
    tags=["practice"],
    dependencies=[Depends(require_practice_access)],
)

_RETRYABLE_UNFINISHED = ("pending", "processing")


@router.get("", response_model=PracticeSessionListResponse)
async def list_sessions(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    status: Annotated[
        Literal["active", "completed", "abandoned"] | None,
        Query(description="Filter by session state."),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PracticeSessionListResponse:
    """The learner's own practice history, newest activity first (§7.7)."""
    rows, total = await list_practice_sessions(session, status=status, limit=limit, offset=offset)
    items = []
    for practice_session, evaluation_status in rows:
        snapshot = practice_session.scenario_snapshot
        items.append(
            PracticeSessionSummary(
                id=practice_session.id,
                scenario=ScenarioReference(id=UUID(snapshot["id"]), title=snapshot["title"]),
                status=practice_session.status,
                turn_count=practice_session.turn_count,
                evaluation_status=evaluation_status,
                started_at=practice_session.started_at,
                last_activity_at=practice_session.last_activity_at,
                completed_at=practice_session.completed_at,
            )
        )
    return PracticeSessionListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=PracticeSessionCreated, status_code=201)
async def create_session(
    body: CreatePracticeSessionRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    provider: Annotated[RoleplayProvider, Depends(get_roleplay_provider)],
) -> PracticeSessionCreated | JSONResponse:
    try:
        (
            practice_session,
            scenario_id,
            scenario_title,
            opening_messages,
        ) = await create_practice_session(
            session,
            scenario_id=body.scenario_id,
            provider=provider,
        )
    except PracticeError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )

    participants = _participants(practice_session.scenario_snapshot)
    return PracticeSessionCreated(
        id=practice_session.id,
        scenario=ScenarioReference(id=scenario_id, title=scenario_title),
        status="active",
        input_mode="text",
        participants=participants,
        messages=[
            OpeningMessage(
                id=opening.id,
                turn_index=opening.turn_index,
                seq=opening.seq,
                role="assistant",
                speaker_key=opening.speaker_key,
                speaker=_speaker(participants, opening.speaker_key),
                content=opening.content,
                status="completed",
            )
            for opening in opening_messages
        ],
        started_at=practice_session.started_at,
    )


@router.get("/{session_id}", response_model=PracticeSessionDetail)
async def read_session(
    session_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PracticeSessionDetail | JSONResponse:
    try:
        practice_session, messages = await get_practice_session(session, session_id=session_id)
    except PracticeError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )

    snapshot = practice_session.scenario_snapshot
    participants = _participants(snapshot)
    return PracticeSessionDetail(
        id=practice_session.id,
        scenario=ScenarioReference(
            id=UUID(snapshot["id"]),
            title=snapshot["title"],
        ),
        status=practice_session.status,
        input_mode=practice_session.input_mode,
        scenario_version=practice_session.scenario_version,
        turn_count=practice_session.turn_count,
        participants=participants,
        messages=[_message_detail(message, participants) for message in messages],
        started_at=practice_session.started_at,
        completed_at=practice_session.completed_at,
    )


@router.post(
    "/{session_id}/messages",
    response_model=SendPracticeMessageResponse,
    status_code=201,
)
async def post_message(
    session_id: UUID,
    body: SendPracticeMessageRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    provider: Annotated[RoleplayProvider, Depends(get_roleplay_provider)],
) -> SendPracticeMessageResponse | JSONResponse:
    try:
        practice_session, user_message, assistant_messages, replayed = await send_practice_message(
            session,
            session_id=session_id,
            client_message_id=body.client_message_id,
            content=body.content,
            provider=provider,
        )
    except PracticeError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )

    if replayed:
        response.status_code = 200
    participants = _participants(practice_session.scenario_snapshot)
    return SendPracticeMessageResponse(
        user_message=_message_response(user_message, participants),
        assistant_messages=[
            _message_response(message, participants) for message in assistant_messages
        ],
        session_status="active",
    )


@router.post("/{session_id}/advance", response_model=AdvanceMeetingResponse)
async def post_advance(
    session_id: UUID,
    body: AdvanceMeetingRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    provider: Annotated[RoleplayProvider, Depends(get_roleplay_provider)],
) -> AdvanceMeetingResponse | JSONResponse:
    """Let the meeting continue while the learner listens (design §7.14).

    Not a message endpoint: no learner turn is created, and ``turn_count`` does not move. What the
    room said is appended as its own round, in one transaction, exactly as a reply to a spoken turn
    would be.
    """
    try:
        practice_session, assistant_messages, remaining = await advance_meeting(
            session,
            session_id=session_id,
            provider=provider,
            after_seq=body.after_seq,
        )
    except PracticeError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )

    participants = _participants(practice_session.scenario_snapshot)
    return AdvanceMeetingResponse(
        assistant_messages=[
            _message_response(message, participants) for message in assistant_messages
        ],
        session_status="active",
        advances_remaining=remaining,
    )


@router.post("/{session_id}/finish", response_model=EvaluationStatusResponse)
async def finish_session(
    session_id: UUID,
    body: FinishPracticeSessionRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    provider: Annotated[EvaluationProvider, Depends(get_evaluation_provider)],
) -> EvaluationStatusResponse | JSONResponse:
    """End the practice and generate the report. Idempotent; a failed report is reported in the
    body."""
    try:
        practice_session, evaluation = await finish_practice_session(
            session, session_id=session_id, provider=provider
        )
    except PracticeError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )
    return _evaluation_response(practice_session, evaluation)


@router.get("/{session_id}/evaluation", response_model=EvaluationStatusResponse)
async def read_evaluation(
    session_id: UUID,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EvaluationStatusResponse | JSONResponse:
    try:
        practice_session, evaluation = await get_evaluation(session, session_id=session_id)
    except PracticeError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )
    if evaluation is None:
        return error_response(
            request,
            status_code=404,
            code="evaluation_not_found",
            message="This session has no evaluation yet.",
        )
    if evaluation.status in _RETRYABLE_UNFINISHED:
        response.status_code = 202
    return _evaluation_response(practice_session, evaluation)


@router.post("/{session_id}/evaluation/retry", response_model=EvaluationStatusResponse)
async def retry_session_evaluation(
    session_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    provider: Annotated[EvaluationProvider, Depends(get_evaluation_provider)],
) -> EvaluationStatusResponse | JSONResponse:
    try:
        practice_session, evaluation = await retry_evaluation(
            session, session_id=session_id, provider=provider
        )
    except PracticeError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )
    return _evaluation_response(practice_session, evaluation)


def _participants(snapshot: dict) -> list[ScenarioParticipant]:
    """The people in this session's room, from its own snapshot (docs/meeting-mode-v0.1.md §4)."""
    return [ScenarioParticipant(**item) for item in participant_payloads(snapshot)]


def _speaker(participants: list[ScenarioParticipant], key: str) -> ScenarioParticipant | None:
    if not key:
        return None
    for participant in participants:
        if participant.key == key:
            return participant
    # A key the snapshot does not know: the scenario was edited after this session started, or a
    # provider bug invented it. Showing the raw key is ugly but truthful; falling back to the
    # learner would silently attribute someone else's words to them.
    return ScenarioParticipant(key=key, name=key, title="")


def _message_response(
    message: Message, participants: list[ScenarioParticipant]
) -> PracticeMessageResponse:
    return PracticeMessageResponse(
        id=message.id,
        client_message_id=message.client_message_id,
        turn_index=message.turn_index,
        seq=message.seq,
        role=message.role,
        speaker_key=message.speaker_key,
        speaker=_speaker(participants, message.speaker_key),
        content=message.content,
        created_at=message.created_at,
    )


def _message_detail(
    message: Message, participants: list[ScenarioParticipant]
) -> PracticeMessageDetail:
    payload = _message_response(message, participants)
    return PracticeMessageDetail(**payload.model_dump(), status=message.status)


def _evaluation_response(
    practice_session: PracticeSession, evaluation: Evaluation
) -> EvaluationStatusResponse:
    result = evaluation.result
    return EvaluationStatusResponse(
        session_id=practice_session.id,
        session_status=practice_session.status,
        evaluation_status=evaluation.status,
        evaluation=EvaluationPayload.model_validate(result) if result else None,
        error_code=evaluation.error_code,
        retryable=evaluation.status == "failed",
        attempt_count=evaluation.attempt_count,
        completed_at=practice_session.completed_at,
    )
