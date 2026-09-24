"""Offline freeze, structural oracle, and cost guard for the Slice 3 model gate."""

from __future__ import annotations

import io
import json
from decimal import Decimal
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
    PlannerClarification,
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


def relational_write() -> RequestPlan:
    """Represent the established singular W01 contract without a model call."""
    selection = SelectionCriteria(
        None,
        "mi hija",
        "person",
        (),
        None,
        relational_reference=RelationalReference("mi hija", "self", None, "one"),
    )
    return RequestPlan(
        (WriteAction((KnowledgeUnit(selection, "record", (), (), ("Vive en Lyon.",), ()),)),), ()
    )


def test_frozen_registry_and_oracle_align() -> None:
    """Load only the hashed ten-case registry before any provider construction."""
    registry, oracles = load_frozen_registry()
    assert len(registry["cases"]) == len(oracles) == 10
    assert [case["id"] for case in registry["cases"]] == list(oracles)
    assert evaluate_result(relational_read(), oracles["R01"]).classification == "PASS"
    assert evaluate_result(relational_write(), oracles["W01"]).classification == "PASS"


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


def test_cost_ceiling_blocks_provider_construction_above_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refuse before construction when the frozen maximum exceeds an authorization cap."""
    registry, _oracles = load_frozen_registry()
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    cost, luna_input, sol_input = conservative_cost_ceiling(
        registry["cases"], registry["fixed_context"], schema
    )
    assert cost <= MAX_COST_USD
    assert luna_input > 0 and sol_input > 0
    import benchmarks.reference_relationship_v1.run_live as runner

    monkeypatch.setattr(runner, "OUTPUT_PATH", tmp_path / "should-not-exist.jsonl")
    monkeypatch.setattr(runner, "MAX_COST_USD", Decimal("0.45"))
    monkeypatch.setattr(
        runner.LunaFirstRequestPlanner,
        "from_environment",
        lambda *_args, **_kwargs: pytest.fail("provider constructed despite cost gate"),
    )
    with pytest.raises(SystemExit, match="exceeds"):
        main(["--confirm-live-provider-calls"])
    assert not runner.OUTPUT_PATH.exists()


def test_missing_provider_environment_refuses_before_evidence_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Require a process-exported key before reserving evidence or constructing a provider."""
    import benchmarks.reference_relationship_v1.run_live as runner

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(runner, "OUTPUT_PATH", tmp_path / "should-not-exist.jsonl")
    monkeypatch.setattr(
        runner.LunaFirstRequestPlanner,
        "from_environment",
        lambda *_args, **_kwargs: pytest.fail("provider constructed without process environment"),
    )
    with pytest.raises(SystemExit, match="absent from process environment"):
        main(["--confirm-live-provider-calls"])
    assert not runner.OUTPUT_PATH.exists()


class RecordingEvidence(io.StringIO):
    """Count immediate evidence flushes without opening a live-result file."""

    def __init__(self) -> None:
        """Start with no emitted rows."""
        super().__init__()
        self.flush_count = 0

    def flush(self) -> None:
        """Record the runner's per-row durability boundary."""
        self.flush_count += 1
        super().flush()


class StubPlanner:
    """Provide prevalidated local planner outcomes without provider access or retries."""

    last_provider_calls: tuple[Any, ...] = ()

    def __init__(self, outcomes: list[tuple[int, RequestPlan | PlannerClarification]]) -> None:
        """Consume exactly one configured outcome for each logical case requested."""
        self.outcomes = iter(outcomes)
        self.last_attempt_count = 0
        self.requests: list[str] = []

    def plan(
        self, request: str, conversation: tuple[Any, ...]
    ) -> RequestPlan | PlannerClarification:
        """Return one configured outcome and expose whether the production fallback occurred."""
        assert not conversation
        self.requests.append(request)
        self.last_attempt_count, result = next(self.outcomes)
        return result


def _cases(*identifiers: str) -> list[dict[str, str]]:
    """Create tiny local frozen-shaped cases for runner control-flow tests."""
    return [
        {"id": identifier, "request": f"request-{index}"}
        for index, identifier in enumerate(identifiers)
    ]


def test_runner_continues_through_multiple_luna_only_passes() -> None:
    """Continue when validated Luna-only outcomes pass and never retry a logical case."""
    _registry, oracles = load_frozen_registry()
    planner = StubPlanner([(1, relational_read()), (1, relational_read()), (1, relational_read())])
    evidence = RecordingEvidence()
    rows = run_cases(
        planner,
        _cases("R01", "R01", "R01"),
        oracles,
        evidence,
    )
    assert [row["classification"] for row in rows] == ["PASS", "PASS", "PASS"]
    assert planner.requests == ["request-0", "request-1", "request-2"]
    assert evidence.flush_count == 3
    assert all("prompt" not in row and "reasoning" not in row for row in rows)


def test_runner_flushes_first_fallback_and_stops_before_later_cases() -> None:
    """Persist the first Sol fallback for review, then prevent further Sol exposure."""
    _registry, oracles = load_frozen_registry()
    planner = StubPlanner([(1, relational_read()), (2, relational_read()), (1, relational_read())])
    evidence = RecordingEvidence()
    rows = run_cases(planner, _cases("R01", "R01", "R01"), oracles, evidence)
    assert [row["fallback"] for row in rows] == [False, True]
    assert [row["classification"] for row in rows] == ["PASS", "PASS"]
    assert planner.requests == ["request-0", "request-1"]
    assert len(evidence.getvalue().splitlines()) == evidence.flush_count == 2


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (relational_read(), "FAIL"),
        (PlannerClarification("clarify"), "FAIL_CLOSED"),
    ],
)
def test_runner_stops_immediately_on_fail_or_fail_closed(
    outcome: RequestPlan | PlannerClarification, expected: str
) -> None:
    """Keep existing unsafe-result stops independent of fallback handling."""
    _registry, oracles = load_frozen_registry()
    planner = StubPlanner([(1, outcome), (1, relational_read())])
    evidence = RecordingEvidence()
    rows = run_cases(planner, _cases("S01", "R01"), oracles, evidence)
    assert [row["classification"] for row in rows] == [expected]
    assert planner.requests == ["request-0"]
    assert evidence.flush_count == 1
