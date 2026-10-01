from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
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
