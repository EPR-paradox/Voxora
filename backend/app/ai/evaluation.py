"""Evaluation provider contract, a deterministic fake, and output validation.

The model is asked for a structured English-communication review (see design §8.3). Model output is
untrusted: ``parse_evaluation_result`` re-derives every field it keeps, drops anything the learner
never
said, and refuses the whole result when nothing is attributable. Evidence that cannot be traced back
to a
learner turn would turn a language report into a plausible-looking fiction, which is worse than a
failure.

Error mapping matches the roleplay provider: ``TimeoutError`` -> 504, ``EvaluationOutputError`` and
other
failures -> mapped by the service layer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from app.ai.prompts import EVALUATION_PROMPT_VERSION

RUBRIC_VERSION = "english-communication-v1"
PROMPT_VERSION = EVALUATION_PROMPT_VERSION

REQUIRED_DIMENSIONS = (
    "clarity",
    "fluency",
    "naturalness",
    "professional_tone",
    "response_relevance",
)
RATINGS = ("strong", "developing", "needs_work")
REVIEW_ITEM_TYPES = ("expression", "grammar", "clarity", "communication")

MAX_EVIDENCE_PER_DIMENSION = 3
MAX_STRENGTHS = 4
MAX_IMPROVEMENTS = 3
MAX_SUGGESTED_REPHRASES = 5
MAX_REVIEW_ITEMS = 5
MAX_FIELD_CHARS = 1200

_PUNCTUATION = re.compile(r"[^\w\s']", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")

# A model may tidy punctuation or drop a filler while quoting; an exact substring match is the
# primary
# test, and this looser one only applies to long quotes so it cannot rescue an invented sentence.
_FUZZY_MIN_TOKENS = 6
_FUZZY_MIN_OVERLAP = 0.85


@dataclass(frozen=True)
class EvaluationRequest:
    """Everything the evaluation prompt is allowed to see (design §7.8: no keys, no unrelated user
    data)."""

    scenario: dict[str, Any]
    transcript: list[dict[str, str]]
    user_objective: str


class EvaluationOutputError(RuntimeError):
    """The model returned something that cannot be accepted as a language evaluation."""


class EvaluationProvider(Protocol):
    """Contract for producing one validated evaluation.

    ``name``/``model``/``prompt_version``/``rubric_version`` describe how the report was produced
    and are
    recorded on the evaluation row even when the attempt fails, so they belong to the provider
    rather than
    to the parsed payload.
    """

    name: str
    model: str
    prompt_version: str
    rubric_version: str

    async def evaluate(self, request: EvaluationRequest) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...


def learner_turns(transcript: list[dict[str, str]]) -> list[str]:
    return [
        item["content"].strip()
        for item in transcript
        if item.get("role") == "user" and item.get("content", "").strip()
    ]


class FakeEvaluationProvider:
    """Deterministic provider for tests and offline development.

    It quotes the learner's own first turn as evidence, so it satisfies the same validation the real
    provider's output has to pass — a fake that could not pass validation would test nothing.
    """

    name = "fake"
    model = "fake-evaluation-1"
    prompt_version = PROMPT_VERSION
    rubric_version = RUBRIC_VERSION

    async def evaluate(self, request: EvaluationRequest) -> dict[str, Any]:
        turns = learner_turns(request.transcript)
        quote = turns[0] if turns else ""
        evidence = [quote] if quote else []
        dimensions = {
            name: {
                "rating": "developing",
                "evidence": list(evidence),
                "feedback": f"{name}: keep going.",
            }
            for name in REQUIRED_DIMENSIONS
        }
        result: dict[str, Any] = {
            "rubric_version": RUBRIC_VERSION,
            "summary": "The answer stayed on topic; specifics and numbers would make it stronger.",
            "dimensions": dimensions,
            "strengths": ["Answered the question that was asked."],
            "improvements": ["Add the measurable outcome of the work."],
            "suggested_rephrases": [],
            "review_items": [],
        }
        if quote:
            result["suggested_rephrases"] = [
                {
                    "original": quote,
                    "suggestion": "We cut the measurement cycle time by about half.",
                    "reason": "A concrete result reads as evidence.",
                }
            ]
            result["review_items"] = [
                {
                    "item_type": "expression",
                    "original_text": quote,
                    "target_text": "We cut the measurement cycle time by about half.",
                    "explanation": "Lead with the result, then the method.",
                }
            ]
        return result

    async def aclose(self) -> None:
        return None


def parse_evaluation_result(raw: str, *, learner_turns: list[str]) -> dict[str, Any]:
    """Validate and normalize a model's evaluation JSON.

    Raises ``EvaluationOutputError`` when the payload is malformed, misses a required field, uses an
    out-of-range rating, or contains no evidence traceable to the learner.
    """
    payload = _load_json_object(raw)
    normalized_turns = [_normalize(turn) for turn in learner_turns]

    dimensions: dict[str, dict[str, Any]] = {}
    accepted_evidence = 0
    raw_dimensions = payload.get("dimensions")
    if not isinstance(raw_dimensions, dict):
        raise EvaluationOutputError("Evaluation output has no 'dimensions' object.")

    for name in REQUIRED_DIMENSIONS:
        raw_dimension = raw_dimensions.get(name)
        if not isinstance(raw_dimension, dict):
            raise EvaluationOutputError(f"Evaluation output is missing dimension {name!r}.")
        rating = raw_dimension.get("rating")
        if rating not in RATINGS:
            raise EvaluationOutputError(
                f"Dimension {name!r} has rating {rating!r}, expected one of {RATINGS}."
            )
        feedback = _clean_text(raw_dimension.get("feedback"))
        if not feedback:
            raise EvaluationOutputError(f"Dimension {name!r} has no feedback.")

        raw_evidence = raw_dimension.get("evidence", [])
        if not isinstance(raw_evidence, list):
            raise EvaluationOutputError(f"Dimension {name!r} has a non-list 'evidence'.")
        evidence = [
            quote
            for item in raw_evidence
            if isinstance(item, str)
            and _is_learner_quote(item, normalized_turns)
            and (quote := _clean_text(item))
        ]
        accepted_evidence += len(evidence)
        dimensions[name] = {
            "rating": rating,
            "evidence": evidence[:MAX_EVIDENCE_PER_DIMENSION],
            "feedback": feedback,
        }

    if accepted_evidence == 0:
        raise EvaluationOutputError(
            "Evaluation cites no text attributable to the learner, so it cannot be trusted."
        )

    summary = _clean_text(payload.get("summary"))
    if not summary:
        raise EvaluationOutputError("Evaluation output has no 'summary'.")

    return {
        "rubric_version": RUBRIC_VERSION,
        "summary": summary,
        "dimensions": dimensions,
        "strengths": _clean_string_list(payload.get("strengths"), MAX_STRENGTHS),
        "improvements": _clean_string_list(payload.get("improvements"), MAX_IMPROVEMENTS),
        "suggested_rephrases": _clean_rephrases(
            payload.get("suggested_rephrases"), normalized_turns
        ),
        "review_items": _clean_review_items(payload.get("review_items"), normalized_turns),
    }


def _load_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        payload = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise EvaluationOutputError("Evaluation output is not JSON.") from None
        try:
            payload = json.loads(text[start : end + 1])
        except ValueError as exc:
            raise EvaluationOutputError("Evaluation output is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise EvaluationOutputError("Evaluation output is not a JSON object.")
    return payload


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return _WHITESPACE.sub(" ", value).strip()[:MAX_FIELD_CHARS]


def _clean_string_list(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned = [_clean_text(item) for item in value if isinstance(item, str)]
    return [item for item in cleaned if item][:limit]


def _clean_rephrases(value: Any, normalized_turns: list[str]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    kept: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        original = _clean_text(item.get("original"))
        suggestion = _clean_text(item.get("suggestion"))
        if not original or not suggestion:
            continue
        if not _is_learner_quote(original, normalized_turns):
            continue
        kept.append(
            {
                "original": original,
                "suggestion": suggestion,
                "reason": _clean_text(item.get("reason")),
            }
        )
    return kept[:MAX_SUGGESTED_REPHRASES]


def _clean_review_items(value: Any, normalized_turns: list[str]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    kept: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        item_type = item.get("item_type")
        if item_type not in REVIEW_ITEM_TYPES:
            continue
        target_text = _clean_text(item.get("target_text"))
        if not target_text:
            continue
        original_text = _clean_text(item.get("original_text"))
        if original_text and not _is_learner_quote(original_text, normalized_turns):
            continue
        kept.append(
            {
                "item_type": item_type,
                "original_text": original_text,
                "target_text": target_text,
                "explanation": _clean_text(item.get("explanation")),
            }
        )
    return kept[:MAX_REVIEW_ITEMS]


def _normalize(text: str) -> str:
    lowered = text.lower().replace("\u2019", "'")
    return _WHITESPACE.sub(" ", _PUNCTUATION.sub(" ", lowered)).strip()


def _is_learner_quote(quote: str, normalized_turns: list[str]) -> bool:
    needle = _normalize(quote)
    if not needle:
        return False
    if any(needle in turn for turn in normalized_turns):
        return True
    tokens = needle.split()
    if len(tokens) < _FUZZY_MIN_TOKENS:
        return False
    for turn in normalized_turns:
        haystack = set(turn.split())
        overlap = sum(1 for token in tokens if token in haystack) / len(tokens)
        if overlap >= _FUZZY_MIN_OVERLAP:
            return True
    return False
