#!/usr/bin/env python3
"""Run the four-case Phase 15.3 Selection-before-Operation semantic gate."""

from __future__ import annotations

import argparse

from .run_benchmark import run
from .targeted import TARGETED_RESULTS_DIR, evaluate_targeted, load_targeted_cases


def main() -> None:
    """Run one append-only targeted evidence directory with production planner contracts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    arguments = parser.parse_args()
    run(
        arguments.run_id,
        cases=load_targeted_cases(),
        results_dir=TARGETED_RESULTS_DIR,
        evaluator=evaluate_targeted,
        benchmark_version="targeted-1.0.0",
    )


if __name__ == "__main__":
    main()
