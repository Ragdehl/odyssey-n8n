"""Real Core/E3 receipts must never disappear when one source touches N notes.

The GUI renders all materialized route.writes; the presentation projection may
not collapse a complete write into an empty result merely due to cardinality.
"""

from __future__ import annotations

from types import SimpleNamespace

from odyssey_core.application import (
    ActionResult,
    ActionStatus,
    ApplicationResult,
    ApplicationStatus,
    UnitResult,
    UnitStatus,
    execute_request,
)
from odyssey_core.notes import parse_note
from odyssey_core.request_planning import RequestPlan
from odyssey_core.whole_source_compiler import compile_reviewed_operations
from odyssey_runtime.whole_source_light import _verified_route_writes
from tests.runtime.test_whole_source_light_product_p4 import _fixture


def test_route_projection_preserves_all_checked_receipts_not_just_first_eight():
    ids = tuple(f"note-{index:02d}" for index in range(12))
    result = ApplicationResult(
        "twelve-independent-writes",
        ApplicationStatus.COMPLETED,
        (
            ActionResult(
                0,
                "write",
                ActionStatus.COMPLETED,
                unit_results=tuple(
                    UnitResult(index, UnitStatus.SUCCEEDED, "UPDATED", note_id)
                    for index, note_id in enumerate(ids)
                ),
            ),
        ),
        ids,
    )
    assert [w["target"] for w in _verified_route_writes(result)] == list(ids)
    assert all(w["status"] == "succeeded" for w in _verified_route_writes(result))


def test_projection_excludes_unaffected_failed_and_unverified_identity_units():
    result = ApplicationResult(
        "negative",
        ApplicationStatus.PARTIAL,
        (
            ActionResult(
                0,
                "write",
                ActionStatus.COMPLETED,
                unit_results=(
                    UnitResult(0, UnitStatus.SUCCEEDED, "UPDATED", "valid-a"),
                    UnitResult(
                        1,
                        UnitStatus.SUCCEEDED,
                        "UPDATED",
                        "no-material-change",
                        materially_affected=False,
                    ),
                    UnitResult(2, UnitStatus.FAILED, "UPDATED", "failed-b"),
                    UnitResult(3, UnitStatus.SUCCEEDED, "UPDATED", "outside-affected-set"),
                    UnitResult(4, UnitStatus.SUCCEEDED, "", "empty-operation"),
                    UnitResult(5, UnitStatus.SUCCEEDED, "UPDATED", None),
                ),
            ),
        ),
        ("valid-a", "no-material-change", "failed-b", "empty-operation"),
    )
    assert _verified_route_writes(result) == [
        {"status": "succeeded", "operation": "UPDATED", "target": "valid-a"}
    ]
    assert (
        _verified_route_writes(
            ApplicationResult("empty", ApplicationStatus.NEEDS_ATTENTION, (), ())
        )
        == []
    )


def test_ten_physical_core_day_writes_remain_ten_projected_results(tmp_path):
    repo, actor, service, _runtime = _fixture(tmp_path)
    facts = [
        {
            "kind": "record",
            "date": f"2026-10-{i + 11:02d}",
            "reviewed_text": f"Recordé algo el día {i + 1}.",
            "reference_names": [],
        }
        for i in range(10)
    ]
    operations = compile_reviewed_operations({"facts": facts}, (True,) * len(facts))
    plan = RequestPlan(tuple(action for op in operations for action in op.plan.actions), ())
    assert len(plan.actions) == 10
    result = execute_request(
        "Una decena de recuerdos en fechas diferentes.",
        planner=SimpleNamespace(plan=lambda *_args: plan),
        repository=repo,
        schema=service.schema,
        context_index=service.context_index,
        semantic_index=service.semantic_index,
        embedder=service.embedder,
        contextual_reasoner=service.reasoner,
        authenticated_actor=actor,
        self_binding_repository=service.bindings,
        actor=actor.stable_user_id,
        now="2026-10-16T15:30:00+02:00",
        context_limit=20,
        request_id_factory=lambda: "r0-ten-day-results",
    )
    assert result.status is ApplicationStatus.COMPLETED, result
    assert len(result.action_results) == 10
    for fact in facts:
        day = parse_note(repo.read_text(f"calendar/days/{fact['date']}.md"))
        assert fact["reviewed_text"].rstrip(".") in day.content
    assert len(_verified_route_writes(result)) == 10
    assert len(result.affected_stable_note_ids) == 10
    assert {w["target"] for w in _verified_route_writes(result)} == set(
        result.affected_stable_note_ids
    )


def test_p4_route_graph_contains_all_verified_ten_day_writes_and_replays(tmp_path):
    """Actual P4 -> Core/E3 physical flow, with recorded—not live—model output."""
    from tests.runtime.test_whole_source_light_product_p4 import RecordedClient, _speaker

    repo, actor, service, runtime = _fixture(tmp_path)
    clauses = [
        f"El {11 + i} de octubre de 2026 escribí mi recuerdo número {i + 1}." for i in range(10)
    ]
    source = " ".join(clauses)
    route = {
        "capabilities": ["core", "temporal"],
        "interpretation": "joint",
        "reason": "one_source",
        "self_relation_span": None,
        "app_scopes": [],
    }
    proposal = {
        "entities": [],
        "unresolved": [],
        "facts": [
            {
                "meaning": clause,
                "kind": "record",
                "subject": "yo",
                "date": f"2026-10-{11 + i:02d}",
                "daypart": None,
                "participants": [],
                "source_evidence": clause,
                "dependent_on_fact_index": None,
                "needs_clarification": False,
            }
            for i, clause in enumerate(clauses)
        ],
    }
    review = {
        "approved": True,
        "complete": True,
        "reason": None,
        "facts": [
            {
                "ordinal": i,
                "source_quote": clause,
                "kind": "record",
                "reviewed_text": f"Escribí mi recuerdo número {i + 1}.",
                "date": f"2026-10-{11 + i:02d}",
                "reference_names": [],
                "supported": True,
            }
            for i, clause in enumerate(clauses)
        ],
    }
    service.client = RecordedClient(
        [
            route,
            proposal,
            review,
            _speaker(source, proposal, base=1),
            _speaker(source, proposal),
        ]
    )
    result = runtime.execute_product(source, "ten-dated-p4", "main", actor)
    assert result["status"] == "completed", (result, service.client.calls)
    routes = result["execution_flow"]["routes"]
    assert len(routes) == 1
    assert len(routes[0]["writes"]) == 10
    for i in range(10):
        path = f"calendar/days/2026-10-{11 + i:02d}.md"
        assert f"recuerdo número {i + 1}" in parse_note(repo.read_text(path)).content
    snapshot = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    again = runtime.execute_product(source, "ten-dated-p4", "main", actor)
    assert again["delivery_replayed"] is True
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == snapshot
