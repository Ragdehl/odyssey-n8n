"""Agent supervisor contracts: bounded, opt-in, persistent, fail closed."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/odyssey_agent_cycle.py"
spec = importlib.util.spec_from_file_location("odyssey_agent_cycle", SCRIPT)
assert spec and spec.loader
cycle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cycle)


def test_pilot_has_one_builder_four_independent_read_only_reviewers_and_schema():
    assert cycle.REVIEW_ROLES == ("generality", "quality", "testing", "performance")
    assert all(
        (cycle.ROLES / (role + ".md")).is_file() for role in ("builder", *cycle.REVIEW_ROLES)
    )
    schema = json.loads(cycle.SCHEMA.read_text())
    assert schema["properties"]["verdict"]["enum"] == ["pass", "fail", "blocked"]
    assert schema["additionalProperties"] is False
    for role in cycle.REVIEW_ROLES:
        assert "READ-ONLY" in (cycle.ROLES / (role + ".md")).read_text()


def test_plan_dry_run_is_persistent_does_not_create_worktree_and_cannot_reuse_id(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "check_repository", lambda: None)
    monkeypatch.setattr(
        cycle,
        "running",
        lambda args, **_kw: type(
            "Run", (), {"returncode": 0, "stdout": "" if "status" in args else "a" * 40}
        )(),
    )
    brief = cycle.ROLES / "pilot-p4.md"
    report = cycle.plan(brief, "agent-dry-run-1")
    assert report["phase"] == "planned"
    assert report["ready_for_user"] is False
    assert not (cycle.ROOT.parent / "odyssey-agent-work-agent-dry-run-1").exists()
    assert cycle.load("agent-dry-run-1") == report
    with pytest.raises(cycle.CycleError, match="already exists"):
        cycle.plan(brief, "agent-dry-run-1")


@pytest.mark.parametrize("job", ["../prod", "x", "WITH-SPACES", "odyssey-prod-release"])
def test_untrusted_job_names_cannot_escape_state_directory(job):
    with pytest.raises(cycle.CycleError):
        cycle.job_path(job)


def test_untrusted_feature_brief_outside_checkout_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(cycle, "check_repository", lambda: None)
    outside = tmp_path / "personal.md"
    outside.write_text("# All private data is not a feature brief" * 3)
    with pytest.raises(cycle.CycleError, match="inside this source checkout"):
        cycle.plan(outside, "safe-job-one")


def test_live_never_runs_implicitly(monkeypatch):
    with pytest.raises(cycle.CycleError, match="--live"):
        cycle.run("arbitrary", 2, live=False)


def test_bounded_repair_and_external_browser_blocks_do_not_claim_product_ready(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "mem_available", lambda: 2100)
    monkeypatch.setattr(cycle, "workspace", lambda job, sha: tmp_path / "isolated")
    monkeypatch.setattr(cycle, "safe_worktree", lambda path, job: None)
    monkeypatch.setattr(
        cycle, "running", lambda *_args, **_kw: type("Git", (), {"returncode": 0, "stdout": ""})()
    )
    workspace = tmp_path / "isolated"
    workspace.mkdir()
    job = "safe-team-job"
    path = cycle.job_path(job)
    path.mkdir(parents=True)
    (path / "brief.md").write_text("A very long standalone feature brief; enough text to run.")
    report = {
        "phase": "planned",
        "baseline_commit": "a" * 40,
        "last_error": None,
        "round": 0,
        "ready_for_user": False,
        "reviews": {},
        "gate": {},
    }
    cycle.atomic_json(path / "status.json", report)
    roles = []

    def mock_codex(role, prompt, _dest, _evidence, *, read_only):
        roles.append((role, read_only))
        return {"verdict": {"verdict": "pass", "findings": []}} if read_only else {"role": role}

    monkeypatch.setattr(cycle, "codex", mock_codex)
    monkeypatch.setattr(
        cycle,
        "deterministic_gates",
        lambda _dest, _evidence: {"cross_surface": {"pass": True}},
    )
    response = cycle.run(job, 2, live=True)
    assert response["phase"] == "reviewed_browser_gate_pending"
    assert response["ready_for_user"] is False
    assert response["round"] == 1
    assert roles == [("builder", False)] + [(x, True) for x in cycle.REVIEW_ROLES]


def test_a_blocked_independent_reviewer_stops_repair_loop(monkeypatch, tmp_path):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "mem_available", lambda: 1900)
    monkeypatch.setattr(cycle, "workspace", lambda _job, _sha: tmp_path / "isolated")
    monkeypatch.setattr(cycle, "safe_worktree", lambda _dest, _job: None)
    monkeypatch.setattr(
        cycle, "running", lambda *_args, **_kw: type("Git", (), {"returncode": 0, "stdout": ""})()
    )
    (tmp_path / "isolated").mkdir()
    job = "blocked-team-job"
    path = cycle.job_path(job)
    path.mkdir(parents=True)
    (path / "brief.md").write_text("A meaningful feature brief for safe automation.")
    cycle.atomic_json(
        path / "status.json",
        {
            "phase": "planned",
            "baseline_commit": "b" * 40,
            "ready_for_user": False,
            "reviews": {},
            "gate": {},
        },
    )
    roles = []

    def reviewer(role, *_args, **kwargs):
        roles.append(role)
        if role == "builder":
            return {"role": role}
        return {"verdict": {"verdict": "blocked" if role == "testing" else "pass"}}

    monkeypatch.setattr(cycle, "codex", reviewer)
    monkeypatch.setattr(cycle, "deterministic_gates", lambda *_: {"cross_surface": {"pass": True}})
    result = cycle.run(job, 3, live=True)
    assert result["phase"] == "blocked_external_evidence"
    assert result["round"] == 1
    assert roles.count("builder") == 1
    assert not result["ready_for_user"]


def test_chatgpt_handoff_anchors_committed_feature_and_preserves_original_author(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "check_repository", lambda: None)
    previous, feature = "a" * 40, "b" * 40

    def git_call(args, **_kwargs):
        if "status" in args:
            value = ""
        elif "diff" in args:
            value = "odyssey_core/source_provenance.py\n"
        elif "rev-parse" in args and "HEAD" in args:
            value = feature + "\n"
        else:
            value = previous + "\n"
        return type("Git", (), {"returncode": 0, "stdout": value})()

    monkeypatch.setattr(cycle, "running", git_call)
    state = cycle.plan(
        cycle.ROLES / "pilot-p4.md",
        "p4-chatgpt-handoff",
        implemented_by="chatgpt",
        against=previous,
    )
    assert state["implemented_by"] == "chatgpt"
    assert state["baseline_commit"] == feature
    assert state["review_base"] == previous
    assert state["feature_commit"] == feature
    assert state["phase"] == "planned"


@pytest.mark.parametrize("bad", ["HEAD~1", "--revision", "../prod", "0123", "foo"])
def test_chatgpt_handoff_rejects_untrusted_git_revision(tmp_path, monkeypatch, bad):
    monkeypatch.setattr(cycle, "check_repository", lambda: None)
    monkeypatch.setattr(
        cycle,
        "running",
        lambda args, **_kw: type(
            "Git", (), {"returncode": 0, "stdout": "" if "status" in args else "b" * 40}
        )(),
    )
    with pytest.raises(cycle.CycleError, match="literal Git SHA"):
        cycle.plan(
            cycle.ROLES / "pilot-p4.md", "p4-bad-handoff", implemented_by="chatgpt", against=bad
        )


def test_chatgpt_first_iteration_skips_codex_builder_but_same_reviewers_run(monkeypatch, tmp_path):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "mem_available", lambda: 1800)
    monkeypatch.setattr(cycle, "workspace", lambda _job, _sha: tmp_path / "isolated")
    monkeypatch.setattr(cycle, "safe_worktree", lambda _path, _job: None)
    monkeypatch.setattr(
        cycle, "running", lambda *_args, **_kw: type("Git", (), {"returncode": 0, "stdout": ""})()
    )
    (tmp_path / "isolated").mkdir()
    job = "p4-external-author"
    state_root = cycle.job_path(job)
    state_root.mkdir(parents=True)
    (state_root / "brief.md").write_text(
        "Check a ChatGPT-authored feature without additional Builder usage."
    )
    cycle.atomic_json(
        state_root / "status.json",
        {
            "phase": "planned",
            "baseline_commit": "b" * 40,
            "review_base": "a" * 40,
            "feature_commit": "b" * 40,
            "implemented_by": "chatgpt",
            "ready_for_user": False,
            "reviews": {},
            "gate": {},
        },
    )
    called = []

    def reviewer(role, instructions, *_args, **_kwargs):
        called.append((role, instructions))
        return {"verdict": {"verdict": "pass", "findings": []}}

    monkeypatch.setattr(cycle, "codex", reviewer)
    monkeypatch.setattr(cycle, "deterministic_gates", lambda *_: {"cross_surface": {"pass": True}})
    report = cycle.run(job, 2, live=True)
    assert report["phase"] == "reviewed_browser_gate_pending"
    assert report["ready_for_user"] is False
    assert [role for role, _ in called] == list(cycle.REVIEW_ROLES)
    assert all("git diff" in prompt for _role, prompt in called)
    assert (state_root / "round-1/handoff.json").is_file()
    assert "builder.md" not in [p.name for p in (state_root / "round-1").iterdir()]


def test_chatgpt_failed_review_invokes_builder_only_on_second_round(monkeypatch, tmp_path):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "mem_available", lambda: 1800)
    monkeypatch.setattr(cycle, "workspace", lambda _job, _sha: tmp_path / "isolated")
    monkeypatch.setattr(cycle, "safe_worktree", lambda _path, _job: None)
    monkeypatch.setattr(
        cycle, "running", lambda *_args, **_kw: type("Git", (), {"returncode": 0, "stdout": ""})()
    )
    (tmp_path / "isolated").mkdir()
    job = "p4-external-repair"
    state_root = cycle.job_path(job)
    state_root.mkdir(parents=True)
    (state_root / "brief.md").write_text(
        "Check a ChatGPT-authored change and fix it if a reviewer fails."
    )
    cycle.atomic_json(
        state_root / "status.json",
        {
            "phase": "planned",
            "baseline_commit": "b" * 40,
            "review_base": "a" * 40,
            "feature_commit": "b" * 40,
            "implemented_by": "chatgpt",
            "ready_for_user": False,
            "reviews": {},
            "gate": {},
        },
    )
    calls = []

    def codex_mock(role, *_args, **_kwargs):
        calls.append(role)
        return (
            {"role": "builder"}
            if role == "builder"
            else {
                "verdict": {
                    "verdict": "fail"
                    if len(calls) <= len(cycle.REVIEW_ROLES) and role == "generality"
                    else "pass",
                    "findings": [],
                }
            }
        )

    monkeypatch.setattr(cycle, "codex", codex_mock)
    monkeypatch.setattr(cycle, "deterministic_gates", lambda *_: {"cross_surface": {"pass": True}})
    result = cycle.run(job, 2, live=True)
    assert result["phase"] == "reviewed_browser_gate_pending"
    assert calls == [*cycle.REVIEW_ROLES, "builder", *cycle.REVIEW_ROLES]
    assert result["round"] == 2
