"""Request and response models for review items (design §7.10, §6.3)."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ReviewItemType = Literal["expression", "grammar", "clarity", "pronunciation", "communication"]
ReviewItemStatus = Literal["new", "reviewing", "mastered", "archived"]

ReviewText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1200)]
OptionalReviewText = Annotated[
    str | None, StringConstraints(strip_whitespace=True, max_length=1200)
]


class ReviewItemCreateRequest(BaseModel):
    source_session_id: UUID
    source_message_id: UUID | None = None
    item_type: ReviewItemType
    original_text: OptionalReviewText = None
    target_text: ReviewText
    explanation: OptionalReviewText = None
    due_at: datetime | None = None


class ReviewItemUpdateRequest(BaseModel):
    """Only these four fields are writable; ownership fields are absent by construction (§7.10)."""

    status: ReviewItemStatus | None = None
    due_at: datetime | None = None
    success_count: int | None = Field(default=None, ge=0)
    failure_count: int | None = Field(default=None, ge=0)


class ReviewItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_session_id: UUID | None
    source_message_id: UUID | None
    item_type: ReviewItemType
    original_text: str | None
    target_text: str
    explanation: str | None
    status: ReviewItemStatus
    due_at: datetime | None
    success_count: int
    failure_count: int
    created_at: datetime
    updated_at: datetime


class ReviewItemListResponse(BaseModel):
    items: list[ReviewItemResponse]
    total: int
    limit: int
    offset: int
