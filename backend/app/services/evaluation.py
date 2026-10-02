"""Session finish, evaluation generation and retry (design §7.8, §7.9, §9.2).

Transaction shape follows §9.3: the model call never shares a transaction with the database.
Transaction A
locks the session, flips it to ``completed`` and puts its evaluation row into ``processing``; the
model
runs outside any transaction; transaction B writes the outcome. A crash between A and B leaves a
``processing`` row, which is what the §9.2 state machine expects an explicit retry to pick up.

A failed evaluation does not fail the request. Finishing a session and producing its report are
different
things, and the session really is finished either way: the response carries ``evaluation_status``
plus an
``error_code``, so the first call and a replay have the same shape and the client keeps one code
path.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.evaluation import EvaluationOutputError, EvaluationProvider, EvaluationRequest
from app.core.config import settings
from app.db.models import Evaluation, Message, PracticeSession
from app.services.practice import PracticeError


async def finish_practice_session(
    session: AsyncSession,
    *,
    session_id: UUID,
    provider: EvaluationProvider,
) -> tuple[PracticeSession, Evaluation]:
    """Complete a session and produce its evaluation. Idempotent: a second call replays the stored
    report."""
    async with session.begin():
        practice_session = await _lock_session(session, session_id)
        if practice_session.status == "abandoned":
            raise PracticeError(409, "session_not_active", "This practice session was abandoned.")

        evaluation = await session.scalar(
            select(Evaluation).where(Evaluation.session_id == practice_session.id)
        )
        if (
            practice_session.status == "completed"
            and evaluation is not None
            and evaluation.status == "completed"
        ):
            return practice_session, evaluation

        if practice_session.processing_turn_id is not None:
            raise PracticeError(409, "turn_in_progress", "A reply is still being generated.")

        turn_count = await session.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.session_id == practice_session.id,
                Message.role == "user",
                Message.status == "completed",
            )
        )
        if not turn_count:
            raise PracticeError(
                409, "session_has_no_user_turns", "This session has no learner turns to evaluate."
            )

        now = datetime.now(timezone.utc)
        practice_session.status = "completed"
        practice_session.completed_at = now
        practice_session.last_activity_at = now

        evaluation = _start_attempt(evaluation, practice_session.id, provider)
        session.add(evaluation)
        await session.flush()
        # Resolve everything the post-transaction work needs while the objects are still loaded: the
        # rollback in _run_attempt expires them, and touching an expired attribute outside greenlet
        # context raises instead of lazy-loading.
        evaluation_id = evaluation.id
        session_id_value = practice_session.id
        snapshot = dict(practice_session.scenario_snapshot)

    await _run_attempt(session, evaluation_id, session_id_value, snapshot, provider)
    return await _read_result(session, session_id_value, evaluation_id)


async def retry_evaluation(
    session: AsyncSession,
    *,
    session_id: UUID,
    provider: EvaluationProvider,
) -> tuple[PracticeSession, Evaluation]:
    """Re-run a failed evaluation on the same row (a session never gets a second evaluation row)."""
    async with session.begin():
        practice_session = await _lock_session(session, session_id)
        if practice_session.status != "completed":
            raise PracticeError(
                409, "session_not_active", "Finish the practice session before evaluating it."
            )

        evaluation = await session.scalar(
            select(Evaluation).where(Evaluation.session_id == practice_session.id).with_for_update()
        )
        if evaluation is None:
            raise PracticeError(404, "evaluation_not_found", "This session has no evaluation yet.")
        if evaluation.status == "completed":
            return practice_session, evaluation
        if evaluation.status == "processing":
            raise PracticeError(
                409, "evaluation_in_progress", "An evaluation for this session is already running."
            )

        evaluation = _start_attempt(evaluation, practice_session.id, provider)
        await session.flush()
        evaluation_id = evaluation.id
        session_id_value = practice_session.id
        snapshot = dict(practice_session.scenario_snapshot)

    await _run_attempt(session, evaluation_id, session_id_value, snapshot, provider)
    return await _read_result(session, session_id_value, evaluation_id)


async def get_evaluation(
    session: AsyncSession, *, session_id: UUID
) -> tuple[PracticeSession, Evaluation | None]:
    practice_session = await session.scalar(
        select(PracticeSession).where(
            PracticeSession.id == session_id,
            PracticeSession.user_id == settings.local_user_id,
        )
    )
    if practice_session is None:
        raise PracticeError(404, "resource_not_found", "Practice session not found.")
    evaluation = await session.scalar(
        select(Evaluation).where(Evaluation.session_id == practice_session.id)
    )
    return practice_session, evaluation


async def _lock_session(session: AsyncSession, session_id: UUID) -> PracticeSession:
    practice_session = await session.scalar(
        select(PracticeSession)
        .where(
            PracticeSession.id == session_id,
            PracticeSession.user_id == settings.local_user_id,
        )
        .with_for_update()
    )
    if practice_session is None:
        raise PracticeError(404, "resource_not_found", "Practice session not found.")
    return practice_session


def _start_attempt(
    evaluation: Evaluation | None, session_id: UUID, provider: EvaluationProvider
) -> Evaluation:
    """Reuse the session's single evaluation row, or open it; either way the attempt counter moves.
    Reuse the session's single evaluation row, or open it; either way the attempt counter moves."""
    if evaluation is None:
        return Evaluation(
            id=uuid4(),
            session_id=session_id,
            status="processing",
            rubric_version=provider.rubric_version,
            provider=provider.name,
            model=provider.model,
            prompt_version=provider.prompt_version,
            attempt_count=1,
        )
    evaluation.status = "processing"
    evaluation.provider = provider.name
    evaluation.model = provider.model
    evaluation.prompt_version = provider.prompt_version
    evaluation.rubric_version = provider.rubric_version
    evaluation.result = None
    evaluation.error_code = None
    evaluation.attempt_count += 1
    return evaluation


async def _run_attempt(
    session: AsyncSession,
    evaluation_id: UUID,
    session_id: UUID,
    snapshot: dict,
    provider: EvaluationProvider,
) -> None:
    transcript = await _completed_transcript(session, session_id)
    await session.rollback()

    request = EvaluationRequest(
        scenario=snapshot,
        transcript=transcript,
        user_objective=snapshot.get("user_objective", ""),
    )
    result: dict | None = None
    error_code: str | None = None
    try:
        result = await provider.evaluate(request)
    except TimeoutError:
        error_code = "ai_provider_timeout"
    except EvaluationOutputError:
        # The model answered, but not in a form that can be trusted as a language report (§8.3).
        error_code = "invalid_ai_output"
    except Exception:
        error_code = "ai_provider_error"

    async with session.begin():
        evaluation = await session.scalar(
            select(Evaluation)
            .where(Evaluation.id == evaluation_id)
            .execution_options(populate_existing=True)
        )
        if evaluation is None:
            raise RuntimeError("Evaluation row disappeared while generating the report.")
        if error_code is None:
            evaluation.status = "completed"
            evaluation.result = result
            evaluation.error_code = None
        else:
            evaluation.status = "failed"
            evaluation.result = None
            evaluation.error_code = error_code


async def _completed_transcript(session: AsyncSession, session_id: UUID) -> list[dict[str, str]]:
    """Only finished turns: the evaluator must never see a half-written exchange."""
    rows = await session.scalars(
        select(Message)
        .where(
            Message.session_id == session_id,
            Message.status == "completed",
        )
        .order_by(Message.turn_index, Message.created_at, Message.id)
    )
    return [{"role": message.role, "content": message.content} for message in rows]


async def _read_result(
    session: AsyncSession, session_id: UUID, evaluation_id: UUID
) -> tuple[PracticeSession, Evaluation]:
    practice_session = await session.get(PracticeSession, session_id)
    evaluation = await session.scalar(
        select(Evaluation)
        .where(Evaluation.id == evaluation_id)
        .execution_options(populate_existing=True)
    )
    if practice_session is None or evaluation is None:
        raise RuntimeError("Session or evaluation disappeared after generation.")
    return practice_session, evaluation
