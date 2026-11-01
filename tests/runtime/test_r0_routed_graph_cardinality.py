"""R0: original Core route collector must never truncate actual verified receipts.

Synthetic application receipts test the runtime output boundary, NOT provider semantics.
"""

from __future__ import annotations

from odyssey_apps import Route
from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.observability import OperationalEvidence, OperationalOutcome, OperationalStage
from odyssey_runtime.routing import _routed_result


def test_n_independent_routes_preserve_every_actual_result_and_receipt():
    routes = tuple(Route("core", f"Afirmación {i}.") for i in range(10))
    result_rows = []
    for i, _route in enumerate(routes):
        writes = [
            {"status": "succeeded", "operation": "UPDATED", "target": f"note-{i}-{j}"}
            for j in range(12 if i == 0 else 1)
        ]
        result_rows.append(
            ApplicationResult(
                f"route-{i}",
                ApplicationStatus.COMPLETED,
                (),
                tuple(w["target"] for w in writes),
                operational=OperationalEvidence(
                    1.0, (OperationalStage("core.writer", OperationalOutcome.COMPLETED),)
                ),
                execution_flow={"writes": writes, "plan": [], "entities": [], "temporal": []},
            )
        )
    source = " ".join(route.source_text for route in routes)
    combined = _routed_result(
        "r0-ten-route-graph",
        source,
        routes,
        result_rows,
        False,
        OperationalStage("application.router", OperationalOutcome.COMPLETED),
    )
    assert combined.status is ApplicationStatus.COMPLETED
    assert len(combined.execution_flow["routes"]) == 10
    assert len(combined.execution_flow["routes"][0]["writes"]) == 12
    assert len(combined.affected_stable_note_ids) == 21
    assert combined.execution_flow["routes"][-1]["writes"][0]["target"] == "note-9-0"
    assert len(combined.operational.stages) == 11


def test_n_routed_graph_keeps_failed_receipt_status_without_inventing_write():
    route = Route("core", "He intentado guardarlo.")
    result = ApplicationResult(
        "negative",
        ApplicationStatus.FAILED,
        (),
        (),
        operational=OperationalEvidence(
            1, (OperationalStage("core.writer", OperationalOutcome.FAILED),)
        ),
        execution_flow={"writes": [], "plan": [], "entities": [], "temporal": []},
    )
    combined = _routed_result(
        "negative-r0",
        route.source_text,
        (route,),
        (result,),
        False,
        OperationalStage("application.router", OperationalOutcome.COMPLETED),
    )
    assert combined.status is ApplicationStatus.FAILED
    assert combined.execution_flow["routes"][0]["writes"] == []
    assert combined.affected_stable_note_ids == ()
