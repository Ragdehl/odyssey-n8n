"""Final planner-only v7 recheck after the reviewed teaching/oracle correction."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.semantic_set_planner import run_live_v7_planner_recheck_retry1 as retry  # noqa: E402

retry.OUTPUT_PATH = (
    retry.ROOT
    / "benchmarks/.live-results/semantic-set-slice1-v7-final-planner-recheck-luna-gate-retry3.jsonl"
)


if __name__ == "__main__":
    raise SystemExit(retry.main())
