"""Execution smoke test for the focused Phase 16.5C live benchmark runner."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "benchmarks/phase16_5_writer_links/run_benchmark.py"


def test_runner_imports_from_repo_root_without_live_calls() -> None:
    """The documented direct script command must start without package import failures."""
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--output-dir" in result.stdout
