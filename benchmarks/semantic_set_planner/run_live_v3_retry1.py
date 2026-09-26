"""Run the immutable retry1 copy of frozen v3 only with fresh authorization."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.semantic_set_planner.run_live_v3 import run_v3_gate  # noqa: E402

OUTPUT_PATH = ROOT / "benchmarks/.live-results/semantic-set-slice1-v3-luna-gate-retry1.jsonl"


def main(argv: list[str] | None = None) -> int:
    """Run only the reviewed retry1 evidence attempt for the unchanged frozen v3 gate."""
    return run_v3_gate(OUTPUT_PATH, argv)


if __name__ == "__main__":
    raise SystemExit(main())
