"""Provider-free freeze for the disposable-E2E Router/Core follow-up gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from benchmarks.router_core_followup_live_v3 import run_live

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "benchmarks/router_core_followup_live_v3/matrix.json"


def test_followup_v3_matrix_is_frozen_and_bounded() -> None:
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    assert hashlib.sha256(MATRIX.read_bytes()).hexdigest() == run_live.MATRIX_SHA256
    assert matrix["version"] == 3
    assert len(matrix["router_cases"]) == 5
    assert len(matrix["core_cases"]) == 3
    assert len(matrix["sol_cases"]) == 1
    assert run_live.MAX_CALLS == 9
    assert run_live._budget_upper(matrix) < run_live.PROPOSED_CEILING_USD == 0.31


def test_followup_v3_repeats_split_but_preserves_dependent_no_split_sentinels() -> None:
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    router = matrix["router_cases"]
    for case in router[:3]:
        assert case["source"] == "Ayer vi a Ana y hoy vi a Luis."
        assert case["expect"]["routes"] == [
            ["temporal", "Ayer vi a Ana"],
            ["temporal", "y hoy vi a Luis."],
        ]
    assert len(router[3]["expect"]["routes"]) == 1
    assert len(router[4]["expect"]["routes"]) == 1


def test_followup_v3_core_scope_targets_the_disposable_e2e_failure_and_regressions() -> None:
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    by_id = {case["id"]: case for case in matrix["core_cases"]}
    assert by_id["C1-day-exact-datetime"]["expect_anchors"] == ["2026-10-05T15:35:00+02:00"]
    assert "mis hijos" in by_id["C2-bea-children-date"]["must_contain"]
    assert by_id["C3-entity-exact-datetime"]["expect_anchors"] == ["2026-10-05T15:35:00+02:00"]
    sol = matrix["sol_cases"]
    assert [case["id"] for case in sol] == ["S1-day-exact-datetime-fallback-contract"]
    assert sol[0]["source"] == "Mañana a las 15:35 viene el fontanero."
    assert sol[0]["expect_anchors"] == ["2026-10-05T15:35:00+02:00"]


def test_followup_v3_preflight_never_needs_provider_authority(monkeypatch) -> None:
    monkeypatch.delenv(run_live.AUTH_ENV, raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert run_live.run(preflight_only=True) == 0
