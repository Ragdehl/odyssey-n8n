"""E6: trusted direct Task/Event receipts preserve real stages for the UI flow."""

from __future__ import annotations

import pytest

from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.observability import OperationalEvidence, OperationalOutcome, OperationalStage
from odyssey_runtime.serialization import application_result_to_response
from tests.runtime.test_whole_source_light_product_p4 import RecordedClient, _fixture


def _app_result(capability, request, status=ApplicationStatus.COMPLETED):
    if capability == "events":
        stages = ("events.interpretation", "temporal.interpretation")
    else:
        stages = ("tasks.interpretation", "temporal.interpretation", "planner")
    return ApplicationResult(
        request,
        status,
        (),
        (),
        operational=OperationalEvidence(
            100.0,
            tuple(OperationalStage(name, OperationalOutcome.COMPLETED, 5.0) for name in stages),
        ),
        execution_flow={"task": {"operation": "create"}} if capability == "tasks" else None,
    )


def _assert_complete_flow(result, capability, source, expected_reviews):
    raw = application_result_to_response(result)
    flow = raw["execution_flow"]
    assert flow["version"] == 1
    assert flow["input"] == source
    assert flow["parallel_preparation"] is False
    assert len(flow["routes"]) == 1
    route = flow["routes"][0]
    assert route["capability"] == capability
    assert route["status"] == result.status.value
    assert route["temporal"] == []
    assert route["text"] == source
    all_stages = raw["operational"]["stages"]
    assert all_stages[0]["name"] == "application.router"
    assert len(all_stages) == route["stage_count"] + 1
    # Router child spans must not swallow later source-scope calls.
    assert len(all_stages[0].get("substeps", [])) == 1
    assert len(route["steps"]) == route["stage_count"]
    assert [step["name"] for step in route["steps"]] == [stage["name"] for stage in all_stages[1:]]
    assert all(
        stage["name"] == "candidate.scope_prewrite"
        for stage in all_stages[1 : expected_reviews + 1]
    )
    assert all(stage.get("duration_ms") is not None for stage in all_stages[: expected_reviews + 1])
    assert raw["operational"]["total_duration_ms"] >= 0


def test_direct_event_produces_contract_complete_measured_router_flow(tmp_path):
    source = "Concierto ficticio el 29 de octubre de 2026."
    repository, actor, executor, _ = _fixture(tmp_path)
    seen = []
    executor.event_delegate = lambda s, req, act: (
        seen.append((s, req, act.stable_user_id)) or _app_result("events", req)
    )
    executor.client = RecordedClient(
        [
            {
                "capabilities": ["events"],
                "interpretation": "joint",
                "reason": "single",
                "app_scopes": [],
            }
        ]
    )
    result = executor(source, "e6-direct-event-flow", actor, "main")
    _assert_complete_flow(result, "events", source, 0)
    assert seen == [(source, "e6-direct-event-flow", actor.stable_user_id)]
    assert [
        stage["name"] for stage in application_result_to_response(result)["operational"]["stages"]
    ] == ["application.router", "events.interpretation", "temporal.interpretation"]
    assert len(repository.list_markdown_paths()) == 1


def test_direct_task_preserves_independent_source_scope_reviews_as_timed_stages(tmp_path):
    source = "Mañana debo preparar un informe ficticio."
    calls = []

    def delegate(s, req, actor):
        calls.append((s, req, actor.stable_user_id))
        return _app_result("tasks", req)

    repository, actor, executor, _ = _fixture(tmp_path, task_delegate=delegate)
    executor.client = RecordedClient(
        [
            {
                "capabilities": ["tasks"],
                "interpretation": "joint",
                "reason": "single",
                "app_scopes": [],
            },
            {"only_task_semantics": True, "exactly_one_operation": True, "source_quote": source},
        ]
    )
    result = executor(source, "e6-direct-task-flow", actor, "main")
    _assert_complete_flow(result, "tasks", source, 1)
    assert calls == [(source, "e6-direct-task-flow", actor.stable_user_id)]
    assert len(repository.list_markdown_paths()) == 1


@pytest.mark.parametrize(
    "outcome",
    (ApplicationStatus.FAILED, ApplicationStatus.NEEDS_ATTENTION, ApplicationStatus.PARTIAL),
)
@pytest.mark.parametrize("capability", ("events", "tasks"))
def test_direct_app_incomplete_outcome_preserves_observed_flow(tmp_path, capability, outcome):
    """A failed or deferred app is the case where route diagnostics matter most."""
    source = "Mañana debo revisar mi tarea ficticia."
    repository, actor, executor, _ = _fixture(tmp_path)
    executor.client = RecordedClient(
        [
            {
                "capabilities": [capability],
                "interpretation": "joint",
                "reason": "single",
                "app_scopes": [],
            },
            *(
                [
                    {
                        "only_task_semantics": True,
                        "exactly_one_operation": True,
                        "source_quote": source,
                    }
                ]
                if capability == "tasks"
                else []
            ),
        ]
    )

    def fake_delegate(text, request, authenticated):
        assert text == source
        assert authenticated.stable_user_id == actor.stable_user_id
        return _app_result(capability, request, outcome)

    if capability == "tasks":
        executor.task_delegate = fake_delegate
    else:
        executor.event_delegate = fake_delegate
    result = executor(source, f"e6-{capability}-{outcome.value}", actor, "main")
    assert result.status == outcome
    _assert_complete_flow(result, capability, source, int(capability == "tasks"))
    assert len(repository.list_markdown_paths()) == 1
    assert not application_result_to_response(result)["affected_stable_note_ids"]
