"""Fail-closed manual next-day resume of independent reviews; no live Codex."""

import json
import subprocess

import pytest

from scripts import odyssey_agent_cycle as cycle


def synthetic_repo(path):
    path.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "fixture@invalid.example"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Disposable"], cwd=path, check=True)
    (path / "file.txt").write_text("base")
    subprocess.run(["git", "add", "file.txt"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=path, check=True)
    return path


def make_paused(monkeypatch, tmp_path):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "mem_available", lambda: 1600)
    repo = synthetic_repo(tmp_path / "repo")
    monkeypatch.setattr(cycle, "workspace", lambda *_: repo)
    monkeypatch.setattr(cycle, "safe_worktree", lambda *_: None)
    job = "review-pause-fixture"
    folder = cycle.job_path(job)
    folder.mkdir(parents=True)
    (folder / "brief.md").write_text("Check the safe review checkpoint.")
    cycle.atomic_json(
        folder / "status.json",
        {
            "phase": "planned",
            "baseline_commit": "a" * 40,
            "ready_for_user": False,
            "gate": {},
            "reviews": {},
            "acceptance_profile": "product",
        },
    )
    called = []

    def fake_codex(role, _prompt, _dest, _evidence, *, read_only):
        called.append(role)
        if role == "quality":
            raise cycle.DailyBudgetPause("Daily reported-token pacing exhausted")
        if read_only:
            return {"verdict": {"verdict": "pass", "findings": []}}
        return {"role": role}

    monkeypatch.setattr(cycle, "codex", fake_codex)
    monkeypatch.setattr(cycle, "deterministic_gates", lambda *_: {"offline": {"pass": True}})
    state = cycle.run(job, 2, live=True)
    assert state["phase"] == "paused_daily_budget"
    assert state["ready_for_user"] is False
    assert state["resume_checkpoint"]["next_role"] == "quality"
    assert called == ["builder", "generality", "quality"]
    assert list(state["reviews"]) == ["generality"]
    assert (folder / "round-1" / "generality-completed.json").exists()
    return repo, job, called


def test_manual_resume_skips_successful_builder_gate_and_reviews(monkeypatch, tmp_path):
    _repo, job, called = make_paused(monkeypatch, tmp_path)
    resumed_roles = []
    monkeypatch.setattr(
        cycle,
        "deterministic_gates",
        lambda *_: pytest.fail("Never repeat existing deterministic gates"),
    )

    def reviewer(role, *_args, read_only):
        assert read_only is True
        resumed_roles.append(role)
        return {"verdict": {"verdict": "pass", "findings": []}}

    monkeypatch.setattr(cycle, "codex", reviewer)
    result = cycle.run(job, 2, live=True, resume=True)
    assert result["phase"] == "reviewed_browser_gate_pending"
    assert result["ready_for_user"] is False
    assert resumed_roles == ["quality", "testing", "performance"]
    assert called == ["builder", "generality", "quality"]
    assert list(result["reviews"]) == list(cycle.REVIEW_ROLES)


@pytest.mark.parametrize("tamper", ["code", "artifact", "role", "gate", "phase", "round"])
def test_manual_resume_rejects_stale_or_incomplete_checkpoint(monkeypatch, tmp_path, tamper):
    repo, job, _ = make_paused(monkeypatch, tmp_path)
    state = cycle.load(job)
    if tamper == "code":
        (repo / "file.txt").write_text("changed")
    elif tamper == "artifact":
        artifact = cycle.job_path(job) / "round-1" / "generality-completed.json"
        data = json.loads(artifact.read_text())
        data["verdict"]["verdict"] = "fail"
        artifact.write_text(json.dumps(data))
    elif tamper == "role":
        state["resume_checkpoint"]["next_role"] = "performance"
    elif tamper == "gate":
        state["gate"] = {"offline": {"pass": False}}
    elif tamper == "phase":
        state["phase"] = "blocked"
    else:
        state["resume_checkpoint"]["round"] = 2
    if tamper not in {"code", "artifact"}:
        cycle.atomic_json(cycle.job_path(job) / "status.json", state)
    monkeypatch.setattr(
        cycle, "codex", lambda *_args, **_kwargs: pytest.fail("Never call model on stale resume")
    )
    with pytest.raises(cycle.CycleError):
        cycle.run(job, 2, live=True, resume=True)


def test_resume_never_restarts_or_promotes_other_blocked_jobs(monkeypatch, tmp_path):
    monkeypatch.setattr(cycle, "STATE", tmp_path)
    folder = cycle.job_path("old-blocked-job")
    folder.mkdir()
    cycle.atomic_json(folder / "status.json", {"phase": "blocked_insufficient_review_budget"})
    with pytest.raises(cycle.CycleError, match="no paused"):
        cycle.run("old-blocked-job", 2, live=True, resume=True)


def test_resume_rejects_lower_round_count_without_state_modification(monkeypatch, tmp_path):
    _, job, _ = make_paused(monkeypatch, tmp_path)
    state = cycle.load(job)
    state["round"] = 2
    state["resume_checkpoint"]["round"] = 2
    cycle.atomic_json(cycle.job_path(job) / "status.json", state)
    saved = (cycle.job_path(job) / "status.json").read_bytes()
    with pytest.raises(cycle.CycleError, match="exceeds"):
        cycle.run(job, 1, live=True, resume=True)
    assert (cycle.job_path(job) / "status.json").read_bytes() == saved


def test_review_refuses_daily_checkpoint_if_reviewer_changed_code(monkeypatch, tmp_path):
    repo, job, called = make_paused(monkeypatch, tmp_path)
    # A pause must not hide a mutation in a supposedly read-only reviewer.
    import shutil

    state = cycle.load(job)
    state.update(phase="planned", reviews={}, gate={}, review_artifacts={})
    shutil.rmtree(cycle.job_path(job) / "round-1")
    called.clear()
    cycle.atomic_json(cycle.job_path(job) / "status.json", state)

    def malicious(role, *_args, read_only):
        called.append(role)
        if role == "quality":
            (repo / "existing-mutation.txt").write_text("changed")
            raise cycle.DailyBudgetPause("quota refused")
        return {"verdict": {"verdict": "pass", "findings": []}} if read_only else {"role": role}

    monkeypatch.setattr(cycle, "codex", malicious)
    result = cycle.run(job, 1, live=True)
    assert result["phase"] == "blocked"
    assert result["ready_for_user"] is False
    assert "no safe resume" in result["last_error"]
