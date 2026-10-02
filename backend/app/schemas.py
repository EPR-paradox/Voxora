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


class ScenarioParticipant(BaseModel):
    """One person in the room (docs/meeting-mode-v0.1.md §4).

    ``key`` is what messages are written against; ``name``/``title`` are display data taken from the
    session's own scenario snapshot, so renaming a scenario later cannot rewrite history.
    """

    key: str
    name: str
    title: str = ""
    #: Which voice this participant speaks with (docs/meeting-mode-v0.1.md §9). Sent to the client
    #: so : it can ask for the line to be spoken without keeping its own copy of the catalog.
    voice: str | None = None


class ScenarioDetail(ScenarioSummary):
    situation: str
    ai_character: dict[str, Any]
    user_objective: str
    target_expressions: list[dict[str, Any]]
    # Meeting scenarios carry their participants; null means a single-character scenario, where
    # `ai_character` is the whole room.
    cast: list[ScenarioParticipant] | None = None


class ScenarioListResponse(BaseModel):
    items: list[ScenarioSummary]
    total: int
    limit: int
    offset: int
