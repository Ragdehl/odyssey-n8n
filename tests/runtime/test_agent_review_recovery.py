"""One controlled genuine independent-review retry; never rewrite original evidence."""

import json
import subprocess

import pytest

from scripts import odyssey_agent_cycle as cycle
from tests.runtime.test_agent_daily_review_resume import synthetic_repo


def make_job(monkeypatch, tmp_path):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    repo = synthetic_repo(tmp_path / "repo")
    monkeypatch.setattr(cycle, "safe_worktree", lambda *_: None)
    monkeypatch.setattr(cycle, "tooling_scope_is_safe", lambda *_: True)
    monkeypatch.setattr(cycle, "mem_available", lambda: 1900)
    monkeypatch.setattr(
        cycle.pacing,
        "require_session_headroom",
        lambda *_args, **_kwargs: {"can_start_next_model": True},
    )
    folder = cycle.job_path("quality-recovery-test")
    folder.mkdir(parents=True)
    (folder / "brief.md").write_text("Run a strictly scoped synthetic test-only tooling audit.")
    evidence = folder / "round-1"
    evidence.mkdir()
    refs = {}
    reviews = {}
    for role, verdict in (("generality", "pass"), ("quality", "blocked")):
        receipt = {"role": role, "verdict": {"verdict": verdict, "findings": []}}
        path = evidence / f"{role}-completed.json"
        cycle.atomic_json(path, receipt)
        refs[role] = str(path)
        reviews[role] = receipt["verdict"]
    state = {
        "job": "quality-recovery-test",
        "phase": "blocked_external_evidence",
        "acceptance_profile": "tooling",
        "risk": "normal",
        "round": 1,
        "ready_for_user": False,
        "worktree": str(repo),
        "baseline_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True
        ).strip(),
        "reported_token_budget": 210000,
        "token_usage": {"reported_total": 80000, "sessions": []},
        "gate": {"cross_surface": {"pass": True}},
        "reviews": reviews,
        "review_artifacts": refs,
        "audit_source_sha256": cycle.review_snapshot(repo).hex(),
    }
    cycle.atomic_json(folder / "status.json", state)
    return repo, folder


def test_blocked_last_reviewer_can_recover_without_rebilling_others(monkeypatch, tmp_path):
    repo, folder = make_job(monkeypatch, tmp_path)
    expected = cycle.review_snapshot(repo)
    before = (folder / "round-1/quality-completed.json").read_bytes()
    calls = []
    monkeypatch.setattr(cycle, "deterministic_gates", lambda *_: {"cross_surface": {"pass": True}})

    def audit(role, _prompt, _dest, _evidence, *, read_only):
        assert read_only is True
        assert role == "quality"
        calls.append(role)
        return {
            "reported_tokens": 12000,
            "model": "gpt-6-luna",
            "tier": "economy",
            "routing_reason": "routine",
            "verdict": {"verdict": "pass", "findings": []},
        }

    monkeypatch.setattr(cycle, "codex", audit)
    result = cycle.retry_blocked_review("quality-recovery-test", live=True)
    assert result["phase"] == "reviewed_tooling_ready"
    assert result["ready_for_user"] is True
    assert calls == ["quality"]
    assert result["token_usage"]["reported_total"] == 92000
    assert list(result["reviews"]) == ["generality", "quality"]
    assert all(v["verdict"] == "pass" for v in result["reviews"].values())
    assert len(result["review_recovery_history"]) == 1
    assert result["review_recovery_history"][0]["original_verdict"]["verdict"] == "blocked"
    assert (folder / "round-1/quality-completed.json").read_bytes() == before
    assert cycle.review_snapshot(repo) == expected
    with pytest.raises(cycle.CycleError, match="Only an externally blocked"):
        cycle.retry_blocked_review("quality-recovery-test", live=True)


@pytest.mark.parametrize(
    "reason",
    [
        "changed_source",
        "wrong_role",
        "no_gate",
        "wrong_evidence",
        "product",
        "not_blocked",
        "no_budget",
        "missing_pin",
        "no_live",
        "policy_missing",
    ],
)
def test_recovery_fails_closed_before_model(monkeypatch, tmp_path, reason):
    repo, folder = make_job(monkeypatch, tmp_path)
    state = cycle.load("quality-recovery-test")
    if reason == "changed_source":
        (repo / "file.txt").write_text("altered")
    elif reason == "wrong_role":
        state["reviews"]["generality"]["verdict"] = "blocked"
    elif reason == "no_gate":
        state["gate"] = {"cross_surface": {"pass": False}}
    elif reason == "wrong_evidence":
        state["review_artifacts"]["quality"] = "/tmp/fake.json"
    elif reason == "product":
        state["acceptance_profile"] = "product"
    elif reason == "not_blocked":
        state["phase"] = "reviewed_tooling_ready"
    elif reason == "no_budget":
        state["reported_token_budget"] = 90000
    elif reason == "missing_pin":
        state.pop("audit_source_sha256")
    elif reason == "policy_missing":
        monkeypatch.setattr(
            cycle.pacing,
            "require_session_headroom",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                cycle.pacing.PacingError("no quota configured")
            ),
        )
    if reason not in {"changed_source", "policy_missing"}:
        cycle.atomic_json(folder / "status.json", state)
    monkeypatch.setattr(cycle, "codex", lambda *_a, **_k: pytest.fail("Model must never start"))
    with pytest.raises(cycle.CycleError):
        cycle.retry_blocked_review("quality-recovery-test", live=reason != "no_live")
    assert not (folder / "blocked-quality-retry-1").exists()


def test_retry_refuses_gate_failure_without_starting_model(monkeypatch, tmp_path):
    _repo, folder = make_job(monkeypatch, tmp_path)
    monkeypatch.setattr(cycle, "deterministic_gates", lambda *_: {"cross_surface": {"pass": False}})
    monkeypatch.setattr(cycle, "codex", lambda *_a, **_kw: pytest.fail("Gate failure must block"))
    result = cycle.retry_blocked_review("quality-recovery-test", live=True)
    assert result["phase"] == "blocked"
    assert result["ready_for_user"] is False
    assert (folder / "round-1/quality-completed.json").exists()


def test_retry_cannot_mark_unapproved_verdict_as_pass(monkeypatch, tmp_path):
    _repo, folder = make_job(monkeypatch, tmp_path)
    monkeypatch.setattr(cycle, "deterministic_gates", lambda *_: {"cross_surface": {"pass": True}})
    monkeypatch.setattr(
        cycle,
        "codex",
        lambda *_a, **_kw: {
            "reported_tokens": 5000,
            "model": "gpt-6-luna",
            "verdict": {"verdict": "blocked", "findings": []},
        },
    )
    result = cycle.retry_blocked_review("quality-recovery-test", live=True)
    assert result["phase"] == "blocked_external_evidence"
    assert result["ready_for_user"] is False
    assert result["review_recovery_history"][0]["original_verdict"]["verdict"] == "blocked"
    with pytest.raises(cycle.CycleError, match="Bounded recovery already attempted"):
        cycle.retry_blocked_review("quality-recovery-test", live=True)


def test_legacy_recovery_requires_existing_real_diagnostic_source_proof(monkeypatch, tmp_path):
    repo, folder = make_job(monkeypatch, tmp_path)
    state = cycle.load("quality-recovery-test")
    state.pop("audit_source_sha256")
    cycle.atomic_json(folder / "status.json", state)
    diag = folder / "quality-diagnostic"
    diag.mkdir()
    (diag / "result.json").write_text(
        json.dumps(
            {
                "role": "quality-diagnostic",
                "source_snapshot": cycle.review_snapshot(repo).hex(),
                "review": {"verdict": "pass", "findings": []},
            }
        )
    )
    monkeypatch.setattr(cycle, "deterministic_gates", lambda *_: {"cross_surface": {"pass": True}})
    monkeypatch.setattr(
        cycle,
        "codex",
        lambda *_a, **_kw: {
            "reported_tokens": 7000,
            "verdict": {"verdict": "pass", "findings": []},
        },
    )
    state = cycle.retry_blocked_review("quality-recovery-test", live=True)
    assert state["phase"] == "reviewed_tooling_ready"
