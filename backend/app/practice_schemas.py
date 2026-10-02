from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.core.config import settings
from app.schemas import ScenarioParticipant


class CreatePracticeSessionRequest(BaseModel):
    scenario_id: UUID
    input_mode: Literal["text"] = "text"


class ScenarioReference(BaseModel):
    id: UUID
    title: str


class OpeningMessage(BaseModel):
    id: UUID
    turn_index: int
    seq: int
    role: Literal["assistant"]
    speaker_key: str = ""
    speaker: ScenarioParticipant | None = None
    content: str
    status: Literal["completed"]


class PracticeSessionCreated(BaseModel):
    id: UUID
    scenario: ScenarioReference
    status: Literal["active"]
    input_mode: Literal["text"]
    participants: list[ScenarioParticipant] = []
    messages: list[OpeningMessage]
    started_at: datetime


MessageContent = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=settings.max_user_message_chars,
    ),
]


class SendPracticeMessageRequest(BaseModel):
    client_message_id: UUID
    content: MessageContent


class PracticeMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_message_id: UUID | None = None
    turn_index: int
    # Display order inside the session. Clients sort by this, not by array position: it is the
    # same number the server ordered by (docs/meeting-mode-v0.1.md §3).
    seq: int
    role: Literal["user", "assistant"]
    # Empty for the learner, otherwise a participant key. Never null: the uniqueness rule
    # keeping a learner turn to one message depends on it (docs/meeting-mode-v0.1.md §3).
    speaker_key: str = ""
    speaker: ScenarioParticipant | None = None
    content: str
    created_at: datetime


class SendPracticeMessageResponse(BaseModel):
    user_message: PracticeMessageResponse
    # A meeting answers with several turns (§7.6). Always a list, even for a single-character
    # scenario, so the client has one shape to render.
    assistant_messages: list[PracticeMessageResponse]
    session_status: Literal["active"]


class PracticeMessageDetail(PracticeMessageResponse):
    status: Literal["pending", "completed", "failed"]


class PracticeSessionSummary(BaseModel):
    """One row of the learner's history (§7.7). ``scenario`` comes from the session snapshot, so a
    renamed scenario does not rewrite what a past practice looked like at the time."""

    id: UUID
    scenario: ScenarioReference
    status: Literal["active", "completed", "abandoned"]
    turn_count: int
    evaluation_status: Literal["pending", "processing", "completed", "failed"] | None
    started_at: datetime
    last_activity_at: datetime
    completed_at: datetime | None


class PracticeSessionListResponse(BaseModel):
    items: list[PracticeSessionSummary]
    total: int
    limit: int
    offset: int


class PracticeSessionDetail(BaseModel):
    id: UUID
    scenario: ScenarioReference
    status: Literal["active", "completed", "abandoned"]
    input_mode: Literal["text", "voice"]
    scenario_version: int
    turn_count: int
    # Who is in this session's room, from its own snapshot (§7.4). A single-character one has 1.
    participants: list[ScenarioParticipant] = []
    messages: list[PracticeMessageDetail]
    started_at: datetime
    completed_at: datetime | None
