"""Provider-free tests for the frozen Slice 1 semantic-set Luna gate."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.luna_first_planner.evaluate_v2 import load_frozen_registry_v2
from benchmarks.semantic_set_planner.gate import (
    MAX_LUNA_INPUT_TOKENS,
)
from benchmarks.semantic_set_planner.run_live import run_cases
from benchmarks.semantic_set_planner.run_live_v3 import (
    OUTPUT_PATH as V3_ATTEMPT1_OUTPUT_PATH,
)
from benchmarks.semantic_set_planner.run_live_v3 import run_v3_gate
from benchmarks.semantic_set_planner.run_live_v3_retry1 import (
    OUTPUT_PATH as V3_RETRY1_OUTPUT_PATH,
)
from benchmarks.semantic_set_planner.run_live_v3_retry2 import (
    OUTPUT_PATH as V3_RETRY2_OUTPUT_PATH,
)
from benchmarks.semantic_set_planner.run_live_v4_retry1 import (
    OUTPUT_PATH as V4_RETRY1_OUTPUT_PATH,
)
from benchmarks.semantic_set_planner.v2_gate import (
    evaluate_v2_result,
    load_v2_registry,
    v2_preflight,
)
from benchmarks.semantic_set_planner.v3_gate import (
    evaluate_v3_result,
    load_v3_registry,
    v3_preflight,
)
from benchmarks.semantic_set_planner.v3_regression_gate import (
    CASE_IDS as V3_REGRESSION_CASE_IDS,
)
from benchmarks.semantic_set_planner.v3_regression_gate import (
    load_v3_regression_registry,
    v3_regression_preflight,
)
from benchmarks.semantic_set_planner.v4_gate import load_v4_registry, v4_preflight
from odyssey_core.experimental_luna_planning import validate_luna_experimental_result

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def schema() -> dict:
    """Load the canonical planner schema without any provider or vault access."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def selection(query: str, semantic_set: dict | None = None, relational: dict | None = None) -> dict:
    """Build one complete provider-shaped selection for local production validation."""
    return {
        "entity": None,
        "query": query,
        "type": None,
        "filters": [],
        "link_scope": None,
        "self_target": None,
        "relational_reference": relational,
        "semantic_set": semantic_set,
    }


def plan(selection_value: dict) -> dict:
    """Build one single-retrieval production planner result."""
    return {
        "outcome": "PLAN",
        "actions": [{"kind": "retrieve", "plan": selection_value}],
        "limitations": [],
        "clarification_code": None,
        "presentation_intent": "answer",
    }


def semantic(
    subject_kind: str, subject_query: str | None, member_query: str, qualifiers: str = ""
) -> dict:
    """Build the approved planner-visible semantic-set intent shape."""
    return {
        "subject_kind": subject_kind,
        "subject_query": subject_query,
        "member_query": member_query,
        "explicit_qualifiers": qualifiers,
        "asks_exhaustive": True,
    }


def validated(payload: dict, schema: dict):
    """Use the same local validator as the live Luna planner boundary."""
    return validate_luna_experimental_result(payload, schema)


def test_frozen_registry_and_conservative_luna_budget(schema: dict) -> None:
    """Lock exactly six cases and reserve less than the approved USD 0.10 before any call."""
    cases, oracles = load_v2_registry()
    details = v2_preflight(schema, cases)

    assert list(oracles) == [case["id"] for case in cases["cases"]]
    assert details["logical_cases"] == details["maximum_provider_calls"] == 6
    assert details["maximum_luna_input_bound"] == MAX_LUNA_INPUT_TOKENS
    assert float(details["conservative_no_cache_maximum_usd"]) <= 0.10


@pytest.mark.parametrize(
    ("case_id", "payload"),
    [
        (
            "SSET01",
            plan(selection("familia", semantic("self", None, "personas de mi familia"))),
        ),
        (
            "SSET02",
            plan(selection("kit", semantic("query", "kit básico para la bici", "piezas"))),
        ),
        (
            "SSET03",
            plan(selection("tortilla", semantic("query", "receta de tortilla", "ingredientes"))),
        ),
        (
            "SSET04",
            plan(selection("viaje", semantic("self", None, "compañeros de viaje", "Italia"))),
        ),
        (
            "REG01",
            plan(
                selection(
                    "mi ahijada",
                    relational={
                        "reference": "mi ahijada",
                        "source_kind": "self",
                        "source_query": None,
                        "members": "one",
                    },
                )
            ),
        ),
        ("REG02", plan(selection("dónde trabaja Marta"))),
    ],
)
def test_evaluator_accepts_frozen_safe_structures(
    case_id: str, payload: dict, schema: dict
) -> None:
    """Accept each intended structural outcome with local production validation first."""
    _cases, oracles = load_v2_registry()

    assert evaluate_v2_result(validated(payload, schema), oracles[case_id]).classification == "PASS"


def test_evaluator_rejects_dropped_qualifier_and_semantic_regression(schema: dict) -> None:
    """Fail a material qualifier loss and accidental set semantics on an ordinary named read."""
    _cases, oracles = load_v2_registry()
    missing_italy = validated(
        plan(selection("viaje", semantic("self", None, "compañeros de viaje"))), schema
    )
    accidental_set = validated(
        plan(selection("Marta", semantic("self", None, "personas de mi familia"))), schema
    )

    assert evaluate_v2_result(missing_italy, oracles["SSET04"]).findings == (
        "material_qualifier_dropped",
    )
    assert evaluate_v2_result(accidental_set, oracles["REG02"]).findings == (
        "semantic_set_on_named_regression",
    )


def test_runner_flushes_first_failure_and_does_not_call_later_cases(
    tmp_path: Path, schema: dict
) -> None:
    """Stop after one failed evaluation while retaining a compact JSONL row immediately."""
    _cases, oracles = load_v2_registry()
    planner = SimpleNamespace(
        last_error_category=None,
        last_input_sizes={"user_request_bytes": 1},
        last_parse_status="succeeded",
        last_provider_status="completed",
        last_response_id="response",
        last_usage={"input_tokens": 1, "output_tokens": 1},
        last_validation_code=None,
        last_validation_stage=None,
        calls=[],
    )

    def plan_request(request: str):
        planner.calls.append(request)
        return validated(plan(selection("Marta", semantic("self", None, "familia"))), schema)

    planner.plan = plan_request
    evidence_path = tmp_path / "evidence.jsonl"
    with evidence_path.open("x", encoding="utf-8") as evidence:
        rows = run_cases(
            planner,
            [{"id": "REG02", "request": "uno"}, {"id": "REG01", "request": "dos"}],
            oracles,
            evidence,
            evaluator=evaluate_v2_result,
        )

    assert [row["classification"] for row in rows] == ["FAIL"]
    assert planner.calls == ["uno"]
    assert len(evidence_path.read_text(encoding="utf-8").splitlines()) == 1


def test_v3_evaluator_requires_lossless_meaning_and_schema_member_type(schema: dict) -> None:
    """Freeze the next gate's family and travel semantic-preservation sentinels locally."""
    _cases, oracles = load_v3_registry()
    family = validated(
        plan(selection("personas de mi familia", semantic("self", None, "personas de mi familia"))),
        schema,
    )
    assert evaluate_v3_result(family, oracles["SSET01"]).findings == (
        "member_type_missing_or_wrong",
    )
    typed = semantic("self", None, "personas", "mi familia")
    typed["member_type"] = "person"
    assert (
        evaluate_v3_result(
            validated(plan(selection("personas de mi familia", typed)), schema), oracles["SSET01"]
        ).classification
        == "PASS"
    )
    cases, _oracles = load_v3_registry()
    assert float(v3_preflight(schema, cases)["conservative_no_cache_maximum_usd"]) <= 0.10


def test_v4_freezes_v3_evaluations_with_possessive_subject_teaching(schema: dict) -> None:
    """Version the model-facing correction without rewriting v3 evidence contracts."""
    v3_cases = json.loads((ROOT / "benchmarks/semantic_set_planner/v3_cases.json").read_text())
    v3_oracles = json.loads((ROOT / "benchmarks/semantic_set_planner/v3_oracle.json").read_text())
    cases, oracles = load_v4_registry()
    teaching = json.loads(
        (ROOT / "benchmarks/semantic_set_planner/v4_teaching_examples.json").read_text()
    )["examples"]

    assert cases["cases"] == v3_cases["cases"]
    assert list(oracles.values()) == v3_oracles["oracles"]
    assert [case["id"] for case in cases["cases"]] == [
        "SSET01",
        "SSET02",
        "SSET03",
        "SSET04",
        "REG01",
        "REG02",
    ]
    assert all(case["request"] not in str(teaching) for case in cases["cases"])
    possessive = next(
        item for item in teaching if item["id"] == "semantic-set-possessive-object-subject"
    )
    assert possessive["request"] == "What is in my emergency bag?"
    intent = possessive["result"]["actions"][0]["plan"]["semantic_set"]
    assert intent["subject_kind"] == "query"
    assert intent["subject_query"] == "my emergency bag"
    assert intent["member_type"] is None
    assert validate_luna_experimental_result(possessive["result"], schema)
    assert float(v4_preflight(schema, cases)["conservative_no_cache_maximum_usd"]) <= 0.10


def test_v4_retry1_has_a_fixed_distinct_immutable_evidence_path() -> None:
    """Keep retry1 evidence separate from the preserved original v4 attempt."""
    from benchmarks.semantic_set_planner.run_live_v4 import OUTPUT_PATH as v4_attempt1_output_path

    assert V4_RETRY1_OUTPUT_PATH != v4_attempt1_output_path
    assert V4_RETRY1_OUTPUT_PATH.name == "semantic-set-slice1-v4-luna-gate-retry1.jsonl"


def test_v4_retry1_wrapper_delegates_to_the_exact_frozen_v4_logic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reuse v4 unchanged while substituting only the reserved evidence path."""
    import benchmarks.semantic_set_planner.run_live_v4 as frozen_v4
    import benchmarks.semantic_set_planner.run_live_v4_retry1 as retry1

    observed: list[list[str] | None] = []

    def frozen_main(argv: list[str] | None = None) -> int:
        observed.append(argv)
        return 0

    monkeypatch.setattr(frozen_v4, "main", frozen_main)

    assert retry1.main(["--confirm-live-provider-calls"]) == 0
    assert frozen_v4.OUTPUT_PATH != V4_RETRY1_OUTPUT_PATH
    assert observed == [["--confirm-live-provider-calls"]]


def test_v4_subject_contract_distinguishes_human_and_possessive_object(schema: dict) -> None:
    """Keep prompt examples contract-valid without claiming they predict Luna output."""
    _cases, _oracles = load_v4_registry()
    self_anchored = semantic("self", None, "people I travelled with", "Japan")
    self_anchored["member_type"] = "person"
    possessive_object = semantic("query", "my emergency bag", "items")

    self_intent = (
        validated(plan(selection("people I travelled with to Japan", self_anchored)), schema)
        .actions[0]
        .plan.semantic_set
    )
    assert self_intent is not None
    assert self_intent.subject_kind == "self"
    assert self_intent.subject_query is None
    query_intent = (
        validated(plan(selection("items in my emergency bag", possessive_object)), schema)
        .actions[0]
        .plan.semantic_set
    )
    assert query_intent is not None
    assert query_intent.subject_kind == "query"
    assert query_intent.subject_query == "my emergency bag"
    assert query_intent.member_type is None


def test_v3_regression_gate_reuses_exact_historical_contracts(schema: dict) -> None:
    """Keep the compact live regression gate tied to Phase 20.2E evidence."""
    cases, oracles = load_v3_regression_registry()
    historical_cases, historical_oracles = load_frozen_registry_v2()
    historical_by_id = {case["id"]: case for case in historical_cases["cases"]}
    teaching = json.loads(
        (ROOT / "benchmarks/semantic_set_planner/v3_teaching_examples.json").read_text()
    )["examples"]

    assert tuple(case["id"] for case in cases["cases"]) == V3_REGRESSION_CASE_IDS
    assert all(case == historical_by_id[case["id"]] for case in cases["cases"])
    assert all(
        oracles[case_id] == historical_oracles[case_id] for case_id in V3_REGRESSION_CASE_IDS
    )
    details = v3_regression_preflight(schema, cases, teaching)
    assert details["maximum_provider_calls"] == 10
    assert float(details["conservative_no_cache_maximum_usd"]) > 0.10


def test_v3_retry1_has_a_fixed_distinct_immutable_evidence_path() -> None:
    """Keep retry1 separate from the preserved original v3 attempt evidence."""
    assert V3_RETRY1_OUTPUT_PATH != V3_ATTEMPT1_OUTPUT_PATH
    assert V3_RETRY1_OUTPUT_PATH.name == "semantic-set-slice1-v3-luna-gate-retry1.jsonl"
    assert V3_ATTEMPT1_OUTPUT_PATH.name == "semantic-set-slice1-v3-luna-gate.jsonl"


def test_v3_retry2_has_a_fixed_distinct_immutable_evidence_path() -> None:
    """Keep retry2 separate from both preserved prior v3 attempts."""
    assert len({V3_ATTEMPT1_OUTPUT_PATH, V3_RETRY1_OUTPUT_PATH, V3_RETRY2_OUTPUT_PATH}) == 3
    assert V3_RETRY2_OUTPUT_PATH.name == "semantic-set-slice1-v3-luna-gate-retry2.jsonl"


def test_v3_retry1_wrapper_reuses_the_exact_v3_execution_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delegate retry1 to shared v3 plumbing rather than copy cases, oracles, or model settings."""
    import benchmarks.semantic_set_planner.run_live_v3 as attempt1
    import benchmarks.semantic_set_planner.run_live_v3_retry1 as retry1

    observed: list[tuple[Path, list[str] | None]] = []

    def shared_gate(output_path: Path, argv: list[str] | None = None) -> int:
        observed.append((output_path, argv))
        return 0

    assert retry1.run_v3_gate is attempt1.run_v3_gate
    monkeypatch.setattr(retry1, "run_v3_gate", shared_gate)

    assert retry1.main(["--confirm-live-provider-calls"]) == 0
    assert observed == [(V3_RETRY1_OUTPUT_PATH, ["--confirm-live-provider-calls"])]


def test_v3_retry2_wrapper_reuses_the_exact_v3_execution_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delegate retry2 to the same reviewed v3 gate rather than copying frozen contracts."""
    import benchmarks.semantic_set_planner.run_live_v3 as attempt1
    import benchmarks.semantic_set_planner.run_live_v3_retry2 as retry2

    observed: list[tuple[Path, list[str] | None]] = []

    def shared_gate(output_path: Path, argv: list[str] | None = None) -> int:
        observed.append((output_path, argv))
        return 0

    assert retry2.run_v3_gate is attempt1.run_v3_gate
    monkeypatch.setattr(retry2, "run_v3_gate", shared_gate)

    assert retry2.main(["--confirm-live-provider-calls"]) == 0
    assert observed == [(V3_RETRY2_OUTPUT_PATH, ["--confirm-live-provider-calls"])]


def test_v3_runner_refuses_without_confirmation_before_provider_construction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ensure a dry retry cannot create evidence or build the provider client."""
    import benchmarks.semantic_set_planner.run_live_v3 as runner

    output_path = tmp_path / "retry1.jsonl"
    constructed = False

    def unexpected_client(*args, **kwargs):
        nonlocal constructed
        constructed = True
        raise AssertionError("provider construction must not happen during dry preflight")

    monkeypatch.setattr(runner.OpenAILunaExperimentalPlanner, "from_environment", unexpected_client)
    monkeypatch.setenv("OPENAI_API_KEY", "test-presence-only")

    with pytest.raises(SystemExit, match="preflight refused"):
        run_v3_gate(output_path, [])

    assert constructed is False
    assert output_path.exists() is False


def test_v3_retry1_refuses_an_existing_path_before_provider_construction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Prevent a future retry from overwriting either an attempt or partial evidence."""
    import benchmarks.semantic_set_planner.run_live_v3 as runner

    output_path = tmp_path / "retry1.jsonl"
    original = '{"attempt":"immutable"}\n'
    output_path.write_text(original, encoding="utf-8")
    constructed = False

    def unexpected_client(*args, **kwargs):
        nonlocal constructed
        constructed = True
        raise AssertionError("provider construction must not happen after an output collision")

    monkeypatch.setattr(runner.OpenAILunaExperimentalPlanner, "from_environment", unexpected_client)
    monkeypatch.setenv("OPENAI_API_KEY", "test-presence-only")

    with pytest.raises(SystemExit, match="preflight refused"):
        run_v3_gate(output_path, ["--confirm-live-provider-calls"])

    assert constructed is False
    assert output_path.read_text(encoding="utf-8") == original


def test_v3_retry2_refuses_existing_evidence_without_altering_prior_attempts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Protect every reserved attempt path before a retry2 client could be built."""
    import benchmarks.semantic_set_planner.run_live_v3 as runner

    attempt1 = tmp_path / "attempt1.jsonl"
    retry1 = tmp_path / "retry1.jsonl"
    retry2 = tmp_path / "retry2.jsonl"
    attempt1.write_text('{"attempt":1}\n', encoding="utf-8")
    retry1.write_text('{"attempt":2}\n', encoding="utf-8")
    retry2.write_text('{"attempt":3}\n', encoding="utf-8")
    original_attempt1 = attempt1.read_bytes()
    original_retry1 = retry1.read_bytes()
    monkeypatch.setenv("OPENAI_API_KEY", "test-presence-only")
    monkeypatch.setattr(
        runner.OpenAILunaExperimentalPlanner,
        "from_environment",
        lambda *_args, **_kwargs: pytest.fail("provider construction must not occur"),
    )

    with pytest.raises(SystemExit, match="preflight refused"):
        run_v3_gate(retry2, ["--confirm-live-provider-calls"])

    assert attempt1.read_bytes() == original_attempt1
    assert retry1.read_bytes() == original_retry1
    assert retry2.read_text(encoding="utf-8") == '{"attempt":3}\n'


def test_failure_evidence_includes_only_safe_error_type_chain(tmp_path: Path) -> None:
    """Project planner type-only transport diagnostics without hidden request data."""
    planner = SimpleNamespace(
        last_error_category="APIConnectionError",
        last_error_chain=("APIConnectionError", "ConnectError", "ConnectionResetError"),
        last_input_sizes=None,
        last_parse_status=None,
        last_provider_status=None,
        last_response_id=None,
        last_usage=None,
        last_validation_code=None,
        last_validation_stage=None,
    )

    def fail(_request: str):
        raise RuntimeError("SECRET_PROMPT_OR_REQUEST")

    planner.plan = fail
    evidence_path = tmp_path / "evidence.jsonl"
    with evidence_path.open("x", encoding="utf-8") as evidence:
        rows = run_cases(planner, [{"id": "SSET01", "request": "SECRET_REQUEST"}], {}, evidence)

    assert rows[0]["error_chain"] == (
        "APIConnectionError",
        "ConnectError",
        "ConnectionResetError",
    )
    serialized = evidence_path.read_text(encoding="utf-8")
    assert json.loads(serialized)["error_chain"] == [
        "APIConnectionError",
        "ConnectError",
        "ConnectionResetError",
    ]
    assert "SECRET" not in serialized
