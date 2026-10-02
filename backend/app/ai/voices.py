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

#: Names are Piper voice models, resolved on disk as ``<name>.onnx`` (see ``piper_synthesis``).
#: Ordered so that walking the list rotates accent (US/GB) and gender.
#:
#: The catalog is pinned by name because these strings are stored inside scenarios and repeated in
#: synthesis requests: adding a voice is safe, but renaming or removing one quietly changes how
#: characters sound and orphans what is already stored. Hence the read path maps an unknown value to
#: a deterministic catalog voice rather than refusing to speak, while the write path rejects it.
#:
#: **The names belong to the configured synthesiser.** A catalog of edge-tts voice ids was correct
#: while ``SPEECH_SYNTHESIS_PROVIDER=edge_tts``; switching the provider means switching the catalog,
#: which is why the old ids no longer appear here — stored scenarios holding one are repaired to a
#: catalog voice on read.
VOICE_CATALOG: tuple[str, ...] = (
    "en_US-ryan-medium",
    "en_GB-jenny_dioco-medium",
    "en_US-amy-medium",
    "en_GB-alan-medium",
    "en_US-joe-medium",
    "en_US-hfc_female-medium",
    "en_US-lessac-medium",
    "en_US-hfc_male-medium",
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
