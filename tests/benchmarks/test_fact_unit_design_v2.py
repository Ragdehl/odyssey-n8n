"""Approved v2 event/source-oracle invariants, alongside immutable v1 tests.

These are human semantic design obligations, not a live Router/Luna pass.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "benchmarks/application_router/fact_units_v1.design.json"
NEW = ROOT / "benchmarks/application_router/fact_units_v2.design.json"


def _cases(path: Path):
    """Read one non-executable design matrix without trusting its semantics."""
    return json.loads(path.read_text(encoding="utf-8"))


def test_approved_v2_adds_a_new_oracle_without_rewriting_v1_history() -> None:
    """Source design versioning preserves the original 26-case safety matrix."""
    old, new = _cases(OLD), _cases(NEW)
    assert old["version"] == 1 and new["version"] == 2
    assert old["status"] == new["status"] == "non_executable_design_oracle"
    assert len(old["cases"]) == 26 and len(new["cases"]) == 27
    assert sum(len(c["expected_units"]) for c in old["cases"]) == 56
    assert sum(len(c["expected_units"]) for c in new["cases"]) == 58
    assert [c["id"] for c in new["cases"]] == [f"F{i:02d}" for i in range(1, 28)]
    before = {c["id"]: c for c in old["cases"]}
    after = {c["id"]: c for c in new["cases"]}
    assert before["F14"]["expected_units"] != after["F14"]["expected_units"]
    assert all(after[i] == before[i] for i in before if i != "F14")


def test_single_shared_event_has_both_source_names_without_claiming_togetherness() -> None:
    """One source candidate can independently link multiple canonical targets."""
    cases = {c["id"]: c for c in _cases(NEW)["cases"]}
    together = cases["F14"]
    assert together["source"] == "Ayer hablé con Eric y Luis. Mañana iré al cine con él."
    assert len(together["expected_units"]) == 2
    event, pending = together["expected_units"]
    assert event["kind"] == "occurrence" and event["state"] == "candidate"
    assert event["source_anchors"] == ["Ayer hablé con Eric y Luis"]
    assert {tuple(scope.values()) for scope in event["scoped_source"]} >= {
        ("participants", "Eric y Luis"),
    }
    assert pending["source_anchors"] == ["Mañana iré al cine con él"]
    assert pending["state"] == "ambiguous_identity"
    assert "simultaneidad" in together["safety_oracle"]


def test_explicit_sequence_retains_two_independent_facts_and_unresolved_pronoun() -> None:
    """Splitting a distinct temporal event is not the same as splitting each name."""
    cases = {c["id"]: c for c in _cases(NEW)["cases"]}
    serial = cases["F27"]
    assert "después con Luis" in serial["source"]
    assert len(serial["expected_units"]) == 3
    assert [u["source_anchors"] for u in serial["expected_units"]] == [
        ["Eric"],
        ["Luis"],
        ["Mañana iré al cine con él"],
    ]
    assert serial["expected_units"][2]["state"] == "ambiguous_identity"
    assert len(cases["F09"]["expected_units"]) == 2  # independently true properties
    assert len(cases["F10"]["expected_units"]) == 1  # one relationship
    assert len(cases["F11"]["expected_units"]) == 2  # same shopping transaction, two items
    assert len(cases["F17"]["expected_units"]) == 2  # two explicit negatives
    assert len(cases["F20"]["expected_units"]) == 2  # two independent conditions
