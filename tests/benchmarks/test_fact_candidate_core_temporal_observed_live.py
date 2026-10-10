"""Actual GPT-5.6 F14/F27 refusals replayed offline as non-acceptance evidence.

All four provider calls completed; both original and scoped-partial prompt
revisions returned safe ESCALATE rather than the required independent writes.
These are synthetic-only receipts, not Core acceptance and not personal notes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.fact_candidate_core_live import run_temporal_live as gate

ROOT = Path(__file__).resolve().parents[2]
FILES = {
    ("F14", "original"): "20261010T202736Z-F14.json",
    ("F27", "original"): "20261010T202803Z-F27.json",
    ("F14", "opt_in_scoped_partial"): "20261010T203404Z-P-F14.json",
    ("F27", "opt_in_scoped_partial"): "20261010T203640Z-P-F27.json",
}


@pytest.mark.parametrize("case_id,revision", FILES)
def test_actual_gpt56_model_refused_safe_partial_planning(case_id: str, revision: str) -> None:
    evidence = ROOT / "benchmarks/fact_candidate_core_live/results" / FILES[case_id, revision]
    observed = json.loads(evidence.read_text(encoding="utf-8"))
    assert observed["mode"] == "LIVE_CORE_PLAN_ONLY"
    assert observed["case"] == case_id
    assert observed["model"] == "gpt-5.6-luna"
    assert observed.get("prompt_revision", "original") == revision
    assert observed["provider_status"] == "completed"
    assert observed["validation"] == "locally_valid"
    assert observed["outcome"] == "ESCALATE"
    assert observed["action_count"] == 0
    assert observed["may_authorize_writes"] is False
    raw = json.loads(observed["raw_model_response"])["result"]
    assert raw == {
        "outcome": "ESCALATE",
        "actions": None,
        "limitations": None,
        "clarification_code": None,
    }
    assert observed["usage"]["input_tokens"] > 0
    assert observed["usage"]["output_tokens"] > 0


def test_four_core_model_escalations_remain_under_authorized_budget() -> None:
    """Use only frozen token usage at pinned full noncached standard rates."""
    rates = json.loads((ROOT / "config/runtime-pricing-snapshot.json").read_text())["models"][
        "gpt-5.6-luna"
    ]
    previous = gate.BASELINE_ROUTER_AND_CORE_ESTIMATE_USD
    for file_name in FILES.values():
        path = gate.RESULTS / file_name
        saved = json.loads(path.read_text())
        usage = saved["usage"]
        previous += (
            usage["input_tokens"] * rates["input_per_million"]
            + usage["output_tokens"] * rates["output_per_million"]
        ) / 1_000_000
    assert round(previous, 8) == 0.0185276
    assert previous < gate.AUTHORIZED_CUMULATIVE_CAP_USD


def test_original_and_revised_core_receipts_are_accounted_separately(
    monkeypatch, tmp_path: Path
) -> None:
    """Receipt globs must not accidentally count partial runs as original ones."""
    monkeypatch.setattr(gate, "RESULTS", tmp_path)
    for marker, input_tokens in (("", 1000), ("-P", 2000)):
        (tmp_path / f"reviewed{marker}-F14.json").write_text(
            json.dumps(
                {
                    "mode": "LIVE_CORE_PLAN_ONLY",
                    "case": "F14",
                    "usage": {"input_tokens": input_tokens, "output_tokens": 100},
                }
            )
        )
    assert gate._observed_first_cost() < gate._observed_first_cost(partial_guidance=True)
