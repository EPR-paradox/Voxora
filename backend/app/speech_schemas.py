"""Request/response models for speech transcription (design §7.11)."""

from pydantic import BaseModel


class TranscriptionResponse(BaseModel):
    """What the learner gets back: text they can send, plus the metadata §8.6 wants recorded.

    The client must not treat this as stored data: nothing about the transcription is persisted, and
    the text only becomes durable once it is sent as a message (§7.11 rules 6, 7).
    """

    text: str
    language: str
    duration_ms: int | None = None
    provider: str
    model: str


class SynthesisRequest(BaseModel):
    """One line to speak (docs/meeting-mode-v0.1.md §9).

    ``voice`` comes from the session's ``participants``, so the client never keeps its own copy of
    the catalog. The endpoint is not session-scoped, for the same reason transcription is not (§7.11
    rule 6): speaking a line does not depend on the scenario.
    """

    text: str
    voice: str
