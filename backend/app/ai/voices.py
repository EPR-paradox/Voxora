"""Voices for spoken AI turns (docs/meeting-mode-v0.1.md §9).

A meeting is a room of people, and people do not share a larynx: every participant gets a distinct
voice, and a participant keeps the same voice in every session. Assignment is derived from the cast
key, so shuffling one role does not re-cast the others.

The catalog is pinned by name because these strings end up in stored scenarios and in synthesis
requests: adding a voice is safe, but renaming or removing one quietly changes how characters sound
and orphans what is already stored. Hence the read path maps an unknown value to a deterministic
catalog voice rather than refusing to speak, while the write path rejects it outright.
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection

#: Names are edge-tts voice ids, ordered so that walking the list rotates accent and gender.
VOICE_CATALOG: tuple[str, ...] = (
    "en-US-AndrewMultilingualNeural",
    "en-GB-SoniaNeural",
    "en-US-EmmaNeural",
    "en-GB-RyanNeural",
    "en-US-BrianNeural",
    "en-IN-NeerjaExpressiveNeural",
    "en-US-AvaMultilingualNeural",
    "en-IN-PrabhatNeural",
)


def is_known_voice(voice: object) -> bool:
    return isinstance(voice, str) and voice in VOICE_CATALOG


def resolve_voice(key: str, taken: Collection[str] = ()) -> str:
    """A stable voice for `key`, skipping the voices already in the room.

    Stability matters more than spread: the same character must sound the same tomorrow, so this
    hashes the key rather than counting positions (a new participant would otherwise re-voice
    everyone listed after them).
    """
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    start = int.from_bytes(digest[:4], "big") % len(VOICE_CATALOG)
    for offset in range(len(VOICE_CATALOG)):
        candidate = VOICE_CATALOG[(start + offset) % len(VOICE_CATALOG)]
        if candidate not in taken:
            return candidate
    return VOICE_CATALOG[start]


__all__ = ["VOICE_CATALOG", "is_known_voice", "resolve_voice"]
