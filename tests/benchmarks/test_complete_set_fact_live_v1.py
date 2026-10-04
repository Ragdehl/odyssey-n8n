"""Provider-free freeze for the complete-set fact participant live gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from benchmarks.complete_set_fact_live_v1 import run_live

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "benchmarks/complete_set_fact_live_v1/matrix.json"
RUNNER = ROOT / "benchmarks/complete_set_fact_live_v1/run_live.py"


def test_complete_set_gate_is_frozen_bounded_and_no_mutation() -> None:
    """Pin the four-call matrix and keep the runner outside persistence execution."""
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    assert hashlib.sha256(MATRIX.read_bytes()).hexdigest() == run_live.MATRIX_SHA256
    assert len(matrix["luna_cases"]) == 3
    assert len(matrix["sol_cases"]) == 1
    assert run_live.MAX_CALLS == 4
    assert run_live._budget_upper(matrix) < run_live.PROPOSED_CEILING_USD == 0.31
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


def test_complete_set_gate_covers_set_time_and_singular_regression() -> None:
    """Require both complete-set shapes and one prior singular relationship behavior."""
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    luna = matrix["luna_cases"]
    assert [case["expect_extent"] for case in luna] == [
        "complete_set",
        "complete_set",
        "one_member",
    ]
    assert luna[0]["phrase"] == "mis hijos"
    assert luna[1]["expect_anchors"] == ["2026-10-05T15:35:00+02:00"]
    assert "mi hijo al que le gusta el fútbol" == luna[2]["phrase"]
    assert matrix["sol_cases"][0]["expect_extent"] == "complete_set"


def test_raw_extent_recognizes_luna_and_sol_contracts() -> None:
    """Inspect only declared semantic scope, never infer the member set in the gate."""
    luna = json.dumps(
        {
            "kind": "identity",
            "text": "mis hijos",
            "identity": {"candidate_scope": {"extent": "complete_set"}},
        }
    )
    sol = json.dumps(
        {
            "mention": "mis hijos",
            "selection": {"relational_reference": {"members": "complete_set"}},
        }
    )
    singular = json.dumps(
        {
            "kind": "identity",
            "text": "mi hijo al que le gusta el fútbol",
            "identity": {"candidate_scope": {"extent": "one_member"}},
        },
        ensure_ascii=False,
    )
    assert run_live._raw_extent(luna, "mis hijos") == "complete_set"
    assert run_live._raw_extent(sol, "mis hijos") == "complete_set"
    assert run_live._raw_extent(singular, "mi hijo al que le gusta el fútbol") == "one_member"


def test_complete_set_preflight_needs_no_provider_authority(monkeypatch) -> None:
    """Allow local budget/hash verification without credentials or live authorization."""
    monkeypatch.delenv(run_live.AUTH_ENV, raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert run_live.run(preflight_only=True) == 0
