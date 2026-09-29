"""Preserve the consumed semantic-write-frontend-v8 live-evidence lineage."""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, TextIO

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from benchmarks.semantic_write_frontend_v7 import run_live as _v7  # noqa: E402
from odyssey_core.experimental_luna_planning import (  # noqa: E402
    OpenAILunaExperimentalPlanner,
)

SCHEMA_PATH = _v7.SCHEMA_PATH
FROZEN_SWR_PATH = _v7.FROZEN_SWR_PATH
SENTINELS_PATH = _v7.SENTINELS_PATH
MANIFEST_PATH = Path(__file__).with_name("manifest.json")
OUTPUT_PATH = ROOT / "benchmarks/.live-results/semantic-write-frontend-v8-luna-gate.jsonl"
MAX_COST_USD = Decimal("0.00")
GATE_CONSUMED = True
conservative_cost_ceiling = _v7.conservative_cost_ceiling
run_cases = _v7.run_cases


def run_all_cases(
    planner: OpenAILunaExperimentalPlanner,
    cases: list[dict[str, Any]],
    evidence: TextIO,
) -> list[dict[str, Any]]:
    """Collect one immutable evidence row for every case, even after oracle failures.

    Reuse the established single-case runner so provider/error capture and frozen oracle
    semantics stay identical; limiting each call to one case prevents its historical
    fail-fast behavior from suppressing later diagnostic evidence.
    """
    rows: list[dict[str, Any]] = []
    for case in cases:
        rows.extend(run_cases(planner, [case], evidence))
    return rows


def load_gate_cases() -> tuple[list[dict[str, Any]], dict[str, str]]:
    return _v7.load_gate_cases()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    parser.parse_args(argv)
    raise SystemExit("Refusing live calls: semantic-write-frontend-v8 is permanently consumed")


if __name__ == "__main__":
    raise SystemExit(main())
