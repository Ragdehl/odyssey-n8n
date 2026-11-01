"""R0: audited Markdown write receipts must survive N-route request-detail storage.

This is a synthetic durable-conversation test, not a live browser/model test.
Large user requests should not lose *all* graph provenance solely due to a
fixed count of scopes, verified writes, or stage indices.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from odyssey_core.conversations import ConversationError, ConversationRepository


def _detail(route_count: int = 10, write_count: int = 12) -> dict:
    stages = [{"name": "application.router", "outcome": "completed"}]
    routes = []
    for index in range(route_count):
        stages.append({"name": "core.writer", "outcome": "completed", "route_index": index})
        routes.append(
            {
                "capability": "core",
                "text": f"Hecho {index}.",
                "status": "completed",
                "stage_count": 1,
                "temporal": [],
                "steps": [{"name": "core.writer", "input": f"Hecho {index}.", "output": ""}],
                "writes": [
                    {"status": "succeeded", "operation": "UPDATED", "target": f"note-{index}-{i}"}
                    for i in range(write_count if index == 0 else 1)
                ],
            }
        )
    return {
        "request_id": "r0-many-routes",
        "operational": {"total_duration_ms": 123.0, "stages": stages},
        "flow": {
            "version": 1,
            "input": " ".join(route["text"] for route in routes),
            "parallel_preparation": False,
            "routes": routes,
        },
    }


def test_real_actor_scoped_conversation_preserves_all_routed_writes_and_replay(tmp_path):
    repository = ConversationRepository(tmp_path / "state")
    detail = _detail()
    repository.append_turn(
        "actor-one",
        "main",
        request_id=detail["request_id"],
        role="assistant",
        text="He guardado los hechos",
        status="completed",
        created_at="2026-11-01T15:10:00+01:00",
        request_detail=detail,
    )
    first = repository.load("actor-one", "main")["turns"][-1]["request_detail"]
    assert len(first["flow"]["routes"]) == 10
    assert len(first["flow"]["routes"][0]["writes"]) == 12
    assert first["operational"]["stages"][-1]["route_index"] == 9
    # Neither retry nor a different actor may alter/read the first actor's result.
    repository.append_turn(
        "actor-one",
        "main",
        request_id=detail["request_id"],
        role="assistant",
        text="He guardado los hechos",
        status="completed",
        created_at="2026-11-01T15:10:00+01:00",
        request_detail=detail,
    )
    assert len(repository.load("actor-one", "main")["turns"]) == 1
    assert (
        repository.load_or_create_main("actor-two", now="2026-11-01T15:10:00+01:00")["turns"] == []
    )


def test_durable_graph_refuses_forged_route_stage_and_oversize_without_mutation(tmp_path):
    repository = ConversationRepository(tmp_path / "state")
    base = _detail()
    for corrupted in (
        (lambda item: item["flow"]["routes"][-1]["steps"][0].update(name="fabricated")),
        (lambda item: item["flow"]["routes"][0]["writes"][0].update(status="invented")),
        (lambda item: item["flow"].update(input="X" * 65536)),
    ):
        invalid = deepcopy(base)
        corrupted(invalid)
        with pytest.raises(ConversationError):
            repository.append_turn(
                "actor-one",
                "main",
                request_id=base["request_id"],
                role="assistant",
                text="He guardado los hechos",
                status="completed",
                created_at="2026-11-01T15:10:00+01:00",
                request_detail=invalid,
            )
        assert repository.load("actor-one", "main")["turns"] == []


def test_core_result_projection_keeps_twelve_real_unit_receipts_without_fabricating_more(tmp_path):
    """Core-only projection of a source containing 12 actual materialized units."""
    from odyssey_core.application import (
        ActionResult,
        ActionStatus,
        UnitResult,
        UnitStatus,
        _project_execution_flow,
    )
    from odyssey_core.request_planning import (
        KnowledgeUnit,
        RequestPlan,
        SelectionCriteria,
        WriteAction,
    )
    from tests.runtime.test_whole_source_light_product_p4 import _fixture

    repo, _actor, service, _runtime = _fixture(tmp_path)
    actions = []
    results = []
    for number in range(12):
        unit = KnowledgeUnit(
            SelectionCriteria(f"Ítem {number}", f"Ítem {number}", "concept", (), None),
            "record",
            (),
            (),
            (f"Hecho {number}.",),
            (),
        )
        actions.append(WriteAction((unit,)))
        results.append(
            ActionResult(
                number,
                "write",
                ActionStatus.COMPLETED,
                unit_results=(UnitResult(0, UnitStatus.SUCCEEDED, "UPDATED", f"id-{number}"),),
            )
        )
    projected = _project_execution_flow(
        RequestPlan(tuple(actions), ()), results, repo, service.schema
    )
    assert len(projected["plan"]) == 12
    assert len(projected["writes"]) == 12
    assert projected["writes"][-1]["target"] == "Ítem 11"
    assert len(projected["entities"]) == 12
    # No result for the extra plan: Core must not invent a write it did not execute.
    one_less = _project_execution_flow(
        RequestPlan(tuple(actions), ()), results[:-1], repo, service.schema
    )
    assert len(one_less["writes"]) == 11


def test_actor_conversation_rejects_chunk_path_substitution(tmp_path):
    repository = ConversationRepository(tmp_path / "state")
    detail = _detail()
    repository.append_turn(
        "actor-one",
        "main",
        request_id=detail["request_id"],
        role="assistant",
        text="He guardado los hechos",
        status="completed",
        created_at="2026-11-01T15:10:00+01:00",
        request_detail=detail,
    )
    manifest = repository._main_directory("actor-one") / "manifest.json"
    import json

    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["chunks"][0]["name"] = "../outside.json"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ConversationError, match="manifest"):
        repository.load("actor-one", "main")
