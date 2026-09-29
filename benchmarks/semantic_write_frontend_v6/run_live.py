"""Preserve the consumed semantic-write-frontend-v6 live-evidence lineage."""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from benchmarks.semantic_write_frontend_v5 import run_live as _v5  # noqa: E402

SCHEMA_PATH = _v5.SCHEMA_PATH
FROZEN_SWR_PATH = _v5.FROZEN_SWR_PATH
SENTINELS_PATH = _v5.SENTINELS_PATH
MANIFEST_PATH = Path(__file__).with_name("manifest.json")
OUTPUT_PATH = ROOT / "benchmarks/.live-results/semantic-write-frontend-v6-luna-gate.jsonl"
MAX_COST_USD = Decimal("0.00")
GATE_CONSUMED = True
conservative_cost_ceiling = _v5.conservative_cost_ceiling
run_cases = _v5.run_cases
OpenAILunaExperimentalPlanner = _v5.OpenAILunaExperimentalPlanner


def load_gate_cases() -> tuple[list[dict[str, Any]], dict[str, str]]:
    return _v5.load_gate_cases()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    parser.parse_args(argv)
    raise SystemExit("Refusing live calls: semantic-write-frontend-v6 is permanently consumed")


if __name__ == "__main__":
    raise SystemExit(main())
