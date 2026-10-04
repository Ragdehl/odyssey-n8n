"""Provider-free freeze for the focused Core temporal-write successor gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from benchmarks.core_temporal_write_live_v2 import run_live
from odyssey_core.domain_interpretation import TEMPORAL_REFERENCE_EVIDENCE

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "benchmarks/core_temporal_write_live_v2/matrix.json"
V1_MATRIX = ROOT / "benchmarks/router_temporal_core_live_v1/matrix.json"
MATRIX_SHA256 = "3600ad45d021b29e1819274118c9cbfa29d54ee1b82ad85900deaca1a5643e92"


def test_matrix_is_frozen_and_reuses_only_affected_v1_core_sentinels() -> None:
    matrix = json.loads(MATRIX.read_text())
    v1 = json.loads(V1_MATRIX.read_text())

    assert hashlib.sha256(MATRIX.read_bytes()).hexdigest() == MATRIX_SHA256
    assert matrix["version"] == 2
    assert matrix["current_context"] == v1["current_context"]
    assert [case["id"] for case in matrix["cases"]] == [
        "C5-bea-children-date",
        "C6-bea-children-datetime",
        "C7-qualified-child-date",
        "C4-relational-friend-exact-datetime",
    ]

    old = {case["id"]: case for case in v1["core_cases"]}
    for case in matrix["cases"]:
        assert case == old[case["id"]]


def test_preflight_budget_and_call_ceiling_are_closed_without_provider_access() -> None:
    matrix = json.loads(MATRIX.read_text())
    assert len(matrix["cases"]) == run_live.MAX_CALLS == 4
    assert run_live._budget_upper(matrix) < run_live.PROPOSED_CEILING_USD == 0.05
    assert run_live._sha(MATRIX) == MATRIX_SHA256


def test_every_case_builds_only_bounded_temporal_domain_evidence() -> None:
    matrix = json.loads(MATRIX.read_text())
    for case in matrix["cases"]:
        interpretation = run_live._interpretation(case)
        assert interpretation.capability_id == "temporal"
        assert interpretation.source_text == case["source"]
        assert interpretation.intent == "TEMPORAL_RESOLUTION"
        assert [item.kind for item in interpretation.evidence] == [
            TEMPORAL_REFERENCE_EVIDENCE
        ] * len(case["evidence"])
        assert [(item.source_text, item.value) for item in interpretation.evidence] == [
            tuple(item) for item in case["evidence"]
        ]


def test_v2_gate_has_no_mutation_executor_or_runtime_dependency() -> None:
    source = (ROOT / "benchmarks/core_temporal_write_live_v2/run_live.py").read_text()
    assert "materialize" not in source
    assert "execute_routed_request" not in source
    assert "RuntimeComposition" not in source
    assert "OpenAILunaExperimentalPlanner" in source
    assert "max_retries=0" in source
