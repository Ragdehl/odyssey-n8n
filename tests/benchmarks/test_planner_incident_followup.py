"""Provider-free checks for the closed planner incident diagnostic follow-up gate."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from benchmarks.planner_incident_hardening import run_followup_live
from benchmarks.planner_incident_hardening.run_live import OUTPUT as ORIGINAL_OUTPUT
from odyssey_core.request_planning import (
    PLANNER_AUTOMATIC_RETRIES,
    PLANNER_MAX_OUTPUT_TOKENS,
    KnowledgeUnit,
    PlannerClarification,
    RequestPlan,
    RequestPlanningError,
    RetrieveAction,
    SelectionCriteria,
    WriteAction,
)

ROOT = Path(__file__).resolve().parents[2]


class FakePlanner:
    """Return deterministic planner results without constructing a provider client."""

    last_response_id = "resp_test"
    last_provider_status = "completed"
    last_usage = {"input_tokens": 1, "output_tokens": 1}
    last_parse_status = "succeeded"
    last_validation_stage: str | None = None
    last_validation_code: str | None = None
    last_result_counts = {"actions": 1}
    last_error_category: str | None = None
    last_incomplete_reason: str | None = None
    last_output_text_chars = 100
    last_output_text_bytes = 100

    def __init__(self, fail_request: str | None = None) -> None:
        """Initialize a fake that can fail one case after simulated JSON parsing."""
        self.fail_request = fail_request
        self.calls: list[str] = []

    def plan(self, request: str) -> RequestPlan | PlannerClarification:
        """Record one logical call and return its matching frozen result."""
        self.calls.append(request)
        if request == self.fail_request:
            self.last_error_category = "LocalPlannerValidationError"
            self.last_validation_stage = "SELECTION"
            self.last_validation_code = "EMPTY_QUERY"
            raise RequestPlanningError("synthetic local validation failure")
        self.last_error_category = None
        self.last_validation_stage = None
        self.last_validation_code = None
        selection = SelectionCriteria(None, "safe", None, (), None)
        if request == "Where does Marta work?":
            return RequestPlan((RetrieveAction(selection),), ())
        if request == "Remember that Marta works at Thales.":
            return RequestPlan(
                (WriteAction((KnowledgeUnit(selection, "record", (), (), ("safe",), ()),)),), ()
            )
        if request == "Translate my note about Marta into French.":
            from odyssey_core.request_planning import DelegateAction

            return RequestPlan((DelegateAction("translate", selection),), ())
        if request == "Remember that Marta works at Thales and tell me where she lives.":
            return RequestPlan(
                (
                    RetrieveAction(selection),
                    WriteAction((KnowledgeUnit(selection, "record", (), (), ("safe",), ()),)),
                ),
                (),
            )
        raise AssertionError("unexpected frozen request")


def frozen_cases() -> list[dict[str, str]]:
    """Load a disposable copy of the canonical frozen registry for malformed-fixture tests."""
    return deepcopy(
        json.loads((ROOT / "benchmarks/planner_incident_hardening/cases.json").read_text())
    )


def write_cases(tmp_path: Path, cases: list[dict[str, str]]) -> Path:
    """Write one isolated frozen-registry fixture for deterministic loader tests."""
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases), encoding="utf-8")
    return path


def test_followup_loader_selects_only_the_four_unresolved_cases() -> None:
    """Keep passed historical cases structurally outside the future live gate."""
    cases = run_followup_live.load_followup_cases()

    assert [case["id"] for case in cases] == list(run_followup_live.FOLLOW_UP_IDS)
    assert len(cases) == 4
    assert {case["id"] for case in cases}.isdisjoint(
        {"incident_bdbd", "nonsense_letters", "nonsense_punctuation", "event_date_not_lifecycle"}
    )


def test_followup_loop_rejects_any_non_followup_case() -> None:
    """Prevent an internal caller from expanding the fixed four-case execution set."""
    with pytest.raises(ValueError):
        run_followup_live.run_followup_cases(
            FakePlanner(),
            [{"id": "incident_bdbd", "request": "Bdbd", "expect": "clarify"}],
        )


@pytest.mark.parametrize("mutation", ("missing", "duplicate", "unexpected"))
def test_followup_loader_fails_closed_for_invalid_frozen_registry(
    tmp_path: Path, mutation: str
) -> None:
    """Reject missing, duplicate, and remapped unresolved frozen cases before any planner exists."""
    cases = frozen_cases()
    if mutation == "missing":
        cases = [case for case in cases if case["id"] != "normal_write"]
    elif mutation == "duplicate":
        cases.append(next(case for case in cases if case["id"] == "normal_write"))
    else:
        next(case for case in cases if case["id"] == "normal_write")["expect"] = "retrieve"

    with pytest.raises(ValueError):
        run_followup_live.load_followup_cases(write_cases(tmp_path, cases))


def test_followup_output_is_separate_and_exclusive(tmp_path: Path) -> None:
    """Keep original evidence untouched and refuse a second follow-up evidence write."""
    historical = tmp_path / "planner-incident-hardening.jsonl"
    followup = tmp_path / "planner-incident-hardening-followup.jsonl"
    historical.write_text("historical\n", encoding="utf-8")

    assert run_followup_live.OUTPUT != ORIGINAL_OUTPUT
    run_followup_live.write_followup_rows([{"id": "normal_retrieval"}], followup)
    with pytest.raises(FileExistsError):
        run_followup_live.write_followup_rows([{"id": "normal_retrieval"}], followup)
    assert historical.read_text(encoding="utf-8") == "historical\n"


def test_missing_confirmation_never_constructs_a_planner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Require explicit live confirmation before a provider client could be constructed."""
    monkeypatch.setattr(
        run_followup_live.OpenAIRequestPlanner,
        "from_environment",
        lambda *args: (_ for _ in ()).throw(AssertionError("planner must not be constructed")),
    )

    with pytest.raises(SystemExit):
        run_followup_live.main([])


def test_followup_runs_each_closed_case_once_and_keeps_validation_diagnostics() -> None:
    """Continue through one local failure without retrying or expanding the frozen case set."""
    cases = run_followup_live.load_followup_cases()
    failed_request = next(case["request"] for case in cases if case["id"] == "normal_write")
    planner = FakePlanner(failed_request)

    rows = run_followup_live.run_followup_cases(planner, cases)

    assert planner.calls == [case["request"] for case in cases]
    assert len(planner.calls) == 4
    failed = next(row for row in rows if row["id"] == "normal_write")
    assert failed["passed"] is False
    assert failed["parse_status"] == "succeeded"
    assert failed["validation_stage"] == "SELECTION"
    assert failed["validation_code"] == "EMPTY_QUERY"
    assert sum(not row["passed"] for row in rows) == 1


def test_followup_configuration_preserves_reviewed_planner_limits() -> None:
    """Pin the follow-up runner to the reviewed cap and no-retry planner configuration."""
    run_followup_live.validate_followup_configuration()

    assert PLANNER_MAX_OUTPUT_TOKENS == 4096
    assert PLANNER_AUTOMATIC_RETRIES == 0
