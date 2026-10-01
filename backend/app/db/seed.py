import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.models import Scenario, User

SCENARIO_SEEDS: list[dict[str, Any]] = [
    {
        "slug": "metrology-project-explanation-01",
        "title": "Explain a metrology software project",
        "summary": "Practice explaining your contribution, decisions, and results.",
        "category": "interview",
        "industry_segment": "equipment",
        "companies": ["KLA", "ASML"],
        "roles": ["metrology_software_engineer", "algorithm_engineer"],
        "difficulty": 2,
        "english_level": "B1-B2",
        "situation": (
            "You are interviewing for a metrology software or algorithm role. "
            "The interviewer asks you to describe a technical project you contributed to."
        ),
        "ai_character": {
            "name": "Interviewing manager",
            "title": "Engineering Manager",
            "personality": "curious and professional",
            "communication_style": "asks one concise follow-up at a time",
        },
        "user_objective": (
            "Explain the project context, your specific contribution, one challenge, "
            "and the outcome in a clear, structured way."
        ),
        "target_skills": ["project_explanation", "structured_response", "follow_up_response"],
        "target_expressions": [
            {
                "expression": "I was responsible for...",
                "meaning": "State your personal contribution clearly.",
                "usage": "I was responsible for validating the measurement pipeline.",
            },
            {
                "expression": "The main challenge was...",
                "meaning": "Introduce the central problem you addressed.",
                "usage": "The main challenge was separating noise from process drift.",
            },
        ],
        "roleplay_instructions": (
            "Stay in character as the interviewer. Ask a single natural follow-up at a time. "
            "Do not correct the candidate's English during the roleplay or judge "
            "technical accuracy."
        ),
        "evaluation_rubric": {
            "version": "english-communication-v1",
            "dimensions": [
                "clarity",
                "response_relevance",
                "professional_tone",
                "naturalness",
            ],
        },
        "estimated_minutes": 12,
        "status": "published",
        "version": 1,
    }
]


async def seed_scenarios(session: AsyncSession) -> None:
    for values in SCENARIO_SEEDS:
        scenario = await session.scalar(select(Scenario).where(Scenario.slug == values["slug"]))
        if scenario is None:
            session.add(Scenario(**values))
            continue
        for field, value in values.items():
            setattr(scenario, field, value)
    await session.flush()


async def seed_local_user(session: AsyncSession) -> None:
    user = await session.get(User, settings.local_user_id)
    if user is None:
        session.add(
            User(
                id=settings.local_user_id,
                display_name="Local User",
                status="active",
            )
        )
    await session.flush()


async def main() -> None:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            async with session.begin():
                await seed_local_user(session)
                await seed_scenarios(session)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
