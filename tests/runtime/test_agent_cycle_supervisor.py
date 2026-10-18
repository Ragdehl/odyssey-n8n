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


def test_repairable_review_finding_is_not_suppressed_by_external_blocker(monkeypatch, tmp_path):
    """One reviewer can report code fault and browser dependency at once."""
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "mem_available", lambda: 2000)
    monkeypatch.setattr(cycle, "workspace", lambda _job, _sha: tmp_path / "isolated")
    monkeypatch.setattr(cycle, "safe_worktree", lambda _path, _job: None)
    monkeypatch.setattr(
        cycle,
        "running",
        lambda *_args, **_kw: type("Git", (), {"returncode": 0, "stdout": ""})(),
    )
    (tmp_path / "isolated").mkdir()
    job = "p4-mixed-review"
    state_root = cycle.job_path(job)
    state_root.mkdir(parents=True)
    (state_root / "brief.md").write_text(
        "Test a code issue plus missing external acceptance without user intervention."
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

    def reviewer(role, *_args, **_kwargs):
        calls.append(role)
        if role == "builder":
            return {"role": role}
        if role == "testing":
            findings = (
                [
                    {
                        "severity": "blocking",
                        "path": "test.py",
                        "reason": "Fake regression",
                        "action": "Repair test",
                        "actionability": "repairable",
                    },
                    {
                        "severity": "blocking",
                        "path": "browser",
                        "reason": "No authenticated browser",
                        "action": "External gate",
                        "actionability": "external",
                    },
                ]
                if calls.count("builder") == 0
                else [
                    {
                        "severity": "blocking",
                        "path": "browser",
                        "reason": "No authenticated browser",
                        "action": "External gate",
                        "actionability": "external",
                    },
                ]
            )
            return {"verdict": {"verdict": "blocked", "findings": findings}}
        return {"verdict": {"verdict": "pass", "findings": []}}

    monkeypatch.setattr(cycle, "codex", reviewer)
    monkeypatch.setattr(
        cycle,
        "deterministic_gates",
        lambda *_: {"cross_surface": {"pass": True}},
    )
    state = cycle.run(job, 3, live=True)
    assert calls == [*cycle.REVIEW_ROLES, "builder", *cycle.REVIEW_ROLES]
    assert state["phase"] == "blocked_external_evidence"
    assert state["round"] == 2
    assert not state["ready_for_user"]


def test_supervisor_review_schema_distinguishes_fixable_and_external_findings():
    schema = json.loads(cycle.SCHEMA.read_text())
    item = schema["properties"]["findings"]["items"]
    assert "actionability" in item["required"]
    assert set(item["properties"]["actionability"]["enum"]) == {
        "repairable",
        "external",
    }


def test_cli_blocked_cycle_exits_nonzero_for_shell_orchestration(monkeypatch, tmp_path):
    import sys

    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(
        cycle,
        "run",
        lambda _job, _rounds, _live: {
            "phase": "blocked_external_evidence",
            "ready_for_user": False,
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "odyssey_agent_cycle.py",
            "run",
            "--job",
            "safe-test-job",
            "--live",
        ],
    )
    assert cycle.main() == 3


@pytest.mark.parametrize("author", ["codex", "chatgpt"])
@pytest.mark.parametrize("failure", [None, "exception", "mutation", "verdict"])
def test_incremental_round_status_and_failure_preservation(monkeypatch, tmp_path, author, failure):
    """Real JSON reads expose only guarded completions from the active round."""
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "mem_available", lambda: 2000)
    monkeypatch.setattr(cycle, "workspace", lambda *_: tmp_path / "isolated")
    monkeypatch.setattr(cycle, "safe_worktree", lambda *_: None)
    roles = ("audit-alpha", "audit-beta", "audit-gamma", "audit-delta", "audit-epsilon")
    monkeypatch.setattr(cycle, "REVIEW_ROLES", roles)
    monkeypatch.setattr(cycle, "instructions", lambda *_: "Synthetic audit")
    job = "synthetic-progress"
    root = cycle.job_path(job)
    root.mkdir(parents=True)
    (root / "brief.md").write_text("Synthetic supervisor progress feature.")
    cycle.atomic_json(
        root / "status.json",
        {
            "phase": "planned",
            "baseline_commit": "b" * 40,
            "review_base": "a" * 40,
            "feature_commit": "b" * 40,
            "implemented_by": author,
            "ready_for_user": False,
            "reviews": {},
            "gate": {},
        },
    )
    changed = False

    def git(*_args, **_kwargs):
        return type("Git", (), {"returncode": 0, "stdout": "modified" if changed else ""})()

    monkeypatch.setattr(cycle, "running", git)
    monkeypatch.setattr(cycle, "deterministic_gates", lambda *_: {"offline": {"pass": True}})
    seen = []

    def agent(role, _prompt, _dest, evidence, *, read_only):
        nonlocal changed
        status = cycle.load(job)
        assert not status["ready_for_user"]
        if not read_only:
            assert status["reviews"] == status["review_artifacts"] == status["gate"] == {}
            if status["round"] == 2:
                assert (
                    json.loads((root / "round-1" / (roles[0] + "-completed.json")).read_text())[
                        "verdict"
                    ]["verdict"]
                    == "fail"
                )
            return {"role": role}
        index = roles.index(role)
        assert list(status["reviews"]) == list(roles[:index])
        assert status["round"] == int(evidence.name.split("-")[1])
        for completed in roles[:index]:
            record = json.loads(Path(status["review_artifacts"][completed]).read_text())
            assert record["verdict"] == status["reviews"][completed]
        seen.append((status["round"], index))
        if index == 2 and failure == "exception":
            raise cycle.CycleError("Synthetic reviewer failure")
        if index == 2 and failure == "mutation":
            changed = True
        verdict = "fail" if failure == "verdict" and status["round"] == 1 and index == 0 else "pass"
        return {
            "verdict": {"verdict": verdict, "findings": [{"reason": "synthetic evidence"}]},
            "elapsed_s": 1,
        }

    monkeypatch.setattr(cycle, "codex", agent)
    result = cycle.run(job, 2, live=True)
    assert cycle.load(job) == result
    assert (1, 1) in seen and (1, 2) in seen
    if failure in {"exception", "mutation"}:
        assert result["phase"] == "blocked"
        assert list(result["reviews"]) == list(roles[:2])
        assert roles[2] not in result["review_artifacts"]
    elif failure == "verdict":
        assert result["round"] == 2
        assert all(v["verdict"] == "pass" for v in result["reviews"].values())
        assert (root / "round-1" / (roles[-1] + "-completed.json")).exists()
    assert not result["ready_for_user"]
