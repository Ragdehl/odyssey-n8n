"""Preserve the retired, unexecuted semantic-write-frontend-v7 lineage."""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from benchmarks.semantic_write_frontend_v6 import run_live as _v6  # noqa: E402

SCHEMA_PATH = _v6.SCHEMA_PATH
FROZEN_SWR_PATH = _v6.FROZEN_SWR_PATH
SENTINELS_PATH = _v6.SENTINELS_PATH
MANIFEST_PATH = Path(__file__).with_name("manifest.json")
OUTPUT_PATH = ROOT / "benchmarks/.live-results/semantic-write-frontend-v7-luna-gate.jsonl"
MAX_COST_USD = Decimal("0.00")
conservative_cost_ceiling = _v6.conservative_cost_ceiling
run_cases = _v6.run_cases


def load_gate_cases() -> tuple[list[dict[str, Any]], dict[str, str]]:
    return _v6.load_gate_cases()


OpenAILunaExperimentalPlanner = _v6.OpenAILunaExperimentalPlanner
GATE_RETIRED = True


def main(argv: list[str] | None = None) -> int:
    """Refuse every invocation because v7 was superseded before provider calls."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    parser.parse_args(argv)
    raise SystemExit("Refusing live calls: semantic-write-frontend-v7 was retired unexecuted")


if __name__ == "__main__":
    raise SystemExit(main())
