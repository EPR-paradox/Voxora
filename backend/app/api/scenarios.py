from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_practice_access
from app.schemas import ScenarioDetail, ScenarioListResponse, ScenarioSummary
from app.services.scenarios import get_published_scenario, list_scenarios

router = APIRouter(
    prefix="/api/v1/scenarios",
    tags=["scenarios"],
    dependencies=[Depends(require_practice_access)],
)


@router.get("", response_model=ScenarioListResponse)
async def get_scenarios(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    category: Literal["interview", "workplace", "travel", "daily_life"] | None = None,
    industry_segment: Annotated[str | None, Query(max_length=40)] = None,
    role: Annotated[str | None, Query(pattern=r"^[a-z0-9_-]{1,80}$")] = None,
    difficulty: Annotated[int | None, Query(ge=1, le=5)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ScenarioListResponse:
    scenarios, total = await list_scenarios(
        session,
        category=category,
        industry_segment=industry_segment,
        role=role,
        difficulty=difficulty,
        limit=limit,
        offset=offset,
    )
    return ScenarioListResponse(
        items=[ScenarioSummary.model_validate(scenario) for scenario in scenarios],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{scenario_id}", response_model=ScenarioDetail)
async def get_scenario(
    scenario_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ScenarioDetail | JSONResponse:
    scenario = await get_published_scenario(session, scenario_id)
    if scenario is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "resource_not_found",
                    "message": "Scenario not found.",
                    "request_id": request.state.request_id,
                    "details": {},
                }
            },
        )
    return ScenarioDetail.model_validate(scenario)
