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
