"""Sentinels: a large architecture change cannot silently shrink regression coverage."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts/odyssey_cross_surface_gate.py"
SPEC = importlib.util.spec_from_file_location("cross_surface_gate", MODULE)
assert SPEC is not None and SPEC.loader is not None
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def test_all_required_cross_surface_groups_have_real_test_files():
    GATE.validate_selection()
    assert set(GATE.GROUPS) == {
        "e5_events_isolated_contract",
        "e2_identity_and_source",
        "task_chat_core",
        "task_ui_and_subtask",
        "work_sessions_shared",
        "e3_retry_and_crashes",
        "canonical_graph_and_notes",
        "runtime_http_and_isolation",
        "workflow_and_web",
        "performance_and_indexes",
    }
    assert len(set(x for group in GATE.GROUPS.values() for x in group)) >= 20
    assert GATE.PENDING_LIVE_GATES
    # The v9 audit revealed blind spots in physical alias/progress/readback and
    # live-campaign acceptance; these tests must run on every later change.
    selected = {case for group in GATE.GROUPS.values() for case in group}
    assert {
        "tests/runtime/test_p4_aliased_prior_person.py",
        "tests/runtime/test_p4_composition_plural_postwrite_loss.py",
        "tests/runtime/test_p4_e4_campaign_oracle.py",
    } <= selected


def test_gate_cannot_falsely_claim_live_browser_or_provider_acceptance():
    source = MODULE.read_text()
    assert '"real_full_product_e2e": False' in source
    assert "proc.returncode == 0 and collected" in source
    assert "frozen_provider_replay" in source


def test_missing_or_removed_test_file_fails_gate_before_running(monkeypatch):
    monkeypatch.setattr(GATE, "GROUPS", {"task_ui_and_subtask": ("tests/does_not_exist.py",)})
    with pytest.raises(ValueError, match="Required test file is missing"):
        GATE.validate_selection()


def test_core_does_not_depend_on_any_app_or_runtime_implementation():
    # No semantic type duplication, no reverse dependency from Core to an App.
    for path in (ROOT / "odyssey_core").rglob("*.py"):
        syntax = ast.parse(path.read_text())
        for node in ast.walk(syntax):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""] if node.level == 0 else []
            else:
                continue
            assert not any(
                module.startswith(("odyssey_apps", "odyssey_runtime")) for module in modules
            ), f"Core reverse dependency: {path}"


def test_known_legacy_narrow_code_is_not_mistaken_for_clean_architecture():
    # Document a real debt rather than making a green gate assert it is gone.
    legacy = (ROOT / "odyssey_core/candidate_coverage.py").read_text()
    assert "candidate_sequential_contacts" in legacy
    scoped = (ROOT / "odyssey_runtime/composition.py").read_text()
    assert '"TASK_SCOPED_OPERATION_UNSUPPORTED"' in scoped
    assert "TaskOperation.START_WORK_SESSION" in scoped


def test_legacy_phrase_guard_cannot_spread_to_new_core_consumers():
    allowed = {
        "candidate_coverage.py",
        "candidate_attribution.py",
        "candidate_sequential_contacts.py",
    }
    uses = {
        path.name
        for path in (ROOT / "odyssey_core").rglob("*.py")
        if "candidate_sequential_contacts" in path.read_text()
    }
    assert uses <= allowed, f"New hardcoded legacy grammar dependency: {uses - allowed}"


def test_product_modules_do_not_import_prototype_benchmarks():
    # Product execution must never execute a script from a regression folder.
    for package in ("odyssey_core", "odyssey_apps", "odyssey_runtime"):
        for path in (ROOT / package).rglob("*.py"):
            syntax = ast.parse(path.read_text())
            for node in ast.walk(syntax):
                if isinstance(node, ast.Import):
                    imported = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and not node.level:
                    imported = [node.module or ""]
                else:
                    continue
                assert not any(
                    name == "benchmarks" or name.startswith("benchmarks.") for name in imported
                ), f"Product imported PoC harness: {path}"


def test_p4_plan_schema_is_not_misrepresented_as_full_tasks_lifecycle():
    from benchmarks.application_router.light_router_poc_20261016.run_poc import FACT

    assert set(FACT["properties"]["kind"]["enum"]) == {"record", "task"}
    # This schema has no Work Session or PARENT_TASK capability semantics, so
    # its physical CREATE receipts are not proof of chat session/subtask support.
    assert "operation" not in FACT["properties"]
    assert "parent_task" not in FACT["properties"]


def test_ci_runs_cross_surface_gate_on_every_pull_request():
    ci = (ROOT / ".github/workflows/python-ci.yml").read_text()
    assert "pull_request:" in ci and "push:" in ci
    assert "python scripts/odyssey_cross_surface_gate.py --output" in ci
    assert ci.index("Cross-surface mutation regression gate") < ci.index("- name: Run tests")


def test_new_product_p4_compiler_keeps_task_plan_ownership_in_core():
    executor = (ROOT / "odyssey_runtime/whole_source_light.py").read_text()
    compiler = (ROOT / "odyssey_core/whole_source_compiler.py").read_text()
    assert "TaskCorePlanner" not in executor
    assert "from odyssey_core.whole_source_compiler import" in executor
    assert "TaskLifecycleGuard" in executor
    assert "RequestPlan" in compiler
    assert "odyssey_apps" not in compiler
