"""Prepare the authorization-gated Luna semantic-write-frontend-v2 live evidence."""

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

from benchmarks.semantic_write_frontend_v1 import run_live as _v1  # noqa: E402

SCHEMA_PATH = _v1.SCHEMA_PATH
FROZEN_SWR_PATH = _v1.FROZEN_SWR_PATH
SENTINELS_PATH = _v1.SENTINELS_PATH
MANIFEST_PATH = Path(__file__).with_name("manifest.json")
OUTPUT_PATH = ROOT / "benchmarks/.live-results/semantic-write-frontend-v2-luna-gate.jsonl"
# Reset after the authorized v2 attempt; any successor run requires fresh explicit authorization.
MAX_COST_USD = Decimal("0.00")
GATE_CONSUMED = True

# Execution/evaluation mechanics are intentionally shared with the consumed v1 lineage. The v2
# contract differs only in the current Luna teaching material and its fresh manifest/artifact path.
conservative_cost_ceiling = _v1.conservative_cost_ceiling
run_cases = _v1.run_cases
OpenAILunaExperimentalPlanner = _v1.OpenAILunaExperimentalPlanner


def load_gate_cases() -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Reuse v1's immutable ten-plus-three inputs while pinning them again in the v2 manifest."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    v1_manifest = json.loads(_v1.MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest["sha256"] != v1_manifest["sha256"]:
        raise RuntimeError("v2 gate input pins diverged from consumed v1")
    return _v1.load_gate_cases()


def main(argv: list[str] | None = None) -> int:
    """Refuse every invocation because the v2 lineage and artifact are permanently consumed."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider-calls", action="store_true")
    parser.parse_args(argv)
    raise SystemExit("Refusing live calls: semantic-write-frontend-v2 is permanently consumed")


if __name__ == "__main__":
    raise SystemExit(main())
