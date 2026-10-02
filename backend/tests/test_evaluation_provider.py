"""The OpenAI-compatible evaluation provider: request shape, error mapping and the single retry."""

from __future__ import annotations

import json

import httpx
import pytest

from app.ai.evaluation import REQUIRED_DIMENSIONS, EvaluationRequest
from app.ai.openai_compatible_evaluation import (
    EVALUATION_ATTEMPTS,
    OpenAICompatibleEvaluationProvider,
)
from app.ai.openai_compatible_http import ModelEndpointError

LEARNER_TURN = "I built a measurement pipeline and cut the cycle time by half."


def report_json() -> str:
    return json.dumps(
        {
            "rubric_version": "english-communication-v1",
            "summary": "Clear answer.",
            "dimensions": {
                name: {"rating": "strong", "evidence": [LEARNER_TURN], "feedback": "Good."}
                for name in REQUIRED_DIMENSIONS
            },
            "strengths": [],
            "improvements": [],
            "suggested_rephrases": [],
            "review_items": [],
        }
    )


def chat_response(content: str, *, finish_reason: str = "stop") -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}, "finish_reason": finish_reason}]},
    )


def build_provider(handler, **overrides) -> OpenAICompatibleEvaluationProvider:
    kwargs = {
        "base_url": "https://model.test/v1",
        "api_key": "test-key",
        "model": "test-model",
        "timeout_seconds": 5,
        "max_tokens": 100,
        "retry_delay_seconds": 0,
    }
    kwargs.update(overrides)
    return OpenAICompatibleEvaluationProvider(transport=httpx.MockTransport(handler), **kwargs)


def evaluation_request() -> EvaluationRequest:
    return EvaluationRequest(
        scenario={"title": "T", "situation": "S", "user_objective": "O", "evaluation_rubric": {}},
        transcript=[{"role": "user", "content": LEARNER_TURN}],
        user_objective="O",
    )


async def test_valid_report_is_returned() -> None:
    provider = build_provider(lambda request: chat_response(report_json()))

    result = await provider.evaluate(evaluation_request())

    assert result["summary"] == "Clear answer."
    assert result["dimensions"]["clarity"]["evidence"] == [LEARNER_TURN]
    await provider.aclose()


async def test_transcript_travels_as_data_never_as_instructions() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return chat_response(report_json())

    provider = build_provider(handler)
    await provider.evaluate(evaluation_request())
    await provider.aclose()

    payload = json.loads(seen[0].content)
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["max_tokens"] == 100
    assert payload["messages"][0]["role"] == "system"
    assert LEARNER_TURN in payload["messages"][1]["content"]
    assert LEARNER_TURN not in payload["messages"][0]["content"], "user text never enters the rules"


async def test_json_mode_can_be_disabled() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return chat_response(report_json())

    provider = build_provider(handler, json_mode=False)
    await provider.evaluate(evaluation_request())
    await provider.aclose()

    assert "response_format" not in json.loads(seen[0].content)


async def test_empty_message_is_retried_once() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return chat_response("")
        return chat_response(report_json())

    provider = build_provider(handler)
    result = await provider.evaluate(evaluation_request())
    await provider.aclose()

    assert len(calls) == 2
    assert result["summary"] == "Clear answer."


async def test_truncated_report_is_retried_once() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return chat_response('{"summary": "Half a re')
        return chat_response(report_json())

    provider = build_provider(handler)
    result = await provider.evaluate(evaluation_request())
    await provider.aclose()

    assert len(calls) == 2
    assert result["summary"] == "Clear answer."


async def test_persistent_failure_reaches_the_caller() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return chat_response("")

    provider = build_provider(handler)
    with pytest.raises(ModelEndpointError):
        await provider.evaluate(evaluation_request())
    await provider.aclose()

    assert len(calls) == EVALUATION_ATTEMPTS


async def test_token_limit_is_a_provider_error_not_a_report() -> None:
    provider = build_provider(
        lambda request: chat_response('{"summary": "cut off', finish_reason="length")
    )

    with pytest.raises(ModelEndpointError, match="token limit"):
        await provider.evaluate(evaluation_request())
    await provider.aclose()


async def test_http_error_is_retried_then_reported() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500, text="upstream boom")

    provider = build_provider(handler)
    with pytest.raises(ModelEndpointError, match="500"):
        await provider.evaluate(evaluation_request())
    await provider.aclose()

    assert len(calls) == EVALUATION_ATTEMPTS


async def test_timeout_is_not_retried() -> None:
    """A timeout already cost the caller a full timeout window; retrying would double the wait."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ReadTimeout("too slow", request=request)

    provider = build_provider(handler)
    with pytest.raises(TimeoutError):
        await provider.evaluate(evaluation_request())
    await provider.aclose()

    assert len(calls) == 1
