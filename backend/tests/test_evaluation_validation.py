"""Evaluation output validation: the model is untrusted input (design §8.3, §14.2 #9)."""

from __future__ import annotations

import json

import pytest

from app.ai.evaluation import (
    REQUIRED_DIMENSIONS,
    EvaluationOutputError,
    parse_evaluation_result,
)

LEARNER_TURN = (
    "I built a measurement pipeline for overlay metrology and cut the cycle time by half."
)
LEARNER_TURNS = [LEARNER_TURN]
PARTNER_LINE = "Could you walk me through a project you are proud of?"


def valid_payload(**overrides) -> dict:
    payload = {
        "rubric_version": "english-communication-v1",
        "summary": "Clear answer with a concrete result.",
        "dimensions": {
            name: {"rating": "strong", "evidence": [LEARNER_TURN], "feedback": "Keep it up."}
            for name in REQUIRED_DIMENSIONS
        },
        "strengths": ["Concrete numbers."],
        "improvements": ["Explain the method before the result."],
        "suggested_rephrases": [
            {
                "original": LEARNER_TURN,
                "suggestion": "We cut the cycle time by half.",
                "reason": "Shorter and more direct.",
            }
        ],
        "review_items": [
            {
                "item_type": "expression",
                "original_text": LEARNER_TURN,
                "target_text": "We cut the cycle time by half.",
                "explanation": "Lead with the result.",
            }
        ],
    }
    payload.update(overrides)
    return payload


def parse(payload: dict) -> dict:
    return parse_evaluation_result(json.dumps(payload), learner_turns=LEARNER_TURNS)


def test_valid_payload_is_accepted() -> None:
    result = parse(valid_payload())

    assert result["rubric_version"] == "english-communication-v1"
    assert set(result["dimensions"]) == set(REQUIRED_DIMENSIONS)
    assert result["dimensions"]["clarity"]["evidence"] == [LEARNER_TURN]
    assert result["improvements"] == ["Explain the method before the result."]
    assert result["review_items"][0]["item_type"] == "expression"


def test_partner_line_as_evidence_is_rejected() -> None:
    dimensions = {
        name: {"rating": "strong", "evidence": [PARTNER_LINE], "feedback": "Fine."}
        for name in REQUIRED_DIMENSIONS
    }

    with pytest.raises(EvaluationOutputError, match="attributable"):
        parse(valid_payload(dimensions=dimensions))


def test_unattributable_evidence_is_dropped_but_the_rest_survives() -> None:
    dimensions = valid_payload()["dimensions"]
    dimensions["clarity"] = {
        "rating": "developing",
        "evidence": [PARTNER_LINE, LEARNER_TURN],
        "feedback": "Tighten the opening.",
    }

    result = parse(valid_payload(dimensions=dimensions))

    assert result["dimensions"]["clarity"]["evidence"] == [LEARNER_TURN]


def test_missing_dimension_is_rejected() -> None:
    dimensions = valid_payload()["dimensions"]
    del dimensions["fluency"]

    with pytest.raises(EvaluationOutputError, match="fluency"):
        parse(valid_payload(dimensions=dimensions))


def test_out_of_range_rating_is_rejected() -> None:
    dimensions = valid_payload()["dimensions"]
    dimensions["clarity"] = {"rating": "excellent", "evidence": [LEARNER_TURN], "feedback": "Nice."}

    with pytest.raises(EvaluationOutputError, match="rating"):
        parse(valid_payload(dimensions=dimensions))


def test_missing_feedback_is_rejected() -> None:
    dimensions = valid_payload()["dimensions"]
    dimensions["naturalness"] = {"rating": "strong", "evidence": [LEARNER_TURN], "feedback": "  "}

    with pytest.raises(EvaluationOutputError, match="feedback"):
        parse(valid_payload(dimensions=dimensions))


def test_non_json_output_is_rejected() -> None:
    with pytest.raises(EvaluationOutputError):
        parse_evaluation_result("I think the learner did fine.", learner_turns=LEARNER_TURNS)


def test_json_array_is_rejected() -> None:
    with pytest.raises(EvaluationOutputError, match="object"):
        parse_evaluation_result("[1, 2, 3]", learner_turns=LEARNER_TURNS)


def test_markdown_fenced_json_is_tolerated() -> None:
    fenced = f"```json\n{json.dumps(valid_payload())}\n```"

    result = parse_evaluation_result(fenced, learner_turns=LEARNER_TURNS)

    assert result["summary"] == "Clear answer with a concrete result."


def test_prose_around_the_object_is_tolerated() -> None:
    wrapped = f"Here is the report:\n{json.dumps(valid_payload())}\nHope this helps."

    result = parse_evaluation_result(wrapped, learner_turns=LEARNER_TURNS)

    assert result["summary"] == "Clear answer with a concrete result."


def test_improvements_are_capped_at_three() -> None:
    result = parse(valid_payload(improvements=[f"point {i}" for i in range(9)]))

    assert len(result["improvements"]) == 3


def test_review_item_with_invented_quote_is_dropped() -> None:
    invented = {
        "item_type": "grammar",
        "original_text": "The precision becomes bad when the stage drifts.",
        "target_text": "Precision degrades when the stage drifts.",
        "explanation": "Use degrade.",
    }
    payload = valid_payload(review_items=[*valid_payload()["review_items"], invented])

    result = parse(payload)

    assert len(result["review_items"]) == 1
    assert result["review_items"][0]["original_text"] == LEARNER_TURN


def test_review_item_with_unknown_type_is_dropped() -> None:
    payload = valid_payload(
        review_items=[
            {
                "item_type": "vocabulary",
                "original_text": LEARNER_TURN,
                "target_text": "x",
                "explanation": "y",
            }
        ]
    )

    assert parse(payload)["review_items"] == []


def test_rephrase_with_invented_original_is_dropped() -> None:
    payload = valid_payload(
        suggested_rephrases=[
            {"original": "We deployed the tool to three fabs.", "suggestion": "s", "reason": "r"}
        ]
    )

    assert parse(payload)["suggested_rephrases"] == []


def test_quote_with_punctuation_differences_still_matches() -> None:
    """Models tidy punctuation while quoting; that must not be mistaken for fabrication."""
    dimensions = valid_payload()["dimensions"]
    tidied = "I built a measurement pipeline for overlay metrology, and cut the cycle time by half"
    dimensions["fluency"] = {"rating": "strong", "evidence": [tidied], "feedback": "Good pace."}

    result = parse(valid_payload(dimensions=dimensions))

    assert result["dimensions"]["fluency"]["evidence"] == [tidied]


def test_capitalisation_differences_still_match() -> None:
    dimensions = valid_payload()["dimensions"]
    recased = "i built a measurement pipeline for overlay metrology and cut the cycle time by half."
    dimensions["clarity"] = {"rating": "strong", "evidence": [recased], "feedback": "Clear."}

    result = parse(valid_payload(dimensions=dimensions))

    assert result["dimensions"]["clarity"]["evidence"] == [recased]


def test_short_invented_quote_is_not_rescued_by_fuzzy_matching() -> None:
    """Fuzzy matching only applies to long quotes, so a short fabrication cannot slip through."""
    invented = "We shipped the tool to three fabs."
    dimensions = {
        name: {"rating": "strong", "evidence": [invented], "feedback": "Clear."}
        for name in REQUIRED_DIMENSIONS
    }

    with pytest.raises(EvaluationOutputError, match="attributable"):
        parse(valid_payload(dimensions=dimensions))
