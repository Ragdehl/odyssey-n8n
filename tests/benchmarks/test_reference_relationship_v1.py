"""Offline freeze, structural oracle, and cost guard for the Slice 3 model gate."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.reference_relationship_v1.evaluate import evaluate_result, load_frozen_registry
from benchmarks.reference_relationship_v1.run_live import (
    MAX_COST_USD,
    conservative_cost_ceiling,
    main,
    run_cases,
)
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    RelationalReference,
    RequestPlan,
    RetrieveAction,
    SelectionCriteria,
    WriteAction,
)

ROOT = Path(__file__).resolve().parents[2]


def relational_read() -> RequestPlan:
    """Represent a production-validated-shaped R01 result without a model call."""
    return RequestPlan(
        (
            RetrieveAction(
                SelectionCriteria(
                    None,
                    "¿Dónde vive mi hija?",
                    "person",
                    (),
                    None,
                    relational_reference=RelationalReference("mi hija", "self", None, "one"),
                )
            ),
        ),
        (),
    )


def test_frozen_registry_and_oracle_align() -> None:
    """Load only the hashed ten-case registry before any provider construction."""
    registry, oracles = load_frozen_registry()
    assert len(registry["cases"]) == len(oracles) == 10
    assert [case["id"] for case in registry["cases"]] == list(oracles)
    assert evaluate_result(relational_read(), oracles["R01"]).classification == "PASS"


def test_oracle_rejects_relational_identity_loss_and_extra_actions() -> None:
    """A normal entity assertion cannot masquerade as a relational plan."""
    _registry, oracles = load_frozen_registry()
    ordinary = RequestPlan(
        (RetrieveAction(SelectionCriteria("mi hija", "mi hija", "person", (), None)),), ()
    )
    assert "missing_relational_intent" in evaluate_result(ordinary, oracles["R01"]).findings
    extra = RequestPlan((*relational_read().actions, *ordinary.actions), ())
    assert evaluate_result(extra, oracles["R01"]).findings == ("action_shape",)


def test_complete_set_oracle_accepts_one_source_unit_without_fabricated_members() -> None:
    """The planner carries one fact; Core alone will expand current member bindings."""
    _registry, oracles = load_frozen_registry()
    unit = KnowledgeUnit(
        SelectionCriteria(
            None,
            "todos los que estaban ayer",
            None,
            (),
            None,
            relational_reference=RelationalReference(
                "todos los que estaban ayer", "existing", "the event yesterday", "complete_set"
            ),
        ),
        "record",
        (),
        (),
        ("Fuimos al colegio Laia.",),
        (),
    )
    result = RequestPlan((WriteAction((unit,)),), ())
    evaluation = evaluate_result(result, oracles["W02"])
    assert evaluation.classification == "PASS"
    assert evaluation.semantic_review == ("source_selector_review",)


def test_named_reference_oracle_accepts_either_unit_order() -> None:
    """Evaluate semantic binding without requiring one harmless unit order."""
    _registry, oracles = load_frozen_registry()
    airbus = KnowledgeUnit(
        SelectionCriteria("Airbus", "Airbus", "concept", (), None),
        "record",
        (),
        (),
        (),
        (),
    )
    marta = KnowledgeUnit(
        SelectionCriteria("Marta", "Marta", "person", (), None),
        "record",
        (),
        (),
        ("Trabaja en {{ref:0}}.",),
        (KnowledgeReference(0, "employer", "Airbus"),),
    )
    result = RequestPlan((WriteAction((airbus, marta)),), ())
    assert evaluate_result(result, oracles["S03"]).classification == "PASS"


def test_cost_ceiling_blocks_provider_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refuse the authorized run when every possible Sol fallback exceeds the cap."""
    registry, _oracles = load_frozen_registry()
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    cost, luna_input, sol_input = conservative_cost_ceiling(
        registry["cases"], registry["fixed_context"], schema
    )
    assert cost > MAX_COST_USD
    assert luna_input > 0 and sol_input > 0
    import benchmarks.reference_relationship_v1.run_live as runner

    monkeypatch.setattr(runner, "OUTPUT_PATH", tmp_path / "should-not-exist.jsonl")
    monkeypatch.setattr(
        runner.LunaFirstRequestPlanner,
        "from_environment",
        lambda *_args, **_kwargs: pytest.fail("provider constructed despite cost gate"),
    )
    with pytest.raises(SystemExit, match="exceeds"):
        main(["--confirm-live-provider-calls"])
    assert not runner.OUTPUT_PATH.exists()


def test_runner_flushes_bounded_rows_and_stops_on_failure() -> None:
    """Keep at most one production-composed logical attempt per selected case."""
    _registry, oracles = load_frozen_registry()

    class Planner:
        """Expose only validated result and bounded production attempt metadata."""

        last_attempt_count = 1
        last_provider_calls: tuple[Any, ...] = ()

        def plan(self, request: str, conversation: tuple[Any, ...]) -> RequestPlan:
            """Return one fixed relational plan for the two selected oracle shapes."""
            assert request and not conversation
            return relational_read()

    evidence = io.StringIO()
    rows = run_cases(
        Planner(),
        [
            {"id": "R01", "request": "read"},
            {"id": "S01", "request": "write"},
            {"id": "S02", "request": "unreached"},
        ],
        oracles,
        evidence,
    )
    assert [row["classification"] for row in rows] == ["PASS", "FAIL"]
    assert len(evidence.getvalue().splitlines()) == 2
    assert all("prompt" not in row and "reasoning" not in row for row in rows)
