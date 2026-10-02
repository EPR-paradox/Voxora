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
) -> tuple[PracticeSession, UUID, str, list[Message]]:
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
        opening_turns = await provider.opening_turns(snapshot)
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
    session.add(practice_session)
    await session.flush()

    # The opening is one or more turns (a meeting opens with a short exchange), written in a single
    # transaction: a session that exists with half an opening would leave the learner guessing.
    opening_messages = [
        Message(
            id=uuid4(),
            session_id=practice_session.id,
            turn_index=0,
            seq=position,
            role="assistant",
            speaker_key=turn.speaker_key,
            content=turn.content,
            status="completed",
        )
        for position, turn in enumerate(opening_turns, start=1)
    ]
    session.add_all(opening_messages)
    await session.flush()
    await session.commit()
    return practice_session, scenario_id_value, snapshot["title"], opening_messages


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
) -> tuple[PracticeSession, Message, list[Message], bool]:
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
            assistant_messages = await _assistant_turns(session, existing_message)
            if assistant_messages:
                return practice_session, existing_message, assistant_messages, True
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
    history = [
        {"role": message.role, "speaker_key": message.speaker_key, "content": message.content}
        for message in history_rows
    ]
    await session.rollback()

    try:
        reply_turns = await provider.reply(scenario_snapshot, history, content)
    except TimeoutError as exc:
        await _mark_message_failed(session, session_id, user_message_id)
        raise PracticeError(504, "ai_provider_timeout", "The roleplay provider timed out.") from exc
    except Exception as exc:
        await _mark_message_failed(session, session_id, user_message_id)
        raise PracticeError(502, "ai_provider_error", "The roleplay provider failed.") from exc

    # A provider that answers with nothing violates its own contract; treat it as a provider failure
    # rather than writing a turn with no reply into the transcript.
    if not reply_turns:
        await _mark_message_failed(session, session_id, user_message_id)
        raise PracticeError(502, "ai_provider_error", "The roleplay provider returned no turns.")

    async with session.begin():
        practice_session = await session.scalar(
            select(PracticeSession).where(PracticeSession.id == session_id).with_for_update()
        )
        user_message = await session.get(Message, user_message_id)
        if practice_session is None or user_message is None:
            raise RuntimeError("Practice session state disappeared while generating a reply.")

        user_message.status = "completed"
        # The whole reply lands in one transaction with contiguous sequence numbers: a meeting where
        # only the first participant made it into the database is worse than a failed turn, because
        # nothing downstream can tell that two voices were lost (§9.3, meeting-mode §6).
        base_seq = await _next_message_seq(session, session_id)
        assistant_messages = [
            Message(
                id=uuid4(),
                session_id=session_id,
                turn_index=turn_index,
                seq=base_seq + offset,
                role="assistant",
                speaker_key=turn.speaker_key,
                content=turn.content,
                status="completed",
            )
            for offset, turn in enumerate(reply_turns)
        ]
        session.add_all(assistant_messages)
        practice_session.turn_count = max(practice_session.turn_count, turn_index)
        practice_session.processing_turn_id = None
        practice_session.last_activity_at = datetime.now(timezone.utc)
        await session.flush()

    return practice_session, user_message, assistant_messages, False


async def _assistant_turns(session: AsyncSession, user_message: Message) -> list[Message]:
    """Every AI turn of one learner turn, in display order.

    A meeting can carry several (docs/meeting-mode-v0.1.md §6). Idempotent replay has to hand back
    the same set in the same order the learner already saw, or a network retry would look like the
    conversation being rewritten.
    """
    rows = await session.scalars(
        select(Message)
        .where(
            Message.session_id == user_message.session_id,
            Message.turn_index == user_message.turn_index,
            Message.role == "assistant",
        )
        .order_by(Message.seq)
    )
    return list(rows)


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
