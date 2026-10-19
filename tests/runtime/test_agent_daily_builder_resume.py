"""Synthetic Git proof of safe daily Builder pause and resume."""

import json
from datetime import UTC, datetime

import pytest

from scripts import odyssey_agent_cycle as cycle
from scripts import odyssey_agent_pacing as pacing
from tests.runtime.test_agent_daily_review_resume import synthetic_repo


def _prepare(monkeypatch, tmp_path, *, budget=300_000):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "mem_available", lambda: 1800)
    repo = synthetic_repo(tmp_path / "repo")
    monkeypatch.setattr(cycle, "workspace", lambda *_: repo)
    monkeypatch.setattr(cycle, "safe_worktree", lambda *_: None)
    job = "builder-daily-pause"
    folder = cycle.job_path(job)
    folder.mkdir(parents=True)
    (folder / "brief.md").write_text("Disposable daily Builder proof.")
    cycle.atomic_json(
        folder / "status.json",
        {
            "phase": "planned",
            "baseline_commit": "a" * 40,
            "acceptance_profile": "product",
            "risk": "normal",
            "ready_for_user": False,
            "gate": {},
            "reviews": {},
            "reported_token_budget": budget,
            "token_usage": {"reported_total": 0, "sessions": []},
        },
    )
    pacing.configure(cycle.STATE, 700_000, 20)
    monkeypatch.setattr(cycle, "deterministic_gates", lambda *_: {"offline": {"pass": True}})
    return repo, job


def _burn_daily(tmp_path, tokens=70_000):
    folder = tmp_path / "runs" / "other-job"
    folder.mkdir(parents=True, exist_ok=True)
    cycle.atomic_json(
        folder / "status.json",
        {
            "updated_at": datetime.now(UTC).isoformat(),
            "token_usage": {
                "reported_total": tokens,
                "sessions": [
                    {"reported_tokens": tokens, "ended_at": datetime.now(UTC).isoformat()}
                ],
            },
        },
    )
    return folder


def _clear_daily(folder):
    (folder / "status.json").unlink()


def test_daily_builder_initial_pause_then_resumes_without_double_work(monkeypatch, tmp_path):
    repo, job = _prepare(monkeypatch, tmp_path)
    burned = _burn_daily(tmp_path)
    launches = []

    def codex(role, *_args, read_only):
        launches.append(role)
        return {"verdict": {"verdict": "pass", "findings": []}} if read_only else {"role": role}

    monkeypatch.setattr(cycle, "codex", codex)
    paused = cycle.run(job, 2, live=True)
    assert paused["phase"] == "paused_daily_budget"
    assert paused["resume_checkpoint"]["stage"] == "builder"
    assert paused["resume_checkpoint"]["round"] == 1
    assert paused["ready_for_user"] is False
    assert launches == []
    _clear_daily(burned)
    resumed = cycle.run(job, 2, live=True, resume=True)
    assert resumed["phase"] == "reviewed_browser_gate_pending"
    assert resumed["ready_for_user"] is False
    assert launches == ["builder", *cycle.REVIEW_ROLES]
    assert repo.is_dir()


@pytest.mark.parametrize(
    "tamper", ["source", "brief", "role", "tokens", "gate", "checkpoint", "policy"]
)
def test_daily_builder_resume_refuses_changed_evidence(monkeypatch, tmp_path, tamper):
    repo, job = _prepare(monkeypatch, tmp_path)
    burned = _burn_daily(tmp_path)
    assert cycle.run(job, 2, live=True)["phase"] == "paused_daily_budget"
    _clear_daily(burned)
    state = cycle.load(job)
    if tamper == "source":
        (repo / "file.txt").write_text("tampered")
    elif tamper == "brief":
        (cycle.job_path(job) / "brief.md").write_text("different feature")
    elif tamper == "role":
        state["resume_checkpoint"]["review_roles"] = []
    elif tamper == "tokens":
        state["token_usage"]["reported_total"] = 1
    elif tamper == "gate":
        state["gate"] = {"offline": {"pass": True}}
    elif tamper == "checkpoint":
        state["resume_checkpoint"]["stage"] = "unknown"
    else:
        state["reported_token_budget"] = 100_000
    cycle.atomic_json(cycle.job_path(job) / "status.json", state)
    monkeypatch.setattr(
        cycle, "codex", lambda *_a, **_kw: pytest.fail("No model may start with stale evidence")
    )
    with pytest.raises(cycle.CycleError):
        cycle.run(job, 2, live=True, resume=True)


def test_daily_builder_refuses_resume_after_partial_write(monkeypatch, tmp_path):
    repo, job = _prepare(monkeypatch, tmp_path)

    def tamper(role, *_args, **_kwargs):
        (repo / "file.txt").write_text("partial output")
        raise cycle.DailyBudgetPause("preflight denied after partial file change")

    monkeypatch.setattr(cycle, "codex", tamper)
    result = cycle.run(job, 1, live=True)
    assert result["phase"] == "blocked"
    assert result["ready_for_user"] is False
    with pytest.raises(cycle.CycleError):
        cycle.run(job, 1, live=True, resume=True)


def test_second_round_builder_preserves_prior_reviewer_failure(monkeypatch, tmp_path):
    _repo, job = _prepare(monkeypatch, tmp_path)
    roles = []
    burnout = None

    def fake_codex(role, prompt, _dest, _evidence, *, read_only):
        nonlocal burnout
        roles.append(role)
        if not read_only:
            if len([r for r in roles if r == "builder"]) == 2:
                assert "needs repair" in prompt
            return {"role": role}
        if role == "performance" and burnout is None:
            burnout = _burn_daily(tmp_path)
        if role == "generality" and burnout is None:
            return {
                "verdict": {
                    "verdict": "fail",
                    "findings": [
                        {
                            "severity": "blocking",
                            "actionability": "repairable",
                            "summary": "needs repair",
                        }
                    ],
                }
            }
        return {"verdict": {"verdict": "pass", "findings": []}}

    monkeypatch.setattr(cycle, "codex", fake_codex)
    paused = cycle.run(job, 2, live=True)
    assert paused["phase"] == "paused_daily_budget"
    assert paused["resume_checkpoint"]["stage"] == "builder"
    assert paused["resume_checkpoint"]["round"] == 2
    assert paused["resume_checkpoint"]["findings"]["reviews"]["generality"]["verdict"] == "fail"
    assert roles.count("builder") == 1
    assert burnout is not None
    _clear_daily(burnout)
    monkeypatch.setattr(cycle, "deterministic_gates", lambda *_: {"offline": {"pass": True}})
    resumed = cycle.run(job, 2, live=True, resume=True)
    assert resumed["phase"] == "reviewed_browser_gate_pending"
    assert roles.count("builder") == 2
    assert roles.count("generality") == 2
    assert resumed["ready_for_user"] is False


def test_builder_pause_requires_real_pacing_policy(monkeypatch, tmp_path):
    _repo, job = _prepare(monkeypatch, tmp_path)
    (cycle.STATE / pacing.POLICY_NAME).unlink()
    monkeypatch.setattr(
        cycle,
        "codex",
        lambda *_a, **_kw: (_ for _ in ()).throw(cycle.DailyBudgetPause("quota exhausted")),
    )
    result = cycle.run(job, 1, live=True)
    assert result["phase"] == "blocked"
    assert result["ready_for_user"] is False


def test_route_quotes_builder_and_all_reviewers_when_builder_is_paused(
    monkeypatch, tmp_path, capsys
):
    repo, job = _prepare(monkeypatch, tmp_path)
    burned = _burn_daily(tmp_path)
    assert cycle.run(job, 2, live=True)["phase"] == "paused_daily_budget"
    monkeypatch.setattr(cycle, "select_agent_model", lambda role, *_: {"role": role})
    monkeypatch.setattr(cycle.sys, "argv", ["agent-cycle.py", "route", "--job", job])
    assert cycle.main() == 0
    info = json.loads(capsys.readouterr().out)
    quote = info["review_budget_quote"]
    assert quote["minimum_remaining_reported_tokens"] == 245_000
    assert list(quote["minimum_by_role"]) == ["builder", *cycle.REVIEW_ROLES]
    assert quote["can_start"] is True
    _clear_daily(burned)
    assert repo.is_dir()


def test_route_quotes_only_pending_reviewers_when_review_is_paused():
    quote = {
        "roles": list(cycle.REVIEW_ROLES),
        "minimum_by_role": {
            "generality": 55_000,
            "quality": 45_000,
            "testing": 55_000,
            "performance": 50_000,
        },
        "reported_tokens_available": 180_000,
        "minimum_remaining_reported_tokens": 205_000,
        "can_start": False,
    }
    state = {
        "phase": "paused_daily_budget",
        "resume_checkpoint": {"stage": "reviewing"},
        "reviews": {"generality": {"verdict": "pass"}},
    }
    result = cycle.remaining_resume_review_quote(state, quote)
    assert result["roles"] == ["quality", "testing", "performance"]
    assert result["minimum_remaining_reported_tokens"] == 150_000
    assert result["can_start"] is True
    assert quote["minimum_remaining_reported_tokens"] == 205_000
    state["reviews"] = {"performance": {"verdict": "pass"}}
    with pytest.raises(cycle.CycleError):
        cycle.remaining_resume_review_quote(state, quote)
