"""Request and response models for finishing a session and reading its evaluation (design §7.8,
§7.9)."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

EvaluationStatus = Literal["pending", "processing", "completed", "failed"]


class FinishPracticeSessionRequest(BaseModel):
    """``reason`` is client intent only; it is not persisted (§6.3 has no such column)."""

    reason: Literal["user_finished", "user_abandoned"] = "user_finished"


class EvaluationPayload(BaseModel):
    rubric_version: str
    summary: str
    dimensions: dict[str, Any]
    strengths: list[str]
    improvements: list[str]
    suggested_rephrases: list[dict[str, str]]
    review_items: list[dict[str, str]]


class EvaluationStatusResponse(BaseModel):
    """One shape for finish, retry and read, so the client needs a single code path.

    ``evaluation_status`` is the source of truth for what happened: the session is finished either
    way,
    and a failed report is reported here (with ``error_code``) instead of as a transport error.
    """

    session_id: UUID
    session_status: Literal["active", "completed", "abandoned"]
    evaluation_status: EvaluationStatus
    evaluation: EvaluationPayload | None = None
    error_code: str | None = None
    retryable: bool = False
    attempt_count: int = 0
    completed_at: datetime | None = None
