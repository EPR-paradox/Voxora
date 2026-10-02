"""Shared transport for OpenAI-compatible ``/chat/completions`` endpoints.

Both the roleplay and the evaluation provider talk to the same wire format and need the same error
translation, so the request is written once here. Failure mapping is part of the domain contract:

- ``TimeoutError`` -> the caller maps it to HTTP 504, and **never retries**: a timeout already cost
  a full window, so a second attempt doubles the wait for a learner who is sitting in the chat.
- ``ModelEndpointError`` -> the caller maps it to HTTP 502, and retries it once when
  ``error.retryable`` is set.

``retryable`` encodes §13.2: retry what a later moment can fix (empty or unusable output, 5xx, 429,
transport hiccups, a truncated answer — see the note on `finish_reason` below) and never retry what
only a human can fix (401/403/422
for the answer, a request the endpoint refuses). An empty or malformed assistant message is an
error, never an empty row in a transcript.
"""

from __future__ import annotations

from typing import Any

import httpx

# Upstream statuses worth a second attempt: rate limiting, request timeouts, server-side faults.
RETRYABLE_STATUS_CODES = {408, 409, 425, 429}


def _is_retryable_status(status_code: int) -> bool:
    return status_code in RETRYABLE_STATUS_CODES or status_code >= 500


class ModelEndpointError(RuntimeError):
    """The model endpoint failed or returned a response that cannot be used."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


async def post_chat_completion(
    client: httpx.AsyncClient,
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    response_format: dict[str, Any] | None = None,
    error_cls: type[ModelEndpointError] = ModelEndpointError,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if response_format is not None:
        payload["response_format"] = response_format

    try:
        response = await client.post("chat/completions", json=payload)
    except httpx.TimeoutException as exc:
        raise TimeoutError("The model endpoint timed out.") from exc
    except httpx.HTTPError as exc:
        raise error_cls(f"Model endpoint request failed: {exc}") from exc

    if response.status_code != 200:
        raise error_cls(
            f"Model endpoint returned HTTP {response.status_code}: {response.text[:300]}",
            retryable=_is_retryable_status(response.status_code),
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise error_cls("Model endpoint returned a non-JSON body.") from exc

    try:
        choice = body["choices"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise error_cls("Model endpoint response is missing the assistant message.") from exc
    # A truncated answer is the model spending its whole budget on internal reasoning and emitting
    # nothing, not a malformed reply, so say so instead of handing half a sentence to the caller.
    #
    # It is retryable, a reversal measured on 2026-10-02: `deepseek-flash` burned 1627 characters
    # of reasoning on one call and 0 on the next for the *same* prompt, so a truncation is a
    # lottery, not a property of the request. At a 400-token budget that was 1 call in 10 (2 in 8
    # through the API), each reaching the learner as a bare 502 — worse than one extra attempt.
    # The budget was raised too (AI_MAX_TOKENS): removing a cause beats retrying it.
    if isinstance(choice, dict) and choice.get("finish_reason") == "length":
        raise error_cls("Model endpoint hit the token limit before finishing its answer.")

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise error_cls("Model endpoint response is missing the assistant message.") from exc
    if not isinstance(content, str) or not content.strip():
        raise error_cls("Model endpoint returned an empty assistant message.")
    return content.strip()
