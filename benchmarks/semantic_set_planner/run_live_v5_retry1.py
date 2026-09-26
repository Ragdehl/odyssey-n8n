"""Run the immutable retry1 evidence attempt through the schema-corrected v5 gate."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.semantic_set_planner import run_live_v5  # noqa: E402

OUTPUT_PATH = ROOT / "benchmarks/.live-results/semantic-set-slice1-v5-luna-gate-retry1.jsonl"


def main(argv: list[str] | None = None) -> int:
    """Run unchanged v5 logic once using the distinct retry1 evidence path."""
    original_output_path = run_live_v5.OUTPUT_PATH
    try:
        run_live_v5.OUTPUT_PATH = OUTPUT_PATH
        return run_live_v5.main(argv)
    finally:
        run_live_v5.OUTPUT_PATH = original_output_path


if __name__ == "__main__":
    raise SystemExit(main())
