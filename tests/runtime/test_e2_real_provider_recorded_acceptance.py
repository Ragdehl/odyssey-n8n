"""Real GPT-6/5.6 responses, replayed FREE through full isolated Core Writer.

The fixture contains synthetic user phrases only. No credentials or provider
requests occur in these tests; these prevent regression on the live E2 review.
"""

import json
from pathlib import Path

import pytest

from benchmarks.e2_shared_context_live.replay_recorded import replay_case

_ROOT = Path(__file__).resolve().parents[2]
_CASES = json.loads(
    (_ROOT / "benchmarks/e2_shared_context_live/postfix_recorded_replies_v1.json").read_text()
)["cases"]


@pytest.mark.parametrize("case", _CASES, ids=[c["case"] for c in _CASES])
def test_replay_postfix_real_provider_output_in_canonical_writer(case):
    outcome = replay_case(case)
    assert outcome["status"] == "completed", outcome
    assert outcome["provider_calls"] == outcome["recorded_calls"]
    assert outcome["changed_paths"]
    assert outcome["invented_clock"] is False
    if case["case"] != "third_party":
        assert outcome["saved_qualifier"] is True
    if case["case"] == "two_same_day":
        assert outcome["changed_paths"] == ["calendar/days/2026-10-15.md"]
    if case["case"] == "third_party":
        assert "fixture-person-user" not in str(outcome)
