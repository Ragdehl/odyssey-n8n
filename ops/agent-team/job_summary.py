#!/usr/bin/env python3
"""Print a safe, read-only summary of one Odyssey agent-team job."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import odyssey_agent_cycle as cycle  # noqa: E402

ROLE_LABELS = {
    "generality": "Generality",
    "quality": "Quality",
    "testing": "Testing",
    "performance": "Performance",
}
VERDICT_LABELS = {"pass": "PASS", "fail": "FAIL", "blocked": "BLOCKED"}


class SummaryError(ValueError):
    """The persisted status does not contain a safe, usable summary."""


def _verdict(value: object) -> str:
    """Validate a persisted reviewer verdict and return its stable display form."""
    if not isinstance(value, dict) or value.get("verdict") not in VERDICT_LABELS:
        raise SummaryError("Job status has an invalid reviewer verdict")
    return VERDICT_LABELS[value["verdict"]]


def build_summary(job: str) -> dict:
    """Project validated read-only supervisor state onto a fixed safe field set."""
    try:
        state = cycle.load(job)
    except (cycle.CycleError, OSError, ValueError) as error:
        raise SummaryError("Job status is unavailable or corrupt") from error
    if not isinstance(state, dict):
        raise SummaryError("Job status is unavailable or corrupt")

    phase = state.get("phase")
    round_number = state.get("round")
    ready = state.get("ready_for_user")
    reviews = state.get("reviews")
    review_plan = state.get("review_plan")
    token_usage = state.get("token_usage")
    token_cap = state.get("reported_token_budget")
    if (
        not isinstance(phase, str)
        or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", phase)
        or isinstance(round_number, bool)
        or not isinstance(round_number, int)
        or not isinstance(ready, bool)
        or not isinstance(reviews, dict)
        or not isinstance(review_plan, dict)
        or not isinstance(token_usage, dict)
        or isinstance(token_cap, bool)
        or not isinstance(token_cap, int)
    ):
        raise SummaryError("Job status is missing valid summary fields")

    roles = review_plan.get("roles")
    used = token_usage.get("reported_total")
    if (
        not isinstance(roles, list)
        or not roles
        or any(not isinstance(role, str) or role not in ROLE_LABELS for role in roles)
        or len(set(roles)) != len(roles)
        or isinstance(used, bool)
        or not isinstance(used, int)
        or used < 0
        or token_cap < 0
    ):
        raise SummaryError("Job status has invalid reviewer selection or token totals")

    auditors = []
    for role in roles:
        if role not in reviews:
            raise SummaryError("Job status is missing a selected reviewer verdict")
        auditors.append({"role": ROLE_LABELS[role], "verdict": _verdict(reviews[role])})

    recovered = []
    history = state.get("review_recovery_history", [])
    if not isinstance(history, list) or len(history) > 1:
        raise SummaryError("Job status has invalid recovery history")
    for entry in history:
        if not isinstance(entry, dict) or entry.get("role") != "quality":
            raise SummaryError("Job status has invalid recovery history")
        role = entry["role"]
        if role not in roles or role not in ROLE_LABELS:
            raise SummaryError("Job status has an invalid recovered reviewer")
        if (
            phase != "reviewed_tooling_ready"
            or ready is not True
            or _verdict(entry.get("original_verdict")) != "BLOCKED"
            or _verdict(reviews.get(role)) != "PASS"
            or entry.get("source_sha256") != state.get("audit_source_sha256")
            or not isinstance(entry.get("source_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", entry["source_sha256"])
            or round_number < 1
        ):
            raise SummaryError("Job status has unverified recovery evidence")
        root = cycle.job_path(job)
        original_path = root / f"round-{round_number}" / f"{role}-completed.json"
        retry_path = root / "blocked-quality-retry-1" / f"{role}-completed.json"
        if (
            entry.get("original_artifact") != str(original_path)
            or entry.get("retry_artifact") != str(retry_path)
            or state.get("review_artifacts", {}).get(role) != str(retry_path)
        ):
            raise SummaryError("Job status has unverified recovery evidence")
        try:
            if (
                original_path.is_symlink()
                or retry_path.is_symlink()
                or not original_path.is_file()
                or not retry_path.is_file()
                or original_path.stat().st_size > 65536
                or retry_path.stat().st_size > 65536
            ):
                raise SummaryError("Job status has unverified recovery evidence")
            original_receipt = json.loads(original_path.read_text(encoding="utf-8"))
            retry_receipt = json.loads(retry_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise SummaryError("Job status has unverified recovery evidence") from error
        if (
            not isinstance(original_receipt, dict)
            or not isinstance(retry_receipt, dict)
            or original_receipt.get("verdict") != entry["original_verdict"]
            or retry_receipt.get("verdict") != reviews[role]
            or _verdict(retry_receipt.get("verdict")) != "PASS"
        ):
            raise SummaryError("Job status has unverified recovery evidence")
        recovered.append(
            {
                "role": ROLE_LABELS[role],
                "original_verdict": "BLOCKED",
                "accepted_retry_verdict": "PASS",
            }
        )

    return {
        "job": job,
        "phase": phase,
        "round": round_number,
        "ready_for_maintainer": ready,
        "mandatory_auditors": auditors,
        "reported_tokens_used": used,
        "reported_token_cap": token_cap,
        "recovered_reviews": recovered,
    }


def render_text(summary: dict) -> str:
    """Format the stable summary without exposing any other stored status fields."""
    lines = [
        f"Job: {summary['job']}",
        f"Phase: {summary['phase']}",
        f"Round: {summary['round']}",
        f"Ready for maintainer: {str(summary['ready_for_maintainer']).lower()}",
        "Mandatory auditors:",
    ]
    lines.extend(f"  {row['role']}: {row['verdict']}" for row in summary["mandatory_auditors"])
    lines.extend(
        [
            f"CLI-reported tokens: {summary['reported_tokens_used']} / "
            f"{summary['reported_token_cap']} job cap",
        ]
    )
    for row in summary["recovered_reviews"]:
        lines.append(
            f"Recovered {row['role']}: original {row['original_verdict']}; "
            f"accepted retry {row['accepted_retry_verdict']}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run the read-only job summary command and return a shell status code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    try:
        summary = build_summary(args.job)
    except SummaryError as error:
        print(f"Job summary: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(summary, ensure_ascii=False, indent=2) if args.as_json else render_text(summary)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
