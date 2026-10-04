"""Provider-free freeze for the focused Router/Temporal/Core live regression gate."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

from odyssey_apps import ApplicationDescriptor, ApplicationRegistry, Route, RouteOutcome, RoutePlan
from odyssey_apps.router import validate_route_plan
from odyssey_core.domain_interpretation import (
    TEMPORAL_REFERENCE_EVIDENCE,
    DomainEvidence,
    DomainInterpretation,
)
from odyssey_core.experimental_luna_planning import (
    luna_experimental_result_json_schema,
    render_luna_experimental_prompt,
)
from odyssey_core.temporal import TemporalAnchor

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "benchmarks/router_temporal_core_live_v1/matrix.json"
RUNNER = ROOT / "benchmarks/router_temporal_core_live_v1/run_live.py"
MATRIX_SHA256 = "02d7f053a346db249282484f5d3740c9f6b0ea17de11a0e5524f1894495126a9"
EXPECTED_IDS = [
    "R1-multiple-dates",
    "R2-exact-datetime-relational-friend",
    "R3-date-range",
    "T1-today-bea-children",
    "T2-multiple-dates",
    "T3-exact-datetime",
    "T4-date-range",
    "C1-exact-dates-compound",
    "C2-entity-exact-datetime",
    "C3-day-exact-datetime",
    "C4-relational-friend-exact-datetime",
    "C5-bea-children-date",
    "C6-bea-children-datetime",
    "C7-qualified-child-date",
]


def _load() -> dict:
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def _runner_module():
    spec = importlib.util.spec_from_file_location("router_temporal_core_live_v1", RUNNER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _catalog():
    return ApplicationRegistry.from_descriptors(
        (
            ApplicationDescriptor(
                "tasks", "task lifecycle, due dates, completion and obligations", ("temporal",)
            ),
        )
    ).catalog()


def test_frozen_matrix_keeps_all_regression_sentinels() -> None:
    matrix = _load()
    assert hashlib.sha256(MATRIX.read_bytes()).hexdigest() == MATRIX_SHA256
    cases = matrix["router_cases"] + matrix["temporal_cases"] + matrix["core_cases"]
    assert matrix["version"] == 1
    assert len(cases) == 14
    assert [case["id"] for case in cases] == EXPECTED_IDS
    assert any("Bea y mis hijos" in case["source"] for case in matrix["core_cases"])
    assert any(
        "mi hijo al que le gusta el fútbol" in case["source"] for case in matrix["core_cases"]
    )
    assert any(
        "amigo del barrio que tiene un barco" in case["source"] for case in matrix["core_cases"]
    )


def test_router_and_core_oracles_are_locally_grounded() -> None:
    matrix = _load()
    catalog = _catalog()
    for case in matrix["router_cases"]:
        validate_route_plan(
            RoutePlan(RouteOutcome.ROUTE, (Route(case["expect_capability"], case["source"]),)),
            case["source"],
            catalog,
        )
    for case in matrix["core_cases"]:
        evidence = tuple(
            DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, text, value)
            for text, value in case["evidence"]
        )
        interpretation = DomainInterpretation(
            "temporal", case["source"], "TEMPORAL_RESOLUTION", evidence
        )
        assert all(text in case["source"] for text, _value in case["evidence"])
        assert [item.temporal_anchor().value for item in evidence] == case["expect_anchors"]
        for _text, value in case["evidence"]:
            TemporalAnchor.from_value(value)
        prompt = render_luna_experimental_prompt(
            json.loads((ROOT / "config/note-schema.json").read_text()),
            matrix["current_context"],
            domain_interpretation=interpretation,
        )
        provider_schema = luna_experimental_result_json_schema(
            json.loads((ROOT / "config/note-schema.json").read_text()), interpretation
        )
        assert "Specialized domain interpretation" in prompt
        assert provider_schema["additionalProperties"] is False


def test_authorized_live_envelope_is_bounded_without_mutation() -> None:
    matrix = _load()
    runner = _runner_module()
    assert runner.MAX_CALLS == 14
    assert runner.AUTHORIZED_CEILING_USD == 0.10
    assert runner._budget_upper(matrix) < runner.AUTHORIZED_CEILING_USD
    source = RUNNER.read_text(encoding="utf-8")
    for forbidden in (
        "execute_request(",
        "materialize_",
        "create_entity(",
        "update_entity(",
        "git commit",
        "git push",
    ):
        assert forbidden not in source
