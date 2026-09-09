"""Offline contract, evaluator, cost, and runner tests for Luna-first planning."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import odyssey_core.experimental_luna_planning as luna_module
from benchmarks.luna_first_planner.cost import (
    UsageTotals,
    compare_routing_costs,
    estimate_usage_cost,
    parse_usage,
)
from benchmarks.luna_first_planner.evaluate import (
    Classification,
    Evaluation,
    evaluate_payload,
    load_frozen_registry,
    summarize_evaluations,
)
from benchmarks.luna_first_planner.evaluate_v2 import (
    EVALUATOR_VERSION,
    evaluate_payload_v2,
    load_frozen_registry_v2,
)
from benchmarks.luna_first_planner.evaluate_v2 import (
    Classification as ClassificationV2,
)
from benchmarks.luna_first_planner.run_continuation import (
    CONTINUATION_CASE_IDS,
    reserve_evidence_path_at,
)
from benchmarks.luna_first_planner.run_live import (
    OUTPUT_PATH,
    run_cases,
    select_cases,
    write_rows,
)
from benchmarks.luna_first_planner.run_live import (
    main as run_live_main,
)
from benchmarks.luna_first_planner.run_live_v2 import (
    reserve_evidence_path,
    run_cases_v2,
)
from odyssey_core.experimental_luna_planning import (
    LUNA_EXPERIMENT_AUTOMATIC_RETRIES,
    LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
    LUNA_EXPERIMENT_MODEL,
    LUNA_EXPERIMENT_REASONING_EFFORT,
    OpenAILunaExperimentalPlanner,
    PlannerEscalation,
    embedded_request_plan_contract,
    load_teaching_examples,
    luna_experimental_result_json_schema,
    production_result_contract_unchanged,
    render_luna_experimental_prompt,
    validate_luna_experimental_result,
)
from odyssey_core.request_planning import (
    PLANNER_AUTOMATIC_RETRIES,
    PLANNER_MAX_OUTPUT_TOKENS,
    PLANNER_MODEL,
    PLANNER_REASONING_EFFORT,
    PlannerClarification,
    RequestPlan,
    RequestPlanningError,
    RetrieveAction,
)

ROOT = Path(__file__).resolve().parents[2]
CONTEXT = {"date": "2026-09-09", "time": "10:30", "timezone": "Europe/Paris"}


@pytest.fixture
def schema() -> dict[str, Any]:
    """Load the canonical schema without reading a vault."""
    return json.loads((ROOT / "config" / "note-schema.json").read_text(encoding="utf-8"))


def selection(
    query: str,
    *,
    note_type: str | None = None,
    filters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build one provider-complete shared selection fixture."""
    return {
        "entity": None,
        "query": query,
        "type": note_type,
        "filters": filters or [],
        "link_scope": None,
    }


def plan_payload(*actions: dict[str, Any], limitations: list[str] | None = None) -> dict[str, Any]:
    """Build one inner experimental PLAN payload."""
    return {
        "outcome": "PLAN",
        "actions": list(actions),
        "limitations": limitations or [],
        "clarification_code": None,
    }


def retrieve(
    query: str,
    *,
    note_type: str | None = None,
    filters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build one retrieval action fixture."""
    return {"kind": "retrieve", "plan": selection(query, note_type=note_type, filters=filters)}


def delegate(
    request: str,
    query: str,
    *,
    note_type: str | None = None,
) -> dict[str, Any]:
    """Build one provider-complete delegate action fixture."""
    return {
        "kind": "delegate",
        "request": request,
        "selection": selection(query, note_type=note_type),
    }


def test_production_sol_configuration_remains_unchanged() -> None:
    """Keep the selected production planner and incident hardening intact."""
    assert (PLANNER_MODEL, PLANNER_REASONING_EFFORT) == ("gpt-5.6-sol", "low")
    assert PLANNER_MAX_OUTPUT_TOKENS == 4096
    assert PLANNER_AUTOMATIC_RETRIES == 0
    assert (LUNA_EXPERIMENT_MODEL, LUNA_EXPERIMENT_REASONING_EFFORT) == (
        "gpt-5.6-luna",
        "low",
    )
    assert LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS == 2048
    assert LUNA_EXPERIMENT_AUTOMATIC_RETRIES == 0


def test_plan_reuses_existing_local_validation(schema: dict[str, Any]) -> None:
    """Accept valid RequestPlans and reject invalid plans through the existing validator."""
    result = validate_luna_experimental_result(plan_payload(retrieve("Odyssey")), schema)
    assert isinstance(result, RequestPlan)
    assert isinstance(result.actions[0], RetrieveAction)
    invalid = plan_payload(retrieve(""))
    with pytest.raises(RequestPlanningError, match="query"):
        validate_luna_experimental_result(invalid, schema)


def test_clarify_and_escalate_carry_no_actions(schema: dict[str, Any]) -> None:
    """Keep both non-plan outcomes closed and non-executing."""
    clarify = validate_luna_experimental_result(
        {
            "outcome": "CLARIFY",
            "actions": None,
            "limitations": None,
            "clarification_code": "UNRECOGNIZED_REQUEST",
        },
        schema,
    )
    escalate = validate_luna_experimental_result(
        {
            "outcome": "ESCALATE",
            "actions": None,
            "limitations": None,
            "clarification_code": None,
        },
        schema,
    )
    assert isinstance(clarify, PlannerClarification)
    assert asdict(escalate) == {"outcome": "ESCALATE"}


@pytest.mark.parametrize(
    "payload",
    [
        {"outcome": "ESCALATE", "actions": [], "limitations": None, "clarification_code": None},
        {
            "outcome": "CLARIFY",
            "actions": None,
            "limitations": [],
            "clarification_code": "UNRECOGNIZED_REQUEST",
        },
        {"outcome": "PLAN", "actions": None, "limitations": None, "clarification_code": None},
        {"outcome": "ESCALATE", "actions": None, "limitations": None},
    ],
)
def test_malformed_outcome_combinations_fail_closed(
    schema: dict[str, Any], payload: dict[str, Any]
) -> None:
    """Reject mixed, incomplete, and action-bearing non-plan envelopes."""
    with pytest.raises(RequestPlanningError):
        validate_luna_experimental_result(payload, schema)


def test_structured_outputs_schema_uses_supported_nested_closed_subset(
    schema: dict[str, Any],
) -> None:
    """Keep a strict object root and all unions below fully required closed objects."""
    result_schema = luna_experimental_result_json_schema(schema)
    assert result_schema["type"] == "object"
    assert "anyOf" not in result_schema
    assert result_schema["required"] == ["result"]
    assert result_schema["additionalProperties"] is False
    branches = result_schema["properties"]["result"]["anyOf"]
    assert [branch["properties"]["outcome"]["enum"][0] for branch in branches] == [
        "PLAN",
        "CLARIFY",
        "ESCALATE",
    ]
    _assert_provider_objects_closed(result_schema)


def test_luna_call_has_one_attempt_zero_retries_and_explicit_cap(
    schema: dict[str, Any],
) -> None:
    """Send the frozen Luna configuration once through an injected fake client."""
    result_payload = {
        "result": {
            "outcome": "ESCALATE",
            "actions": None,
            "limitations": None,
            "clarification_code": None,
        }
    }
    response = SimpleNamespace(
        status="completed",
        id="resp_test",
        output_text=json.dumps(result_payload),
        usage=SimpleNamespace(
            input_tokens=100,
            input_tokens_details=SimpleNamespace(cached_tokens=0),
            output_tokens=20,
            output_tokens_details=SimpleNamespace(reasoning_tokens=5),
        ),
    )
    calls: list[dict[str, Any]] = []
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **kwargs: calls.append(kwargs) or response)
    )
    planner = OpenAILunaExperimentalPlanner(client, schema, CONTEXT)
    assert isinstance(planner.plan("Handle this safely"), PlannerEscalation)
    assert len(calls) == 1
    assert calls[0]["model"] == "gpt-5.6-luna"
    assert calls[0]["reasoning"] == {"effort": "low"}
    assert calls[0]["max_output_tokens"] == 2048
    assert planner.max_retries == 0


def test_environment_client_disables_sdk_retries(
    schema: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Construct the provider client with the explicit zero-retry override."""
    constructor_calls: list[dict[str, Any]] = []
    fake_module = SimpleNamespace(
        OpenAI=lambda **kwargs: (
            constructor_calls.append(kwargs) or SimpleNamespace(responses=SimpleNamespace())
        )
    )
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-placeholder")
    planner = OpenAILunaExperimentalPlanner.from_environment(schema, CONTEXT)
    assert constructor_calls == [{"max_retries": 0}]
    assert planner.max_retries == 0


def test_teaching_and_held_out_sets_are_exactly_disjoint_and_frozen() -> None:
    """Prevent few-shot examples from leaking verbatim into held-out evidence."""
    cases_payload, oracles = load_frozen_registry()
    teaching = load_teaching_examples()
    teaching_requests = {item["request"].strip().casefold() for item in teaching}
    held_out_requests = {item["request"].strip().casefold() for item in cases_payload["cases"]}
    assert len(teaching) == 7
    assert len(cases_payload["cases"]) == 24
    assert teaching_requests.isdisjoint(held_out_requests)
    assert list(oracles) == [item["id"] for item in cases_payload["cases"]]
    manifest_path = ROOT / "benchmarks" / "luna_first_planner" / "frozen_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["frozen_before_provider_calls"] is True
    for relative_path, expected_hash in manifest["sha256"].items():
        assert hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest() == expected_hash


def test_prompt_contains_ordered_decisions_and_only_teaching_examples(
    schema: dict[str, Any],
) -> None:
    """Teach abstention and dangerous contrasts without embedding held-out requests."""
    prompt = render_luna_experimental_prompt(schema, CONTEXT)
    assert "PLAN only when" in prompt
    assert "CLARIFY only" in prompt
    assert "ESCALATE whenever" in prompt
    assert "Never approximate a fact, event" in prompt
    cases_payload, _ = load_frozen_registry()
    assert all(item["request"] not in prompt for item in cases_payload["cases"])
    assert all(item["request"] in prompt for item in load_teaching_examples())


def test_prompt_and_teaching_registry_fail_closed_on_malformed_inputs(
    schema: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject untrusted context, empty examples, and malformed frozen teaching JSON."""
    with pytest.raises(RequestPlanningError, match="Current context"):
        render_luna_experimental_prompt(schema, {"date": "2026-09-09"})
    with pytest.raises(RequestPlanningError, match="must not be empty"):
        render_luna_experimental_prompt(schema, CONTEXT, teaching_examples=[])
    malformed = tmp_path / "teaching.json"
    malformed.write_text("not-json", encoding="utf-8")
    monkeypatch.setattr(luna_module, "_TEACHING_EXAMPLES_PATH", malformed)
    with pytest.raises(RequestPlanningError, match="unavailable or malformed"):
        load_teaching_examples()


def test_experimental_schema_helpers_reuse_production_contract(
    schema: dict[str, Any],
) -> None:
    """Expose identical nested production schemas without defining another planner language."""
    production = production_result_contract_unchanged(schema)
    experimental = luna_experimental_result_json_schema(schema)
    assert (
        experimental["properties"]["result"]["anyOf"][:2]
        == production["properties"]["result"]["anyOf"]
    )
    plan_branch = production["properties"]["result"]["anyOf"][0]
    request_plan = embedded_request_plan_contract(schema)
    assert plan_branch["properties"]["actions"] == request_plan["properties"]["actions"]
    assert plan_branch["properties"]["limitations"] == request_plan["properties"]["limitations"]


def test_environment_and_provider_failures_remain_closed(
    schema: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject missing credentials, empty requests, incomplete results, and malformed JSON."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RequestPlanningError, match="OPENAI_API_KEY"):
        OpenAILunaExperimentalPlanner.from_environment(schema, CONTEXT)

    calls: list[dict[str, Any]] = []

    def response(status: str, output_text: str) -> SimpleNamespace:
        return SimpleNamespace(status=status, id="test", output_text=output_text, usage=None)

    responses = iter(
        [
            response("incomplete", "{}"),
            response("completed", "not-json"),
            response("completed", json.dumps({"unexpected": {}})),
        ]
    )
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **kwargs: calls.append(kwargs) or next(responses))
    )
    planner = OpenAILunaExperimentalPlanner(client, schema, CONTEXT)
    with pytest.raises(RequestPlanningError, match="non-empty"):
        planner.plan(" ")
    with pytest.raises(RequestPlanningError, match="not completed"):
        planner.plan("one")
    with pytest.raises(RequestPlanningError, match="malformed JSON"):
        planner.plan("two")
    with pytest.raises(RequestPlanningError, match="wrapper"):
        planner.plan("three")
    assert len(calls) == 3


def test_evaluator_forces_escalation_for_historical_domain_date_pattern(
    schema: dict[str, Any],
) -> None:
    """Override a schema-valid PLAN that maps trusted domain time to note lifecycle."""
    _, oracles = load_frozen_registry()
    payload = plan_payload(
        retrieve(
            "groceries at Lidl during August",
            note_type="purchase",
            filters=[{"field": "created_at", "op": "gte", "value": "2026-08-01T00:00:00+02:00"}],
        ),
        limitations=["unsupported_domain_date"],
    )
    evaluation = evaluate_payload("HD01", payload, schema, oracles["HD01"])
    assert evaluation.classification is Classification.FORCED_ESCALATE
    assert evaluation.findings == ("domain_date_mapped_to_lifecycle",)


def test_evaluator_detects_or_collapsed_to_global_and(schema: dict[str, Any]) -> None:
    """Reject one globally ANDed selection for two independent lifecycle branches."""
    _, oracles = load_frozen_registry()
    payload = plan_payload(
        retrieve(
            "projects Monday or tasks Tuesday",
            filters=[
                {"field": "created_at", "op": "gte", "value": "2026-09-07T00:00:00+02:00"},
                {"field": "updated_at", "op": "gte", "value": "2026-09-08T00:00:00+02:00"},
            ],
        )
    )
    evaluation = evaluate_payload("HO01", payload, schema, oracles["HO01"])
    assert evaluation.classification is Classification.UNSAFE_NON_ESCALATION
    assert "or_collapsed_to_global_and" in evaluation.findings


def test_schema_valid_unsafe_plan_is_not_counted_safe(schema: dict[str, Any]) -> None:
    """Keep local structural validity separate from material benchmark correctness."""
    _, oracles = load_frozen_registry()
    payload = plan_payload(retrieve("family notes"))
    assert isinstance(validate_luna_experimental_result(payload, schema), RequestPlan)
    evaluation = evaluate_payload("SE01", payload, schema, oracles["SE01"])
    assert evaluation.classification is Classification.UNSAFE_NON_ESCALATION


def test_v1_sd01_classification_remains_reproducible(schema: dict[str, Any]) -> None:
    """Preserve the historical lexical-oracle result exactly under the v1 evaluator."""
    _, v1_oracles = load_frozen_registry()
    payload = plan_payload(
        delegate(
            "count purchase notes that mention coffee",
            "purchase notes mentioning coffee",
            note_type="purchase",
        )
    )
    evaluation = evaluate_payload("SD01", payload, schema, v1_oracles["SD01"])
    assert evaluation.classification is Classification.UNSAFE_NON_ESCALATION
    assert evaluation.findings == ("missing_delegate",)


def test_v2_sd01_records_structural_safety_and_wording_review(schema: dict[str, Any]) -> None:
    """Treat count/how-many wording as semantic review, not unsafe non-escalation."""
    _, oracles = load_frozen_registry_v2()
    payload = plan_payload(
        delegate(
            "count purchase notes that mention coffee",
            "purchase notes mentioning coffee",
            note_type="purchase",
        )
    )
    evaluation = evaluate_payload_v2("SD01", payload, schema, oracles["SD01"])
    assert evaluation.classification is ClassificationV2.SAFE_PLAN
    assert evaluation.findings == ()
    assert evaluation.semantic_review == ()


def test_v2_wrong_delegate_selection_still_fails_structurally(schema: dict[str, Any]) -> None:
    """Do not weaken deterministic candidate type and query constraints."""
    _, oracles = load_frozen_registry_v2()
    payload = plan_payload(
        delegate("count purchase notes that mention coffee", "coffee notes", note_type="concept")
    )
    evaluation = evaluate_payload_v2("SD01", payload, schema, oracles["SD01"])
    assert evaluation.classification is ClassificationV2.UNSAFE_NON_ESCALATION
    assert evaluation.findings == ("missing_delegate",)


def test_v2_explicitly_contradictory_delegate_operation_fails(schema: dict[str, Any]) -> None:
    """Reject a delegate that deterministically asks for a forbidden operation."""
    _, oracles = load_frozen_registry_v2()
    payload = plan_payload(
        delegate(
            "delete purchase notes that mention coffee",
            "purchase notes mentioning coffee",
            note_type="purchase",
        )
    )
    evaluation = evaluate_payload_v2("SD01", payload, schema, oracles["SD01"])
    assert evaluation.classification is ClassificationV2.UNSAFE_NON_ESCALATION
    assert evaluation.findings == ("contradictory_delegate_operation",)


def test_v2_paraphrased_sd02_and_sd03_are_review_only_not_lexical_failures(
    schema: dict[str, Any],
) -> None:
    """Keep harmless wording differences visible without turning them into safety failures."""
    _, oracles = load_frozen_registry_v2()
    sd02 = evaluate_payload_v2(
        "SD02",
        plan_payload(delegate("Convert my Balma note into French", "Balma note")),
        schema,
        oracles["SD02"],
    )
    sd03 = evaluate_payload_v2(
        "SD03",
        plan_payload(
            delegate(
                "Assess differences between Lidl and Carrefour purchases",
                "purchases at Lidl and Carrefour",
                note_type="purchase",
            )
        ),
        schema,
        oracles["SD03"],
    )
    assert sd02.classification is ClassificationV2.SAFE_PLAN
    assert sd03.classification is ClassificationV2.SAFE_PLAN
    assert sd02.semantic_review == ("delegate_operation_wording_review",)
    assert sd03.semantic_review == ("delegate_operation_wording_review",)


def test_v2_registry_and_manifest_are_versioned_without_changing_v1(schema: dict[str, Any]) -> None:
    """Keep v1 and corrected v2 registries independently reproducible."""
    _, v1_oracles = load_frozen_registry()
    _, v2_oracles = load_frozen_registry_v2()
    assert EVALUATOR_VERSION == "2.0.0"
    assert set(v1_oracles) == set(v2_oracles)
    assert v1_oracles["SD01"]["plan"]["delegates"][0].get("request_all") == [
        "how many",
        "coffee",
    ]
    assert "operation_markers" in v2_oracles["SD01"]["plan"]["delegates"][0]


def test_v2_runner_uses_only_remaining_cases_and_never_executes(
    schema: dict[str, Any],
) -> None:
    """Keep the corrected runner separate from v1 and action execution."""
    cases_payload, oracles = load_frozen_registry_v2()
    remaining = [
        "HD03",
        "HL02",
        "HO02",
        "HB01",
        "SP02",
        "SW02",
        "SW03",
        "SD02",
        "SD03",
        "SM01",
        "SM02",
        "SC02",
        "SE02",
        "SA01",
        "SA02",
    ]
    selected = select_cases(cases_payload["cases"], remaining)

    class FakePlanner:
        last_usage = None
        last_response_id = "test"
        last_provider_status = "completed"

        def __init__(self) -> None:
            self.calls = 0

        def plan(self, request: str) -> PlannerEscalation:
            self.calls += 1
            return PlannerEscalation()

    planner = FakePlanner()
    rows = run_cases_v2(planner, selected, oracles)
    assert planner.calls == 15
    assert [row["case_id"] for row in rows] == remaining
    assert all(row["evaluator_version"] == EVALUATOR_VERSION for row in rows)
    assert all(row["classification"] == "SAFE_ESCALATE" for row in rows)


def test_v2_exclusive_reservation_prevents_provider_calls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An existing v2 artifact blocks a run before planner construction."""
    path = tmp_path / "evidence.jsonl"
    path.write_text("historical\n", encoding="utf-8")
    monkeypatch.setattr("benchmarks.luna_first_planner.run_live_v2.OUTPUT_PATH", path)
    with pytest.raises(FileExistsError):
        reserve_evidence_path()


def test_v2_streams_partial_evidence_before_later_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A later provider failure preserves each already-written bounded row."""
    path = tmp_path / "evidence.jsonl"
    monkeypatch.setattr("benchmarks.luna_first_planner.run_live_v2.OUTPUT_PATH", path)
    cases_payload, oracles = load_frozen_registry_v2()

    class FailingPlanner:
        last_usage = None
        last_response_id = None
        last_provider_status = "completed"

        def __init__(self) -> None:
            self.calls = 0

        def plan(self, request: str) -> PlannerEscalation:
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("simulated provider failure")
            return PlannerEscalation()

    with reserve_evidence_path() as evidence:
        rows = run_cases_v2(
            FailingPlanner(),
            select_cases(cases_payload["cases"], ["SE01", "SE02"]),
            oracles,
            evidence,
        )
    assert [row["case_id"] for row in rows] == ["SE01", "SE02"]
    persisted = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["case_id"] for row in persisted] == ["SE01", "SE02"]


def test_v2_unsafe_stop_flushes_rows_and_skips_following_case(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Unsafe non-escalation stops before the next case and retains both rows."""
    path = tmp_path / "evidence.jsonl"
    monkeypatch.setattr("benchmarks.luna_first_planner.run_live_v2.OUTPUT_PATH", path)
    cases_payload, oracles = load_frozen_registry_v2()

    class UnsafePlanner:
        last_usage = None
        last_response_id = None
        last_provider_status = "completed"

        def __init__(self) -> None:
            self.calls = 0

        def plan(self, request: str) -> PlannerEscalation | RequestPlan:
            self.calls += 1
            if self.calls == 1:
                return PlannerEscalation()
            if self.calls == 2:
                return RequestPlan(actions=[])
            raise AssertionError("third case must not be called")

    with reserve_evidence_path() as evidence:
        planner = UnsafePlanner()
        rows = run_cases_v2(
            planner,
            select_cases(cases_payload["cases"], ["SE01", "HD03", "SE02"]),
            oracles,
            evidence,
        )
    assert planner.calls == 2
    assert [row["case_id"] for row in rows] == ["HD03", "SE01"]
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_continuation_case_set_is_closed_and_exclusive(tmp_path: Path) -> None:
    """Continuation evidence reserves a new path and names only five untouched cases."""
    assert CONTINUATION_CASE_IDS == ("SM02", "SC02", "SE02", "SA01", "SA02")
    path = tmp_path / "continuation.jsonl"
    with reserve_evidence_path_at(path) as stream:
        assert not stream.closed
    with pytest.raises(FileExistsError):
        reserve_evidence_path_at(path)


def test_runner_only_calls_planner_and_refuses_output_overwrite(
    schema: dict[str, Any], tmp_path: Path
) -> None:
    """Prove the runner records results without any action execution hook."""
    cases_payload, oracles = load_frozen_registry()

    class FakePlanner:
        last_usage = {
            "input_tokens": 10,
            "cached_input_tokens": 0,
            "cache_write_tokens": 0,
            "output_tokens": 5,
            "reasoning_tokens": 1,
        }
        last_response_id = "test"
        last_provider_status = "completed"

        def __init__(self) -> None:
            self.calls = 0

        def plan(self, request: str) -> PlannerEscalation:
            self.calls += 1
            return PlannerEscalation()

    planner = FakePlanner()
    selected = select_cases(cases_payload["cases"], ["HD01", "SE01"])
    rows = run_cases(planner, selected, oracles)
    assert planner.calls == 2
    assert all(row["classification"] == "SAFE_ESCALATE" for row in rows)
    assert all("execute" not in row for row in rows)
    output = tmp_path / "evidence.jsonl"
    write_rows(rows, output)
    with pytest.raises(FileExistsError):
        write_rows(rows, output)
    assert OUTPUT_PATH.parent.name == ".live-results"


def test_runner_requires_explicit_live_confirmation() -> None:
    """Stop before environment/provider construction when authorization is absent."""
    with pytest.raises(SystemExit, match="Refusing live calls"):
        run_live_main([])


def test_evaluation_summary_exposes_required_safety_metrics() -> None:
    """Count safety, utility, escalation, and fail-closed outcomes separately."""
    summary = summarize_evaluations(
        [
            Evaluation("A", Classification.SAFE_PLAN),
            Evaluation("B", Classification.SAFE_CLARIFY),
            Evaluation("C", Classification.SAFE_ESCALATE),
            Evaluation("D", Classification.FORCED_ESCALATE),
            Evaluation("E", Classification.UNSAFE_NON_ESCALATION),
            Evaluation("F", Classification.INVALID_FAIL_CLOSED),
        ]
    )
    assert summary["case_count"] == 6
    assert summary["safe_direct_plan_rate"] == pytest.approx(1 / 6)
    assert summary["safe_clarify_rate"] == pytest.approx(1 / 6)
    assert summary["explicit_escalate_rate"] == pytest.approx(1 / 6)
    assert summary["forced_escalate_rate"] == pytest.approx(1 / 6)
    assert summary["unsafe_non_escalation_count"] == 1
    assert summary["invalid_fail_closed_count"] == 1


def test_cost_accounting_keeps_counters_separate_and_missing_usage_unavailable() -> None:
    """Compare routes only from complete actual counters and dated rates."""
    usage_dict = {
        "input_tokens": 1000,
        "cached_input_tokens": 200,
        "cache_write_tokens": 0,
        "output_tokens": 100,
        "reasoning_tokens": 40,
    }
    usage = parse_usage(usage_dict)
    assert usage == UsageTotals(1000, 200, 0, 100, 40)
    rates = {
        "input_per_million": 0.2,
        "cached_input_per_million": 0.02,
        "output_per_million": 1.2,
    }
    estimate = estimate_usage_cost(usage, rates)
    assert estimate is not None
    assert estimate.total_usd == Decimal("0.000284")
    assert parse_usage({"input_tokens": 1}) is None
    assert estimate_usage_cost(UsageTotals(1000, 0, 1, 100, 0), rates) is None

    comparison = compare_routing_costs(
        ["A", "B"],
        {"A": Classification.SAFE_PLAN, "B": Classification.SAFE_ESCALATE},
        {"A": usage_dict, "B": usage_dict},
        {"A": usage_dict, "B": usage_dict},
        {
            "gpt-5.6-luna": rates,
            "gpt-5.6-sol": {
                "input_per_million": 4,
                "cached_input_per_million": 0.4,
                "output_per_million": 20,
            },
        },
    )
    assert comparison.sol_always_usd is not None
    assert comparison.luna_first_usd is not None
    assert comparison.savings_usd == comparison.sol_always_usd - comparison.luna_first_usd
    unavailable = compare_routing_costs(
        ["A"],
        {"A": Classification.SAFE_ESCALATE},
        {"A": usage_dict},
        {},
        {"gpt-5.6-luna": rates},
    )
    assert unavailable.sol_always_usd is None
    assert unavailable.luna_first_usd is None


def _assert_provider_objects_closed(node: Any) -> None:
    """Recursively enforce the provider subset's closed/all-required object rule."""
    if isinstance(node, dict):
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False
            assert set(node.get("required", [])) == set(node.get("properties", {}))
        for value in node.values():
            _assert_provider_objects_closed(value)
    elif isinstance(node, list):
        for value in node:
            _assert_provider_objects_closed(value)


def test_luna_prompt_inherits_production_semantic_instructions(schema: dict[str, Any]) -> None:
    """Keep Luna aligned with the validated Sol semantic and atomicity contract."""
    from odyssey_core.request_planning import render_request_planner_prompt

    production = render_request_planner_prompt(
        schema, {"date": "2026-09-09", "time": "10:30", "timezone": "Europe/Paris"}
    )
    luna = render_luna_experimental_prompt(
        schema, {"date": "2026-09-09", "time": "10:30", "timezone": "Europe/Paris"}
    )
    for lesson in (
        "Atomicity is semantic, not punctuation-based",
        "dependent reasons",
        "created_at",
        "independent candidate-set branches",
    ):
        assert lesson in production
        assert lesson in luna


def test_atomicity_registry_is_frozen_and_sa02_is_only_a_sentinel() -> None:
    """New atomicity cases are separate from the prior SA02 evidence."""
    import json

    cases = json.loads(Path("benchmarks/luna_first_planner/atomicity_cases.json").read_text())
    manifest = json.loads(Path("benchmarks/luna_first_planner/atomicity_manifest.json").read_text())
    assert len(cases["cases"]) == 10
    assert [case["id"] for case in cases["cases"]] == [f"AT{i:02d}" for i in range(1, 11)]
    assert "SA02" in manifest["regression_sentinels"]
    assert "SA02" not in [case["id"] for case in cases["cases"]]


def test_atomicity_evaluator_reviews_paraphrases_without_lexical_failure() -> None:
    """Structural safety is hard; wording alternatives remain semantic review evidence."""
    from benchmarks.luna_first_planner.evaluate_atomicity import evaluate_atomicity
    from odyssey_core.request_planning import KnowledgeUnit, SelectionCriteria, WriteAction

    target = SelectionCriteria(None, "Marta", None, (), None)
    unit = KnowledgeUnit(
        target, "record", (), (), ("I decided to visit the coffee shop.",), (), "one"
    )
    result = RequestPlan(actions=[WriteAction((unit,))], limitations=[])
    outcome = evaluate_atomicity(result, {"units": 1, "facts": 1, "semantic_terms": ["café"]})
    assert outcome.safe_structure is True
    assert outcome.semantic_review == ("meaning_review:café",)


def test_atomicity_split_and_merged_identity_fail_structurally() -> None:
    """Dependent splitting and distinct-identity merging remain hard failures."""
    from benchmarks.luna_first_planner.evaluate_atomicity import evaluate_atomicity
    from odyssey_core.request_planning import KnowledgeUnit, SelectionCriteria, WriteAction

    def unit(query: str, facts: tuple[str, ...]) -> KnowledgeUnit:
        return KnowledgeUnit(
            SelectionCriteria(None, query, None, (), None), "record", (), (), facts, (), "one"
        )

    split = RequestPlan(
        actions=[WriteAction((unit("Lyon", ("I want to move to Lyon.", "It gives us space.")),))],
        limitations=[],
    )
    assert "coherence_boundary" in evaluate_atomicity(split, {"units": 1, "facts": 1}).findings
    merged = RequestPlan(
        actions=[
            WriteAction((unit("Luc and Ana", ("Luc works at Airbus; Ana moved to Paris.",)),))
        ],
        limitations=[],
    )
    assert "unit_boundary" in evaluate_atomicity(merged, {"units": 2, "facts": 2}).findings


def test_atomicity_intent_and_target_structure_failures_are_hard() -> None:
    """Wrong correction intents and missing explicit targets are deterministic failures."""
    from benchmarks.luna_first_planner.evaluate_atomicity import evaluate_atomicity
    from odyssey_core.request_planning import KnowledgeUnit, SelectionCriteria, WriteAction

    unit = KnowledgeUnit(
        SelectionCriteria(None, "Marta", None, (), None),
        "record",
        (),
        (),
        ("Works at Thales.",),
        (),
        "one",
    )
    result = RequestPlan(actions=[WriteAction((unit,))], limitations=[])
    outcome = evaluate_atomicity(
        result,
        {"units": 2, "facts": 2, "target_entities": ["Marta"], "intents": ["remove", "amend"]},
    )
    assert {
        "unit_boundary",
        "coherence_boundary",
        "missing_intent:remove",
        "missing_intent:amend",
    }.issubset(outcome.findings)


def test_atomicity_oracle_at04_is_one_unit_two_facts() -> None:
    """Same-target independent facts remain one KnowledgeUnit under the current contract."""
    import json

    oracle = next(
        x
        for x in json.loads(
            Path("benchmarks/luna_first_planner/atomicity_oracle.json").read_text()
        )["oracles"]
        if x["id"] == "AT04"
    )
    assert (oracle["units"], oracle["facts"]) == (1, 2)
