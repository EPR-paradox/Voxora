from typing import Any, Protocol


class RoleplayProvider(Protocol):
    async def opening_message(self, scenario: dict[str, Any]) -> str: ...

    async def reply(
        self,
        scenario: dict[str, Any],
        history: list[dict[str, str]],
        user_message: str,
    ) -> str: ...

    async def aclose(self) -> None: ...


class FakeRoleplayProvider:
    """Deterministic provider for tests and offline development."""

    async def opening_message(self, scenario: dict[str, Any]) -> str:
        return "Could you briefly introduce the project and your role in it?"

    async def reply(
        self,
        scenario: dict[str, Any],
        history: list[dict[str, str]],
        user_message: str,
    ) -> str:
        return "What was the main challenge you had to solve?"

    async def aclose(self) -> None:
        return None
