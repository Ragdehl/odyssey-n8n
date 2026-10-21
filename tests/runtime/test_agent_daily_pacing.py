"""Offline tests for Odyssey's cross-job daily Codex pacing approximation.

Never confuses CLI-reported tokens with the ChatGPT account's actual quota.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scripts import odyssey_agent_cycle as cycle
from scripts import odyssey_agent_pacing as pacing


def _session(path: Path, role: str, tokens: int, stamp: str | None) -> None:
    path.mkdir(parents=True, exist_ok=True)
    entry = {"role": role, "reported_tokens": tokens}
    if stamp is not None:
        entry["ended_at"] = stamp
    (path / "status.json").write_text(
        json.dumps({"token_usage": {"reported_total": tokens, "sessions": [entry]}})
    )


def test_unconfigured_never_claims_account_allowance(tmp_path):
    report = pacing.status(tmp_path)
    assert report["configured"] is False
    assert report["can_start_next_model"] is False
    assert report["account_quota_verified"] is False
    assert report["automatic_resume_available"] is False
    assert report["daily_cap_reported_tokens"] is None
    with pytest.raises(pacing.PacingError, match="no explicit"):
        pacing.require_session_headroom(tmp_path)


def test_weekly_proxy_calculates_a_seven_day_distribution_with_reserved_share(tmp_path):
    policy = pacing.configure(tmp_path, 700_000, 20)
    assert policy["daily_reported_cap"] == 80_000
    assert (tmp_path / pacing.POLICY_NAME).stat().st_mode & 0o777 == 0o600
    report = pacing.status(tmp_path)
    assert report["weekly_reported_proxy"] == 700_000
    assert report["reserve_percent"] == 20
    assert report["daily_cap_reported_tokens"] == 80_000
    assert report["remaining_reported_tokens_today"] == 80_000
    assert report["can_start_next_model"] is True
    assert report["account_quota_verified"] is False


@pytest.mark.parametrize(
    "weekly,reserve",
    [
        (None, 20),
        (False, 20),
        (1, 20),
        (99999, 20),
        (10_000_001, 20),
        (700_000, 51),
        (700_000, -1),
        (700_000, True),
        (100_000, 20),
    ],
)
def test_invalid_pacing_settings_fail_closed_without_writing_files(tmp_path, weekly, reserve):
    with pytest.raises(pacing.PacingError):
        pacing.configure(tmp_path, weekly, reserve)
    assert not (tmp_path / pacing.POLICY_NAME).exists()


def test_all_jobs_share_one_day_limit_across_roles_and_sessions(tmp_path):
    pacing.configure(tmp_path, 700_000, 20)
    now = datetime.now(ZoneInfo("Europe/Paris"))
    stamp = now.isoformat(timespec="seconds")
    _session(tmp_path / "agent-job-one", "builder", 47_400, stamp)
    _session(tmp_path / "agent-job-two", "generality", 34_377, stamp)
    report = pacing.status(tmp_path)
    assert report["reported_tokens_today"] == 81_777
    assert report["model_sessions_today"] == 2
    assert report["remaining_reported_tokens_today"] == 0
    assert report["can_start_next_model"] is False
    with pytest.raises(pacing.PacingError, match="exhausted"):
        pacing.require_session_headroom(tmp_path)


def test_cross_midnight_session_belongs_to_ending_local_day_and_resets_next_day(tmp_path):
    pacing.configure(tmp_path, 700_000, 20)
    # Local Paris midnight is UTC 22:00 when summer time is active.
    stamp = "2026-10-19T22:30:00+00:00"
    _session(tmp_path / "job", "builder", 47_400, stamp)
    current = pacing.status(tmp_path, instant=datetime(2026, 10, 19, 21, 30, tzinfo=UTC))
    next_day = pacing.status(tmp_path, instant=datetime(2026, 10, 20, 22, 30, tzinfo=UTC))
    assert current["reported_tokens_today"] == 0
    assert next_day["reported_tokens_today"] == 0
    on_the_day = pacing.status(tmp_path, instant=datetime(2026, 10, 20, 12, tzinfo=UTC))
    assert on_the_day["reported_tokens_today"] == 47_400


def test_legacy_sessions_today_are_conservatively_counted_without_faking_account_quota(tmp_path):
    pacing.configure(tmp_path, 700_000, 20)
    folder = tmp_path / "historical"
    _session(folder, "quality", 153_831, None)
    doc = json.loads((folder / "status.json").read_text())
    doc["updated_at"] = datetime.now(ZoneInfo("Europe/Paris")).isoformat()
    (folder / "status.json").write_text(json.dumps(doc))
    result = pacing.status(tmp_path)
    assert result["reported_tokens_today"] == 153_831
    assert result["legacy_conservative_tokens_today"] == 153_831
    assert result["can_start_next_model"] is False
    assert result["account_quota_verified"] is False


def test_legacy_sessions_from_an_older_day_are_not_misattributed_today(tmp_path):
    pacing.configure(tmp_path, 700_000, 20)
    folder = tmp_path / "historical"
    _session(folder, "quality", 153_831, None)
    doc = json.loads((folder / "status.json").read_text())
    doc["updated_at"] = "2026-10-18T13:25:00+02:00"
    (folder / "status.json").write_text(json.dumps(doc))
    result = pacing.status(tmp_path, instant=datetime(2026, 10, 19, 13, tzinfo=UTC))
    assert result["reported_tokens_today"] == 0
    assert result["legacy_conservative_tokens_today"] == 0


def test_unattributable_legacy_sessions_block_quota_calculation(tmp_path):
    pacing.configure(tmp_path, 700_000, 20)
    _session(tmp_path / "no-activity-dates", "builder", 41_000, None)
    with pytest.raises(pacing.PacingError, match="reliable"):
        pacing.status(tmp_path)


def test_malformed_or_symlinked_policy_blocks_pacing(tmp_path):
    (tmp_path / pacing.POLICY_NAME).write_text("{BROKEN")
    with pytest.raises(pacing.PacingError):
        pacing.status(tmp_path)
    (tmp_path / pacing.POLICY_NAME).unlink()
    (tmp_path / pacing.POLICY_NAME).symlink_to("/etc/hosts")
    with pytest.raises(pacing.PacingError, match="symlink"):
        pacing.status(tmp_path)


def test_malformed_session_tracking_fails_closed(tmp_path):
    pacing.configure(tmp_path, 700_000, 20)
    (tmp_path / "malformed").mkdir()
    (tmp_path / "malformed/status.json").write_text(
        '{"token_usage":{"sessions":[{"ended_at":"today","reported_tokens":-3}]}}'
    )
    with pytest.raises(pacing.PacingError):
        pacing.status(tmp_path)


def test_existing_no_config_real_cli_entrypoint_refuses_live_without_models(monkeypatch, tmp_path):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    called = []
    monkeypatch.setattr(cycle, "run", lambda *_args, **_kwargs: called.append(True))
    monkeypatch.setattr(
        cycle.sys,
        "argv",
        ["odyssey_agent_cycle.py", "run", "--job", "nonexistent-fixture", "--live"],
    )
    assert cycle.main() == 2
    assert called == []


def test_codex_usage_receipt_has_an_ended_at_for_cross_job_accounting(monkeypatch, tmp_path):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    job = "new-paced-job"
    cycle.job_path(job).mkdir(parents=True)
    state = {
        "phase": "reviewing",
        "round": 1,
        "reported_token_budget": 200_000,
        "token_usage": {"reported_total": 0, "sessions": []},
    }
    cycle.atomic_json(cycle.job_path(job) / "status.json", state)
    cycle.record_agent_usage(
        job,
        state,
        "quality",
        {
            "role": "quality",
            "reported_tokens": 15_000,
            "model": "gpt-6-luna",
            "tier": "economy",
        },
    )
    entry = cycle.load(job)["token_usage"]["sessions"][0]
    assert entry["reported_tokens"] == 15_000
    assert entry["ended_at"].endswith("+00:00")
    assert pacing.usage_today(cycle.STATE)["tokens"] == 15_000


def test_cross_job_daily_cap_refuses_new_codex_process_before_start(monkeypatch, tmp_path):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    pacing.configure(cycle.STATE, 700_000, 20)
    _session(
        cycle.STATE / "previous-agent-job",
        "builder",
        72_000,
        datetime.now(ZoneInfo("Europe/Paris")).isoformat(),
    )
    job = "different-agent-job"
    folder = cycle.job_path(job)
    (folder / "round-1").mkdir(parents=True)
    cycle.atomic_json(
        folder / "status.json",
        {
            "phase": "implementing",
            "round": 1,
            "risk": "normal",
            "baseline_commit": "b" * 40,
            "reported_token_budget": 210_000,
            "token_usage": {"reported_total": 0, "sessions": []},
        },
    )
    monkeypatch.setattr(cycle, "mem_available", lambda: 1800)
    monkeypatch.setattr(
        cycle,
        "select_agent_model",
        lambda *_: {
            "model": "gpt-6-luna",
            "effort": "low",
            "tier": "economy",
            "reason": "routine",
            "changed_files_count": 0,
        },
    )
    monkeypatch.setattr(
        cycle.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("Must not launch Codex above global daily budget"),
    )
    with pytest.raises(cycle.CycleError, match="Daily reported-token pacing exhausted"):
        cycle.codex(
            "builder", "Synthetic denied session", tmp_path, folder / "round-1", read_only=False
        )
    assert cycle.load(job)["token_usage"]["reported_total"] == 0


def test_cli_pace_report_is_read_only_and_does_not_trigger_model_calls(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(cycle, "STATE", tmp_path / "runs")
    monkeypatch.setattr(cycle.sys, "argv", ["odyssey_agent_cycle.py", "pace"])
    monkeypatch.setattr(
        cycle.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("Pace status must never launch a subprocess"),
    )
    assert cycle.main() == 0
    response = json.loads(capsys.readouterr().out)
    assert response["configured"] is False
    assert response["account_quota_verified"] is False
    assert not (cycle.STATE / pacing.POLICY_NAME).exists()


def test_one_day_operator_exception_only_applies_to_exact_local_date(tmp_path):
    pacing.configure(tmp_path, 700_000, 20)
    file = tmp_path / pacing.ONE_DAY_EXCEPTION_NAME
    file.write_text(
        json.dumps(
            {
                "version": 1,
                "local_day": "2026-10-21",
                "daily_cap_reported_tokens": 10_000_000,
                "reason": pacing.ONE_DAY_EXCEPTION_REASON,
            }
        )
    )
    file.chmod(0o600)
    within = pacing.status(tmp_path, instant=datetime(2026, 10, 21, 10, tzinfo=UTC))
    assert within["one_day_local_exception_active"] is True
    assert within["daily_cap_reported_tokens"] == 10_000_000
    assert within["ordinary_daily_cap_reported_tokens"] == 80_000
    assert within["account_quota_verified"] is False
    after = pacing.status(tmp_path, instant=datetime(2026, 10, 22, 10, tzinfo=UTC))
    assert after["daily_cap_reported_tokens"] == 80_000
    assert after["one_day_local_exception_active"] is False


@pytest.mark.parametrize(
    "reason,cap,date",
    [
        ("fabricated_permission", 10_000_000, "2026-10-21"),
        (pacing.ONE_DAY_EXCEPTION_REASON, 10_000_001, "2026-10-21"),
        (pacing.ONE_DAY_EXCEPTION_REASON, True, "2026-10-21"),
        (pacing.ONE_DAY_EXCEPTION_REASON, 10_000_000, "2026-10-20"),
    ],
)
def test_invalid_one_day_exception_fails_closed(tmp_path, reason, cap, date):
    pacing.configure(tmp_path, 700_000, 20)
    file = tmp_path / pacing.ONE_DAY_EXCEPTION_NAME
    file.write_text(
        json.dumps(
            {
                "version": 1,
                "local_day": date,
                "daily_cap_reported_tokens": cap,
                "reason": reason,
            }
        )
    )
    file.chmod(0o600)
    snapshot = pacing.status(tmp_path, instant=datetime(2026, 10, 21, 10, tzinfo=UTC))
    assert snapshot["daily_cap_reported_tokens"] == 80_000
    assert snapshot["one_day_local_exception_active"] is False


def test_world_readable_exception_is_not_accepted(tmp_path):
    pacing.configure(tmp_path, 700_000, 20)
    file = tmp_path / pacing.ONE_DAY_EXCEPTION_NAME
    file.write_text(
        json.dumps(
            {
                "version": 1,
                "local_day": "2026-10-21",
                "daily_cap_reported_tokens": 10_000_000,
                "reason": pacing.ONE_DAY_EXCEPTION_REASON,
            }
        )
    )
    file.chmod(0o644)
    assert pacing.one_day_exception_cap(tmp_path, day="2026-10-21") is None
