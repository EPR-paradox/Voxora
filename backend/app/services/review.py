"""Review items: list, create, update (design §7.10).

Ownership rules live here rather than in the router: a client may attach a review item to a practice
session it owns, and may never change ownership afterwards. Anything else is a uniform 404, matching
the
"do not leak resource existence" rule used across the API (§7.6, §14.2).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Message, PracticeSession, ReviewItem
from app.services.practice import PracticeError

MUTABLE_FIELDS = ("status", "due_at", "success_count", "failure_count")


async def list_review_items(
    session: AsyncSession,
    *,
    status: str | None,
    due_before: datetime | None,
    limit: int,
    offset: int,
) -> tuple[list[ReviewItem], int]:
    filters = [ReviewItem.user_id == settings.local_user_id]
    if status is not None:
        filters.append(ReviewItem.status == status)
    if due_before is not None:
        filters.append(ReviewItem.due_at.is_not(None))
        filters.append(ReviewItem.due_at <= due_before)

    total = await session.scalar(select(func.count()).select_from(ReviewItem).where(*filters))
    items = list(
        await session.scalars(
            select(ReviewItem)
            .where(*filters)
            # Items with a due date come first, soonest first; undated items trail in creation
            # order.
            .order_by(
                ReviewItem.due_at.is_(None),
                ReviewItem.due_at.asc(),
                ReviewItem.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
    )
    return items, total or 0


async def create_review_item(
    session: AsyncSession,
    *,
    source_session_id: UUID,
    source_message_id: UUID | None,
    item_type: str,
    original_text: str | None,
    target_text: str,
    explanation: str | None,
    due_at: datetime | None,
) -> ReviewItem:
    async with session.begin():
        source_session = await session.scalar(
            select(PracticeSession.id).where(
                PracticeSession.id == source_session_id,
                PracticeSession.user_id == settings.local_user_id,
            )
        )
        if source_session is None:
            raise PracticeError(404, "resource_not_found", "Source practice session not found.")

        if source_message_id is not None:
            source_message = await session.scalar(
                select(Message.id).where(
                    Message.id == source_message_id,
                    Message.session_id == source_session_id,
                )
            )
            if source_message is None:
                raise PracticeError(404, "resource_not_found", "Source message not found.")

        item = ReviewItem(
            id=uuid4(),
            user_id=settings.local_user_id,
            source_session_id=source_session_id,
            source_message_id=source_message_id,
            item_type=item_type,
            original_text=original_text,
            target_text=target_text,
            explanation=explanation,
            status="new",
            due_at=due_at,
            success_count=0,
            failure_count=0,
        )
        session.add(item)
        await session.flush()
        # created_at/updated_at are written by the database, so the row must be re-read inside the
        # transaction: touching an expired attribute afterwards attempts IO outside greenlet context
        # and raises MissingGreenlet instead of returning the created row.
        await session.refresh(item)
    return item


async def update_review_item(
    session: AsyncSession,
    *,
    item_id: UUID,
    changes: dict,
) -> ReviewItem:
    """Apply a review result. Unknown keys are ignored here and rejected by the request schema."""
    async with session.begin():
        item = await session.scalar(
            select(ReviewItem)
            .where(
                ReviewItem.id == item_id,
                ReviewItem.user_id == settings.local_user_id,
            )
            .with_for_update()
        )
        if item is None:
            raise PracticeError(404, "resource_not_found", "Review item not found.")

        for field in MUTABLE_FIELDS:
            if field in changes:
                setattr(item, field, changes[field])
        await session.flush()
        # ``updated_at`` is written by the database on UPDATE and expired by the flush, so re-read
        # the row before handing it back.
        await session.refresh(item)
    return item


async def get_review_item(session: AsyncSession, *, item_id: UUID) -> ReviewItem:
    item = await session.scalar(
        select(ReviewItem).where(
            ReviewItem.id == item_id,
            ReviewItem.user_id == settings.local_user_id,
        )
    )
    if item is None:
        raise PracticeError(404, "resource_not_found", "Review item not found.")
    return item
