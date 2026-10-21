#!/usr/bin/env python3
"""Conservative local Codex pacing proxy. Not ChatGPT account quota telemetry.

Uses CLI-*reported* tokens and a user-chosen weekly proxy. No model/provider
calls. No OAuth, private notes, Cloudflare, or user account usage endpoint.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DEFAULT_ZONE = "Europe/Paris"
POLICY_NAME = "agent-pacing-policy.json"
ONE_DAY_EXCEPTION_NAME = "agent-pacing-one-day-exception.json"
ONE_DAY_EXCEPTION_REASON = "explicit_user_authorization_one_day_only"
VERSION = 1
MAX_WEEKLY_REPORTED = 10_000_000
MIN_WEEKLY_REPORTED = 100_000


class PacingError(RuntimeError):
    pass


def _safe_file(parent: Path, file: Path) -> None:
    if parent.is_symlink() or file.is_symlink():
        raise PacingError("Refusing symlinked agent pacing paths")


def _valid_policy(data: dict) -> dict:
    if not isinstance(data, dict) or data.get("version") != VERSION:
        raise PacingError("Invalid stored pacing policy")
    weekly = data.get("weekly_reported_proxy")
    reserve = data.get("reserve_percent")
    zone = data.get("timezone")
    if (
        isinstance(weekly, bool)
        or not isinstance(weekly, int)
        or not MIN_WEEKLY_REPORTED <= weekly <= MAX_WEEKLY_REPORTED
        or isinstance(reserve, bool)
        or not isinstance(reserve, int)
        or not 0 <= reserve <= 50
        or zone != DEFAULT_ZONE
    ):
        raise PacingError("Unapproved or invalid pacing policy")
    cap = weekly * (100 - reserve) // 700
    if cap < 40_000:
        raise PacingError("Daily cap would be below the minimum model-session reserve")
    return {**data, "daily_reported_cap": cap}


def load_policy(state_dir: Path, *, required: bool = False) -> dict | None:
    file = state_dir / POLICY_NAME
    _safe_file(state_dir, file)
    if not file.exists():
        if required:
            raise PacingError(
                "No local daily pacing policy: configure a weekly REPORTED-token "
                "proxy first; this is NOT the account's weekly quota"
            )
        return None
    try:
        value = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PacingError("Cannot read trusted pacing policy") from error
    return _valid_policy(value)


def configure(state_dir: Path, weekly_reported_proxy: int, reserve_percent: int = 20) -> dict:
    """One-time, explicit operator configuration; NOT automatically inferred."""
    raw = {
        "version": VERSION,
        "weekly_reported_proxy": weekly_reported_proxy,
        "reserve_percent": reserve_percent,
        "timezone": DEFAULT_ZONE,
        "calibration": "local_codex_cli_reported_tokens_only",
    }
    policy = _valid_policy(raw)
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = state_dir / POLICY_NAME
    _safe_file(state_dir, target)
    temporary = state_dir / (POLICY_NAME + ".tmp")
    if temporary.is_symlink():
        raise PacingError("Refusing symlinked pacing policy draft")
    # Explicit 0600 mode, and owner-only parent. No account or provider secrets.
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(raw, stream, indent=2)
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return policy


def local_day(instant: datetime | None = None) -> str:
    zone = ZoneInfo(DEFAULT_ZONE)
    moment = instant or datetime.now(zone)
    if moment.tzinfo is None:
        raise PacingError("An aware timestamp is required")
    return moment.astimezone(zone).date().isoformat()


def usage_today(state_dir: Path, *, day: str | None = None) -> dict:
    """Count sessions from ALL agent jobs, not only the current feature."""
    date = day or local_day()
    spent = 0
    count = 0
    legacy_attributed = 0
    # STATE is owned by the trusted operator, not available to Codex shell.
    if state_dir.is_symlink():
        raise PacingError("Refusing symlinked usage state")
    if not state_dir.exists():
        return {
            "local_day": date,
            "tokens": spent,
            "sessions": count,
            "legacy_conservative_tokens": legacy_attributed,
        }
    for job_dir in state_dir.iterdir():
        if not job_dir.is_dir() or job_dir.is_symlink():
            continue
        status = job_dir / "status.json"
        if not status.exists():
            continue
        if status.is_symlink():
            raise PacingError("Refusing symlinked job accounting")
        try:
            data = json.loads(status.read_text(encoding="utf-8"))
            entries = data.get("token_usage", {}).get("sessions", [])
            if not isinstance(entries, list):
                raise ValueError("bad-session-list")
            for item in entries:
                if not isinstance(item, dict):
                    raise ValueError("bad-session")
                number = item.get("reported_tokens")
                if isinstance(number, bool) or not isinstance(number, int) or number < 0:
                    raise ValueError("bad-tokens")
                stamp = item.get("ended_at")
                legacy = stamp is None
                if legacy:
                    # Old pilot ledgers lack per-session timestamps. Assign
                    # their entire spend to the job's LAST modified local day
                    # to fail conservatively rather than reporting a false
                    # zero when the weekly pacing policy is first installed.
                    stamp = data.get("updated_at") or data.get("created_at")
                    if not stamp:
                        raise ValueError("unattributable-historical-agent-usage")
                if not isinstance(stamp, str):
                    raise ValueError("bad-date")
                observed = datetime.fromisoformat(stamp)
                if local_day(observed) == date:
                    spent += number
                    count += 1
                    if legacy:
                        legacy_attributed += number
        except (OSError, ValueError, TypeError) as error:
            raise PacingError("Cannot establish reliable local agent usage") from error
    return {
        "local_day": date,
        "tokens": spent,
        "sessions": count,
        "legacy_conservative_tokens": legacy_attributed,
    }


def one_day_exception_cap(state_dir: Path, *, day: str) -> int | None:
    """Honor only a trusted, date-bound, user-authorized local pacing exception.

    This does not affect upstream model usage allowances or any provider limit.
    A stale, unreadable, malformed, or untrusted file never grants extra headroom.
    """
    path = state_dir / ONE_DAY_EXCEPTION_NAME
    _safe_file(state_dir, path)
    if not path.is_file():
        return None
    try:
        if path.stat().st_mode & 0o077:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or set(data) != {
        "version",
        "local_day",
        "daily_cap_reported_tokens",
        "reason",
    }:
        return None
    amount = data["daily_cap_reported_tokens"]
    if (
        type(data["version"]) is not int
        or data["version"] != 1
        or data["local_day"] != day
        or data["reason"] != ONE_DAY_EXCEPTION_REASON
        or type(amount) is not int
        or not 40_000 <= amount <= 10_000_000
    ):
        return None
    return amount


def status(state_dir: Path, *, instant: datetime | None = None) -> dict:
    policy = load_policy(state_dir)
    usage = usage_today(state_dir, day=local_day(instant))
    if policy is None:
        return {
            "configured": False,
            "local_day": usage["local_day"],
            "reported_tokens_today": usage["tokens"],
            "legacy_conservative_tokens_today": usage["legacy_conservative_tokens"],
            "daily_cap_reported_tokens": None,
            "can_start_next_model": False,
            "why": "operator must configure a weekly reported-token PROXY",
            "account_quota_verified": False,
            "automatic_resume_available": False,
        }
    ordinary_cap = policy["daily_reported_cap"]
    authorized_exception = one_day_exception_cap(state_dir, day=usage["local_day"])
    cap = max(ordinary_cap, authorized_exception or 0)
    remaining = max(0, cap - usage["tokens"])
    return {
        "configured": True,
        "local_day": usage["local_day"],
        "timezone": DEFAULT_ZONE,
        "weekly_reported_proxy": policy["weekly_reported_proxy"],
        "reserve_percent": policy["reserve_percent"],
        "daily_cap_reported_tokens": cap,
        "one_day_local_exception_active": authorized_exception is not None and cap > ordinary_cap,
        "ordinary_daily_cap_reported_tokens": ordinary_cap,
        "reported_tokens_today": usage["tokens"],
        "legacy_conservative_tokens_today": usage["legacy_conservative_tokens"],
        "model_sessions_today": usage["sessions"],
        "remaining_reported_tokens_today": remaining,
        "can_start_next_model": remaining >= 40_000,
        "account_quota_verified": False,
        "scope": "only local Codex sessions recorded by Odyssey supervisor",
        "automatic_resume_available": False,
        "note": (
            "Soft per-session headroom; model use may overshoot before telemetry arrives. "
            "No real ChatGPT/Work five-hour or weekly allowance is observable here."
        ),
    }


def require_session_headroom(state_dir: Path, *, minimum: int = 40_000) -> dict:
    snapshot = status(state_dir)
    if not snapshot["configured"]:
        raise PacingError("Cannot launch agents: no explicit daily pacing configured")
    if snapshot["remaining_reported_tokens_today"] < minimum:
        raise PacingError(
            "Daily reported-token pacing exhausted; stop before next model session. "
            "This job needs a resumable checkpoint before running another day."
        )
    return snapshot


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--state-dir", type=Path, required=True)
    cli.add_argument("--weekly-reported-proxy", type=int)
    cli.add_argument("--reserve-percent", type=int, default=20)
    opts = cli.parse_args()
    try:
        if opts.weekly_reported_proxy is not None:
            configure(opts.state_dir, opts.weekly_reported_proxy, opts.reserve_percent)
        print(json.dumps(status(opts.state_dir), indent=2))
    except PacingError as error:
        cli.error(str(error))
