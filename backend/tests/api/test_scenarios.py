from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Scenario
from app.main import create_app


@pytest.fixture
async def scenario_client(tmp_path) -> AsyncIterator[AsyncClient]:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'scenarios.db'}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all(
            [
                Scenario(
                    slug="project-explanation",
                    title="Explain a metrology software project",
                    summary="Explain your contribution and decisions.",
                    category="interview",
                    industry_segment="equipment",
                    companies=["KLA", "ASML"],
                    roles=["metrology_software_engineer", "algorithm_engineer"],
                    difficulty=2,
                    situation="A hiring manager asks about a project.",
                    ai_character={"name": "Hiring manager", "title": "Manager"},
                    user_objective="Explain a project clearly.",
                    target_skills=["project_explanation"],
                    target_expressions=[],
                    roleplay_instructions="Ask concise follow-up questions.",
                    evaluation_rubric={"version": "v1"},
                    estimated_minutes=12,
                    status="published",
                ),
                Scenario(
                    slug="role-wildcard-decoy",
                    title="A role filter decoy",
                    summary="Must not match the underscore role filter.",
                    category="interview",
                    industry_segment="equipment",
                    companies=["KLA"],
                    roles=["algorithmxengineer"],
                    difficulty=2,
                    situation="A scenario with a similar but distinct role tag.",
                    ai_character={"name": "Interviewer", "title": "Manager"},
                    user_objective="Explain your experience.",
                    target_skills=["project_explanation"],
                    target_expressions=[],
                    roleplay_instructions="Ask a concise follow-up.",
                    evaluation_rubric={"version": "v1"},
                    estimated_minutes=10,
                    status="published",
                ),
            ]
        )
        await session.commit()

    app = create_app(database_url=database_url)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_scenarios_exposes_published_items_and_supports_filters(
    scenario_client: AsyncClient,
) -> None:
    response = await scenario_client.get(
        "/api/v1/scenarios?category=interview&industry_segment=equipment"
        "&role=algorithm_engineer&difficulty=2"
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": response.json()["items"][0]["id"],
                "slug": "project-explanation",
                "title": "Explain a metrology software project",
                "summary": "Explain your contribution and decisions.",
                "category": "interview",
                "industry_segment": "equipment",
                "companies": ["KLA", "ASML"],
                "roles": ["metrology_software_engineer", "algorithm_engineer"],
                "difficulty": 2,
                "estimated_minutes": 12,
                "target_skills": ["project_explanation"],
            }
        ],
        "total": 1,
        "limit": 20,
        "offset": 0,
    }


@pytest.mark.asyncio
async def test_scenario_detail_omits_internal_instructions(
    scenario_client: AsyncClient,
) -> None:
    listing = await scenario_client.get("/api/v1/scenarios")
    scenario_id = next(
        item["id"] for item in listing.json()["items"] if item["slug"] == "project-explanation"
    )

    response = await scenario_client.get(f"/api/v1/scenarios/{scenario_id}")

    assert response.status_code == 200
    detail = response.json()
    assert detail["situation"] == "A hiring manager asks about a project."
    assert detail["user_objective"] == "Explain a project clearly."
    assert "roleplay_instructions" not in detail
    assert "evaluation_rubric" not in detail


@pytest.mark.asyncio
async def test_scenario_detail_returns_not_found_for_unknown_id(
    scenario_client: AsyncClient,
) -> None:
    response = await scenario_client.get("/api/v1/scenarios/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_scenarios_rejects_difficulty_outside_supported_range(
    scenario_client: AsyncClient,
) -> None:
    response = await scenario_client.get("/api/v1/scenarios?difficulty=6")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_scenarios_treats_role_underscore_as_literal(
    scenario_client: AsyncClient,
) -> None:
    response = await scenario_client.get("/api/v1/scenarios?role=algorithm_engineer")

    assert response.status_code == 200
    assert [item["slug"] for item in response.json()["items"]] == ["project-explanation"]


@pytest.mark.asyncio
async def test_list_scenarios_uses_offset_pagination(
    scenario_client: AsyncClient,
) -> None:
    response = await scenario_client.get("/api/v1/scenarios?limit=1&offset=1")

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert len(response.json()["items"]) == 1
