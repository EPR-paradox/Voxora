"""The cast accessor and cast validation (docs/meeting-mode-v0.1.md §2).

The point of this module is that a scenario written before meeting mode existed behaves exactly
like a one-participant meeting, so most of these tests are about the legacy path, not the new one.
"""

from __future__ import annotations

import pytest

from app.scenario_cast import (
    DEFAULT_CHARACTER_NAME,
    SINGLE_CHARACTER_KEY,
    is_meeting,
    normalize_cast,
    scenario_cast,
    speaker_index,
)

LEGACY_SCENARIO = {
    "ai_character": {"name": "Dana", "title": "Hiring Manager", "personality": "curious"},
    "situation": "A hiring manager asks about your last project.",
}

MEETING_SCENARIO = {
    "ai_character": {"name": "Dana", "title": "Hiring Manager"},
    "cast": [
        {"key": "eng_lead", "name": "Dana Whitfield", "title": "Engineering Lead"},
        {"key": "pm", "name": "Marco Ruiz", "title": "Product Manager"},
    ],
}


def test_stored_cast_wins_over_the_legacy_character() -> None:
    participants = scenario_cast(MEETING_SCENARIO)

    assert [p["key"] for p in participants] == ["eng_lead", "pm"]
    assert is_meeting(MEETING_SCENARIO) is True


def test_legacy_scenario_becomes_a_one_participant_meeting() -> None:
    participants = scenario_cast(LEGACY_SCENARIO)

    assert len(participants) == 1
    assert participants[0]["key"] == SINGLE_CHARACTER_KEY
    assert participants[0]["name"] == "Dana"
    assert participants[0]["title"] == "Hiring Manager"
    assert participants[0]["personality"] == "curious"
    assert is_meeting(LEGACY_SCENARIO) is False


@pytest.mark.parametrize(
    "broken",
    [
        {"ai_character": {"title": "Manager"}},  # no name
        {"ai_character": None},
        {},  # a snapshot with neither field
        {"ai_character": {"name": "Dana"}, "cast": None},
        {"ai_character": {"name": "Dana"}, "cast": []},
        {"ai_character": {"name": "Dana"}, "cast": "eng_lead"},  # not a list
        {"ai_character": {"name": "Dana"}, "cast": [{"name": "no key here"}]},
    ],
)
def test_unusable_cast_falls_back_instead_of_returning_nothing(broken: dict) -> None:
    participants = scenario_cast(broken)

    assert len(participants) == 1
    assert participants[0]["key"] == SINGLE_CHARACTER_KEY
    assert participants[0]["name"]


def test_missing_name_falls_back_to_a_neutral_label() -> None:
    assert scenario_cast({})[0]["name"] == DEFAULT_CHARACTER_NAME


def test_speaker_index_maps_keys_to_display_fields() -> None:
    assert speaker_index(MEETING_SCENARIO) == {
        "eng_lead": {"name": "Dana Whitfield", "title": "Engineering Lead"},
        "pm": {"name": "Marco Ruiz", "title": "Product Manager"},
    }


def test_normalize_cast_accepts_two_to_three_participants() -> None:
    stored = normalize_cast(
        [
            {"key": "eng_lead", "name": "Dana", "title": "Engineering Lead", "voice": "en_f_1"},
            {"key": "pm", "name": "Marco", "personality": "blunt"},
        ]
    )

    assert stored is not None
    assert [p["key"] for p in stored] == ["eng_lead", "pm"]
    # Voice belongs to the speech-output phase, so a value in the input must not be stored as if a
    # synthesiser existed.
    assert stored[0]["voice"] is None
    assert stored[0]["personality"] == ""
    assert stored[1]["personality"] == "blunt"


def test_normalized_cast_survives_a_round_trip() -> None:
    """Keys stored by the validator must be the keys the providers later look up."""
    stored = normalize_cast([{"key": "eng_lead", "name": "Dana"}, {"key": "qa", "name": "Priya"}])

    assert [p["key"] for p in scenario_cast({"cast": stored})] == ["eng_lead", "qa"]


def test_normalize_cast_none_means_single_character_scenario() -> None:
    assert normalize_cast(None) is None
    assert normalize_cast([]) is None


@pytest.mark.parametrize(
    "cast",
    [
        [{"key": "eng_lead", "name": "Dana"}],  # one participant is not a meeting
        [{"key": f"p{i}", "name": "x"} for i in range(4)],  # four is too many
        [{"key": "Eng Lead", "name": "Dana"}, {"key": "pm", "name": "M"}],  # key is not a slug
        [{"key": "ENG_LEAD", "name": "Dana"}, {"key": "pm", "name": "M"}],  # key must be lowercase
        [{"key": "eng_lead", "name": "Dana"}, {"key": "eng_lead", "name": "Other"}],
        [{"key": "eng_lead", "name": "  "}, {"key": "pm", "name": "M"}],
        [{"key": "eng_lead"}, {"key": "pm", "name": "M"}],
        ["eng_lead", "pm"],
        [{"key": "eng_lead", "name": "N" * 201}, {"key": "pm", "name": "M"}],
        [{"key": "eng_lead", "name": {"first": "Dana"}}, {"key": "pm", "name": "M"}],
        {"key": "eng_lead"},
    ],
)
def test_normalize_cast_rejects_shapes_that_would_break_the_provider(cast) -> None:
    """A shape that got stored would only fail later, while the learner waits for a reply."""
    with pytest.raises(ValueError):
        normalize_cast(cast)


def test_normalize_cast_names_the_offending_field() -> None:
    with pytest.raises(ValueError, match="duplicate cast key"):
        normalize_cast([{"key": "pm", "name": "M"}, {"key": "pm", "name": "M2"}])
    with pytest.raises(ValueError, match="needs a name"):
        normalize_cast([{"key": "pm"}, {"key": "qa", "name": "Q"}])
