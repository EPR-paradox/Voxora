"""Scenario seed data is content, but its shape is a contract (design §6.3, §7.3).

A bad seed does not fail on the developer's machine: it fails at `alembic upgrade`/seed time on the
box that runs it, or worse, renders a screen with an empty field. These checks run per seed rather
than on "the seeds" as a whole, so a new scenario that is missing a rubric names itself.
"""

from __future__ import annotations

import pytest

from app.db.scenario_seeds_life import TRAVEL_AND_LIFE_SEEDS
from app.db.seed import SCENARIO_SEEDS

# : Mirrors the CHECK constraint `ck_scenarios_category` (deployment §6.3).
CATEGORIES = {"interview", "workplace", "travel", "daily_life"}


def test_slugs_are_unique() -> None:
    slugs = [seed["slug"] for seed in SCENARIO_SEEDS]

    assert len(slugs) == len(set(slugs))


@pytest.mark.parametrize("seed", SCENARIO_SEEDS, ids=lambda seed: seed["slug"])
def test_every_seed_can_be_stored_and_played(seed: dict) -> None:
    assert seed["category"] in CATEGORIES
    assert 1 <= seed["difficulty"] <= 5
    assert 1 <= seed["estimated_minutes"] <= 60
    assert seed["status"] == "published"
    assert seed["title"].strip() and seed["summary"].strip()
    assert len(seed["situation"]) > 40, "a situation has to set up something to talk about"
    assert len(seed["user_objective"]) > 40
    assert seed["roleplay_instructions"].strip()
    assert seed["evaluation_rubric"]["version"] == "english-communication-v1"
    assert len(seed["evaluation_rubric"]["dimensions"]) == 4
    assert 2 <= len(seed["target_expressions"]) <= 3
    for expression in seed["target_expressions"]:
        assert expression["expression"].strip()
        assert expression["meaning"].strip()
        assert expression["usage"].strip()
    assert seed["target_skills"], "a scenario with no target skills cannot be reviewed later"
    if seed.get("cast"):
        # A meeting derives `ai_character` from its first participant when seeding.
        assert len(seed["cast"]) >= 2
    else:
        # A single-character scenario has to name the other person itself.
        assert seed["ai_character"]["name"].strip()
        assert seed["ai_character"]["communication_style"].strip()


@pytest.mark.parametrize("seed", TRAVEL_AND_LIFE_SEEDS, ids=lambda seed: seed["slug"])
def test_travel_and_life_scenarios_are_one_to_one(seed: dict) -> None:
    """These are single encounters: no cast, and no employer or job title on a hotel desk (§2)."""
    assert seed["category"] in {"travel", "daily_life"}
    assert seed.get("cast") is None
    assert seed["roles"] == []
    assert seed["companies"] == []


def test_each_scenario_carries_its_own_rubric_object() -> None:
    """Ten seeds aliasing one dict is invisible until someone edits one and ten change."""
    rubrics = [id(seed["evaluation_rubric"]) for seed in TRAVEL_AND_LIFE_SEEDS]

    assert len(set(rubrics)) == len(rubrics)


def test_the_set_covers_both_new_categories() -> None:
    categories = {seed["category"] for seed in TRAVEL_AND_LIFE_SEEDS}

    assert categories == {"travel", "daily_life"}
