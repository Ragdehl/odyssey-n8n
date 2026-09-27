"""Provider-free checks for the successor membership-anchor Luna gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.semantic_set_planner.v9_gate import (
    MAX_COST_USD,
    MAX_PROVIDER_CALLS,
    PLANNER_ORDER,
    SELECTOR_ORDER,
    load_v9_registry,
    load_v9_selector_registry,
    v9_preflight,
)

ROOT = Path(__file__).resolve().parents[2]


def test_v9_reuses_exact_v8_inputs_and_recalculates_the_successor_ceiling() -> None:
    """Freeze the revised-prompt gate to the exact prior cases, oracles, and selector rows."""
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    cases, oracles = load_v9_registry()
    selector_cases, selector_oracles = load_v9_selector_registry()

    preflight = v9_preflight(schema, cases)

    assert preflight["gate_version"] == "9.0.0"
    assert preflight["planner_case_order"] == PLANNER_ORDER
    assert preflight["selector_case_order"] == SELECTOR_ORDER
    assert preflight["maximum_provider_calls"] == MAX_PROVIDER_CALLS == 25
    assert preflight["conservative_no_cache_maximum_usd"] == str(MAX_COST_USD) == "0.41144"
    assert preflight["model"] == "gpt-5.6-luna"
    assert preflight["reasoning"] == "low"
    assert preflight["retries"] == 0
    assert oracles["SSET02"]["collection_subject"] == "query"
    assert selector_oracles["RELSEL_CONFLICT"]["selected_fact_ids"] == [
        "relational-0",
        "relational-1",
    ]
    assert [case["id"] for case in cases["cases"]] == list(PLANNER_ORDER[: len(cases["cases"])])
    assert [case["id"] for case in selector_cases["cases"]] == list(SELECTOR_ORDER)


def test_v9_runner_has_a_distinct_immutable_path_and_refuses_without_confirmation(
    monkeypatch, tmp_path: Path
) -> None:
    """Ensure the successor cannot overwrite v8 evidence or construct a provider in dry mode."""
    import benchmarks.semantic_set_planner.run_live_v9 as runner

    output_path = tmp_path / runner.OUTPUT_PATH.name
    monkeypatch.setattr(runner, "OUTPUT_PATH", output_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(runner._v8, "OpenAILunaExperimentalPlanner", object())

    with pytest.raises(SystemExit, match="Live v9 planner gate preflight refused"):
        runner.main([])

    assert not output_path.exists()
    assert runner.OUTPUT_PATH.name == "semantic-self-clarification-v9-luna-gate.jsonl"
    assert runner.OUTPUT_PATH.name != "semantic-self-clarification-v8-luna-gate.jsonl"
