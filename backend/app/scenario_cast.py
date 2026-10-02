"""Who is in the room: the scenario cast (docs/meeting-mode-v0.1.md §2).

One accessor, shared by the AI providers, the API layer and the client-facing projection. Every read
goes through it so a scenario written before meeting mode existed behaves exactly like a
one-participant meeting: a caller reading ``ai_character`` on its own would make old and new
scenarios quietly diverge.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.ai.voices import is_known_voice, resolve_voice

#: `key` of the single participant a pre-meeting-mode scenario is wrapped into.
SINGLE_CHARACTER_KEY = "interviewer"
DEFAULT_CHARACTER_NAME = "Interviewer"

#: A meeting has 2-3 participants: fewer has no meeting feel, more and the learner loses track
#: of who is speaking (docs/meeting-mode-v0.1.md §10).
MIN_MEETING_CAST = 2
MAX_MEETING_CAST = 3

_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
_TEXT_FIELDS = ("name", "title", "personality", "communication_style")
_MAX_TEXT_LENGTH = 200


def scenario_cast(scenario: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Participants of a scenario or of a session's scenario snapshot, always at least one.

    A stored ``cast`` wins. Otherwise the legacy single ``ai_character`` becomes a one-element
    cast, so callers never need to know which generation of scenario they are looking at.
    """
    cast = scenario.get("cast")
    if isinstance(cast, list):
        cleaned = [
            dict(item)
            for item in cast
            if isinstance(item, Mapping) and str(item.get("key") or "").strip()
        ]
        if cleaned:
            return _with_voices(cleaned)
    return [_single_character(scenario)]


def is_meeting(scenario: Mapping[str, Any]) -> bool:
    """True when more than one participant is in the room."""
    return len(scenario_cast(scenario)) > 1


def speaker_index(scenario: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """`speaker_key` -> display fields, for responses that name the speaker (§7.7)."""
    return {
        str(participant["key"]): {
            "name": participant.get("name") or DEFAULT_CHARACTER_NAME,
            "title": participant.get("title") or "",
        }
        for participant in scenario_cast(scenario)
    }


def normalize_cast(cast: Any) -> list[dict[str, Any]] | None:
    """Validate a cast for storage. Returns the cleaned list, or ``None`` for 'no cast'.

    Raises ``ValueError`` rather than storing a shape that would later break prompt building or
    output validation: a cast whose keys do not survive a round trip through the database would
    only fail at the moment the learner is waiting for a reply.
    """
    if cast is None:
        return None
    if not isinstance(cast, list):
        raise ValueError("cast must be a list of participants or null.")

    participants: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in cast:
        if not isinstance(item, Mapping):
            raise ValueError("every cast entry must be an object.")
        key = str(item.get("key") or "").strip()
        if not _KEY_PATTERN.match(key):
            raise ValueError(f"cast key {key!r} must match ^[a-z][a-z0-9_]{{1,31}}$")
        if key in seen:
            raise ValueError(f"duplicate cast key {key!r}")
        seen.add(key)

        entry: dict[str, Any] = {"key": key}
        for field in _TEXT_FIELDS:
            value = item.get(field)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"cast[{key}].{field} must be a string or null.")
            value = (value or "").strip()
            if len(value) > _MAX_TEXT_LENGTH:
                raise ValueError(f"cast[{key}].{field} exceeds {_MAX_TEXT_LENGTH} characters.")
            entry[field] = value
        if not entry["name"]:
            raise ValueError(f"cast[{key}] needs a name.")
        # Voices land with speech output (docs/meeting-mode-v0.1.md §9). An explicit voice must be
        # one the synthesiser knows — storing a typo would only surface as a failed playback — and a
        # cast that names nobody gets stable voices here, so every stored cast can be spoken.
        voice = item.get("voice")
        if voice is not None and not is_known_voice(voice):
            raise ValueError(f"cast[{key}].voice must be a known voice or null.")
        entry["voice"] = voice or resolve_voice(key, {p["voice"] for p in participants})
        participants.append(entry)

    if participants and not MIN_MEETING_CAST <= len(participants) <= MAX_MEETING_CAST:
        raise ValueError(
            f"a cast holds {MIN_MEETING_CAST} to {MAX_MEETING_CAST} participants, "
            f"got {len(participants)}."
        )
    return participants or None


def _single_character(scenario: Mapping[str, Any]) -> dict[str, Any]:
    character = scenario.get("ai_character")
    character = character if isinstance(character, Mapping) else {}
    return {
        "key": SINGLE_CHARACTER_KEY,
        "name": str(character.get("name") or DEFAULT_CHARACTER_NAME),
        "title": str(character.get("title") or ""),
        "personality": str(character.get("personality") or ""),
        "communication_style": str(character.get("communication_style") or ""),
        "voice": resolve_voice(SINGLE_CHARACTER_KEY),
    }


def _with_voices(cast: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill in a voice for every participant, keeping whatever is already stored.

    Scenarios written before voices existed (or hand-edited ones) carry ``None`` or a name from an
    older catalog: playback has to work for them anyway, so the missing voice is derived here rather
    than turned into an error at the moment the learner presses play.
    """
    taken: set[str] = set()
    resolved: list[dict[str, Any]] = []
    for participant in cast:
        entry = dict(participant)
        voice = entry.get("voice")
        if not is_known_voice(voice):
            voice = resolve_voice(str(entry.get("key") or ""), taken)
        entry["voice"] = voice
        taken.add(voice)
        resolved.append(entry)
    return resolved


__all__ = [
    "DEFAULT_CHARACTER_NAME",
    "MAX_MEETING_CAST",
    "MIN_MEETING_CAST",
    "SINGLE_CHARACTER_KEY",
    "is_meeting",
    "normalize_cast",
    "scenario_cast",
    "speaker_index",
]
