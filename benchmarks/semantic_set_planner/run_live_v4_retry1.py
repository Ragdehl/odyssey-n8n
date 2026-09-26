"""Run the immutable retry1 evidence attempt through the frozen v4 gate."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.semantic_set_planner import run_live_v4  # noqa: E402

OUTPUT_PATH = ROOT / "benchmarks/.live-results/semantic-set-slice1-v4-luna-gate-retry1.jsonl"


def main(argv: list[str] | None = None) -> int:
    """Run the frozen v4 logic once using its distinct retry1 evidence path."""
    original_output_path = run_live_v4.OUTPUT_PATH
    try:
        run_live_v4.OUTPUT_PATH = OUTPUT_PATH
        return run_live_v4.main(argv)
    finally:
        run_live_v4.OUTPUT_PATH = original_output_path


if __name__ == "__main__":
    raise SystemExit(main())
