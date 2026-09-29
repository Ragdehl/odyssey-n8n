"""Preserve the consumed semantic-write-frontend-v5 live-evidence lineage."""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from benchmarks.semantic_write_frontend_v4 import run_live as _v4  # noqa: E402

SCHEMA_PATH = _v4.SCHEMA_PATH
FROZEN_SWR_PATH = _v4.FROZEN_SWR_PATH
SENTINELS_PATH = _v4.SENTINELS_PATH
MANIFEST_PATH = Path(__file__).with_name("manifest.json")
OUTPUT_PATH = ROOT / "benchmarks/.live-results/semantic-write-frontend-v5-luna-gate.jsonl"
MAX_COST_USD = Decimal("0.00")
GATE_CONSUMED = True
conservative_cost_ceiling = _v4.conservative_cost_ceiling
run_cases = _v4.run_cases
OpenAILunaExperimentalPlanner = _v4.OpenAILunaExperimentalPlanner


def load_gate_cases() -> tuple[list[dict[str, Any]], dict[str, str]]:
    return _v4.load_gate_cases()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    parser.parse_args(argv)
    raise SystemExit("Refusing live calls: semantic-write-frontend-v5 is permanently consumed")


if __name__ == "__main__":
    raise SystemExit(main())
