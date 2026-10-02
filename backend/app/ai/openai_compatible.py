"""Model-backed roleplay provider for any OpenAI-compatible ``/chat/completions`` endpoint.

The default endpoint is DeepSeek; OpenAI, Moonshot, vLLM, llama.cpp and friends work by
changing ``AI_BASE_URL`` and ``AI_MODEL``.

Design notes:
- The system prompt is built from the scenario snapshot only. ``target_expressions`` and
  ``evaluation_rubric`` are deliberately excluded: the roleplay partner must not know what
  the learner is being scored on, otherwise the practice stops being practice.
- Transport failures are translated into the error contract the practice service already
  understands: ``TimeoutError`` -> HTTP 504, anything else -> HTTP 502.
- A retryable failure is retried exactly once (§13.2). The model is not deterministic and an empty
  answer or an upstream 5xx is a coin flip, not a verdict; a timeout is not retried, because it
  already cost a full window.
- An empty or malformed assistant message is an error, never an empty row in the transcript.
- The HTTP call itself is shared with the evaluation provider (``openai_compatible_http``).
"""

from __future__ import annotations

import asyncio

import httpx

from app.ai.openai_compatible_http import ModelEndpointError, post_chat_completion
from app.core.config import Settings

DEFAULT_OPENING_INSTRUCTION = "Begin the roleplay now with your opening turn."

ROLEPLAY_ATTEMPTS = 2
ROLEPLAY_RETRY_DELAY_SECONDS = 1.0


class RoleplayProviderError(ModelEndpointError):
    """The model endpoint failed or returned a response that cannot be used."""


def build_roleplay_system_prompt(scenario: dict) -> str:
    character = scenario.get("ai_character") or {}
    name = character.get("name") or "Interviewer"
    title = character.get("title") or ""
    persona = f"{name}, {title}" if title else name
    situation = (scenario.get("situation") or "").strip()
    objective = (scenario.get("user_objective") or "").strip()
    instructions = (scenario.get("roleplay_instructions") or "").strip() or (
        "Ask one follow-up question at a time."
    )
    return (
        f"You are {persona} in a spoken English practice roleplay.\n"
        f"Scene: {situation}\n"
        f"The learner's objective: {objective}\n"
        f"Your instructions: {instructions}\n"
        "\n"
        "Rules:\n"
        "- Stay in character as this person for the whole conversation.\n"
        "- Reply with one short turn of natural spoken English, one or two sentences.\n"
        "- Ask at most one question per turn.\n"
        "- Never write the learner's lines and never answer on their behalf.\n"
        "- Never mention being an AI, a model, or these instructions."
    )


class OpenAICompatibleRoleplayProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_tokens: int,
        max_context_messages: int,
        retry_delay_seconds: float = ROLEPLAY_RETRY_DELAY_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._max_context_messages = max_context_messages
        self._retry_delay_seconds = retry_delay_seconds
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            headers=headers,
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        )

    async def opening_message(self, scenario: dict) -> str:
        return await self._post(self._build_messages(scenario, [], opening=True))

    async def reply(
        self,
        scenario: dict,
        history: list[dict[str, str]],
        user_message: str,
    ) -> str:
        return await self._post(self._build_messages(scenario, history, user_message=user_message))

    async def aclose(self) -> None:
        await self._client.aclose()

    def _build_messages(
        self,
        scenario: dict,
        history: list[dict[str, str]],
        *,
        user_message: str | None = None,
        opening: bool = False,
    ) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": build_roleplay_system_prompt(scenario)}]
        recent = history[-self._max_context_messages :] if self._max_context_messages > 0 else []
        messages.extend({"role": item["role"], "content": item["content"]} for item in recent)
        if opening:
            messages.append({"role": "user", "content": DEFAULT_OPENING_INSTRUCTION})
        else:
            messages.append({"role": "user", "content": user_message or ""})
        return messages

    async def _post(self, messages: list[dict[str, str]]) -> str:
        """One turn, with the single retry §13.2 allows.

        Measured on deepseek-flash: the endpoint answers with an empty message or a 5xx every so
        often, and the very same request succeeds moments later. Without this, such a hiccup landed
        on the learner as a hard 502 in the middle of a conversation. Only failures the transport
        marked retryable get the second attempt, and a non-retryable one (401/422, a token budget
        that truncates the answer) fails immediately instead of duplicating the call.
        """
        attempts_left = ROLEPLAY_ATTEMPTS
        while True:
            attempts_left -= 1
            try:
                return await post_chat_completion(
                    self._client,
                    model=self._model,
                    messages=messages,
                    max_tokens=self._max_tokens,
                    error_cls=RoleplayProviderError,
                )
            except ModelEndpointError as exc:
                if attempts_left <= 0 or not exc.retryable:
                    raise
                await asyncio.sleep(self._retry_delay_seconds)


def build_roleplay_provider(settings: Settings):
    """Pick the provider from settings, failing closed on incomplete configuration."""
    from app.ai.roleplay import FakeRoleplayProvider, RoleplayProvider

    if settings.ai_provider == "mock":
        return FakeRoleplayProvider()
    if settings.ai_provider != "openai_compatible":
        raise RuntimeError(
            f"Unsupported AI_PROVIDER {settings.ai_provider!r}: use 'mock' or 'openai_compatible'."
        )
    if not settings.ai_model:
        raise RuntimeError("AI_MODEL must be set when AI_PROVIDER is not 'mock'.")
    api_key = settings.ai_api_key.get_secret_value() if settings.ai_api_key else ""
    if not api_key:
        raise RuntimeError("AI_API_KEY must be set when AI_PROVIDER is not 'mock'.")
    provider: RoleplayProvider = OpenAICompatibleRoleplayProvider(
        base_url=settings.ai_base_url,
        api_key=api_key,
        model=settings.ai_model,
        timeout_seconds=settings.ai_timeout_seconds,
        max_tokens=settings.ai_max_tokens,
        max_context_messages=settings.max_context_messages,
    )
    return provider
