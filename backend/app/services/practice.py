from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.roleplay import RoleplayProvider
from app.core.config import settings
from app.db.models import Evaluation, Message, PracticeSession, Scenario, User


@dataclass
class PracticeError(Exception):
    status_code: int
    code: str
    message: str


async def create_practice_session(
    session: AsyncSession,
    *,
    scenario_id: UUID,
    provider: RoleplayProvider,
) -> tuple[PracticeSession, UUID, str, Message]:
    scenario = await session.scalar(
        select(Scenario).where(
            Scenario.id == scenario_id,
            Scenario.status == "published",
        )
    )
    if scenario is None:
        raise PracticeError(404, "resource_not_found", "Scenario not found.")

    user = await session.get(User, settings.local_user_id)
    if user is None or user.status != "active":
        raise RuntimeError("Local practice user is not seeded or active.")

    snapshot = {
        "id": str(scenario.id),
        "slug": scenario.slug,
        "title": scenario.title,
        "version": scenario.version,
        "situation": scenario.situation,
        "ai_character": scenario.ai_character,
        # Copied into the snapshot like every other roleplay input: a session must keep the cast it
        # started with, even if the scenario is edited later (docs/meeting-mode-v0.1.md §2).
        "cast": scenario.cast,
        "user_objective": scenario.user_objective,
        "target_skills": scenario.target_skills,
        "target_expressions": scenario.target_expressions,
        "roleplay_instructions": scenario.roleplay_instructions,
        "evaluation_rubric": scenario.evaluation_rubric,
    }
    scenario_id_value = scenario.id
    scenario_version = scenario.version
    await session.rollback()

    try:
        opening_line = await provider.opening_message(snapshot)
    except TimeoutError as exc:
        raise PracticeError(504, "ai_provider_timeout", "The roleplay provider timed out.") from exc
    except Exception as exc:
        raise PracticeError(502, "ai_provider_error", "The roleplay provider failed.") from exc

    now = datetime.now(timezone.utc)
    practice_session = PracticeSession(
        id=uuid4(),
        user_id=settings.local_user_id,
        scenario_id=scenario_id_value,
        scenario_version=scenario_version,
        scenario_snapshot=snapshot,
        status="active",
        input_mode="text",
        turn_count=0,
        last_activity_at=now,
        started_at=now,
    )
    opening_message = Message(
        id=uuid4(),
        session_id=practice_session.id,
        turn_index=0,
        seq=1,
        role="assistant",
        content=opening_line,
        status="completed",
    )
    session.add(practice_session)
    await session.flush()
    session.add(opening_message)
    await session.flush()
    await session.commit()
    return practice_session, scenario_id_value, snapshot["title"], opening_message


async def list_practice_sessions(
    session: AsyncSession,
    *,
    status: str | None,
    limit: int,
    offset: int,
) -> tuple[list[tuple[PracticeSession, str | None]], int]:
    """A learner's own sessions, newest activity first.

    The evaluation status comes back with the session rows: the home screen must tell "resume this"
    from "read the report" in one request, and a per-row fetch would be an obvious N+1.
    """
    filters = [PracticeSession.user_id == settings.local_user_id]
    if status is not None:
        filters.append(PracticeSession.status == status)

    total = await session.scalar(select(func.count()).select_from(PracticeSession).where(*filters))
    rows = await session.execute(
        select(PracticeSession, Evaluation.status)
        .outerjoin(Evaluation, Evaluation.session_id == PracticeSession.id)
        .where(*filters)
        .order_by(PracticeSession.last_activity_at.desc(), PracticeSession.id)
        .limit(limit)
        .offset(offset)
    )
    return [
        (practice_session, evaluation_status) for practice_session, evaluation_status in rows
    ], (total or 0)


async def get_practice_session(
    session: AsyncSession, *, session_id: UUID
) -> tuple[PracticeSession, list[Message]]:
    practice_session = await session.scalar(
        select(PracticeSession).where(
            PracticeSession.id == session_id,
            PracticeSession.user_id == settings.local_user_id,
        )
    )
    if practice_session is None:
        raise PracticeError(404, "resource_not_found", "Practice session not found.")
    messages = list(
        await session.scalars(
            select(Message)
            .where(Message.session_id == practice_session.id)
            .order_by(Message.turn_index, Message.seq)
        )
    )
    return practice_session, messages


async def send_practice_message(
    session: AsyncSession,
    *,
    session_id: UUID,
    client_message_id: UUID,
    content: str,
    provider: RoleplayProvider,
) -> tuple[Message, Message, bool]:
    async with session.begin():
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
        if practice_session.status != "active":
            raise PracticeError(
                409, "session_not_active", "This practice session is no longer active."
            )

        existing_message = await session.scalar(
            select(Message).where(
                Message.session_id == practice_session.id,
                Message.client_message_id == client_message_id,
                Message.role == "user",
            )
        )
        if existing_message is not None and existing_message.content != content:
            raise PracticeError(
                409, "idempotency_conflict", "Message ID was already used for different content."
            )
        if practice_session.processing_turn_id is not None:
            raise PracticeError(409, "turn_in_progress", "Another message is being processed.")

        if existing_message is not None and existing_message.status == "completed":
            assistant_message = await session.scalar(
                select(Message).where(
                    Message.session_id == practice_session.id,
                    Message.turn_index == existing_message.turn_index,
                    Message.role == "assistant",
                )
            )
            if assistant_message is not None:
                return existing_message, assistant_message, True
            raise RuntimeError("Completed user message is missing its assistant response.")

        if existing_message is None:
            user_message = Message(
                id=uuid4(),
                session_id=practice_session.id,
                client_message_id=client_message_id,
                turn_index=practice_session.turn_count + 1,
                seq=await _next_message_seq(session, practice_session.id),
                role="user",
                content=content,
                status="pending",
            )
            session.add(user_message)
        else:
            user_message = existing_message
            user_message.status = "pending"

        practice_session.processing_turn_id = user_message.id
        await session.flush()
        turn_index = user_message.turn_index
        scenario_snapshot = practice_session.scenario_snapshot
        user_message_id = user_message.id

    history_rows = await session.scalars(
        select(Message)
        .where(
            Message.session_id == session_id,
            Message.turn_index < turn_index,
            Message.status == "completed",
        )
        .order_by(Message.turn_index, Message.seq)
    )
    history = [{"role": message.role, "content": message.content} for message in history_rows]
    await session.rollback()

    try:
        assistant_content = await provider.reply(scenario_snapshot, history, content)
    except TimeoutError as exc:
        await _mark_message_failed(session, session_id, user_message_id)
        raise PracticeError(504, "ai_provider_timeout", "The roleplay provider timed out.") from exc
    except Exception as exc:
        await _mark_message_failed(session, session_id, user_message_id)
        raise PracticeError(502, "ai_provider_error", "The roleplay provider failed.") from exc

    async with session.begin():
        practice_session = await session.scalar(
            select(PracticeSession).where(PracticeSession.id == session_id).with_for_update()
        )
        user_message = await session.get(Message, user_message_id)
        if practice_session is None or user_message is None:
            raise RuntimeError("Practice session state disappeared while generating a reply.")

        user_message.status = "completed"
        assistant_message = Message(
            id=uuid4(),
            session_id=session_id,
            turn_index=turn_index,
            seq=await _next_message_seq(session, session_id),
            role="assistant",
            content=assistant_content,
            status="completed",
        )
        session.add(assistant_message)
        practice_session.turn_count = max(practice_session.turn_count, turn_index)
        practice_session.processing_turn_id = None
        practice_session.last_activity_at = datetime.now(timezone.utc)
        await session.flush()

    return user_message, assistant_message, False


async def _next_message_seq(session: AsyncSession, session_id: UUID) -> int:
    """Next display position inside a session (docs/meeting-mode-v0.1.md §3).

    Read inside the same transaction that writes the row, after the session row has been locked: two
    turns cannot run at once for one session, so the numbers stay gap-free per session without a
    sequence object.
    """
    current = await session.scalar(
        select(func.max(Message.seq)).where(Message.session_id == session_id)
    )
    return (current or 0) + 1


async def _mark_message_failed(
    session: AsyncSession, session_id: UUID, user_message_id: UUID
) -> None:
    async with session.begin():
        practice_session = await session.scalar(
            select(PracticeSession).where(PracticeSession.id == session_id).with_for_update()
        )
        user_message = await session.get(Message, user_message_id)
        if practice_session is not None and user_message is not None:
            user_message.status = "failed"
            practice_session.turn_count = max(practice_session.turn_count, user_message.turn_index)
            if practice_session.processing_turn_id == user_message_id:
                practice_session.processing_turn_id = None
