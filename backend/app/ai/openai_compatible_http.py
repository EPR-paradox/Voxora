"""Shared transport for OpenAI-compatible ``/chat/completions`` endpoints.

Both the roleplay and the evaluation provider talk to the same wire format and need the same error
translation, so the request is written once here. Failure mapping is part of the domain contract:

- ``TimeoutError`` -> the caller maps it to HTTP 504
- ``ModelEndpointError`` -> the caller maps it to HTTP 502

An empty or malformed assistant message is an error, never an empty row in a transcript.
"""

from __future__ import annotations

from typing import Any

import httpx


class ModelEndpointError(RuntimeError):
    """The model endpoint failed or returned a response that cannot be used."""


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
            f"Model endpoint returned HTTP {response.status_code}: {response.text[:300]}"
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise error_cls("Model endpoint returned a non-JSON body.") from exc

    try:
        choice = body["choices"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise error_cls("Model endpoint response is missing the assistant message.") from exc
    # A truncated answer is a configuration problem (a token budget too small for the model's
    # reasoning overhead), not a malformed reply: say so rather than hand half a sentence to the
    # caller.
    if isinstance(choice, dict) and choice.get("finish_reason") == "length":
        raise error_cls("Model endpoint hit the token limit before finishing its answer.")

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise error_cls("Model endpoint response is missing the assistant message.") from exc
    if not isinstance(content, str) or not content.strip():
        raise error_cls("Model endpoint returned an empty assistant message.")
    return content.strip()
