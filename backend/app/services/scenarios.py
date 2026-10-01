from uuid import UUID

from sqlalchemy import Select, String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Scenario


async def list_scenarios(
    session: AsyncSession,
    *,
    category: str | None,
    industry_segment: str | None,
    role: str | None,
    difficulty: int | None,
    limit: int,
    offset: int,
) -> tuple[list[Scenario], int]:
    filters = [Scenario.status == "published"]
    if category is not None:
        filters.append(Scenario.category == category)
    if industry_segment is not None:
        filters.append(Scenario.industry_segment == industry_segment)
    if difficulty is not None:
        filters.append(Scenario.difficulty == difficulty)
    if role is not None:
        # Roles are JSON arrays; escape SQL LIKE wildcards in the exact JSON token.
        escaped_role = role.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        filters.append(cast(Scenario.roles, String).like(f'%"{escaped_role}"%', escape="\\"))

    total = await session.scalar(select(func.count()).select_from(Scenario).where(*filters))
    query: Select[tuple[Scenario]] = (
        select(Scenario)
        .where(*filters)
        .order_by(Scenario.category, Scenario.difficulty, Scenario.title)
        .limit(limit)
        .offset(offset)
    )
    result = await session.scalars(query)
    return list(result), total or 0


async def get_published_scenario(session: AsyncSession, scenario_id: UUID) -> Scenario | None:
    result = await session.scalar(
        select(Scenario).where(
            Scenario.id == scenario_id,
            Scenario.status == "published",
        )
    )
    return result
