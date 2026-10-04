"""Provider-free freeze for the one-shot Router v6 + Temporal v1 live successor."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "benchmarks/router_temporal_live_v2"
MATRIX = HERE / "matrix.json"
ROUTER_MATRIX = ROOT / "benchmarks/application_router/regression_v6.json"
TEMPORAL_MATRIX = ROOT / "benchmarks/temporal_interpreter/regression_v1.json"
MATRIX_SHA256 = "e6ea6722307f11af1d034b6156545771d7ff54abea9f272e7e6f87cb8110ac69"


def _runner_module():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "router_temporal_live_v2_runner", HERE / "run_live.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_v2_matrix_exactly_freezes_current_router_and_temporal_oracles() -> None:
    matrix = json.loads(MATRIX.read_text())
    router = json.loads(ROUTER_MATRIX.read_text())
    temporal = json.loads(TEMPORAL_MATRIX.read_text())

    assert hashlib.sha256(MATRIX.read_bytes()).hexdigest() == MATRIX_SHA256
    assert matrix["version"] == 2
    assert matrix["router_matrix_version"] == 6
    assert matrix["temporal_matrix_version"] == 1
    assert matrix["router_cases"] == router["cases"]
    assert matrix["temporal_cases"] == temporal["cases"]
    assert matrix["current_context"] == temporal["current_context"]
    assert matrix["route_source_comparison"] == router["route_source_comparison"]


def test_live_v2_is_bounded_provider_free_and_contains_split_no_split_sentinels() -> None:
    runner = _runner_module()
    matrix = json.loads(MATRIX.read_text())
    router_by_id = {case["id"]: case for case in matrix["router_cases"]}

    assert len(matrix["router_cases"]) == 17
    assert len(matrix["temporal_cases"]) == 6
    assert runner.MAX_CALLS == 23
    assert runner._budget_upper(matrix) <= runner.PROPOSED_CEILING_USD
    assert runner.PROPOSED_CEILING_USD == 0.04

    assert len(router_by_id["independent-temporal-temporal-split"]["expect"]["routes"]) == 2
    assert len(router_by_id["independent-core-core-split"]["expect"]["routes"]) == 2
    for case_id in (
        "shared-temporal-scope-no-split",
        "shared-predicate-no-split",
        "elliptical-predicate-no-split",
        "shared-event-participants-no-split",
    ):
        assert len(router_by_id[case_id]["expect"]["routes"]) == 1


def test_live_v2_preflight_requires_no_provider_credentials(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    runner = _runner_module()
    monkeypatch.delenv(runner.AUTH_ENV, raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    matrix = runner._preflight(require_live_auth=False)
    assert len(matrix["router_cases"]) + len(matrix["temporal_cases"]) == 23
