"""Finish a session, read its evaluation, retry a failed report (design §7.8, §7.9)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
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
from app.db.models import Evaluation, PracticeSession
from app.evaluation_schemas import (
    EvaluationPayload,
    EvaluationStatusResponse,
    FinishPracticeSessionRequest,
)
from app.practice_schemas import (
    CreatePracticeSessionRequest,
    OpeningMessage,
    PracticeMessageDetail,
    PracticeMessageResponse,
    PracticeSessionCreated,
    PracticeSessionDetail,
    ScenarioReference,
    SendPracticeMessageRequest,
    SendPracticeMessageResponse,
)
from app.services.evaluation import finish_practice_session, get_evaluation, retry_evaluation
from app.services.practice import (
    PracticeError,
    create_practice_session,
    get_practice_session,
    send_practice_message,
)

router = APIRouter(
    prefix="/api/v1/practice/sessions",
    tags=["practice"],
    dependencies=[Depends(require_practice_access)],
)

_RETRYABLE_UNFINISHED = ("pending", "processing")


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
            opening_message,
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

    return PracticeSessionCreated(
        id=practice_session.id,
        scenario=ScenarioReference(id=scenario_id, title=scenario_title),
        status="active",
        input_mode="text",
        messages=[
            OpeningMessage(
                id=opening_message.id,
                turn_index=0,
                role="assistant",
                content=opening_message.content,
                status="completed",
            )
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
        messages=[PracticeMessageDetail.model_validate(message) for message in messages],
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
        user_message, assistant_message, replayed = await send_practice_message(
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
    return SendPracticeMessageResponse(
        user_message=PracticeMessageResponse.model_validate(user_message),
        assistant_message=PracticeMessageResponse.model_validate(assistant_message),
        session_status="active",
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
