"""Deterministic evidence emphasis and safe incremental audit inheritance."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import odyssey_agent_cycle as cycle
from scripts import odyssey_review_incremental as inc
from scripts import odyssey_review_scope as scope
from tests.runtime.test_agent_reviewer_evidence import fixture, passing_gates


@pytest.mark.parametrize(
    "paths",
    [
        ("odyssey_core/source_bound_dependency.py",),
        ("odyssey_runtime/whole_source_light.py",),
        ("scripts/odyssey_agent_cycle.py",),
        ("config/note-schema.json",),
        ("tests/core/test_e3_mutation.py",),
        ("odyssey_web/identity.js",),
    ],
)
def test_fundamental_changes_invalidate_all_roles(paths):
    assert scope.fundamental(paths)
    assert scope.invalidated_roles(paths) == scope.REVIEW_ROLES
    for role in scope.REVIEW_ROLES:
        assert scope.specialist_paths(role, paths) == paths


def test_test_only_correction_only_reruns_testing_without_claiming_new_passes():
    assert scope.invalidated_roles(("tests/runtime/test_ordinary_feature.py",)) == ("testing",)
    assert (
        scope.invalidated_roles(("tests/runtime/test_ordinary_feature.py", "odyssey_core/app.py"))
        == scope.REVIEW_ROLES
    )
    assert scope.invalidated_roles(("docs/architecture/report.md",)) == ("generality", "quality")
    assert scope.invalidated_roles(("docs/architecture/example-contract.md",)) == scope.REVIEW_ROLES


def test_role_evidence_has_complete_manifest_and_specialized_diff(tmp_path):
    repo, state = fixture(tmp_path)
    source = repo / "scripts/unrelated-feature.py"
    source.write_text("feature = 'new capability'\n")
    (repo / "tests/runtime/test_agent_cycle_supervisor.py").write_text(
        "def test_new(): assert True\n"
    )
    subprocess_run = __import__("subprocess").run
    subprocess_run(["git", "add", "."], cwd=repo, check=True)
    packet_general = cycle.bounded_reviewer_evidence(
        repo, state, passing_gates(), role="generality"
    )
    packet_testing = cycle.bounded_reviewer_evidence(repo, state, passing_gates(), role="testing")
    assert "scripts/unrelated-feature.py" in packet_general
    assert "test_agent_cycle_supervisor.py" in packet_general  # Complete manifest.
    assert "+def test_new" not in packet_general
    assert "+def test_new" in packet_testing
    assert "scripts/unrelated-feature.py" in packet_testing  # Still manifest-accessible.
    assert "Specialist-focused Git diff" in packet_general
    with pytest.raises(cycle.CycleError, match="Unknown"):
        cycle.bounded_reviewer_evidence(repo, state, passing_gates(), role="builder")


def audited_fixture(tmp_path: Path):
    job = "previous-audit"
    root = tmp_path / "evidence"
    review_dir = root / job / "round-1"
    review_dir.mkdir(parents=True)
    records = {}
    artifacts = {}
    for role in scope.REVIEW_ROLES:
        record = {"verdict": "pass", "summary": "Independent specialist PASS", "findings": []}
        file = review_dir / f"{role}-completed.json"
        file.write_text(json.dumps({"role": role, "verdict": record}))
        records[role] = record
        artifacts[role] = str(file)
    prior = {
        "job": job,
        "phase": "reviewed_browser_gate_pending",
        "round": 1,
        "feature_commit": "a" * 40,
        "audit_source_sha256": "b" * 64,
        "reviews": records,
        "review_artifacts": artifacts,
    }
    return root, prior


def test_prior_independent_pass_receipts_are_verified_and_tamper_fails(tmp_path):
    root, prior = audited_fixture(tmp_path)
    hashes = inc.audited_prior(prior, root, "previous-audit")
    assert set(hashes) == set(scope.REVIEW_ROLES)
    assert all(len(sha) == 64 for sha in hashes.values())
    assert inc.inherited_roles(prior, {"changed_paths": ["tests/runtime/test_safe.py"]}) == (
        "generality",
        "quality",
        "performance",
    )
    assert inc.inherited_roles(prior, {"changed_paths": ["odyssey_core/identity.py"]}) == ()
    bad = deepcopy(prior)
    bad["reviews"]["quality"]["verdict"] = "fail"
    with pytest.raises(inc.IncrementalReviewError):
        inc.audited_prior(bad, root, "previous-audit")
    bad = deepcopy(prior)
    bad["review_artifacts"]["quality"] = str(root / "external.json")
    with pytest.raises(inc.IncrementalReviewError):
        inc.audited_prior(bad, root, "previous-audit")
    (root / "previous-audit" / "round-1" / "testing-completed.json").write_text(
        '{"role":"testing","verdict":{"verdict":"fail"}}'
    )
    with pytest.raises(inc.IncrementalReviewError):
        inc.audited_prior(prior, root, "previous-audit")


def test_incomplete_prior_and_unscoped_delta_cannot_be_inherited(tmp_path):
    root, prior = audited_fixture(tmp_path)
    prior["phase"] = "blocked_repair_budget"
    with pytest.raises(inc.IncrementalReviewError):
        inc.audited_prior(prior, root, "previous-audit")
    with pytest.raises(inc.IncrementalReviewError):
        inc.inherited_roles(prior, {"changed_paths": []})


def test_incremental_plan_is_pinned_to_prior_audited_worktree(tmp_path, monkeypatch):
    import subprocess

    repo, data = fixture(tmp_path)
    previous = "previous-audit"
    base = data["baseline_commit"]
    old_dest = tmp_path / ("odyssey-agent-work-" + previous)
    subprocess.run(
        ["git", "worktree", "add", "-q", "-b", "agent/" + previous, str(old_dest), base],
        cwd=repo,
        check=True,
    )
    root, prior = audited_fixture(tmp_path)
    prior["feature_commit"] = base
    prior["acceptance_profile"] = "product"
    prior["implemented_by"] = "chatgpt"
    prior["audit_source_sha256"] = cycle.review_snapshot(old_dest).hex()
    prior["worktree"] = str(old_dest)
    (root / previous / "status.json").write_text(json.dumps(prior))
    monkeypatch.setattr(cycle, "ROOT", repo)
    monkeypatch.setattr(cycle, "STATE", root)
    test = repo / "tests/runtime/test_agent_cycle_supervisor.py"
    test.write_text(test.read_text() + "\ndef test_delta(): assert 3 == 3\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "test-only correction"], cwd=repo, check=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    plan = cycle.verified_incremental_plan(previous, base, head, "product")
    assert plan["rerun_roles"] == ["testing"]
    assert plan["inherited_roles"] == ["generality", "quality", "performance"]
    assert plan["previous_snapshot_sha256"] == prior["audit_source_sha256"]
    (old_dest / "tests/runtime/test_agent_cycle_supervisor.py").write_text("# tampered")
    with pytest.raises(cycle.CycleError, match="snapshot"):
        cycle.verified_incremental_plan(previous, base, head, "product")
