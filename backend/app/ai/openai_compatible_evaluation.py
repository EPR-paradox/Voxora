"""Model-backed evaluation provider for any OpenAI-compatible ``/chat/completions`` endpoint.

Same wire protocol as the roleplay provider; what differs is the prompt and the fact that the answer
is a
structured document that has to survive validation before it is allowed near the database (design
§8.3).

Design notes:
- The prompt text is loaded from ``app/ai/prompts/evaluation_english_v1.txt`` and its version is
stored with
  every evaluation, so a stored result can be traced to the exact prompt that produced it (§8.5).
- The learner's transcript is passed as data, never concatenated into the system prompt: user turns
are
  untrusted text and must not be able to rewrite the reviewer's rules.
- ``response_format`` json mode is used when the endpoint supports it (DeepSeek does). Turning it
off is a
  configuration choice for endpoints that reject the field.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from app.ai.evaluation import (
    PROMPT_VERSION,
    RUBRIC_VERSION,
    EvaluationOutputError,
    EvaluationRequest,
    learner_turns,
    parse_evaluation_result,
)
from app.ai.openai_compatible_http import ModelEndpointError, post_chat_completion
from app.ai.prompts import EVALUATION_PROMPT_FILE, load_prompt
from app.core.config import Settings

EVALUATION_ATTEMPTS = 2
EVALUATION_RETRY_DELAY_SECONDS = 1.0


def build_evaluation_user_prompt(request: EvaluationRequest) -> str:
    """Render the session as data. Only what the rubric needs — never secrets or unrelated user
    data."""
    scenario = request.scenario
    payload = {
        "scenario": {
            "title": scenario.get("title"),
            "situation": scenario.get("situation"),
            "user_objective": request.user_objective,
            "evaluation_rubric": scenario.get("evaluation_rubric"),
        },
        "transcript": [
            {"role": turn.get("role"), "text": turn.get("content", "")}
            for turn in request.transcript
        ],
        "note": "Only turns with role 'user' are the learner's own English. "
        "Never quote role 'assistant'.",
    }
    return (
        "Review this completed practice session and return the json evaluation.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


class OpenAICompatibleEvaluationProvider:
    name = "openai_compatible"
    prompt_version = PROMPT_VERSION
    rubric_version = RUBRIC_VERSION

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_tokens: int,
        json_mode: bool = True,
        retry_delay_seconds: float = EVALUATION_RETRY_DELAY_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._max_tokens = max_tokens
        self._json_mode = json_mode
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

    async def evaluate(self, request: EvaluationRequest) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": load_prompt(EVALUATION_PROMPT_FILE)},
            {"role": "user", "content": build_evaluation_user_prompt(request)},
        ]
        learner = learner_turns(request.transcript)
        # Measured against deepseek-flash: with a realistic token budget the endpoint still answers
        # with an empty message or a half-written report every so often, and the same request
        # succeeds moments later. One immediate retry turns that coin flip into the report the
        # learner is already waiting for; if the second attempt fails too, the failure is real and
        # belongs to the caller, which reports it with the manual retry path from §9.2.
        last_error: Exception | None = None
        for attempt in range(EVALUATION_ATTEMPTS):
            try:
                raw = await post_chat_completion(
                    self._client,
                    model=self.model,
                    messages=messages,
                    max_tokens=self._max_tokens,
                    response_format={"type": "json_object"} if self._json_mode else None,
                )
                return parse_evaluation_result(raw, learner_turns=learner)
            except (ModelEndpointError, EvaluationOutputError) as exc:
                last_error = exc
                if attempt + 1 < EVALUATION_ATTEMPTS:
                    await asyncio.sleep(self._retry_delay_seconds)
        raise last_error

    async def aclose(self) -> None:
        await self._client.aclose()


def build_evaluation_provider(settings: Settings):
    """Pick the evaluation provider from settings, failing closed on incomplete configuration."""
    from app.ai.evaluation import FakeEvaluationProvider

    if settings.ai_provider == "mock":
        return FakeEvaluationProvider()
    if settings.ai_provider != "openai_compatible":
        raise RuntimeError(
            f"Unsupported AI_PROVIDER {settings.ai_provider!r}: use 'mock' or 'openai_compatible'."
        )
    if not settings.ai_model:
        raise RuntimeError("AI_MODEL must be set when AI_PROVIDER is not 'mock'.")
    api_key = settings.ai_api_key.get_secret_value() if settings.ai_api_key else ""
    if not api_key:
        raise RuntimeError("AI_API_KEY must be set when AI_PROVIDER is not 'mock'.")
    return OpenAICompatibleEvaluationProvider(
        base_url=settings.ai_base_url,
        api_key=api_key,
        model=settings.ai_model,
        timeout_seconds=settings.ai_evaluation_timeout_seconds,
        max_tokens=settings.ai_evaluation_max_tokens,
        json_mode=settings.ai_json_mode,
    )


__all__ = [
    "OpenAICompatibleEvaluationProvider",
    "build_evaluation_provider",
    "build_evaluation_user_prompt",
]
