from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class Scenario(Base):
    __tablename__ = "scenarios"
    __table_args__ = (
        CheckConstraint(
            "category IN ('interview', 'workplace', 'travel', 'daily_life')",
            name="ck_scenarios_category",
        ),
        CheckConstraint("difficulty BETWEEN 1 AND 5", name="ck_scenarios_difficulty"),
        CheckConstraint("estimated_minutes > 0", name="ck_scenarios_estimated_minutes"),
        CheckConstraint("status IN ('draft', 'published', 'archived')", name="ck_scenarios_status"),
        Index("ix_scenarios_status_category_difficulty", "status", "category", "difficulty"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    industry_segment: Mapped[str | None] = mapped_column(String(40), nullable=True)
    companies: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    roles: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    difficulty: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    english_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    situation: Mapped[str] = mapped_column(Text, nullable=False)
    ai_character: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    user_objective: Mapped[str] = mapped_column(Text, nullable=False)
    target_skills: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    target_expressions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=list
    )
    roleplay_instructions: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation_rubric: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("status IN ('active', 'disabled')", name="ck_users_status"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PracticeSession(Base):
    __tablename__ = "practice_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'completed', 'abandoned')", name="ck_practice_sessions_status"
        ),
        CheckConstraint("input_mode IN ('text', 'voice')", name="ck_practice_sessions_input_mode"),
        CheckConstraint("turn_count >= 0", name="ck_practice_sessions_turn_count"),
        CheckConstraint(
            "(status = 'completed' AND completed_at IS NOT NULL) OR "
            "(status != 'completed' AND completed_at IS NULL)",
            name="ck_practice_sessions_completed_at",
        ),
        Index("ix_practice_sessions_user_created", "user_id", "created_at"),
        Index("ix_practice_sessions_user_status_activity", "user_id", "status", "last_activity_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scenario_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("scenarios.id", ondelete="RESTRICT"), nullable=False
    )
    scenario_version: Mapped[int] = mapped_column(Integer, nullable=False)
    scenario_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    input_mode: Mapped[str] = mapped_column(String(12), nullable=False, default="text")
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processing_turn_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("turn_index >= 0", name="ck_messages_turn_index"),
        CheckConstraint("role IN ('user', 'assistant')", name="ck_messages_role"),
        CheckConstraint("status IN ('pending', 'completed', 'failed')", name="ck_messages_status"),
        UniqueConstraint("session_id", "client_message_id", "role", name="uq_messages_client_role"),
        UniqueConstraint("session_id", "turn_index", "role", name="uq_messages_turn_role"),
        Index("ix_messages_session_turn", "session_id", "turn_index"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("practice_sessions.id", ondelete="CASCADE"), nullable=False
    )
    client_message_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="completed")
    audio_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
