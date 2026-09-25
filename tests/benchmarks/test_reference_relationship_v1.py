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
from benchmarks.reference_relationship_v1.run_live_continuation import (
    CONTINUATION_CASE_IDS,
    EXPECTED_FROZEN_CASE_IDS,
    load_continuation_cases,
)
from benchmarks.reference_relationship_v1.run_live_continuation import (
    MAX_COST_USD as CONTINUATION_MAX_COST_USD,
)
from benchmarks.reference_relationship_v1.run_live_continuation import (
    conservative_cost_ceiling as continuation_cost_ceiling,
)
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    PlannerClarification,
    RelationalReference,
    RequestPlan,
    RetrieveAction,
    SelectionCriteria,
    TagChange,
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


def all_matching_write() -> RequestPlan:
    """Represent the frozen S04 bulk-tag sentinel without a provider call."""
    unit = KnowledgeUnit(
        SelectionCriteria(None, "todas mis notas de tipo persona", "person", (), None),
        "record",
        (),
        (TagChange("add", "revisado"),),
        (),
        (),
        cardinality="all_matching",
    )
    return RequestPlan((WriteAction((unit,)),), ())


def atomic_write() -> RequestPlan:
    """Represent the frozen S05 one-target two-fact sentinel without a provider call."""
    unit = KnowledgeUnit(
        SelectionCriteria("Marta", "Marta", "person", (), None),
        "record",
        (),
        (),
        ("Vive en Lyon.", "Trabaja en Airbus."),
        (),
    )
    return RequestPlan((WriteAction((unit,)),), ())


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
    assert cost > MAX_COST_USD
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
    monkeypatch.setattr(runner, "MAX_COST_USD", Decimal("1"))
    monkeypatch.setattr(runner, "OUTPUT_PATH", tmp_path / "should-not-exist.jsonl")
    monkeypatch.setattr(
        runner.LunaFirstRequestPlanner,
        "from_environment",
        lambda *_args, **_kwargs: pytest.fail("provider constructed without process environment"),
    )
    with pytest.raises(SystemExit, match="absent from process environment"):
        main(["--confirm-live-provider-calls"])
    assert not runner.OUTPUT_PATH.exists()


def test_attempt_3_uses_a_distinct_exclusive_evidence_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Target a fresh attempt file and preserve any existing evidence at that path."""
    import benchmarks.reference_relationship_v1.run_live as runner

    assert runner.OUTPUT_PATH.name == "reference-relationship-v1-attempt-3.jsonl"
    evidence_path = tmp_path / runner.OUTPUT_PATH.name
    original = b"prior attempt evidence\n"
    evidence_path.write_bytes(original)
    monkeypatch.setattr(runner, "OUTPUT_PATH", evidence_path)
    monkeypatch.setattr(runner, "MAX_COST_USD", Decimal("1"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-presence-only")
    monkeypatch.setattr(
        runner.LunaFirstRequestPlanner,
        "from_environment",
        lambda *_args, **_kwargs: pytest.fail("provider constructed before exclusive open"),
    )

    with pytest.raises(SystemExit, match="Refusing to overwrite existing evidence"):
        main(["--confirm-live-provider-calls"])

    assert evidence_path.read_bytes() == original


def test_continuation_selects_only_the_fixed_unattempted_suffix() -> None:
    """Keep continuation evidence bound to S04 then S05 from the original registry."""
    registry, cases, oracles = load_continuation_cases()
    assert tuple(case["id"] for case in registry["cases"]) == EXPECTED_FROZEN_CASE_IDS
    assert tuple(case["id"] for case in cases) == CONTINUATION_CASE_IDS == ("S04", "S05")
    assert tuple(oracles) == EXPECTED_FROZEN_CASE_IDS
    assert len(cases) + 1 == 3


def test_continuation_cost_requires_a_fresh_authorization_after_schema_growth() -> None:
    """Keep the old continuation authorization from silently covering a new schema contract."""
    registry, cases, _oracles = load_continuation_cases()
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    cost, luna_input, sol_input = continuation_cost_ceiling(
        cases, registry["fixed_context"], schema
    )
    assert cost > CONTINUATION_MAX_COST_USD == Decimal("0.37")
    assert luna_input > 0 and sol_input > 0


def test_continuation_lower_guard_refuses_before_provider_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep the no-cache bound as an executable pre-provider authorization guard."""
    import benchmarks.reference_relationship_v1.run_live_continuation as continuation

    registry, cases, _oracles = load_continuation_cases()
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    cost, _luna_input, _sol_input = continuation_cost_ceiling(
        cases, registry["fixed_context"], schema
    )
    monkeypatch.setattr(continuation, "MAX_COST_USD", cost - Decimal("0.0000001"))
    monkeypatch.setattr(continuation, "OUTPUT_PATH", tmp_path / "continuation.jsonl")
    monkeypatch.setenv("OPENAI_API_KEY", "test-presence-only")
    monkeypatch.setattr(
        continuation.LunaFirstRequestPlanner,
        "from_environment",
        lambda *_args, **_kwargs: pytest.fail("provider constructed despite lower cost guard"),
    )
    with pytest.raises(SystemExit, match="requires a fresh explicit cost authorization"):
        continuation.main(["--confirm-live-provider-calls"])
    assert not continuation.OUTPUT_PATH.exists()


def test_continuation_requires_its_confirmation_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject an unconfirmed continuation before evidence reservation or provider construction."""
    import benchmarks.reference_relationship_v1.run_live_continuation as continuation

    monkeypatch.setattr(continuation, "MAX_COST_USD", Decimal("1"))
    monkeypatch.setattr(continuation, "OUTPUT_PATH", tmp_path / "continuation.jsonl")
    monkeypatch.setenv("OPENAI_API_KEY", "test-presence-only")
    monkeypatch.setattr(
        continuation.LunaFirstRequestPlanner,
        "from_environment",
        lambda *_args, **_kwargs: pytest.fail("provider constructed without confirmation"),
    )
    with pytest.raises(SystemExit, match="without --confirm-live-provider-calls"):
        continuation.main([])
    assert not continuation.OUTPUT_PATH.exists()


def test_continuation_refuses_user_selected_cases() -> None:
    """Expose no generic case or start-index input that could alter the fixed suffix."""
    import benchmarks.reference_relationship_v1.run_live_continuation as continuation

    with pytest.raises(SystemExit):
        continuation.main(["--case", "S03"])


def test_continuation_missing_key_refuses_before_evidence_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep process-key validation before continuation evidence or provider construction."""
    import benchmarks.reference_relationship_v1.run_live_continuation as continuation

    monkeypatch.setattr(continuation, "MAX_COST_USD", Decimal("1"))
    monkeypatch.setattr(continuation, "OUTPUT_PATH", tmp_path / "continuation.jsonl")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        continuation.LunaFirstRequestPlanner,
        "from_environment",
        lambda *_args, **_kwargs: pytest.fail("provider constructed without process environment"),
    )
    with pytest.raises(SystemExit, match="absent from process environment"):
        continuation.main(["--confirm-live-provider-calls"])
    assert not continuation.OUTPUT_PATH.exists()


def test_continuation_preserves_existing_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refuse a reused continuation path before constructing a provider."""
    import benchmarks.reference_relationship_v1.run_live_continuation as continuation

    evidence_path = tmp_path / "continuation.jsonl"
    original = b"retained continuation evidence\n"
    evidence_path.write_bytes(original)
    monkeypatch.setattr(continuation, "MAX_COST_USD", Decimal("1"))
    monkeypatch.setattr(continuation, "OUTPUT_PATH", evidence_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-presence-only")
    monkeypatch.setattr(
        continuation.LunaFirstRequestPlanner,
        "from_environment",
        lambda *_args, **_kwargs: pytest.fail("provider constructed before exclusive open"),
    )
    with pytest.raises(SystemExit, match="Refusing to overwrite existing evidence"):
        continuation.main(["--confirm-live-provider-calls"])
    assert evidence_path.read_bytes() == original


def test_continuation_rejects_registry_drift_before_provider_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Require the full original order before selecting the fixed suffix."""
    import benchmarks.reference_relationship_v1.run_live_continuation as continuation

    registry, oracles = load_frozen_registry()
    drifted = {**registry, "cases": registry["cases"][:-1]}
    monkeypatch.setattr(continuation, "MAX_COST_USD", Decimal("1"))
    monkeypatch.setattr(continuation, "OUTPUT_PATH", tmp_path / "continuation.jsonl")
    monkeypatch.setenv("OPENAI_API_KEY", "test-presence-only")
    monkeypatch.setattr(continuation, "load_frozen_registry", lambda: (drifted, oracles))
    monkeypatch.setattr(
        continuation.LunaFirstRequestPlanner,
        "from_environment",
        lambda *_args, **_kwargs: pytest.fail("provider constructed after registry drift"),
    )
    with pytest.raises(ValueError, match="original ordered ten-case registry"):
        continuation.main(["--confirm-live-provider-calls"])
    assert not continuation.OUTPUT_PATH.exists()


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


def test_continuation_stops_after_its_first_fallback() -> None:
    """Use the shared production stop rule without allowing S05 after an S04 fallback."""
    _registry, cases, oracles = load_continuation_cases()
    planner = StubPlanner([(2, all_matching_write()), (1, atomic_write())])
    evidence = RecordingEvidence()
    rows = run_cases(planner, cases, oracles, evidence)
    assert [row["case_id"] for row in rows] == ["S04"]
    assert rows[0]["classification"] == "PASS"
    assert rows[0]["fallback"] is True
    assert planner.requests == [cases[0]["request"]]
    assert evidence.flush_count == 1


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (relational_read(), "FAIL"),
        (PlannerClarification("clarify"), "FAIL_CLOSED"),
    ],
)
def test_continuation_stops_after_fail_or_fail_closed(
    outcome: RequestPlan | PlannerClarification, expected: str
) -> None:
    """Keep S05 unreachable after a failed S04 continuation result."""
    _registry, cases, oracles = load_continuation_cases()
    planner = StubPlanner([(1, outcome), (1, atomic_write())])
    evidence = RecordingEvidence()
    rows = run_cases(planner, cases, oracles, evidence)
    assert [row["case_id"] for row in rows] == ["S04"]
    assert [row["classification"] for row in rows] == [expected]
    assert planner.requests == [cases[0]["request"]]
    assert evidence.flush_count == 1


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
