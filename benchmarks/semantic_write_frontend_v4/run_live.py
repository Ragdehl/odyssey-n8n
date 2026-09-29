"""Preserve the consumed Luna semantic-write-frontend-v4 live-evidence lineage."""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.semantic_write_frontend_v3 import run_live as _v3  # noqa: E402

SCHEMA_PATH = _v3.SCHEMA_PATH
FROZEN_SWR_PATH = _v3.FROZEN_SWR_PATH
SENTINELS_PATH = _v3.SENTINELS_PATH
MANIFEST_PATH = Path(__file__).with_name("manifest.json")
OUTPUT_PATH = ROOT / "benchmarks/.live-results/semantic-write-frontend-v4-luna-gate.jsonl"
MAX_COST_USD = Decimal("0.00")
GATE_CONSUMED = True

conservative_cost_ceiling = _v3.conservative_cost_ceiling
run_cases = _v3.run_cases
OpenAILunaExperimentalPlanner = _v3.OpenAILunaExperimentalPlanner


def load_gate_cases() -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Reuse v3's immutable ten-plus-three inputs while pinning them again in v4."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    v3_manifest = json.loads(_v3.MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest["sha256"] != v3_manifest["sha256"]:
        raise RuntimeError("v4 gate input pins diverged from consumed v3")
    return _v3.load_gate_cases()


def main(argv: list[str] | None = None) -> int:
    """Refuse every invocation because the v4 lineage and artifact are permanently consumed."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    parser.parse_args(argv)
    raise SystemExit("Refusing live calls: semantic-write-frontend-v4 is permanently consumed")


if __name__ == "__main__":
    raise SystemExit(main())
