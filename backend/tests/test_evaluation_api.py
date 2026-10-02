"""Finish, read and retry the evaluation: the API contract (design §7.8, §7.9, §9.2, §14.2 #6)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from conftest import ApiHarness, send_learner_turn, start_practice
from sqlalchemy import func, select

from app.ai.evaluation import EvaluationOutputError, EvaluationRequest, FakeEvaluationProvider
from app.core.config import settings
from app.db.models import Evaluation, PracticeSession, Scenario, User


class FailOnceEvaluationProvider(FakeEvaluationProvider):
    """First attempt times out, second succeeds — the retry path in one object."""

    name = "fail-once"
    model = "fail-once-1"

    def __init__(self) -> None:
        self.calls = 0

    async def evaluate(self, request: EvaluationRequest) -> dict:
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError
        return await super().evaluate(request)


class InvalidOutputEvaluationProvider(FakeEvaluationProvider):
    name = "invalid-output"
    model = "invalid-output-1"

    async def evaluate(self, request: EvaluationRequest) -> dict:
        raise EvaluationOutputError("model answered with prose instead of a report")


async def _evaluation_rows(api: ApiHarness, session_id: str) -> list[Evaluation]:
    async with api.session_factory() as session:
        return list(
            await session.scalars(
                select(Evaluation).where(Evaluation.session_id == UUID(session_id))
            )
        )


async def test_finish_generates_the_report_and_completes_the_session(api: ApiHarness) -> None:
    session_id = await start_practice(api)
    await send_learner_turn(api, session_id)

    response = await api.client.post(f"/api/v1/practice/sessions/{session_id}/finish", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_status"] == "completed"
    assert payload["evaluation_status"] == "completed"
    assert payload["error_code"] is None
    assert payload["retryable"] is False
    assert payload["attempt_count"] == 1
    assert payload["completed_at"] is not None

    report = payload["evaluation"]
    assert report["rubric_version"] == "english-communication-v1"
    assert set(report["dimensions"]) == {
        "clarity",
        "fluency",
        "naturalness",
        "professional_tone",
        "response_relevance",
    }
    assert report["dimensions"]["clarity"]["evidence"], "evidence must survive validation"

    rows = await _evaluation_rows(api, session_id)
    assert len(rows) == 1
    assert rows[0].provider == "fake"
    assert rows[0].prompt_version == "evaluation-english-v1"
    assert rows[0].result == report


async def test_finish_is_idempotent_and_reuses_the_single_row(api: ApiHarness) -> None:
    session_id = await start_practice(api)
    await send_learner_turn(api, session_id)

    first = await api.client.post(f"/api/v1/practice/sessions/{session_id}/finish", json={})
    replay = await api.client.post(f"/api/v1/practice/sessions/{session_id}/finish", json={})

    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert replay.json()["attempt_count"] == 1, "a replay must not re-run the model"

    rows = await _evaluation_rows(api, session_id)
    assert len(rows) == 1


async def test_finish_without_learner_turns_is_rejected(api: ApiHarness) -> None:
    session_id = await start_practice(api)

    response = await api.client.post(f"/api/v1/practice/sessions/{session_id}/finish", json={})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "session_has_no_user_turns"


async def test_failed_evaluation_is_reported_in_the_body_not_as_a_transport_error(
    build_api,
) -> None:
    async with build_api(evaluation_provider=FailOnceEvaluationProvider()) as api:
        session_id = await start_practice(api)
        await send_learner_turn(api, session_id)

        response = await api.client.post(f"/api/v1/practice/sessions/{session_id}/finish", json={})

        assert response.status_code == 200
        payload = response.json()
        assert payload["session_status"] == "completed", "the session really is finished"
        assert payload["evaluation_status"] == "failed"
        assert payload["error_code"] == "ai_provider_timeout"
        assert payload["retryable"] is True
        assert payload["evaluation"] is None

        rows = await _evaluation_rows(api, session_id)
        assert len(rows) == 1
        assert rows[0].status == "failed"
        assert rows[0].result is None


async def test_retry_recovers_a_failed_evaluation_on_the_same_row(build_api) -> None:
    async with build_api(evaluation_provider=FailOnceEvaluationProvider()) as api:
        session_id = await start_practice(api)
        await send_learner_turn(api, session_id)
        await api.client.post(f"/api/v1/practice/sessions/{session_id}/finish", json={})

        response = await api.client.post(
            f"/api/v1/practice/sessions/{session_id}/evaluation/retry", json={}
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["evaluation_status"] == "completed"
        assert payload["error_code"] is None
        assert payload["retryable"] is False
        assert payload["attempt_count"] == 2

        rows = await _evaluation_rows(api, session_id)
        assert len(rows) == 1, "retry must update the existing row, never insert a second one"
        assert rows[0].status == "completed"
        assert rows[0].attempt_count == 2


async def test_invalid_model_output_is_recorded_as_its_own_error_code(build_api) -> None:
    async with build_api(evaluation_provider=InvalidOutputEvaluationProvider()) as api:
        session_id = await start_practice(api)
        await send_learner_turn(api, session_id)

        response = await api.client.post(f"/api/v1/practice/sessions/{session_id}/finish", json={})

        assert response.status_code == 200
        assert response.json()["error_code"] == "invalid_ai_output"


async def test_retry_on_a_running_evaluation_is_rejected(api: ApiHarness) -> None:
    session_id = await start_practice(api)
    await send_learner_turn(api, session_id)
    async with api.session_factory() as session:
        practice_session = await session.get(PracticeSession, UUID(session_id))
        practice_session.status = "completed"
        practice_session.completed_at = datetime.now(timezone.utc)
        session.add(
            Evaluation(
                id=uuid4(),
                session_id=UUID(session_id),
                status="processing",
                rubric_version="english-communication-v1",
                provider="manual",
                model="manual",
                prompt_version="evaluation-english-v1",
                attempt_count=1,
            )
        )
        await session.commit()

    response = await api.client.post(
        f"/api/v1/practice/sessions/{session_id}/evaluation/retry", json={}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "evaluation_in_progress"


async def test_read_evaluation_before_finish_is_404(api: ApiHarness) -> None:
    session_id = await start_practice(api)
    await send_learner_turn(api, session_id)

    response = await api.client.get(f"/api/v1/practice/sessions/{session_id}/evaluation")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "evaluation_not_found"


async def test_read_evaluation_returns_202_while_processing(api: ApiHarness) -> None:
    session_id = await start_practice(api)
    async with api.session_factory() as session:
        session.add(
            Evaluation(
                id=uuid4(),
                session_id=UUID(session_id),
                status="processing",
                rubric_version="english-communication-v1",
                provider="manual",
                model="manual",
                prompt_version="evaluation-english-v1",
                attempt_count=1,
            )
        )
        await session.commit()

    response = await api.client.get(f"/api/v1/practice/sessions/{session_id}/evaluation")

    assert response.status_code == 202
    assert response.json()["evaluation_status"] == "processing"


async def test_read_evaluation_after_finish_returns_the_report(api: ApiHarness) -> None:
    session_id = await start_practice(api)
    await send_learner_turn(api, session_id)
    await api.client.post(f"/api/v1/practice/sessions/{session_id}/finish", json={})

    response = await api.client.get(f"/api/v1/practice/sessions/{session_id}/evaluation")

    assert response.status_code == 200
    assert response.json()["evaluation"]["summary"]


async def test_finish_on_a_missing_session_is_404(api: ApiHarness) -> None:
    response = await api.client.post(f"/api/v1/practice/sessions/{uuid4()}/finish", json={})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource_not_found"


async def test_abandoned_session_cannot_be_finished(api: ApiHarness) -> None:
    session_id = await start_practice(api)
    await send_learner_turn(api, session_id)
    async with api.session_factory() as session:
        practice_session = await session.get(PracticeSession, UUID(session_id))
        practice_session.status = "abandoned"
        await session.commit()

    response = await api.client.post(f"/api/v1/practice/sessions/{session_id}/finish", json={})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "session_not_active"


async def test_evaluation_belongs_to_the_local_user_only(api: ApiHarness) -> None:
    """A session owned by somebody else must be invisible, not merely forbidden."""
    other_user = User(id=uuid4(), status="active")
    async with api.session_factory() as session:
        session.add(other_user)
        await session.flush()
        scenario_id = await session.scalar(select(Scenario.id).limit(1))
        foreign = PracticeSession(
            id=uuid4(),
            user_id=other_user.id,
            scenario_id=scenario_id,
            scenario_version=1,
            scenario_snapshot={"id": str(scenario_id), "title": "Foreign"},
            status="active",
            input_mode="text",
            turn_count=0,
        )
        session.add(foreign)
        await session.commit()
        foreign_id = foreign.id

    finish = await api.client.post(f"/api/v1/practice/sessions/{foreign_id}/finish", json={})
    read = await api.client.get(f"/api/v1/practice/sessions/{foreign_id}/evaluation")

    assert finish.status_code == 404
    assert read.status_code == 404


async def test_a_session_never_gets_two_evaluation_rows(api: ApiHarness) -> None:
    session_id = await start_practice(api)
    await send_learner_turn(api, session_id)
    await api.client.post(f"/api/v1/practice/sessions/{session_id}/finish", json={})
    await api.client.post(f"/api/v1/practice/sessions/{session_id}/finish", json={})
    await api.client.post(f"/api/v1/practice/sessions/{session_id}/evaluation/retry", json={})

    async with api.session_factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(Evaluation)
            .where(Evaluation.session_id == UUID(session_id))
        )
    assert count == 1


@pytest.mark.parametrize("reason", ["user_finished", "user_abandoned"])
async def test_reason_field_is_accepted(api: ApiHarness, reason: str) -> None:
    session_id = await start_practice(api)
    await send_learner_turn(api, session_id)

    response = await api.client.post(
        f"/api/v1/practice/sessions/{session_id}/finish", json={"reason": reason}
    )

    assert response.status_code == 200


async def test_settings_do_not_leak_through_the_report(api: ApiHarness) -> None:
    session_id = await start_practice(api)
    await send_learner_turn(api, session_id)

    response = await api.client.post(f"/api/v1/practice/sessions/{session_id}/finish", json={})

    assert "ai_api_key" not in response.text
    assert "roleplay_instructions" not in response.text
    assert str(settings.local_user_id) not in response.text
