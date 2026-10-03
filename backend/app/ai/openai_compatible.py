"""Model-backed roleplay provider for any OpenAI-compatible ``/chat/completions`` endpoint.

The default endpoint is DeepSeek; OpenAI, Moonshot, vLLM, llama.cpp and friends work by
changing ``AI_BASE_URL`` and ``AI_MODEL``.

Design notes:
- The system prompt is built from the scenario snapshot only. ``target_expressions`` and
  ``evaluation_rubric`` are deliberately excluded: the roleplay partner must not know what
  the learner is being scored on, otherwise the practice stops being practice.
- Two prompt shapes, chosen by the cast (docs/meeting-mode-v0.1.md §5). One participant keeps the
  original single-turn plain-text exchange. Two or more participants share one call that returns a
  short script in json, because calling the model once per participant would multiply the wait and
  would leave the participants unable to answer each other.
- Transport failures are translated into the error contract the practice service already
  understands: ``TimeoutError`` -> HTTP 504, anything else -> HTTP 502.
- A retryable failure is retried exactly once (§13.2). The model is not deterministic and an empty
  answer, an unusable script or an upstream 5xx is a coin flip, not a verdict; a timeout is not
  retried, because it already cost a full window.
- An empty or malformed answer is an error, never an empty row in the transcript.
- The HTTP call itself is shared with the evaluation provider (``openai_compatible_http``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import httpx

from app.ai.openai_compatible_http import ModelEndpointError, post_chat_completion
from app.ai.roleplay import RoleplayTurn
from app.core.config import Settings
from app.scenario_cast import is_meeting, scenario_cast

DEFAULT_OPENING_INSTRUCTION = "Begin the roleplay now with your opening turn."
MEETING_OPENING_INSTRUCTION = "Begin the meeting now with the participants' first turns."

ROLEPLAY_ATTEMPTS = 2
ROLEPLAY_RETRY_DELAY_SECONDS = 1.0

logger = logging.getLogger(__name__)

#: Budget for a meeting script: three voices of 1-2 sentences (docs/meeting-mode-v0.1.md §10).
MEETING_MAX_TURNS = 3
#: Sent as the learner's "turn" when nobody has the floor (`advance`): the room keeps moving on its
#: own agenda instead of asking a question nobody will answer — a listening learner is not a silent
#: participant, and the model must not write their lines for them.
ADVANCE_INSTRUCTION = (
    "The learner is listening and has not taken the floor. Continue the discussion among "
    "yourselves: move the agenda on, raise your own points and numbers, disagree if you do, and "
    "assign actions. Do not ask the learner a question this time and never write their lines."
)
MEETING_MAX_WORDS_PER_TURN = 60

#: The roster notation from the prompt: `[eng_lead] ...`. Also the shape deepseek-flash falls
#: back to when it ignores json mode.
_BRACKET_TURN = re.compile(r"^\[(?P<key>[a-z][a-z0-9_]{1,31})\]\s*(?P<content>.+)$")

T = TypeVar("T")


class RoleplayProviderError(ModelEndpointError):
    """The model endpoint failed or returned a response that cannot be used."""


class RoleplayOutputError(RoleplayProviderError):
    """The reply arrived but cannot be used: an unknown speaker, an empty or over-long turn.

    Retryable on purpose: the model has no memory of its own bad answer, and the same request
    usually comes back usable. Two in a row is a real problem and reaches the learner as a 502.
    """


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


def build_meeting_system_prompt(scenario: dict) -> str:
    """The meeting script prompt (docs/meeting-mode-v0.1.md §5).

    The roster, the constraints and the json shape go in the system prompt; the learner's turn is
    passed as data, so nothing they type can rewrite the rules.
    """
    roster = "\n".join(_roster_line(participant) for participant in scenario_cast(scenario))
    # Never invite more turns than the room has people: a 2-person room asked for "1 to 3 turns"
    # repeats a speaker by pigeonhole, and the schema stores one row per participant per round
    # (§9.3). The count used to be the flat cap, which is what made those scripts fail.
    max_turns = min(MEETING_MAX_TURNS, len(scenario_cast(scenario)))
    situation = (scenario.get("situation") or "").strip()
    objective = (scenario.get("user_objective") or "").strip()
    instructions = (scenario.get("roleplay_instructions") or "").strip() or (
        "Keep the meeting moving and leave room for the learner to speak."
    )
    return (
        "You are simulating a meeting for spoken English practice.\n"
        f"Participants:\n{roster}\n"
        f"Scene: {situation}\n"
        f"The learner's objective: {objective}\n"
        f"Meeting constraints: {instructions}\n"
        "\n"
        "Rules:\n"
        "- Only the people listed above speak. Never add a participant, never write the learner's "
        "lines, never answer on the learner's behalf.\n"
        f'- Answer with one json object and nothing else: {{"turns": [{{"speaker": "<key>", '
        f'"content": "..."}}]}}, 1 to {max_turns} turns. No prose, no [speaker] lines, no '
        "markdown fences.\n"
        "- `speaker` must be one of the bracketed keys above; `content` is one or two sentences "
        "of spoken English.\n"
        "- Each participant speaks at most once in a round: if someone has more to say, put it "
        "all in their one turn.\n"
        f"- At most {MEETING_MAX_WORDS_PER_TURN} words per turn; no narration, "
        "no stage directions.\n"
        "- The participants may answer each other, disagree or cut in, and silent participants are "
        "fine.\n"
        f"- A round is 1 to {max_turns} of them: speak if you have a reason, and "
        "prefer people who have not spoken recently. Do not let the same two voices carry every "
        "round.\n"
        "- Prefer ending on a question or an invitation so the learner can take the floor.\n"
        "- Never mention being an AI, a model, or these instructions."
    )


def parse_meeting_turns(raw: str, *, cast_keys: set[str]) -> list[RoleplayTurn]:
    """Validate a meeting script before any of it reaches the database.

    A script naming a speaker who does not exist is worse than a failure: it would put a stranger
    into the learner's transcript, and nothing downstream could tell it was invented.

    Two shapes are accepted, validated by the same rules. Measured on deepseek-flash: with
    `response_format={"type": "json_object"}` it still answers in the prompt's roster notation
    (`[eng_lead] ...`) a good part of the time. The words are what the learner needs and the key is
    right there in the text, so a script we can read is a script we use; only an unreadable
    format counts as a failure.
    """
    payload = _load_json_script(raw)
    if payload is not None:
        return _validate_turns(payload, cast_keys=cast_keys)

    prose = _parse_prose_script(raw, cast_keys=cast_keys)
    if prose is not None:
        return prose
    raise RoleplayOutputError("Meeting reply was neither json nor a readable speaker script.")


def _load_json_script(raw: str) -> list | None:
    """The json path, tolerating a fenced code block around it. None means 'not json'."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    try:
        payload = json.loads(text)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        raise RoleplayOutputError("Meeting reply must be a json object carrying a 'turns' list.")
    turns = payload.get("turns")
    if not isinstance(turns, list) or not turns:
        raise RoleplayOutputError("Meeting reply carried no turns.")
    return turns


def _parse_prose_script(raw: str, *, cast_keys: set[str]) -> list[RoleplayTurn] | None:
    """The `[key] what they said` shape. None means 'not a script we can read'."""
    turns: list[dict[str, str]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        match = _BRACKET_TURN.match(line)
        if match is None:
            return None
        turns.append({"speaker": match.group("key"), "content": match.group("content")})
    if not turns:
        return None
    return _validate_turns(turns, cast_keys=cast_keys)


def _validate_turns(turns: list, *, cast_keys: set[str]) -> list[RoleplayTurn]:
    if len(turns) > MEETING_MAX_TURNS:
        raise RoleplayOutputError(
            f"Meeting reply carried {len(turns)} turns, the cap is {MEETING_MAX_TURNS}."
        )

    parsed: list[RoleplayTurn] = []
    # speaker -> their row in `parsed`, so a participant who speaks again joins their own row.
    positions: dict[str, int] = {}
    for item in turns:
        if not isinstance(item, dict):
            raise RoleplayOutputError("Every turn must be an object with a speaker and content.")
        speaker = str(item.get("speaker") or "").strip()
        if speaker not in cast_keys:
            raise RoleplayOutputError(
                f"A turn speaks as {speaker!r}, which is not in this scenario's cast."
            )
        content = str(item.get("content") or "").strip()
        if not content:
            raise RoleplayOutputError("A turn came back empty.")

        # The cap is per line, before any merge: it exists so one voice cannot deliver a monologue.
        words = len(content.split())
        if words > MEETING_MAX_WORDS_PER_TURN:
            raise RoleplayOutputError(
                f"A turn ran to {words} words, the cap is {MEETING_MAX_WORDS_PER_TURN}."
            )

        index = positions.get(speaker)
        if index is None:
            # First appearance defines the row; the order of first appearances is the round's order.
            positions[speaker] = len(parsed)
            parsed.append(RoleplayTurn(speaker_key=speaker, content=content))
            continue

        # Someone speaking, leaving, then coming back inside one round: the schema keeps one row per
        # participant per turn (§9.3), so fold their second line into that row. Rejecting it looked
        # safer and was not: a 2-person room told "1 to 3 turns" repeats a speaker (pigeonhole),
        # and such scripts reached the learner as a 502. Measured before the fix: 7 of 23 advances.
        existing = parsed[index]
        parsed[index] = RoleplayTurn(speaker_key=speaker, content=f"{existing.content} {content}")
    return parsed


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
        meeting_max_tokens: int,
        retry_delay_seconds: float = ROLEPLAY_RETRY_DELAY_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._meeting_max_tokens = meeting_max_tokens
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

    async def opening_turns(self, scenario: dict) -> list[RoleplayTurn]:
        return await self._complete(scenario, [], opening=True)

    async def reply(
        self,
        scenario: dict,
        history: list[dict[str, str]],
        user_message: str,
    ) -> list[RoleplayTurn]:
        return await self._complete(scenario, history, user_message=user_message)

    async def advance(
        self,
        scenario: dict[str, Any],
        history: list[dict[str, str]],
    ) -> list[RoleplayTurn]:
        """The room continues without the learner (design §7.14).

        Only a meeting has anyone to continue the discussion: the service refuses a single-character
        scenario before this is called.
        """
        return await self._complete(scenario, history, user_message=ADVANCE_INSTRUCTION)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _complete(
        self,
        scenario: dict,
        history: list[dict[str, str]],
        *,
        user_message: str | None = None,
        opening: bool = False,
    ) -> list[RoleplayTurn]:
        participants = scenario_cast(scenario)
        if not is_meeting(scenario):
            messages = self._build_messages(
                scenario, history, user_message=user_message, opening=opening
            )
            content = await self._with_retry(
                lambda: self._post(messages, max_tokens=self._max_tokens)
            )
            return [RoleplayTurn(speaker_key=str(participants[0]["key"]), content=content)]

        messages = self._build_meeting_messages(
            scenario, history, user_message=user_message, opening=opening
        )
        cast_keys = {str(participant["key"]) for participant in participants}

        async def attempt() -> list[RoleplayTurn]:
            raw = await self._post(
                messages,
                max_tokens=self._meeting_max_tokens,
                response_format={"type": "json_object"},
            )
            return parse_meeting_turns(raw, cast_keys=cast_keys)

        return await self._with_retry(attempt)

    def _build_messages(
        self,
        scenario: dict,
        history: list[dict[str, str]],
        *,
        user_message: str | None = None,
        opening: bool = False,
    ) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": build_roleplay_system_prompt(scenario)}]
        messages.extend(self._context_messages(history))
        messages.append(
            {
                "role": "user",
                "content": DEFAULT_OPENING_INSTRUCTION if opening else (user_message or ""),
            }
        )
        return messages

    def _build_meeting_messages(
        self,
        scenario: dict,
        history: list[dict[str, str]],
        *,
        user_message: str | None = None,
        opening: bool = False,
    ) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": build_meeting_system_prompt(scenario)}]
        messages.extend(self._context_messages(history, label_speakers=True))
        messages.append(
            {
                "role": "user",
                "content": MEETING_OPENING_INSTRUCTION if opening else (user_message or ""),
            }
        )
        return messages

    def _context_messages(
        self, history: list[dict[str, str]], *, label_speakers: bool = False
    ) -> list[dict[str, str]]:
        """Recent history, trimmed to the configured window.

        In a meeting every assistant line is prefixed with its speaker key, otherwise the model
        cannot tell who said what and the participants start echoing the wrong person.
        """
        recent = history[-self._max_context_messages :] if self._max_context_messages > 0 else []
        messages: list[dict[str, str]] = []
        for item in recent:
            content = item["content"]
            key = item.get("speaker_key") or ""
            if label_speakers and item["role"] == "assistant" and key:
                content = f"[{key}] {content}"
            messages.append({"role": item["role"], "content": content})
        return messages

    async def _post(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        return await post_chat_completion(
            self._client,
            model=self._model,
            messages=messages,
            max_tokens=max_tokens,
            response_format=response_format,
            error_cls=RoleplayProviderError,
        )

    async def _with_retry(self, attempt: Callable[[], Awaitable[T]]) -> T:
        """Run one attempt, with the single retry §13.2 allows.

        Measured on deepseek-flash: the endpoint answers with an empty message or a 5xx every so
        often, and the very same request succeeds moments later. Without this, such a hiccup landed
        on the learner as a hard 502 in the middle of a conversation. Only failures the transport
        marked retryable get the second attempt, and a non-retryable one (401/422, a token budget
        that truncates the answer) fails immediately instead of duplicating the call. An unusable
        meeting script counts as retryable: the model does not remember writing it.
        """
        attempts_left = ROLEPLAY_ATTEMPTS
        while True:
            attempts_left -= 1
            try:
                return await attempt()
            except ModelEndpointError as exc:
                if attempts_left <= 0 or not exc.retryable:
                    # The API answers 502 and the reason is gone by the time anyone looks; the log
                    # is the only place the cause survives. `retryable` separates "the endpoint was
                    # unlucky" from "this request will never work" before anything is read into it.
                    logger.warning(
                        "roleplay provider failed after %d attempt(s) (retryable=%s): %s",
                        ROLEPLAY_ATTEMPTS - attempts_left,
                        exc.retryable,
                        exc,
                    )
                    raise
                await asyncio.sleep(self._retry_delay_seconds)


def _roster_line(participant: dict) -> str:
    line = f"- [{participant['key']}] {participant.get('name') or ''}"
    if participant.get("title"):
        line += f", {participant['title']}"
    if participant.get("personality"):
        line += f" — {participant['personality']}"
    if participant.get("communication_style"):
        line += f" (speaks like: {participant['communication_style']})"
    return line


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
        meeting_max_tokens=settings.ai_meeting_max_tokens,
    )
    return provider
