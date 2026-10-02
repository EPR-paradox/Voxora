"""Contract tests for the roleplay providers.

Covered: provider selection, prompt construction, context trimming, and the mapping of
transport/response failures onto the error contract the practice service relies on
(``TimeoutError`` -> 504, anything else -> 502).
"""

import json

import httpx
import pytest

from app.ai.openai_compatible import (
    DEFAULT_OPENING_INSTRUCTION,
    ROLEPLAY_ATTEMPTS,
    OpenAICompatibleRoleplayProvider,
    RoleplayProviderError,
    build_roleplay_provider,
    build_roleplay_system_prompt,
)
from app.ai.roleplay import FakeRoleplayProvider
from app.core.config import Settings

SCENARIO = {
    "id": "3f1c9f34-0c1e-4b7a-9f5f-2f3a5b6c7d8e",
    "title": "Explain a metrology project",
    "situation": "A hiring manager asks about your last project.",
    "ai_character": {"name": "Dana", "title": "Hiring Manager"},
    "user_objective": "Explain your role and one challenge.",
    "roleplay_instructions": "Ask one follow-up question at a time.",
    "target_expressions": ["root cause analysis"],
    "evaluation_rubric": {"rubric_version": "english-communication-v1"},
}


def make_settings(**overrides) -> Settings:
    values = {
        "ai_provider": "openai_compatible",
        "ai_base_url": "https://model.test/v1",
        "ai_model": "deepseek-chat",
        "ai_api_key": "test-key",
    }
    values.update(overrides)
    return Settings(**values)


def completion_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": content}}]},
    )


def provider_with_handler(handler, **overrides) -> OpenAICompatibleRoleplayProvider:
    settings = make_settings(**overrides)
    api_key = settings.ai_api_key.get_secret_value() if settings.ai_api_key else ""
    return OpenAICompatibleRoleplayProvider(
        base_url=settings.ai_base_url,
        api_key=api_key,
        model=settings.ai_model,
        timeout_seconds=settings.ai_timeout_seconds,
        max_tokens=settings.ai_max_tokens,
        max_context_messages=settings.max_context_messages,
        retry_delay_seconds=0,
        transport=httpx.MockTransport(handler),
    )


def test_mock_provider_is_selected_by_default() -> None:
    assert isinstance(build_roleplay_provider(Settings(ai_provider="mock")), FakeRoleplayProvider)


def test_unset_provider_defaults_to_mock() -> None:
    assert isinstance(build_roleplay_provider(Settings(_env_file=None)), FakeRoleplayProvider)


def test_unknown_provider_name_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="Unsupported AI_PROVIDER"):
        build_roleplay_provider(make_settings(ai_provider="anthropic"))


def test_missing_model_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="AI_MODEL must be set"):
        build_roleplay_provider(make_settings(ai_model=""))


def test_missing_api_key_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="AI_API_KEY must be set"):
        build_roleplay_provider(make_settings(ai_api_key=None))


def test_real_provider_is_built_from_settings() -> None:
    provider = build_roleplay_provider(make_settings())

    assert isinstance(provider, OpenAICompatibleRoleplayProvider)


def test_system_prompt_hides_scoring_material() -> None:
    prompt = build_roleplay_system_prompt(SCENARIO)

    assert "Dana, Hiring Manager" in prompt
    assert SCENARIO["situation"] in prompt
    assert SCENARIO["roleplay_instructions"] in prompt
    # The roleplay partner must not know what the learner is scored on.
    assert "root cause analysis" not in prompt
    assert "rubric" not in prompt.lower()


def test_system_prompt_falls_back_when_scenario_is_sparse() -> None:
    prompt = build_roleplay_system_prompt({"ai_character": None})

    assert "Interviewer" in prompt
    assert "Ask one follow-up question at a time." in prompt


@pytest.mark.asyncio
async def test_opening_message_sends_system_prompt_and_opening_instruction() -> None:
    captured: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append({"url": str(request.url), "payload": _json_body(request)})
        return completion_response("  So, tell me about the project.  ")

    provider = provider_with_handler(handler)
    try:
        content = await provider.opening_message(SCENARIO)
    finally:
        await provider.aclose()

    assert content == "So, tell me about the project."
    assert captured[0]["url"] == "https://model.test/v1/chat/completions"
    payload = captured[0]["payload"]
    assert payload["model"] == "deepseek-chat"
    assert payload["max_tokens"] == 400
    assert payload["stream"] is False
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][-1] == {
        "role": "user",
        "content": DEFAULT_OPENING_INSTRUCTION,
    }


@pytest.mark.asyncio
async def test_reply_keeps_only_the_most_recent_context_messages() -> None:
    captured: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(_json_body(request))
        return completion_response("What was the main challenge?")

    provider = provider_with_handler(handler, max_context_messages=2)
    history = [
        {"role": "assistant", "content": "opening"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
        {"role": "user", "content": "third"},
    ]
    try:
        await provider.reply(SCENARIO, history, "Where do I start?")
    finally:
        await provider.aclose()

    assert [message["content"] for message in captured[0]["messages"][1:]] == [
        "second",
        "third",
        "Where do I start?",
    ]


@pytest.mark.asyncio
async def test_timeout_maps_to_timeout_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    provider = provider_with_handler(handler)
    try:
        with pytest.raises(TimeoutError):
            await provider.reply(SCENARIO, [], "Hello?")
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_connection_failure_maps_to_provider_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider = provider_with_handler(handler)
    try:
        with pytest.raises(RoleplayProviderError):
            await provider.reply(SCENARIO, [], "Hello?")
    finally:
        await provider.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 429, 500])
async def test_error_status_maps_to_provider_error(status_code: int) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"message": "nope"}})

    provider = provider_with_handler(handler)
    try:
        with pytest.raises(RoleplayProviderError, match=str(status_code)):
            await provider.opening_message(SCENARIO)
    finally:
        await provider.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>not json</html>"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {"content": ""}}]}),
        httpx.Response(200, json={"choices": [{"message": {"content": "   "}}]}),
        httpx.Response(200, json={"choices": [{"message": {"content": None}}]}),
    ],
)
async def test_unusable_body_maps_to_provider_error(response: httpx.Response) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return response

    provider = provider_with_handler(handler)
    try:
        with pytest.raises(RoleplayProviderError):
            await provider.opening_message(SCENARIO)
    finally:
        await provider.aclose()


def _json_body(request: httpx.Request) -> dict:
    return json.loads(request.content)


def _counting_handler(responses: list[httpx.Response], calls: list[httpx.Request]):
    """Answer with the queued responses in order, repeating the last one for extra calls."""

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return responses[min(len(calls) - 1, len(responses) - 1)]

    return handler


@pytest.mark.asyncio
async def test_empty_answer_is_retried_once() -> None:
    """The measured coin flip: an empty message now, the same request answered a second later."""
    calls: list[httpx.Request] = []
    handler = _counting_handler(
        [completion_response("   "), completion_response("What was the main challenge?")], calls
    )

    provider = provider_with_handler(handler)
    try:
        content = await provider.reply(SCENARIO, [], "I ran the pipeline.")
    finally:
        await provider.aclose()

    assert content == "What was the main challenge?"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_upstream_5xx_is_retried_once() -> None:
    calls: list[httpx.Request] = []
    handler = _counting_handler(
        [
            httpx.Response(500, text="upstream boom"),
            completion_response("Got it. What did the sensor noise look like?"),
        ],
        calls,
    )

    provider = provider_with_handler(handler)
    try:
        content = await provider.reply(SCENARIO, [], "I ran the pipeline.")
    finally:
        await provider.aclose()

    assert content.startswith("Got it.")
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_two_failures_surface_as_provider_error_after_two_calls() -> None:
    """The retry is an attempt, not a guarantee: a real outage must still reach the caller."""
    calls: list[httpx.Request] = []
    handler = _counting_handler([httpx.Response(503, text="down")], calls)

    provider = provider_with_handler(handler)
    try:
        with pytest.raises(RoleplayProviderError):
            await provider.reply(SCENARIO, [], "Hello?")
    finally:
        await provider.aclose()

    assert len(calls) == ROLEPLAY_ATTEMPTS


@pytest.mark.asyncio
async def test_rejected_request_is_not_retried() -> None:
    """§13.2: a request the endpoint refuses is refused again, so do not spend a second call."""
    calls: list[httpx.Request] = []
    handler = _counting_handler(
        [httpx.Response(401, json={"error": {"message": "bad key"}})], calls
    )

    provider = provider_with_handler(handler)
    try:
        with pytest.raises(RoleplayProviderError, match="401"):
            await provider.reply(SCENARIO, [], "Hello?")
    finally:
        await provider.aclose()

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_truncated_answer_is_not_retried() -> None:
    """`finish_reason=length` is a token budget that is too small: the same call truncates again."""
    calls: list[httpx.Request] = []
    truncated = httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {"role": "assistant", "content": "half a sen"},
                    "finish_reason": "length",
                }
            ]
        },
    )
    handler = _counting_handler([truncated], calls)

    provider = provider_with_handler(handler)
    try:
        with pytest.raises(RoleplayProviderError, match="token limit"):
            await provider.reply(SCENARIO, [], "Hello?")
    finally:
        await provider.aclose()

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_timeout_is_not_retried() -> None:
    calls: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ReadTimeout("timed out", request=request)

    provider = provider_with_handler(handler)
    try:
        with pytest.raises(TimeoutError):
            await provider.reply(SCENARIO, [], "Hello?")
    finally:
        await provider.aclose()

    assert len(calls) == 1
