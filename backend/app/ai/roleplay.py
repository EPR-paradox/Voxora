"""The roleplay contract: one learner turn in, one or more AI turns out.

Meeting mode (docs/meeting-mode-v0.1.md §5) makes the reply plural — several participants answer the
same learner turn, and the opening can be a short exchange between them. A single-character
scenario is the degenerate case: exactly one turn, whose ``speaker_key`` is that scenario's only
participant.

``speaker_key`` is always a key from ``app.scenario_cast.scenario_cast()``, never a name: names are
display data and can be edited, keys are what history is written against.
"""

from dataclasses import dataclass
from typing import Any, Protocol

from app.scenario_cast import scenario_cast


@dataclass(frozen=True)
class RoleplayTurn:
    """One AI utterance: who said it, and what they said."""

    speaker_key: str
    content: str


class RoleplayProvider(Protocol):
    async def opening_turns(self, scenario: dict[str, Any]) -> list[RoleplayTurn]: ...

    async def reply(
        self,
        scenario: dict[str, Any],
        history: list[dict[str, str]],
        user_message: str,
    ) -> list[RoleplayTurn]: ...

    async def advance(
        self,
        scenario: dict[str, Any],
        history: list[dict[str, str]],
    ) -> list[RoleplayTurn]: ...

    async def aclose(self) -> None: ...


class FakeRoleplayProvider:
    """Deterministic provider for tests and offline development.

    Single-character scenarios keep the exact two sentences the whole suite was written against. A
    meeting answers with two of its participants, so the client's speaker grouping and the
    multi-row write path are exercised without a model in the loop.
    """

    OPENING = "Could you briefly introduce the project and your role in it?"
    FOLLOW_UP = "What was the main challenge you had to solve?"
    MEETING_OPENING = "Thanks for joining. We have thirty minutes — shall we start?"
    MEETING_FOLLOW_UP = "Anything you want to add before we move on?"
    MEETING_ADVANCE = "Let's keep that on the list and look at the numbers first."

    async def opening_turns(self, scenario: dict[str, Any]) -> list[RoleplayTurn]:
        return self._turns(scenario, self.OPENING, self.MEETING_OPENING)

    async def reply(
        self,
        scenario: dict[str, Any],
        history: list[dict[str, str]],
        user_message: str,
    ) -> list[RoleplayTurn]:
        return self._turns(scenario, self.FOLLOW_UP, self.MEETING_FOLLOW_UP)

    async def advance(
        self,
        scenario: dict[str, Any],
        history: list[dict[str, str]],
    ) -> list[RoleplayTurn]:
        """The room carries on: in a meeting the participants talk to each other, not to nobody.

        A single-character scenario has no one else to talk to, so advancing it is a caller error:
        the service refuses it long before this is reached, and this path stays honest about that
        instead of inventing a monologue.
        """
        return self._turns(scenario, self.FOLLOW_UP, self.MEETING_ADVANCE)

    async def aclose(self) -> None:
        return None

    def _turns(
        self, scenario: dict[str, Any], single: str, meeting_second: str
    ) -> list[RoleplayTurn]:
        participants = scenario_cast(scenario)
        if len(participants) == 1:
            return [RoleplayTurn(speaker_key=str(participants[0]["key"]), content=single)]
        return [
            RoleplayTurn(speaker_key=str(participants[0]["key"]), content=single),
            RoleplayTurn(speaker_key=str(participants[1]["key"]), content=meeting_second),
        ]
