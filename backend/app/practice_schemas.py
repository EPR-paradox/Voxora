from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.core.config import settings


class CreatePracticeSessionRequest(BaseModel):
    scenario_id: UUID
    input_mode: Literal["text"] = "text"


class ScenarioReference(BaseModel):
    id: UUID
    title: str


class OpeningMessage(BaseModel):
    id: UUID
    turn_index: int
    role: Literal["assistant"]
    content: str
    status: Literal["completed"]


class PracticeSessionCreated(BaseModel):
    id: UUID
    scenario: ScenarioReference
    status: Literal["active"]
    input_mode: Literal["text"]
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
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class SendPracticeMessageResponse(BaseModel):
    user_message: PracticeMessageResponse
    assistant_message: PracticeMessageResponse
    session_status: Literal["active"]


class PracticeMessageDetail(PracticeMessageResponse):
    status: Literal["pending", "completed", "failed"]


class PracticeSessionDetail(BaseModel):
    id: UUID
    scenario: ScenarioReference
    status: Literal["active", "completed", "abandoned"]
    input_mode: Literal["text", "voice"]
    scenario_version: int
    turn_count: int
    messages: list[PracticeMessageDetail]
    started_at: datetime
    completed_at: datetime | None
