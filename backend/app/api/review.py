"""Review item endpoints (design §7.10)."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_practice_access
from app.api.errors import error_response
from app.review_schemas import (
    ReviewItemCreateRequest,
    ReviewItemListResponse,
    ReviewItemResponse,
    ReviewItemUpdateRequest,
)
from app.services.practice import PracticeError
from app.services.review import create_review_item, list_review_items, update_review_item

router = APIRouter(
    prefix="/api/v1/review-items",
    tags=["review"],
    dependencies=[Depends(require_practice_access)],
)


@router.get("", response_model=ReviewItemListResponse)
async def read_review_items(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    status: Annotated[
        Literal["new", "reviewing", "mastered", "archived"] | None,
        Query(description="Filter by review state."),
    ] = None,
    due_before: Annotated[
        datetime | None,
        Query(description="Only items due at or before this instant."),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReviewItemListResponse:
    items, total = await list_review_items(
        session,
        status=status,
        due_before=due_before,
        limit=limit,
        offset=offset,
    )
    return ReviewItemListResponse(
        items=[ReviewItemResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=ReviewItemResponse, status_code=201)
async def add_review_item(
    body: ReviewItemCreateRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReviewItemResponse | JSONResponse:
    try:
        item = await create_review_item(
            session,
            source_session_id=body.source_session_id,
            source_message_id=body.source_message_id,
            item_type=body.item_type,
            original_text=body.original_text,
            target_text=body.target_text,
            explanation=body.explanation,
            due_at=body.due_at,
        )
    except PracticeError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )
    return ReviewItemResponse.model_validate(item)


@router.patch("/{item_id}", response_model=ReviewItemResponse)
async def patch_review_item(
    item_id: UUID,
    body: ReviewItemUpdateRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReviewItemResponse | JSONResponse:
    try:
        item = await update_review_item(
            session,
            item_id=item_id,
            changes=body.model_dump(exclude_unset=True),
        )
    except PracticeError as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )
    return ReviewItemResponse.model_validate(item)
