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

SUMMARY_SCRIPT = Path(__file__).resolve().parents[2] / "ops/agent-team/job_summary.py"
summary_spec = importlib.util.spec_from_file_location("odyssey_job_summary", SUMMARY_SCRIPT)
assert summary_spec and summary_spec.loader
summary_cli = importlib.util.module_from_spec(summary_spec)
summary_spec.loader.exec_module(summary_cli)


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


def test_job_summary_text_and_json_are_safe_read_only_projections(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(summary_cli.cycle, "STATE", tmp_path / "runs")
    job = "summary-recovered-job"
    job_dir = cycle.job_path(job)
    job_dir.mkdir(parents=True)
    old_dir = job_dir / "round-1"
    retry_dir = job_dir / "blocked-quality-retry-1"
    old_dir.mkdir()
    retry_dir.mkdir()
    original_path = old_dir / "quality-completed.json"
    retry_path = retry_dir / "quality-completed.json"
    cycle.atomic_json(
        original_path,
        {
            "role": "quality",
            "verdict": {"verdict": "blocked", "summary": "private history"},
        },
    )
    cycle.atomic_json(
        retry_path,
        {
            "role": "quality",
            "verdict": {"verdict": "pass", "summary": "safe recovered verdict"},
        },
    )
    cycle.atomic_json(
        job_dir / "status.json",
        {
            "job": job,
            "phase": "reviewed_tooling_ready",
            "round": 1,
            "ready_for_user": True,
            "review_plan": {"roles": ["generality", "quality"]},
            "reviews": {
                "generality": {"verdict": "pass", "summary": "safe reviewer detail"},
                "quality": {"verdict": "pass", "summary": "safe recovered verdict"},
            },
            "reported_token_budget": 220000,
            "token_usage": {"reported_total": 137380, "sessions": []},
            "audit_source_sha256": "a" * 64,
            "review_artifacts": {"quality": str(retry_path)},
            "review_recovery_history": [
                {
                    "role": "quality",
                    "original_verdict": {"verdict": "blocked", "summary": "private history"},
                    "retry_artifact": str(retry_path),
                    "original_artifact": str(original_path),
                    "source_sha256": "a" * 64,
                    "prompt": "never expose prompt text",
                }
            ],
            "private_path": "/private/path",
            "credential": "never expose credential",
        },
    )
    before = (job_dir / "status.json").read_bytes()

    assert summary_cli.main(["--job", job]) == 0
    text_output = capsys.readouterr().out
    assert "Job: summary-recovered-job" in text_output
    assert "Phase: reviewed_tooling_ready" in text_output
    assert "Round: 1" in text_output
    assert "Ready for maintainer: true" in text_output
    assert "Generality: PASS" in text_output
    assert "Quality: PASS" in text_output
    assert "Testing" not in text_output
    assert "137380 / 220000 job cap" in text_output
    assert "original BLOCKED; accepted retry PASS" in text_output
    for private in ("private", "credential", "prompt", "retry_artifact", "safe reviewer detail"):
        assert private not in text_output

    assert summary_cli.main(["--job", job, "--json"]) == 0
    json_output = json.loads(capsys.readouterr().out)
    assert json_output == {
        "job": job,
        "phase": "reviewed_tooling_ready",
        "round": 1,
        "ready_for_maintainer": True,
        "mandatory_auditors": [
            {"role": "Generality", "verdict": "PASS"},
            {"role": "Quality", "verdict": "PASS"},
        ],
        "reported_tokens_used": 137380,
        "reported_token_cap": 220000,
        "recovered_reviews": [
            {
                "role": "Quality",
                "original_verdict": "BLOCKED",
                "accepted_retry_verdict": "PASS",
            }
        ],
    }
    assert "/private" not in json.dumps(json_output)
    assert "credential" not in json.dumps(json_output)
    assert (job_dir / "status.json").read_bytes() == before
    assert sorted(path.name for path in job_dir.iterdir()) == [
        "blocked-quality-retry-1",
        "round-1",
        "status.json",
    ]


def test_job_summary_refuses_stale_recovery_or_fabricated_approval(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(summary_cli.cycle, "STATE", tmp_path / "runs")
    job = "summary-unverified-recovery"
    folder = cycle.job_path(job)
    folder.mkdir(parents=True)
    fake_receipt = folder / "blocked-quality-retry-1" / "quality-completed.json"
    fake_receipt.parent.mkdir()
    cycle.atomic_json(fake_receipt, {"verdict": {"verdict": "blocked"}})
    state = {
        "job": job,
        "phase": "reviewed_tooling_ready",
        "round": 1,
        "ready_for_user": True,
        "review_plan": {"roles": ["quality"]},
        "reviews": {"quality": {"verdict": "pass"}},
        "reported_token_budget": 180000,
        "token_usage": {"reported_total": 90000},
        "audit_source_sha256": "b" * 64,
        "review_artifacts": {"quality": str(fake_receipt)},
        "review_recovery_history": [
            {
                "role": "quality",
                "original_verdict": {"verdict": "blocked"},
                "original_artifact": str(folder / "round-1" / "quality-completed.json"),
                "retry_artifact": str(fake_receipt),
                "source_sha256": "b" * 64,
            }
        ],
    }
    cycle.atomic_json(folder / "status.json", state)
    assert summary_cli.main(["--job", job, "--json"]) == 2
    assert "unverified recovery" in capsys.readouterr().err
    # The status alone must never be able to create an accepted retry.
    assert fake_receipt.is_file()


def test_job_summary_unknown_malformed_and_corrupt_status_fail_closed(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(summary_cli.cycle, "STATE", tmp_path / "runs")
    assert summary_cli.main(["--job", "missing-summary-job"]) == 2
    assert "unavailable or corrupt" in capsys.readouterr().err
    assert summary_cli.main(["--job", "../escape-summary-job"]) == 2
    assert "unavailable or corrupt" in capsys.readouterr().err

    malformed_dir = cycle.job_path("malformed-summary-job")
    malformed_dir.mkdir(parents=True)
    (malformed_dir / "status.json").write_text("{broken", encoding="utf-8")
    assert summary_cli.main(["--job", "malformed-summary-job", "--json"]) == 2
    error = capsys.readouterr().err
    assert "unavailable or corrupt" in error
    assert "broken" not in error

    invalid_dir = cycle.job_path("invalid-summary-job")
    invalid_dir.mkdir(parents=True)
    cycle.atomic_json(
        invalid_dir / "status.json",
        {
            "phase": "reviewed_tooling_ready",
            "round": 1,
            "ready_for_user": True,
            "review_plan": {"roles": ["generality", "testing"]},
            "reviews": {"generality": {"verdict": "pass"}},
            "reported_token_budget": 100000,
            "token_usage": {"reported_total": 0},
        },
    )
    assert summary_cli.main(["--job", "invalid-summary-job"]) == 2
    assert "missing a selected reviewer verdict" in capsys.readouterr().err


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
    assert report["acceptance_profile"] == "product"
    assert report["ready_for_user"] is False
    assert not (cycle.ROOT.parent / "odyssey-agent-work-agent-dry-run-1").exists()
    assert cycle.load("agent-dry-run-1") == report
    with pytest.raises(cycle.CycleError, match="already exists"):
        cycle.plan(brief, "agent-dry-run-1")


@pytest.mark.parametrize("author", ["codex", "chatgpt"])
def test_acceptance_profile_is_validated_and_persisted_for_each_author(
    monkeypatch, tmp_path, author
):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "check_repository", lambda: None)
    previous, feature = "a" * 40, "b" * 40

    def git_call(args, **_kwargs):
        if "status" in args:
            value = ""
        elif "diff" in args:
            value = "scripts/odyssey_agent_cycle.py\n"
        elif "HEAD" in args:
            value = feature + "\n"
        else:
            value = previous + "\n"
        return type("Git", (), {"returncode": 0, "stdout": value})()

    monkeypatch.setattr(cycle, "running", git_call)
    kwargs = {"implemented_by": author, "acceptance": "tooling"}
    if author == "chatgpt":
        kwargs["against"] = previous
    state = cycle.plan(cycle.ROLES / "pilot-p4.md", "tooling-profile-job", **kwargs)
    assert state["acceptance_profile"] == "tooling"
    assert cycle.load("tooling-profile-job")["acceptance_profile"] == "tooling"
    assert state["ready_for_user"] is False
    with pytest.raises(cycle.CycleError, match="Acceptance"):
        cycle.plan(cycle.ROLES / "pilot-p4.md", "invalid-profile-job", acceptance="future")


@pytest.fixture
def mocked_review_snapshot(monkeypatch):
    """Keep supervisor flow tests independent of a physical Git fixture."""
    monkeypatch.setattr(cycle, "review_snapshot", lambda *_: b"unchanged")


def test_successful_tooling_review_is_ready_only_for_allowlisted_diff(
    monkeypatch, tmp_path, mocked_review_snapshot
):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "mem_available", lambda: 1900)
    monkeypatch.setattr(cycle, "workspace", lambda _job, _sha: tmp_path / "isolated")
    monkeypatch.setattr(cycle, "safe_worktree", lambda _dest, _job: None)
    (tmp_path / "isolated").mkdir()
    job = "tooling-ready-job"
    path = cycle.job_path(job)
    path.mkdir(parents=True)
    (path / "brief.md").write_text("Disposable tooling review brief.")
    cycle.atomic_json(
        path / "status.json",
        {
            "phase": "planned",
            "baseline_commit": "a" * 40,
            "acceptance_profile": "tooling",
            "ready_for_user": False,
            "reviews": {},
            "gate": {},
        },
    )

    def git_call(args, **_kwargs):
        output = "scripts/odyssey_agent_cycle.py\0" if "--name-only" in args else ""
        return type("Git", (), {"returncode": 0, "stdout": output})()

    monkeypatch.setattr(cycle, "running", git_call)
    monkeypatch.setattr(
        cycle,
        "codex",
        lambda role, *_args, read_only: (
            {"verdict": {"verdict": "pass"}} if read_only else {"role": role}
        ),
    )
    monkeypatch.setattr(cycle, "deterministic_gates", lambda *_: {"focused": {"pass": True}})
    result = cycle.run(job, 1, live=True)
    assert result["phase"] == "reviewed_tooling_ready"
    assert list(result["reviews"]) == ["generality", "quality"]
    assert result["ready_for_user"] is True
    assert "no deploy" in result["readiness_meaning"]
    assert cycle.load(job) == result


@pytest.mark.parametrize(
    "changed",
    [
        "odyssey_core/domain.py",
        "future_apps/custom/app.py",
        "docs/architecture/odyssey-acceptance-contracts.json",
    ],
)
def test_tooling_profile_fails_closed_on_product_or_unknown_paths(monkeypatch, tmp_path, changed):
    workspace = tmp_path / "worktree"
    workspace.mkdir()

    def git_call(args, **_kwargs):
        if "--name-only" in args:
            output = changed + "\0"
        elif "--others" in args:
            output = "untracked-product.py\0"
        else:
            output = ""
        return type("Git", (), {"returncode": 0, "stdout": output})()

    monkeypatch.setattr(cycle, "running", git_call)
    assert cycle.tooling_scope_is_safe(workspace, "a" * 40) is False


def test_tooling_product_path_tampering_blocks_before_gates_or_reviewers(monkeypatch, tmp_path):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "mem_available", lambda: 1900)
    monkeypatch.setattr(cycle, "workspace", lambda _job, _sha: tmp_path / "isolated")
    monkeypatch.setattr(cycle, "safe_worktree", lambda _dest, _job: None)
    (tmp_path / "isolated").mkdir()
    path = cycle.job_path("tooling-tamper-job")
    path.mkdir(parents=True)
    (path / "brief.md").write_text("Disposable tooling tamper brief.")
    cycle.atomic_json(
        path / "status.json",
        {
            "phase": "planned",
            "baseline_commit": "a" * 40,
            "acceptance_profile": "tooling",
            "ready_for_user": False,
            "reviews": {},
            "gate": {},
        },
    )
    calls = []

    def git_call(args, **_kwargs):
        calls.append(args)
        output = "odyssey_runtime/runtime.py\0" if "--name-only" in args else ""
        return type("Git", (), {"returncode": 0, "stdout": output})()

    monkeypatch.setattr(cycle, "running", git_call)
    monkeypatch.setattr(
        cycle,
        "codex",
        lambda role, *_args, read_only: (
            pytest.fail("review launched") if read_only else {"role": role}
        ),
    )
    monkeypatch.setattr(cycle, "deterministic_gates", lambda *_: pytest.fail("gate launched"))
    result = cycle.run("tooling-tamper-job", 1, live=True)
    assert result["phase"] == "blocked_acceptance_scope"
    assert result["ready_for_user"] is False
    assert all("deploy" not in " ".join(args) for args in calls)


def test_tooling_profile_rejects_a_blocked_reviewer(monkeypatch, tmp_path, mocked_review_snapshot):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "mem_available", lambda: 1900)
    monkeypatch.setattr(cycle, "workspace", lambda _job, _sha: tmp_path / "isolated")
    monkeypatch.setattr(cycle, "safe_worktree", lambda _dest, _job: None)
    (tmp_path / "isolated").mkdir()
    path = cycle.job_path("tooling-review-blocked")
    path.mkdir(parents=True)
    (path / "brief.md").write_text("Disposable blocked review brief.")
    cycle.atomic_json(
        path / "status.json",
        {
            "phase": "planned",
            "baseline_commit": "a" * 40,
            "acceptance_profile": "tooling",
            "risk": "high",
            "ready_for_user": False,
            "reviews": {},
            "gate": {},
        },
    )

    def git_call(args, **_kwargs):
        output = "tests/runtime/test_agent_cycle_supervisor.py\0" if "--name-only" in args else ""
        return type("Git", (), {"returncode": 0, "stdout": output})()

    monkeypatch.setattr(cycle, "running", git_call)
    monkeypatch.setattr(
        cycle,
        "codex",
        lambda role, *_args, read_only: (
            {"verdict": {"verdict": "blocked" if role == "testing" else "pass"}}
            if read_only
            else {"role": role}
        ),
    )
    monkeypatch.setattr(cycle, "deterministic_gates", lambda *_: {"focused": {"pass": True}})
    result = cycle.run("tooling-review-blocked", 1, live=True)
    assert result["phase"] == "blocked_external_evidence"
    assert result["ready_for_user"] is False


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
    monkeypatch, tmp_path, mocked_review_snapshot
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


def test_a_blocked_independent_reviewer_stops_repair_loop(
    monkeypatch, tmp_path, mocked_review_snapshot
):
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


def test_chatgpt_first_iteration_skips_codex_builder_but_same_reviewers_run(
    monkeypatch, tmp_path, mocked_review_snapshot
):
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


def test_chatgpt_failed_review_invokes_builder_only_on_second_round(
    monkeypatch, tmp_path, mocked_review_snapshot
):
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


def test_repairable_review_finding_is_not_suppressed_by_external_blocker(
    monkeypatch, tmp_path, mocked_review_snapshot
):
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
    cycle.pacing.configure(cycle.STATE, 700_000, 20)
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
    monkeypatch.setattr(cycle, "select_review_roles", lambda _state, _dest=None: roles)
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
    monkeypatch.setattr(cycle, "review_snapshot", lambda *_: b"modified" if changed else b"")
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


@pytest.mark.parametrize(
    ("role", "risk", "paths", "round_number", "expected_model", "expected_effort"),
    [
        ("builder", "normal", (), 1, "gpt-6-luna", "low"),
        ("generality", "normal", ("scripts/tool.py",), 1, "gpt-6-luna", "low"),
        ("performance", "normal", ("tests/core/test_example.py",), 1, "gpt-6-luna", "low"),
        ("builder", "normal", ("odyssey_core/identity.py",), 1, "gpt-6-sol", "medium"),
        ("generality", "normal", ("odyssey_runtime/composition.py",), 1, "gpt-6-sol", "medium"),
        ("quality", "normal", ("odyssey_apps/custom.py",), 1, "gpt-6-sol", "medium"),
        ("testing", "high", ("scripts/tool.py",), 1, "gpt-6-sol", "medium"),
        ("builder", "normal", ("scripts/tool.py",), 2, "gpt-6-sol", "medium"),
        ("builder", "high", ("odyssey_core/writer.py",), 2, "gpt-6-sol", "high"),
        ("quality", "critical", ("scripts/tool.py",), 1, "gpt-6-sol", "high"),
        ("performance", "normal", ("odyssey_core/writer.py",), 1, "gpt-6-luna", "low"),
    ],
)
def test_model_routing_by_impact_role_and_repair(
    monkeypatch, tmp_path, role, risk, paths, round_number, expected_model, expected_effort
):
    monkeypatch.setattr(cycle, "touched_paths", lambda _dest, _base: paths)
    choice = cycle.select_agent_model(
        role,
        {"risk": risk, "round": round_number, "baseline_commit": "a" * 40},
        tmp_path,
    )
    assert (choice["model"], choice["effort"]) == (expected_model, expected_effort)
    assert choice["changed_files_count"] == len(paths)


def test_model_selector_refuses_unapproved_role_and_invalid_risk(monkeypatch, tmp_path):
    monkeypatch.setattr(cycle, "touched_paths", lambda *_: ())
    with pytest.raises(cycle.CycleError, match="role"):
        cycle.select_agent_model("invented-app", {"baseline_commit": "a" * 40}, tmp_path)
    with pytest.raises(cycle.CycleError, match="risk"):
        cycle.select_agent_model(
            "quality", {"baseline_commit": "a" * 40, "risk": "unbounded"}, tmp_path
        )


@pytest.mark.parametrize("value", [-1, 5000, 19999, 300001, "110000", True])
def test_model_budget_configuration_rejects_invalid_values(monkeypatch, value):
    monkeypatch.setattr(cycle, "check_repository", lambda: None)
    with pytest.raises(cycle.CycleError, match="Token budget"):
        cycle.plan(cycle.ROLES / "pilot-p4.md", "invalid-budget-test", token_budget=value)


def test_codex_reported_tokens_parser_handles_real_cli_footer(tmp_path):
    log = tmp_path / "cli.log"
    log.write_text("model: gpt-6-luna\nreasoning effort: low\ntokens used\n9,278\nMODEL_OK\n")
    assert cycle.reported_token_count(log) == 9278
    log.write_text("tokens used\n9,278\n...\ntokens used\n13,541\n")
    assert cycle.reported_token_count(log) == 13541
    log.write_text("response without reliable accounting")
    assert cycle.reported_token_count(log) is None


def test_shared_reported_token_ledger_stops_at_budget_and_keeps_receipts(monkeypatch, tmp_path):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    job = "bounded-cost-job"
    path = cycle.job_path(job)
    path.mkdir(parents=True)
    state = {
        "phase": "reviewing",
        "round": 1,
        "reported_token_budget": 20000,
        "token_usage": {"reported_total": 0, "sessions": []},
    }
    cycle.atomic_json(path / "status.json", state)
    cycle.record_agent_usage(
        job,
        state,
        "builder",
        {
            "reported_tokens": 12000,
            "model": "gpt-6-luna",
            "tier": "economy",
            "routing_reason": "routine",
        },
    )
    assert state["token_usage"]["reported_total"] == 12000
    with pytest.raises(cycle.CycleError, match="budget"):
        cycle.record_agent_usage(
            job,
            state,
            "generality",
            {
                "reported_tokens": 10000,
                "model": "gpt-6-sol",
                "tier": "standard",
                "routing_reason": "contract_change",
            },
        )
    persisted = cycle.load(job)["token_usage"]
    assert persisted["reported_total"] == 22000
    assert [x["role"] for x in persisted["sessions"]] == ["builder", "generality"]


def test_pinned_luna_and_sol_policy_exists_and_is_not_supplied_by_untrusted_app():
    policy = cycle.model_policy()
    assert policy["models"]["economy"]["id"] == "gpt-6-luna"
    assert policy["models"]["standard"]["id"] == "gpt-6-sol"
    assert policy["models"]["deep"]["effort"] == "high"
    assert "odyssey_core/" in policy["architectural_change_prefixes"]
    assert "odyssey_runtime/" in policy["architectural_change_prefixes"]
    assert policy["default_reported_token_budget"] < 249201


@pytest.mark.parametrize(
    ("risk", "changed", "expected_model", "expected_effort"),
    [
        ("normal", ("scripts/agent_tool.py",), "gpt-6-luna", "low"),
        ("normal", ("odyssey_core/writer.py",), "gpt-6-sol", "medium"),
        ("critical", ("scripts/agent_tool.py",), "gpt-6-sol", "high"),
    ],
)
def test_actual_codex_cli_command_routes_model_and_records_reported_tokens(
    monkeypatch, tmp_path, risk, changed, expected_model, expected_effort
):
    import io

    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "mem_available", lambda: 1600)
    monkeypatch.setattr(
        cycle,
        "probe_native_profile",
        lambda *_args, **kwargs: {
            "profile": "odyssey-scope-read",
            "scope_verified": True,
            "workspace_read_only": kwargs["read_only"],
        },
    )
    monkeypatch.setattr(
        cycle,
        "permission_overrides",
        lambda *_args, **kwargs: (
            "odyssey-scope-read",
            ["--config", 'default_permissions="odyssey-scope-read"'],
        ),
    )
    monkeypatch.setattr(cycle, "touched_paths", lambda *_: changed)
    job = "model-profile-fixture"
    run_root = cycle.job_path(job)
    work = run_root / "round-1"
    work.mkdir(parents=True)
    cycle.atomic_json(
        run_root / "status.json",
        {
            "phase": "reviewing",
            "risk": risk,
            "round": 1,
            "baseline_commit": "a" * 40,
            "reported_token_budget": 110000,
            "token_usage": {"reported_total": 0, "sessions": []},
        },
    )
    observed = {}

    class FakeProc:
        def __init__(self, command, **kwargs):
            observed["command"] = command
            self.stdin = io.StringIO()
            self.returncode = 0
            output = Path(command[command.index("--output-last-message") + 1])
            output.write_text(
                json.dumps({"verdict": "pass", "summary": "OK", "findings": [], "evidence": []})
            )
            kwargs["stdout"].write(
                "OpenAI Codex test\nmodel: "
                + expected_model
                + "\nreasoning effort: "
                + expected_effort
                + "\n\ntokens used\n9,278\n"
            )
            kwargs["stdout"].flush()

        def poll(self):
            return 0

    monkeypatch.setattr(cycle.subprocess, "Popen", FakeProc)
    receipt = cycle.codex(
        "generality",
        "Review scoped current Git diff only",
        tmp_path,
        work,
        read_only=True,
    )
    argv = observed["command"]
    assert argv[argv.index("--model") + 1] == expected_model
    assert 'model_reasoning_effort="' + expected_effort + '"' in argv
    assert "--ephemeral" in argv
    assert "--sandbox" not in argv
    assert 'default_permissions="odyssey-scope-read"' in argv
    assert receipt["permissions"]["scope_verified"] is True
    assert receipt["permissions"]["workspace_read_only"] is True
    assert receipt["reported_tokens"] == 9278
    assert receipt["model"] == expected_model
    assert receipt["tier"] in {"economy", "standard", "deep"}
    cycle.record_agent_usage(job, cycle.load(job), "generality", receipt)
    assert cycle.load(job)["token_usage"]["reported_total"] == 9278


def test_codex_cli_refuses_unverified_model_substitution(monkeypatch, tmp_path):
    import io

    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "mem_available", lambda: 1600)
    monkeypatch.setattr(
        cycle,
        "probe_native_profile",
        lambda *_args, **kwargs: {
            "profile": "odyssey-scope-read",
            "scope_verified": True,
            "workspace_read_only": kwargs["read_only"],
        },
    )
    monkeypatch.setattr(
        cycle,
        "permission_overrides",
        lambda *_args, **kwargs: (
            "odyssey-scope-read",
            ["--config", 'default_permissions="odyssey-scope-read"'],
        ),
    )
    monkeypatch.setattr(cycle, "touched_paths", lambda *_: ())
    job = "wrong-model-fixture"
    run_root = cycle.job_path(job)
    work = run_root / "round-1"
    work.mkdir(parents=True)
    cycle.atomic_json(
        run_root / "status.json",
        {
            "phase": "reviewing",
            "round": 1,
            "risk": "normal",
            "baseline_commit": "a" * 40,
            "reported_token_budget": 110000,
            "token_usage": {"reported_total": 0, "sessions": []},
        },
    )

    class WrongModel:
        def __init__(self, command, **kwargs):
            self.stdin = io.StringIO()
            self.returncode = 0
            output = Path(command[command.index("--output-last-message") + 1])
            output.write_text(
                json.dumps({"verdict": "pass", "summary": "OK", "findings": [], "evidence": []})
            )
            kwargs["stdout"].write("model: gpt-6-sol\ntokens used\n9,278\n")
            kwargs["stdout"].flush()

        def poll(self):
            return 0

    monkeypatch.setattr(cycle.subprocess, "Popen", WrongModel)
    with pytest.raises(cycle.CycleError, match="not verified"):
        cycle.codex("generality", "Review", tmp_path, work, read_only=True)


def test_missing_native_scoped_permissions_refuses_model_before_launch(monkeypatch, tmp_path):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "mem_available", lambda: 1600)
    monkeypatch.setattr(cycle, "touched_paths", lambda *_: ())
    job = "scoped-permission-denied"
    work = cycle.job_path(job) / "round-1"
    work.mkdir(parents=True)
    cycle.atomic_json(
        cycle.job_path(job) / "status.json",
        {
            "phase": "reviewing",
            "risk": "normal",
            "round": 1,
            "baseline_commit": "a" * 40,
            "reported_token_budget": 110000,
            "token_usage": {"reported_total": 0, "sessions": []},
        },
    )

    def deny_proof(*_args, **_kwargs):
        raise cycle.ScopeError("private HOME unexpectedly visible")

    monkeypatch.setattr(cycle, "probe_native_profile", deny_proof)
    monkeypatch.setattr(
        cycle.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("Model must never launch without OS scope proof"),
    )
    with pytest.raises(cycle.CycleError, match="Unsafe Codex filesystem/network scope"):
        cycle.codex("generality", "Review", tmp_path, work, read_only=True)
    assert cycle.load(job)["token_usage"]["sessions"] == []


def test_failing_offline_gate_skips_all_model_reviewers_and_preserves_logs(monkeypatch, tmp_path):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "mem_available", lambda: 1900)
    monkeypatch.setattr(cycle, "workspace", lambda *_: tmp_path / "isolated")
    monkeypatch.setattr(cycle, "safe_worktree", lambda *_: None)
    (tmp_path / "isolated").mkdir()
    monkeypatch.setattr(
        cycle, "running", lambda *_args, **_kw: type("Git", (), {"returncode": 0, "stdout": ""})()
    )
    job = "failfast-pilot"
    base = cycle.job_path(job)
    base.mkdir(parents=True)
    (base / "brief.md").write_text("Prove deterministic failures skip LLM reviewers.")
    cycle.atomic_json(
        base / "status.json",
        {
            "phase": "planned",
            "baseline_commit": "b" * 40,
            "ready_for_user": False,
            "reviews": {},
            "gate": {},
            "reported_token_budget": 110000,
            "token_usage": {"reported_total": 0, "sessions": []},
        },
    )
    calls = []

    def fake_model(role, *_args, **_kw):
        calls.append(role)
        return {
            "role": "builder",
            "reported_tokens": 85844,
            "model": "gpt-6-luna",
            "tier": "economy",
            "routing_reason": "routine",
        }

    monkeypatch.setattr(cycle, "codex", fake_model)
    monkeypatch.setattr(
        cycle,
        "deterministic_gates",
        lambda *_: {
            "cross_surface": {"pass": False, "log": "/tmp/failed.log"},
            "acceptance": {"pass": True},
        },
    )
    status = cycle.run(job, 2, live=True)
    assert calls == []  # Foresee an impossible full review before using a single token.
    assert status["phase"] == "blocked_insufficient_review_budget"
    assert status["token_usage"]["reported_total"] == 0
    assert status["reviews"] == {}
    assert "shortfall" in status["last_error"].lower()


def test_review_failure_cannot_launch_repair_without_full_independent_review_reserve(
    monkeypatch, tmp_path, mocked_review_snapshot
):
    """Reproduce actual 19 Oct outcome: 119153 tokens used, 220k budget.

    Previously the supervisor spent another 34,678 tokens on Builder and only
    THEN learned it could not afford the two mandatory reviewer reservations.
    """
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "mem_available", lambda: 1900)
    workspace = tmp_path / "isolated"
    workspace.mkdir()
    monkeypatch.setattr(cycle, "workspace", lambda *_: workspace)
    monkeypatch.setattr(cycle, "safe_worktree", lambda *_: None)
    monkeypatch.setattr(cycle, "tooling_scope_is_safe", lambda *_: True)
    monkeypatch.setattr(
        cycle,
        "touched_paths",
        lambda *_: ("tests/runtime/test_agent_cycle_supervisor.py",),
    )
    monkeypatch.setattr(cycle, "deterministic_gates", lambda *_: {"cross_surface": {"pass": True}})
    job = "review-reserve-before-repair"
    folder = cycle.job_path(job)
    folder.mkdir(parents=True)
    (folder / "brief.md").write_text("A small tooling regression, requiring two reviews.")
    cycle.atomic_json(
        folder / "status.json",
        {
            "phase": "planned",
            "implemented_by": "codex",
            "acceptance_profile": "tooling",
            "risk": "normal",
            "baseline_commit": "b" * 40,
            "reported_token_budget": 220000,
            "token_usage": {"reported_total": 0, "sessions": []},
            "ready_for_user": False,
            "reviews": {},
            "gate": {},
        },
    )
    invoked = []

    def fake_agent(role, *_args, **_kwargs):
        invoked.append(role)
        if role == "builder":
            return {"role": role, "reported_tokens": 47400}
        if role == "generality":
            return {
                "role": role,
                "reported_tokens": 34377,
                "verdict": {"verdict": "pass", "findings": []},
            }
        assert role == "quality"
        return {
            "role": role,
            "reported_tokens": 37376,
            "verdict": {
                "verdict": "fail",
                "findings": [
                    {
                        "severity": "blocking",
                        "actionability": "repairable",
                        "reason": "Optional test incorrectly deemed mandatory",
                    }
                ],
            },
        }

    monkeypatch.setattr(cycle, "codex", fake_agent)
    result = cycle.run(job, 2, live=True)
    assert invoked == ["builder", "generality", "quality"]
    assert result["phase"] == "blocked_insufficient_review_budget"
    assert result["round"] == 1
    assert result["token_usage"]["reported_total"] == 119153
    assert result["review_plan"]["minimum_remaining_reported_tokens"] == 140000
    assert result["review_plan"]["reported_tokens_available"] == 100847
    assert "Cannot start unreviewable repair" in result["last_error"]
    assert not (folder / "round-2").exists()
    assert result["ready_for_user"] is False


def test_every_independent_reviewer_prompt_rejects_optional_criteria_as_blocker():
    for role in cycle.REVIEW_ROLES:
        result = cycle.instructions(role, "Optional: extra timeout test", "b" * 40)
        assert "clearly OPTIONAL" in result
        assert "host gate receipt" in result


def test_failing_gates_go_straight_to_bounded_builder_repair_without_review(
    monkeypatch, tmp_path, mocked_review_snapshot
):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "mem_available", lambda: 1900)
    monkeypatch.setattr(cycle, "workspace", lambda *_: tmp_path / "isolated")
    monkeypatch.setattr(cycle, "safe_worktree", lambda *_: None)
    monkeypatch.setattr(
        cycle, "running", lambda *_args, **_kw: type("Git", (), {"returncode": 0, "stdout": ""})()
    )
    (tmp_path / "isolated").mkdir()
    job = "repair-without-review"
    path = cycle.job_path(job)
    path.mkdir(parents=True)
    (path / "brief.md").write_text("Repair an offline failure without GPT review first.")
    cycle.atomic_json(
        path / "status.json",
        {
            "phase": "planned",
            "baseline_commit": "b" * 40,
            "ready_for_user": False,
            "reviews": {},
            "gate": {},
            "reported_token_budget": 300000,
            "token_usage": {"reported_total": 0, "sessions": []},
        },
    )
    roles, gate_calls = [], []

    def fake_model(role, *_args, **_kw):
        roles.append(role)
        return {"verdict": {"verdict": "pass"}} if role != "builder" else {"role": role}

    def gates(*_args):
        gate_calls.append(1)
        return {"focused": {"pass": len(gate_calls) > 1}}

    monkeypatch.setattr(cycle, "codex", fake_model)
    monkeypatch.setattr(cycle, "deterministic_gates", gates)
    result = cycle.run(job, 2, live=True)
    assert result["phase"] == "reviewed_browser_gate_pending"
    assert result["round"] == 2
    assert roles == ["builder", "builder", *cycle.REVIEW_ROLES]
    assert len(gate_calls) == 2
    assert list(result["reviews"]) == list(cycle.REVIEW_ROLES)


def test_headroom_guard_stops_before_spawning_codex(monkeypatch, tmp_path):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "mem_available", lambda: 1900)
    job = "headroom-guard"
    directory = cycle.job_path(job)
    (directory / "round-1").mkdir(parents=True)
    cycle.atomic_json(
        directory / "status.json",
        {
            "phase": "reviewing",
            "round": 1,
            "baseline_commit": "a" * 40,
            "reported_token_budget": 110000,
            "token_usage": {"reported_total": 85844, "sessions": []},
        },
    )
    monkeypatch.setattr(
        cycle.subprocess, "Popen", lambda *_args, **_kwargs: pytest.fail("Should not call Codex")
    )
    with pytest.raises(cycle.CycleError, match="headroom"):
        cycle.codex("generality", "Review", tmp_path, directory / "round-1", read_only=True)


def test_tooling_scope_rejects_similar_named_docs_outside_exact_namespace(monkeypatch, tmp_path):
    """An arbitrary product doc named agent-team is NOT supervisor documentation."""

    def fake_git(args, **_kwargs):
        out = "docs/product/agent-team.md\0" if "--name-only" in args else ""
        return type("Git", (), {"returncode": 0, "stdout": out})()

    monkeypatch.setattr(cycle, "running", fake_git)
    assert cycle.tooling_scope_is_safe(tmp_path, "a" * 40) is False


def test_tooling_scope_accepts_exact_designated_architecture_report(monkeypatch, tmp_path):
    def fake_git(args, **_kwargs):
        out = "docs/architecture/agent-team-pilot-20261018.md\0" if "--name-only" in args else ""
        return type("Git", (), {"returncode": 0, "stdout": out})()

    monkeypatch.setattr(cycle, "running", fake_git)
    assert cycle.tooling_scope_is_safe(tmp_path, "a" * 40) is True


def test_dirty_tracked_file_mutation_by_readonly_reviewer_is_detected_even_when_git_status_matches(
    monkeypatch, tmp_path
):
    """A dirty file can change content while its ' M' porcelain flag stays identical.

    This is an independent security regression: reviewers cannot rewrite source
    and still get a PASS merely because the file was dirty before review.
    """
    import subprocess

    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "mem_available", lambda: 1900)
    repo = tmp_path / "isolated"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "fixture@invalid.example"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Disposable Test"], cwd=repo, check=True)
    tracked = repo / "existing.py"
    tracked.write_text("value = 1\n")
    subprocess.run(["git", "add", "existing.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "synthetic base"], cwd=repo, check=True)
    tracked.write_text("value = 2\n")
    assert (
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        == " M existing.py\n"
    )

    monkeypatch.setattr(cycle, "workspace", lambda *_: repo)
    monkeypatch.setattr(cycle, "safe_worktree", lambda *_: None)
    job = "dirty-tracked-mutation-guard"
    root = cycle.job_path(job)
    root.mkdir(parents=True)
    (root / "brief.md").write_text("Require content integrity for independent read-only reviews.")
    cycle.atomic_json(
        root / "status.json",
        {
            "phase": "planned",
            "baseline_commit": "a" * 40,
            "ready_for_user": False,
            "reviews": {},
            "gate": {},
        },
    )

    def fake_codex(role, _prompt, _dest, _evidence, *, read_only):
        if read_only:
            if role == "generality":
                tracked.write_text("value = 999\n")
            return {"verdict": {"verdict": "pass", "findings": []}}
        return {"role": role}

    monkeypatch.setattr(cycle, "codex", fake_codex)
    monkeypatch.setattr(
        cycle,
        "deterministic_gates",
        lambda *_: {"offline": {"pass": True}},
    )
    before = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    result = cycle.run(job, 1, live=True)
    after = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert before == after  # Git flags by themselves miss a real content mutation.
    assert result["ready_for_user"] is False
    assert result["phase"] == "blocked"
    assert "changed" in result["last_error"].lower() or "mutat" in result["last_error"].lower()
    assert list(result["reviews"]) == []  # No approval of mutated worktree.


def _disposable_git_repo(path):
    """Create a synthetic repository for real content-snapshot tests."""
    import subprocess

    path.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "fixture@invalid.example"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Disposable Test"], cwd=path, check=True)
    tracked = path / "existing.py"
    tracked.write_text("value = 1\n")
    subprocess.run(["git", "add", "existing.py"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "synthetic base"], cwd=path, check=True)
    return tracked


@pytest.mark.parametrize("mutation", ["content", "staging", "mode", "deletion", "addition"])
def test_review_snapshot_detects_tracked_content_and_index_mutations(tmp_path, mutation):
    """Content, index state, paths, and mode all belong to the read-only boundary."""
    import os
    import subprocess

    repo = tmp_path / "repo"
    tracked = _disposable_git_repo(repo)
    tracked.write_text("value = 2\n")
    before = cycle.review_snapshot(repo)
    if mutation == "content":
        tracked.write_text("value = 3\n")
    elif mutation == "staging":
        subprocess.run(["git", "add", "existing.py"], cwd=repo, check=True)
    elif mutation == "mode":
        os.chmod(tracked, 0o755)
    elif mutation == "deletion":
        tracked.unlink()
    else:
        (repo / "added.txt").write_text("new")
        subprocess.run(["git", "add", "added.txt"], cwd=repo, check=True)
    assert cycle.review_snapshot(repo) != before


def test_review_snapshot_hashes_untracked_content_without_following_symlinks(tmp_path):
    """Same Git path listing cannot hide untracked edits or a changed symlink target."""
    import subprocess

    repo = tmp_path / "repo"
    _disposable_git_repo(repo)
    extra = repo / "untracked.txt"
    extra.write_text("first")
    before = cycle.review_snapshot(repo)
    extra.write_text("other")
    assert cycle.review_snapshot(repo) != before
    extra.unlink()
    private = tmp_path / "outside.txt"
    private.write_text("private fixture")
    extra.symlink_to(private)
    linked = cycle.review_snapshot(repo)
    private.write_text("different private fixture")
    assert cycle.review_snapshot(repo) == linked  # Only link metadata, never target contents.
    extra.unlink()
    extra.symlink_to(tmp_path / "other-outside.txt")
    assert cycle.review_snapshot(repo) != linked
    assert (
        subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        == "?? untracked.txt\n"
    )


def test_review_snapshot_fails_closed_when_untracked_content_exceeds_limit(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    _disposable_git_repo(repo)
    (repo / "large.bin").write_bytes(b"abcd")
    monkeypatch.setattr(cycle, "REVIEW_UNTRACKED_FILE_LIMIT", 3)
    with pytest.raises(cycle.CycleError, match="too large"):
        cycle.review_snapshot(repo)


def test_untracked_file_mutation_by_readonly_reviewer_blocks_before_next_review(
    monkeypatch, tmp_path
):
    """An unchanged untracked path listing cannot produce a reviewer approval."""
    import subprocess

    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "mem_available", lambda: 1900)
    repo = tmp_path / "repo"
    _disposable_git_repo(repo)
    extra = repo / "untracked.txt"
    extra.write_text("first")
    monkeypatch.setattr(cycle, "workspace", lambda *_: repo)
    monkeypatch.setattr(cycle, "safe_worktree", lambda *_: None)
    job = "untracked-mutation-guard"
    root = cycle.job_path(job)
    root.mkdir(parents=True)
    (root / "brief.md").write_text("Require content integrity for independent read-only reviews.")
    cycle.atomic_json(
        root / "status.json",
        {
            "phase": "planned",
            "baseline_commit": "a" * 40,
            "ready_for_user": False,
            "reviews": {},
            "gate": {},
        },
    )
    roles = []

    def reviewer(role, _prompt, _dest, _evidence, *, read_only):
        roles.append(role)
        if read_only:
            extra.write_text("other")
            return {
                "verdict": {"verdict": "pass", "findings": []},
                "reported_tokens": 123,
                "model": "gpt-6-luna",
                "tier": "economy",
                "routing_reason": "routine",
            }
        return {"role": role}

    monkeypatch.setattr(cycle, "codex", reviewer)
    monkeypatch.setattr(cycle, "deterministic_gates", lambda *_: {"offline": {"pass": True}})
    before = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout
    result = cycle.run(job, 1, live=True)
    after = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout
    assert before == after
    assert roles == ["builder", "generality"]
    assert result["phase"] == "blocked"
    assert result["ready_for_user"] is False
    assert result["reviews"] == {}
    assert len(result["token_usage"]["sessions"]) == 1
    assert result["token_usage"]["sessions"][0]["ended_at"].endswith("+00:00")
    without_time = [
        {key: value for key, value in entry.items() if key != "ended_at"}
        for entry in result["token_usage"]["sessions"]
    ]
    assert without_time == [
        {
            "role": "generality",
            "round": 1,
            "model": "gpt-6-luna",
            "tier": "economy",
            "reason": "routine",
            "reported_tokens": 123,
        }
    ]


def test_semantic_qa_knows_own_review_cannot_depend_on_future_reviewers():
    qa_contract = (cycle.ROLES / "testing.md").read_text()
    assert "future reviewer" in qa_contract
    assert "Never mark the feature FAIL or BLOCKED" in qa_contract
    assert "--acceptance tooling" in qa_contract
    assert "--acceptance product" in qa_contract


@pytest.mark.parametrize(
    ("profile", "risk", "expected"),
    [
        ("tooling", "normal", ("generality", "quality")),
        ("tooling", "high", cycle.REVIEW_ROLES),
        ("tooling", "critical", cycle.REVIEW_ROLES),
        ("product", "normal", cycle.REVIEW_ROLES),
        ("product", "high", cycle.REVIEW_ROLES),
        ("product", "critical", cycle.REVIEW_ROLES),
    ],
)
def test_risk_based_review_minimums_never_skip_product_or_high_risk_roles(profile, risk, expected):
    assert cycle.select_review_roles({"acceptance_profile": profile, "risk": risk}) == expected


def test_default_product_budget_refuses_before_starting_builder(monkeypatch, tmp_path):
    """Default 110k cannot possibly fund full product audit after a Builder."""
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "mem_available", lambda: 1900)
    monkeypatch.setattr(
        cycle,
        "workspace",
        lambda *_: pytest.fail("Worktree would spend host IO on an impossible budget"),
    )
    job = "product-budget-preflight"
    home = cycle.job_path(job)
    home.mkdir(parents=True)
    (home / "brief.md").write_text("No model should launch at an impossible budget.")
    cycle.atomic_json(
        home / "status.json",
        {
            "phase": "planned",
            "baseline_commit": "a" * 40,
            "implemented_by": "codex",
            "acceptance_profile": "product",
            "risk": "normal",
            "reported_token_budget": 110000,
            "token_usage": {"reported_total": 0, "sessions": []},
            "reviews": {},
            "gate": {},
            "ready_for_user": False,
        },
    )
    result = cycle.run(job, 2, live=True)
    assert result["phase"] == "blocked_insufficient_review_budget"
    assert result["ready_for_user"] is False
    quote = result["review_plan"]
    assert quote["roles"] == list(cycle.REVIEW_ROLES)
    assert quote["omitted_roles"] == []
    assert quote["minimum_remaining_reported_tokens"] == 245000
    assert quote["reported_token_budget"] == 110000
    assert not quote["can_start"]
    assert result["token_usage"]["sessions"] == []


def test_routine_tooling_budget_preflight_has_true_multi_role_reservation():
    status = {
        "acceptance_profile": "tooling",
        "risk": "normal",
        "implemented_by": "chatgpt",
        "reported_token_budget": 110000,
        "token_usage": {"reported_total": 0, "sessions": []},
    }
    quote = cycle.review_budget_quote(status)
    assert quote["can_start"] is True
    assert quote["roles"] == ["generality", "quality"]
    assert [row["role"] for row in quote["omitted_roles"]] == ["testing", "performance"]
    assert quote["minimum_by_role"] == {"generality": 55000, "quality": 45000}
    assert quote["minimum_remaining_reported_tokens"] == 100000
    assert cycle.review_budget_quote(status, include_builder=True)["can_start"] is False
    status["token_usage"]["reported_total"] = 70000
    assert not cycle.review_budget_quote(status)["can_start"]


def test_remaining_review_budget_reserves_all_outstanding_roles(tmp_path):
    state = {
        "reported_token_budget": 110000,
        "token_usage": {"reported_total": 44000},
        "acceptance_profile": "tooling",
        "risk": "normal",
    }
    cycle.check_review_reserve("safe-budget-test", state, ("quality",))
    with pytest.raises(cycle.CycleError, match="Review reservation shortfall"):
        cycle.check_review_reserve("safe-budget-test", state, ("generality", "quality"))


def test_resume_review_quote_without_completed_reviewers_keeps_full_reservation():
    state = {
        "phase": "paused_daily_budget",
        "resume_checkpoint": {"stage": "reviewing"},
        "reviews": {},
    }
    quote = {
        "roles": ["generality", "quality", "testing"],
        "minimum_by_role": {"generality": 55, "quality": 45, "testing": 35},
        "minimum_remaining_reported_tokens": 135,
        "reported_tokens_available": 120,
        "can_start": False,
    }

    remaining = cycle.remaining_resume_review_quote(state, quote)

    assert remaining["completed_roles"] == []
    assert remaining["roles"] == ["generality", "quality", "testing"]
    assert remaining["minimum_by_role"] == {
        "generality": 55,
        "quality": 45,
        "testing": 35,
    }
    assert remaining["minimum_remaining_reported_tokens"] == 135
    assert remaining["can_start"] is False


def test_resume_review_quote_deducts_completed_prefix_without_mutating_inputs():
    state = {
        "phase": "paused_daily_budget",
        "resume_checkpoint": {"stage": "reviewing"},
        "reviews": {"generality": {"verdict": "pass"}},
    }
    quote = {
        "roles": ["generality", "quality", "testing"],
        "minimum_by_role": {"generality": 55, "quality": 45, "testing": 35},
        "minimum_remaining_reported_tokens": 135,
        "reported_tokens_available": 80,
        "can_start": False,
    }
    original_state = {
        **state,
        "resume_checkpoint": dict(state["resume_checkpoint"]),
        "reviews": dict(state["reviews"]),
    }
    original_quote = {
        **quote,
        "roles": list(quote["roles"]),
        "minimum_by_role": dict(quote["minimum_by_role"]),
    }

    remaining = cycle.remaining_resume_review_quote(state, quote)

    assert remaining["completed_roles"] == ["generality"]
    assert remaining["roles"] == ["quality", "testing"]
    assert remaining["minimum_by_role"] == {"quality": 45, "testing": 35}
    assert remaining["minimum_remaining_reported_tokens"] == 80
    assert remaining["can_start"] is True
    assert state == original_state
    assert quote == original_quote
    assert remaining is not quote
    assert remaining["roles"] is not quote["roles"]
    assert remaining["minimum_by_role"] is not quote["minimum_by_role"]


def test_resume_review_quote_rejects_out_of_order_completed_reviewers():
    state = {
        "phase": "paused_daily_budget",
        "resume_checkpoint": {"stage": "reviewing"},
        "reviews": {"quality": {"verdict": "pass"}},
    }
    quote = {
        "roles": ["generality", "quality", "testing"],
        "minimum_by_role": {"generality": 55, "quality": 45, "testing": 35},
        "minimum_remaining_reported_tokens": 135,
        "reported_tokens_available": 120,
        "can_start": False,
    }

    with pytest.raises(cycle.CycleError, match="out-of-order or unknown"):
        cycle.remaining_resume_review_quote(state, quote)


def test_tooling_high_risk_must_not_masquerade_as_low_risk_for_cost_savings(monkeypatch, tmp_path):
    policy_path = tmp_path / "policy.json"
    import json

    original = json.loads(cycle.MODEL_POLICY.read_text())
    original["required_reviews"]["product"]["normal"] = ["generality", "quality"]
    policy_path.write_text(json.dumps(original))
    monkeypatch.setattr(cycle, "MODEL_POLICY", policy_path)
    with pytest.raises(cycle.CycleError, match="requires all"):
        cycle.model_policy()
    original["required_reviews"]["product"]["normal"] = list(cycle.REVIEW_ROLES)
    original["required_reviews"]["tooling"]["high"] = ["generality", "quality"]
    policy_path.write_text(json.dumps(original))
    with pytest.raises(cycle.CycleError, match="requires all"):
        cycle.model_policy()


def test_routine_tooling_zero_cost_mock_checks_only_selected_independent_roles(
    monkeypatch, tmp_path, mocked_review_snapshot
):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle, "mem_available", lambda: 2000)
    monkeypatch.setattr(cycle, "workspace", lambda *_: tmp_path / "isolated")
    monkeypatch.setattr(cycle, "safe_worktree", lambda *_: None)
    (tmp_path / "isolated").mkdir()
    job = "routed-two-roles"
    path = cycle.job_path(job)
    path.mkdir(parents=True)
    (path / "brief.md").write_text(
        "A pre-implemented low-risk tooling change under independent review."
    )
    cycle.atomic_json(
        path / "status.json",
        {
            "phase": "planned",
            "baseline_commit": "b" * 40,
            "implemented_by": "chatgpt",
            "review_base": "a" * 40,
            "feature_commit": "b" * 40,
            "acceptance_profile": "tooling",
            "risk": "normal",
            "reported_token_budget": 110000,
            "token_usage": {"reported_total": 0, "sessions": []},
            "ready_for_user": False,
            "reviews": {},
            "gate": {},
        },
    )
    monkeypatch.setattr(
        cycle,
        "running",
        lambda args, **_kw: type(
            "Git",
            (),
            {
                "returncode": 0,
                "stdout": "ops/agent-team/builder.md\\0" if "--name-only" in args else "",
            },
        )(),
    )
    roles = []

    def reviewer(role, *_args, **_kwargs):
        roles.append(role)
        return {"verdict": {"verdict": "pass", "findings": []}}

    monkeypatch.setattr(cycle, "codex", reviewer)
    monkeypatch.setattr(cycle, "deterministic_gates", lambda *_: {"offline": {"pass": True}})
    state = cycle.run(job, 1, live=True)
    assert roles == ["generality", "quality"]
    assert state["phase"] == "reviewed_tooling_ready"
    assert state["ready_for_user"] is True
    assert state["review_plan"]["roles"] == roles
    assert len(state["review_plan"]["omitted_roles"]) == 2
    assert state["review_artifacts"].keys() == set(roles)
    assert state["gate"]["offline"]["pass"] is True


@pytest.mark.parametrize(
    ("paths", "risk", "expected"),
    [
        (("ops/agent-team/README.md",), "normal", ("generality", "quality")),
        (("ops/agent-team/pilot-budget-preflight-proof.md",), "normal", ("generality", "quality")),
        (("scripts/odyssey_agent_cycle.py",), "high", cycle.REVIEW_ROLES),
        (("ops/agent-team/model-policy.json",), "high", cycle.REVIEW_ROLES),
        (("ops/agent-team/quality.md",), "high", cycle.REVIEW_ROLES),
        (("ops/agent-team/testing.md",), "high", cycle.REVIEW_ROLES),
        (("ops/agent-team/review.schema.json",), "high", cycle.REVIEW_ROLES),
    ],
)
def test_security_sensitive_tooling_files_auto_escalate_actual_review_scope(
    monkeypatch, tmp_path, paths, risk, expected
):
    monkeypatch.setattr(cycle, "touched_paths", lambda _dest, _base: paths)
    state = {
        "risk": "normal",
        "acceptance_profile": "tooling",
        "review_base": "a" * 40,
        "baseline_commit": "b" * 40,
        "reported_token_budget": 110000,
        "token_usage": {"reported_total": 0, "sessions": []},
    }
    chosen, triggering_files = cycle.effective_review_risk(state, tmp_path)
    assert chosen == risk
    assert set(triggering_files).issubset(paths)
    assert cycle.select_review_roles(state, tmp_path) == expected
    quote = cycle.review_budget_quote(state, dest=tmp_path)
    assert quote["effective_risk"] == risk
    if risk == "high":
        assert quote["can_start"] is False
        assert quote["minimum_remaining_reported_tokens"] == 205000
        assert cycle.select_agent_model("generality", state, tmp_path)["model"] == "gpt-6-sol"
    else:
        assert quote["can_start"] is True
        assert quote["minimum_remaining_reported_tokens"] == 100000


def test_sensitive_policy_catalog_cannot_omit_core_supervisor_code(monkeypatch, tmp_path):
    import json

    policy = cycle.model_policy()
    policy["security_sensitive_tooling_paths"].remove("scripts/odyssey_agent_cycle.py")
    filename = tmp_path / "insecure.json"
    filename.write_text(json.dumps(policy))
    monkeypatch.setattr(cycle, "MODEL_POLICY", filename)
    with pytest.raises(cycle.CycleError, match="cannot be weakened"):
        cycle.model_policy()


def test_daily_only_mode_keeps_all_reviewers_and_daily_session_preflight(monkeypatch):
    """Disabling E4's aggregate cap must not disable safety or four reviewer roles."""
    policy = cycle.model_policy()
    state = {
        "acceptance_profile": "product",
        "risk": "high",
        "reported_token_budget": 0,
        "token_usage": {"reported_total": 900000, "sessions": []},
    }
    monkeypatch.setattr(cycle, "effective_review_risk", lambda _state, _dest=None: ("high", []))
    quote = cycle.review_budget_quote(state)
    assert quote["daily_only_budget"] is True
    assert quote["reported_tokens_available"] is None
    assert quote["can_start"] is True
    assert set(quote["roles"]) == set(cycle.REVIEW_ROLES)
    cycle.check_review_reserve("daily-only-test", state, cycle.REVIEW_ROLES)
    assert cycle.remaining_resume_review_quote(
        {
            **state,
            "phase": "paused_daily_budget",
            "resume_checkpoint": {"stage": "reviewing"},
            "reviews": {},
        },
        quote,
    )["can_start"]
    # The per-job cap is absent, but daily pacing remains a separate mandatory
    # launch guard in codex() and run(), checked on every agent session.
    assert policy["minimum_session_headroom"] > 0


def test_daily_only_codex_session_still_obeys_shared_daily_pacing(monkeypatch, tmp_path):
    """A zero job cap cannot reach the model launcher after daily refusal."""
    state = {
        "reported_token_budget": 0,
        "token_usage": {"reported_total": 900000, "sessions": []},
    }
    monkeypatch.setattr(cycle, "require_budget", lambda _job: None)
    monkeypatch.setattr(cycle, "load", lambda _job: state)

    def refuse_daily_start():
        raise cycle.DailyBudgetPause("daily pacing exhausted")

    monkeypatch.setattr(cycle, "require_daily_model_start", refuse_daily_start)
    monkeypatch.setattr(
        cycle,
        "probe_native_profile",
        lambda *_args, **_kwargs: pytest.fail("Model scope probe ran after daily refusal"),
    )
    with pytest.raises(cycle.DailyBudgetPause, match="daily pacing exhausted"):
        cycle.codex("generality", "review", tmp_path, tmp_path, read_only=True)
