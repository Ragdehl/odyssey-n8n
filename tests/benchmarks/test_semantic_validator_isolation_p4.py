"""Fail CI if retired pilot grammar quietly creeps into P4/E2/E3 modules."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _audit():
    path = ROOT / "scripts/audit_semantic_validator_boundaries.py"
    spec = importlib.util.spec_from_file_location("validator_boundary_audit", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.audit()


def test_case_specific_validator_call_sites_are_strictly_quarantined():
    evidence = _audit()
    assert evidence["not_a_global_validator_count"] is True
    assert evidence["P4_product_caller_of_legacy_adapters"] is False
    known = evidence["identified"]
    assert set(known) == {
        "candidate_sequential_contacts",
        "candidate_multi_participant",
        "candidate_scoped_handoff",
        "candidate_continuation_guard",
        "task_core_planner",
    }
    assert known["candidate_continuation_guard"]["product_callers"] == []
    assert known["candidate_scoped_handoff"]["product_callers"] == [
        "odyssey_core/candidate_scoped_planning.py"
    ]
    assert known["candidate_multi_participant"]["product_callers"] == [
        "odyssey_core/candidate_attribution.py",
        "odyssey_core/candidate_coverage.py",
    ]
    assert known["candidate_sequential_contacts"]["product_callers"] == [
        "odyssey_core/candidate_attribution.py",
        "odyssey_core/candidate_coverage.py",
    ]
    assert known["task_core_planner"]["product_callers"] == [
        "odyssey_apps/tasks/__init__.py",
        "odyssey_runtime/composition.py",
    ]


def test_p4_source_compiler_does_not_import_legacy_grammar_or_task_plan_rewriter():
    for name in (
        "odyssey_runtime/whole_source_light.py",
        "odyssey_core/whole_source_compiler.py",
        "odyssey_core/whole_source_readback.py",
    ):
        text = (ROOT / name).read_text()
        for forbidden in (
            "candidate_sequential_contacts",
            "candidate_multi_participant",
            "candidate_scoped_handoff",
            "candidate_continuation_guard",
            "TaskCorePlanner",
            "candidate_coverage_factory",
        ):
            assert forbidden not in text, (name, forbidden)
