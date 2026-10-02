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
