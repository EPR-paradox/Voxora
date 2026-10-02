import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.models import Scenario, User
from app.scenario_cast import normalize_cast

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
    },
    {
        # Meeting mode (docs/meeting-mode-v0.1.md §2). Three participants, so the learner has to
        # notice who is speaking and choose when to take the floor.
        "slug": "design-review-scope-01",
        "title": "Defend your scope in a technical design review",
        "summary": "Explain your plan, hold your estimate, and agree on what gets cut.",
        "category": "workplace",
        "industry_segment": "equipment",
        "companies": [],
        "roles": ["metrology_software_engineer", "software_engineer", "project_engineer"],
        "difficulty": 3,
        "english_level": "B1-B2",
        "situation": (
            "A design review for a measurement data pipeline. The product manager wants an "
            "earlier date, the lead engineer questions your estimate, and QA asks what is "
            "actually testable. You are the engineer who has to defend the plan."
        ),
        "cast": [
            {
                "key": "eng_lead",
                "name": "Dana Whitfield",
                "title": "Engineering Lead",
                "personality": "direct, dislikes vague estimates",
                "communication_style": "short sentences, asks for numbers, occasionally cuts in",
            },
            {
                "key": "pm",
                "name": "Marco Ruiz",
                "title": "Product Manager",
                "personality": "under date pressure, focused on the customer commitment",
                "communication_style": "friendly but keeps returning to the schedule",
            },
            {
                "key": "qa",
                "name": "Priya Raman",
                "title": "QA Engineer",
                "personality": "quiet until something is untestable",
                "communication_style": "asks one precise question at a time",
            },
        ],
        "user_objective": (
            "Explain the plan briefly, defend the estimate with reasons, agree one cut, and "
            "leave the meeting with a clear next step."
        ),
        "target_skills": ["meeting_participation", "justifying_estimates", "clarifying_question"],
        "target_expressions": [
            {
                "expression": "Can I flag one risk before we move on?",
                "meaning": "Take the floor without interrupting aggressively.",
                "usage": "Can I flag one risk before we move on?",
            },
            {
                "expression": "That would cost us the calibration pass.",
                "meaning": "State a concrete consequence instead of only disagreeing.",
                "usage": "Cutting that would cost us the calibration pass.",
            },
        ],
        "roleplay_instructions": (
            "Run a twelve-minute design review. The participants may disagree with each other. "
            "Let the learner finish their point before pressing further. Never correct the "
            "learner's English and never judge the technical conclusion."
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
    },
    {
        # Two participants: the smallest meeting, and the one where being interrupted matters most.
        "slug": "standup-blocker-01",
        "title": "Raise a blocker in a daily standup",
        "summary": "Report status in three lines and ask for the help you actually need.",
        "category": "workplace",
        "industry_segment": "equipment",
        "companies": [],
        "roles": ["software_engineer", "test_engineer", "field_service_engineer"],
        "difficulty": 2,
        "english_level": "A2-B1",
        "situation": (
            "The morning standup. You are stuck on something that needs another team, and the lead "
            "wants to know today's impact rather than the history of the problem."
        ),
        "cast": [
            {
                "key": "team_lead",
                "name": "Sam Okafor",
                "title": "Team Lead",
                "personality": "practical, keeps the standup short",
                "communication_style": "asks what you need, not how you feel about it",
            },
            {
                "key": "field_eng",
                "name": "Elena Kovacs",
                "title": "Field Service Engineer",
                "personality": "has a customer waiting for the fix",
                "communication_style": "impatient, asks for a date",
            },
        ],
        "user_objective": (
            "State where you are, name the blocker, and ask for one specific thing. Keep it "
            "under a minute and answer the follow-up questions."
        ),
        "target_skills": ["status_reporting", "asking_for_help", "meeting_participation"],
        "target_expressions": [
            {
                "expression": "I'm blocked on...",
                "meaning": "Name the blocker in one sentence.",
                "usage": "I'm blocked on the sensor firmware release.",
            },
            {
                "expression": "What I need from you is...",
                "meaning": "Make the request explicit instead of hinting.",
                "usage": "What I need from you is a two-hour slot on the test rig.",
            },
        ],
        "roleplay_instructions": (
            "Keep the standup short and businesslike. Ask at most one follow-up per turn. "
            "Never correct the learner's English and never judge the technical conclusion."
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
        "estimated_minutes": 8,
        "status": "published",
        "version": 1,
    },
]


async def seed_scenarios(session: AsyncSession) -> None:
    for seed in SCENARIO_SEEDS:
        values = dict(seed)
        # Validate the cast on the way in (docs/meeting-mode-v0.1.md §2): keys that do not survive a
        # round trip through the database would only fail later, while a learner waits for a reply.
        values["cast"] = normalize_cast(values.get("cast"))
        if values["cast"] and not values.get("ai_character"):
            # `ai_character` stays NOT NULL for everything that predates meeting mode; in a
            # meeting the first participant is the closest thing to "the other person".
            first = values["cast"][0]
            values["ai_character"] = {"name": first["name"], "title": first["title"]}

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
