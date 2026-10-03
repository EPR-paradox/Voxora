"""The meeting script: prompt shape, json output, and what happens to a script we cannot use.

docs/meeting-mode-v0.1.md §5. Two things worth guarding: the prompt never carries the scoring
material (same rule as the single-character prompt), and a script naming a speaker who is not in the
cast is rejected instead of written into the learner's transcript.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.ai.openai_compatible import (
    MEETING_MAX_TURNS,
    MEETING_MAX_WORDS_PER_TURN,
    OpenAICompatibleRoleplayProvider,
    RoleplayOutputError,
    build_meeting_system_prompt,
    parse_meeting_turns,
)
from app.core.config import Settings

MEETING_SCENARIO = {
    "situation": "A design review for a metrology data pipeline.",
    "user_objective": "Defend your estimate and agree on a scope.",
    "roleplay_instructions": "Keep it to twelve minutes.",
    "target_expressions": [{"expression": "I'd push back on that"}],
    "evaluation_rubric": {"version": "english-communication-v1"},
    "cast": [
        {
            "key": "eng_lead",
            "name": "Dana Whitfield",
            "title": "Engineering Lead",
            "personality": "direct",
            "communication_style": "short sentences",
        },
        {"key": "pm", "name": "Marco Ruiz", "title": "Product Manager"},
    ],
}
CAST_KEYS = {"eng_lead", "pm"}


def script(*turns: tuple[str, str]) -> str:
    return json.dumps({"turns": [{"speaker": key, "content": text} for key, text in turns]})


def json_response(payload: str) -> httpx.Response:
    return httpx.Response(
        200, json={"choices": [{"message": {"role": "assistant", "content": payload}}]}
    )


def provider_with_handler(handler) -> OpenAICompatibleRoleplayProvider:
    settings = Settings(
        ai_provider="openai_compatible",
        ai_base_url="https://model.test/v1",
        ai_model="deepseek-flash",
        ai_api_key="test-key",
    )
    return OpenAICompatibleRoleplayProvider(
        base_url=settings.ai_base_url,
        api_key="test-key",
        model=settings.ai_model,
        timeout_seconds=settings.ai_timeout_seconds,
        max_tokens=settings.ai_max_tokens,
        max_context_messages=settings.max_context_messages,
        meeting_max_tokens=settings.ai_meeting_max_tokens,
        retry_delay_seconds=0,
        transport=httpx.MockTransport(handler),
    )


def test_meeting_prompt_lists_the_cast_and_hides_the_scoring_material() -> None:
    prompt = build_meeting_system_prompt(MEETING_SCENARIO)

    assert "[eng_lead] Dana Whitfield, Engineering Lead" in prompt
    assert "[pm] Marco Ruiz, Product Manager" in prompt
    assert "direct" in prompt
    assert MEETING_SCENARIO["situation"] in prompt
    assert MEETING_SCENARIO["roleplay_instructions"] in prompt
    # §8.1 applies to the meeting prompt too.
    assert "push back" not in prompt
    assert "rubric" not in prompt.lower()


def test_meeting_prompt_states_the_output_contract() -> None:
    prompt = build_meeting_system_prompt(MEETING_SCENARIO)

    assert '"turns"' in prompt
    assert "speaker" in prompt
    assert "at most once in a round" in prompt


def test_the_round_cap_never_asks_for_more_speakers_than_the_room_has() -> None:
    """A 2-person room told "1 to 3 turns" repeats a speaker by pigeonhole, and the schema keeps
    one row per participant per round. The cap has to follow the cast."""
    prompt = build_meeting_system_prompt(MEETING_SCENARIO)
    cast_size = len(MEETING_SCENARIO["cast"])

    assert cast_size < MEETING_MAX_TURNS, "this test is only meaningful for a small room"
    assert f"1 to {cast_size} turns" in prompt


def test_parse_accepts_a_valid_script() -> None:
    turns = parse_meeting_turns(
        script(("eng_lead", "The estimate assumes one pipeline."), ("pm", "Can we split it?")),
        cast_keys=CAST_KEYS,
    )

    assert [(turn.speaker_key, turn.content) for turn in turns] == [
        ("eng_lead", "The estimate assumes one pipeline."),
        ("pm", "Can we split it?"),
    ]


def test_a_prose_script_is_accepted() -> None:
    """Measured: deepseek-flash answers in the roster notation even with json mode on.

    The wording is what the learner needs and the key is in the text, so this is usable — not a
    reason to fail the turn (docs/meeting-mode-v0.1.md §5).
    """
    raw = (
        "[eng_lead] Four weeks total, or four weeks of work plus buffer?\n"
        "\n"
        "[pm] Dropping the CSV import worries me.\n"
        "[pm] Is there a smaller cut that buys the same days?\n"
    )

    turns = parse_meeting_turns(raw, cast_keys=CAST_KEYS)

    # Two lines from one participant are one turn: the transcript holds one row per speaker.
    assert [(turn.speaker_key, turn.content[:14]) for turn in turns] == [
        ("eng_lead", "Four weeks tot"),
        ("pm", "Dropping the C"),
    ]
    assert turns[1].content.endswith("buys the same days?")


def test_a_speaker_returning_inside_one_turn_is_merged() -> None:
    """eng_lead, pm, eng_lead is one row per participant (§9.3): the returning line joins their row.

    Rejecting this was the bug, not caution: a two-person room asked for up to three turns repeats a
    speaker by pigeonhole, so these scripts reached the learner as 502s.
    """
    raw = script(
        ("eng_lead", "First point."), ("pm", "A question."), ("eng_lead", "And another thing.")
    )

    turns = parse_meeting_turns(raw, cast_keys=CAST_KEYS)

    assert [(turn.speaker_key, turn.content) for turn in turns] == [
        ("eng_lead", "First point. And another thing."),
        ("pm", "A question."),
    ]


def test_a_fenced_json_script_is_accepted() -> None:
    raw = "```json\n" + script(("eng_lead", "Let's start.")) + "\n```"

    turns = parse_meeting_turns(raw, cast_keys=CAST_KEYS)
    assert [turn.speaker_key for turn in turns] == ["eng_lead"]


def test_a_prose_script_with_an_unknown_speaker_is_rejected() -> None:
    with pytest.raises(RoleplayOutputError, match="not in this scenario's cast"):
        parse_meeting_turns("[ghost] Hello everyone.", cast_keys=CAST_KEYS)


def test_prose_with_chatter_around_it_is_rejected() -> None:
    """Anything we cannot read line by line is a failure, not something to guess at."""
    raw = "Sure, here is the script:\n\n" + "[eng_lead] Let's start."

    with pytest.raises(RoleplayOutputError, match="neither json nor a readable"):
        parse_meeting_turns(raw, cast_keys=CAST_KEYS)


@pytest.mark.parametrize(
    "payload",
    [
        "not json at all",
        json.dumps(["eng_lead"]),
        json.dumps({}),
        json.dumps({"turns": []}),
        json.dumps({"turns": "eng_lead"}),
        json.dumps({"turns": ["eng_lead"]}),
        script(("nobody", "Who is this?")),
        script(("eng_lead", "   ")),
        script(*[("eng_lead", f"line {index}") for index in range(MEETING_MAX_TURNS + 1)]),
        script(("eng_lead", " ".join(["word"] * (MEETING_MAX_WORDS_PER_TURN + 1)))),
    ],
)
def test_parse_rejects_scripts_that_cannot_be_trusted(payload: str) -> None:
    with pytest.raises(RoleplayOutputError):
        parse_meeting_turns(payload, cast_keys=CAST_KEYS)


@pytest.mark.asyncio
async def test_meeting_call_asks_for_json_and_uses_the_meeting_budget() -> None:
    captured: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return json_response(script(("eng_lead", "Let's start with the scope."), ("pm", "Agreed.")))

    provider = provider_with_handler(handler)
    try:
        turns = await provider.reply(
            MEETING_SCENARIO,
            [{"role": "assistant", "speaker_key": "pm", "content": "We have twelve minutes."}],
            "We can ship the parser first.",
        )
    finally:
        await provider.aclose()

    assert [turn.speaker_key for turn in turns] == ["eng_lead", "pm"]
    payload = captured[0]
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["max_tokens"] == Settings().ai_meeting_max_tokens
    # The history carries the speaker, or the participants cannot tell who said what.
    assert payload["messages"][1] == {
        "role": "assistant",
        "content": "[pm] We have twelve minutes.",
    }


@pytest.mark.asyncio
async def test_single_character_call_still_uses_plain_text() -> None:
    captured: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": "And then?"}}]}
        )

    provider = provider_with_handler(handler)
    try:
        turns = await provider.reply(
            {"ai_character": {"name": "Dana"}, "situation": "Interview"},
            [],
            "I shipped it.",
        )
    finally:
        await provider.aclose()

    assert [turn.speaker_key for turn in turns] == ["interviewer"]
    assert "response_format" not in captured[0]
    assert captured[0]["max_tokens"] == Settings().ai_max_tokens


@pytest.mark.asyncio
async def test_an_unusable_script_is_retried_once() -> None:
    calls: list[httpx.Request] = []
    responses = [
        json_response(script(("ghost", "I was never invited."))),
        json_response(script(("eng_lead", "Let's start with the scope."))),
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return responses[min(len(calls) - 1, len(responses) - 1)]

    provider = provider_with_handler(handler)
    try:
        turns = await provider.opening_turns(MEETING_SCENARIO)
    finally:
        await provider.aclose()

    assert [turn.speaker_key for turn in turns] == ["eng_lead"]
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_two_unusable_scripts_reach_the_caller() -> None:
    calls: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return json_response(script(("ghost", "Still not invited.")))

    provider = provider_with_handler(handler)
    try:
        with pytest.raises(RoleplayOutputError, match="not in this scenario's cast"):
            await provider.opening_turns(MEETING_SCENARIO)
    finally:
        await provider.aclose()

    assert len(calls) == 2
