from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ScenarioSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    title: str
    summary: str
    category: str
    industry_segment: str | None
    companies: list[str]
    roles: list[str]
    difficulty: int
    estimated_minutes: int
    target_skills: list[str]


class ScenarioDetail(ScenarioSummary):
    situation: str
    ai_character: dict[str, Any]
    user_objective: str
    target_expressions: list[dict[str, Any]]


class ScenarioListResponse(BaseModel):
    items: list[ScenarioSummary]
    total: int
    limit: int
    offset: int
