"""Authorization-gated runner for the new atomicity cases; never executes actions."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASE_IDS = tuple(f"AT{index:02d}" for index in range(1, 11))
OUTPUT_PATH = ROOT / "benchmarks/.live-results/luna-atomicity-v1.jsonl"


def authorization_required() -> None:
    """Refuse all execution unless a future explicit authorization is supplied."""
    raise SystemExit("No live provider calls authorized for atomicity benchmark")


def frozen_cases() -> list[dict[str, str]]:
    """Return the closed frozen atomicity registry."""
    payload = json.loads((ROOT / "benchmarks/luna_first_planner/atomicity_cases.json").read_text())
    cases = payload["cases"]
    if tuple(case["id"] for case in cases) != CASE_IDS:
        raise ValueError("Atomicity case registry drifted")
    return cases
